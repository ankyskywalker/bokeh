import logging

import six
import pandas as pd
import numpy as np

from ..plotting import curdoc
from ..models import ColumnDataSource, FactorRange, GridPlot, Panel, Tabs, \
    Range, DataRange1d, Range1d
from ..models.widgets import Select, MultiSelect, InputWidget

# crossfilter plotting utilities
from .plotting import (make_histogram_source,
                       make_histogram, make_continuous_bar_source,
                       make_categorical_bar_source, cross, hide_axes)

# bokeh plotting functions
from ..plotting import figure
from ..plotting_helpers import _get_select_tool
from ..plot_object import PlotObject
from ..properties import Dict, Enum, Instance, List, String, Any, Int

logger = logging.getLogger(__name__)


class DiscreteFacet(object):
    """Pairing of a field and a unique value, representing a subset of the
    total data."""

    def __init__(self, field, value, label=None):
        """Sets object properties and creates label if not provided.

        Args:
          field (str): name of the column
          value: unique value defined for the column
          label (str, optional): string representation of the value

        """
        if label is None:
            label = str(value)
        self.field = field
        self.label = label
        self._value = value

    def __repr__(self):
        return "%s:%s"%(self.field, self.label)

    def filter(self, df):
        """Filters the provided DataFrame to the subset corresponding to value.

        Args:
          df (DataFrame): contains a column of ``field``

        Returns:
          DataFrame: filtered to rows, where column ``field`` has values
            equal to ``_value``.

        """
        return df[df[self.field] == self._value]


class ContinuousFacet(DiscreteFacet):
    """Represents a range of values for a field in a DataFrame."""

    def __init__(self, field, value, bins, label=None):
        """Calls parent ``DiscreteFacet`` and stores bins for later filtering.

        Args:
          field (str): name of the column
          value (str): center of range of values in the column
          bins (list[float]): start and inclusive stop value for the bin
          label (str, optional): string representation

        """
        super(ContinuousFacet, self).__init__(field, value, label=label)
        self.bins = bins

    def filter(self, df):
        """Filters the provided DataFrame to the subset corresponding to bins.

        Args:
          df (DataFrame): contains a column of ``field``

        Returns:
          DataFrame: filtered to rows, where column ``field`` has values
            within the bounds of ``bins``.

        """
        if self.bins[0] is not None:
            df = df[df[self.field] > self.bins[0]]
        if self.bins[1] is not None:
            df = df[df[self.field] <= self.bins[1]]
        return df


class CrossFilterPlugin(object):
    """An adapter class between CrossFilter and custom plotting plugins.

    This adapter is used to provide a consistent interface between single
    plot generation and CrossFilter through some core behaviors. A simple
    plugin can simply override only make_plot to provide a custom plot type.

    See CrossLinePlugin for a simple example.

    Kwargs:
      crossfilter (CrossFilter): reference to the CrossFilter app
      source (ColumnDataSource): the pre-filtered source for the plot
      x_range (Range): the common x range to use for plotting
      y_range (Range): the common y range to use for plotting
      title_text_font_size (str): string of font size, e.g., "12pt"
      plot_height (float): height of the plot in pixels
      plot_width (float): width of the plot in pixels
      tools (str): the string of tools to add to the plot
      facet (bool): whether or not we are faceting
      title (str, optional): overrides the derived title property

    """
    def __init__(self, *args, **kwargs):
        self.cf = kwargs.pop('crossfilter', None)
        self.x = self.cf.x
        self.y = self.cf.y
        self.source = kwargs.pop('source', None)
        self.facet = kwargs.pop('facet', False)
        self.col_meta = self.cf.column_descriptor_dict()
        self.valid_plot = True

        # get any provided title, else generate our own
        self._title = kwargs.pop('title', None)
        if not self._title:
            self._title = self.title
        self.args = args
        self.kwargs = kwargs

    def get_plot(self):
        """Validates, makes blank figure, then makes the plot as necessary.

        It is meant for this method to not be overridden. The methods called
        by this method should be overridden first, and this one only as a last
        resort, since it provides a common interface for plugins.

        """
        self.validate_plot()
        plot = self.make_figure(**self.kwargs)
        if self.valid_plot:
            plot = self.make_plot(plot)
        return plot

    def make_figure(self, **kwargs):
        """Generates the blank figure for the provided options.

        The purpose of this is to avoid for child plugins to have to repeat
        this functionality. It is likely to not need to override this behavior.

        """
        kwargs['title'] = self._title
        return figure(**kwargs)

    def make_plot(self, plot):
        """Plots the data into the provided plot.

        The primary method to be overridden to create a custom plugin.

        """
        plot.scatter(self.x, self.y, source=self.source)
        return plot

    def validate_plot(self):
        """Called before plotting data to check to see if we should plot.

        If valid_plot is set to False in this method, then the figure will
        still be created, but no data will be plotted.

        """
        if not self.facet:
            if len(self.source.data[self.x]) == 0 or len(
                    self.source.data[self.y]) == 0:
                self._title = 'All data is filtered out.'
                self.valid_plot = False

    @property
    def title(self):
        """Generates a title for the plot, and can be overridden per plugin.

        Returns:
          str: a string to place into the title that provides additional plot info

        """
        return "%s by %s" % (self.x, self.y)

    @property
    def x_type(self):
        return self.col_meta[self.x]['type']

    @property
    def y_type(self):
        return self.col_meta[self.y]['type']

    @property
    def df(self):
        return self.source.to_df()

    @staticmethod
    def make_xy_ranges(cf):
        """Generates x/y ranges specific to the plot type for the plugin.

        This method is static so that CrossFilter can generate common ranges
        to construct multiple plots from the plugin. A custom plugin would
        override this method if it has unique range types.

        Args:
          cf (CrossFilter): a reference to the CrossFilter object, used to
            get data to generate the ranges.

        Returns:
          (Range, Range): returns xrange, yrange

        """
        col_meta = cf.column_descriptor_dict()
        x_col = cf.x
        y_col = cf.y
        df = cf.df

        if col_meta[x_col]['type'] == 'DiscreteColumn':
            x_range = FactorRange(factors=sorted(set(df[x_col])))
        else:
            x_vals = df[x_col]
            x_range = DataRange1d(start=x_vals.min(), end=x_vals.max())

        if col_meta[y_col]['type'] == 'DiscreteColumn':
            y_range = FactorRange(factors=sorted(set(df[y_col])))
        else:
            y_vals = df[y_col]
            y_range = DataRange1d(start=y_vals.min(), end=y_vals.max())

        return x_range, y_range


class CrossBarPlugin(CrossFilterPlugin):
    """Bar plot plugin for CrossFilter."""

    def __init__(self, *args, **kwargs):

        cf = kwargs['crossfilter']
        self.agg = cf.agg
        super(CrossBarPlugin, self).__init__(*args, **kwargs)
        self.bar_width = 0.7

    def make_plot(self, plot):
        self.transform_data()
        y = [val/2.0 for val in self.source.data[self.y]]
        plot.rect(self.x, y, self.bar_width, self.y, source=self.source)
        plot.min_border = 0
        plot.h_symmetry = False
        plot.v_symmetry = False

        select_tool = _get_select_tool(plot)
        if select_tool:
            select_tool.dimensions = ['width']
        return plot

    def transform_data(self):
        """Generates custom source that describes the bars to be plotted."""

        if self.y_type == 'DiscreteColumn':
            self.source = make_continuous_bar_source(self.df, self.x, self.y,
                                                     self.agg)
        else:
            self.source = make_categorical_bar_source(self.df, self.x, self.y,
                                                      self.agg)

    def validate_plot(self):
        super(CrossBarPlugin, self).validate_plot()

        if self.y_type == 'DiscreteColumn':
            self._title = 'Bar does not support discrete y column'
            self.valid_plot = False

        if self.x == self.y:
            self._title = 'Bar does not support x and y of same column'
            self.valid_plot = False

        if self.df.empty:
            self._title = 'All data is filtered out'
            self.valid_plot = False

    @property
    def title(self):
        return "%s(%s) by %s" % (self.agg, self.y, self.x)

    @staticmethod
    def make_xy_ranges(cf, bar_width=0.7):
        """Returns ranges for a given bar width.

        Args:
          cf (CrossFilter): the CrossFilter app
          bar_width (float, optional): width of bar that affects ranges

        Returns:
          (xrange, yrange): the x/y ranges to use for the bar plot

        """
        x_col = cf.x
        y_col = cf.y
        df = cf.df
        agg = cf.agg
        col_meta = cf.column_descriptor_dict()

        if col_meta[x_col]['type'] != 'DiscreteColumn':
            source = make_continuous_bar_source(df, x_col, y_col, agg)
            x_range = Range1d(start=df[x_col].min() - bar_width,
                              end=df[x_col].max() - bar_width)
        else:
            source = make_categorical_bar_source(df, x_col, y_col, agg)
            x_range = FactorRange(factors=source.data[x_col])

        top = np.max(source.data[y_col])
        y_range = Range1d(start=0, end=top)

        return x_range, y_range


class CrossScatterPlugin(CrossFilterPlugin):
    """Scatter plot plugin for CrossFilter."""

    def __init__(self, *args, **kwargs):
        super(CrossScatterPlugin, self).__init__(*args, **kwargs)


class CrossLinePlugin(CrossFilterPlugin):
    """Line plot plugin for CrossFilter."""

    def __init__(self, *args, **kwargs):
        super(CrossLinePlugin, self).__init__(*args, **kwargs)

    def make_plot(self, plot):
        plot.line(self.x, self.y, source=self.source)
        return plot


class CrossFilter(PlotObject):
    """Interactive filtering and faceting application with multiple plot
    types"""

    # identify properties for the data
    columns = List(Dict(String, Any))
    data = Instance(ColumnDataSource)
    filtered_data = Instance(ColumnDataSource)

    # list of datasources to use for filtering widgets
    filter_sources = Dict(String, Instance(ColumnDataSource))

    # list of columns we are filtering
    filtering_columns = List(String)

    # dict of column name to filtering widgets
    filter_widgets = Dict(String, Instance(PlotObject))

    # dict which aggregates all the selections from the different filtering
    # widgets
    filtered_selections = Dict(String, Dict(String, Any))

    # list of facet vars
    facet_x = List(String, default=[])
    facet_y = List(String, default=[])
    facet_tab = List(String, default=[])

    # the displayed plot object
    plot = Instance(PlotObject)
    x_range = Instance(Range)
    y_range = Instance(Range)

    # configuration properties for the plot
    plot_type = Enum("line", "scatter", "bar")
    plot_map = {'line': CrossLinePlugin,
                'scatter': CrossScatterPlugin,
                'bar': CrossBarPlugin}
    x = String
    y = String
    agg = String
    color = String
    height = Int()
    width = Int()

    # identify the selector/drop-down properties
    plot_selector = Instance(Select)
    x_selector = Instance(Select)
    y_selector = Instance(Select)
    agg_selector = Instance(Select)

    def __init__(self, *args, **kwargs):
        """Creates original and filtered ColumnDataSource and handles defaults.

        The df and starting configuration are only provided the first time
        init is called, within the create method.

        Kwargs:
          df (DataFrame): the data to use in the crossfilter app
          plot_type (str, optional): starting plot type
          agg (str, optional): starting aggregation type

        """
        if 'df' in kwargs:
            self._df = kwargs.pop('df')
            kwargs['data'] = ColumnDataSource(data=self.df)
            kwargs['filtered_data'] = ColumnDataSource(data=self.df)

        # default plot type
        if 'plot_type' not in kwargs:
            kwargs['plot_type'] = "scatter"

        # default aggregation type
        if 'agg' not in kwargs:
            kwargs['agg'] = 'sum'

        if 'plot_map' in kwargs:
            self.plot_map = kwargs.pop('plot_map')

        super(CrossFilter, self).__init__(**kwargs)

    @classmethod
    def create(cls, **kwargs):
        """Performs all one-time construction of bokeh objects.

        This classmethod is required due to the way that bokeh handles the
        python and javascript components. The initialize method will be
        called each additional time the app is updated (including once in
        the create method), but the PlotObject infrastructure will find that
        the object already exists in any future calls, and will not create a
        new object.

        Kwargs:
          df (DataFrame): the data to use in the crossfilter app
          plot_type (str, optional): starting plot type
          agg (str, optional): starting aggregation type

        :return:
        """
        obj = cls(**kwargs)
        obj.set_metadata()
        choices = obj.make_plot_choices()
        obj.update_plot_choices(choices)
        obj.set_plot()
        obj.set_input_selector()
        return obj

    def set_input_selector(self):
        """Creates and configures each selector (drop-down menu)."""

        col_names = [x['name'] for x in self.columns]

        self.plot_selector = Select.create(
            title="PlotType",
            name="plot_type",
            value=self.plot_type,
            options=["line", "scatter", "bar"],
        )

        self.x_selector = Select.create(
            name="x",
            value=self.x,
            options=col_names,
        )

        self.y_selector = Select.create(
            name="y",
            value=self.y,
            options=col_names,
        )

        self.agg_selector = Select.create(
            name='agg',
            value=self.agg,
            options=['sum', 'mean', 'last'],
        )

    def update_plot_choices(self, input_dict):
        """Sets object attributes corresponding to input_dict's values.

        Args:
          input_dict (dict): dict with x, y, and plot_type keys

        """
        for k, v in input_dict.items():
            if getattr(self, k) is None:
                setattr(self, k, v)

    def get_plot_class(self):
        """Return the class for the current plot selection."""
        return self.plot_map[self.plot_type]

    def column_descriptor_dict(self):
        """Creates column stats dict with keys of column names.

        Returns:
          dict: dict with key per column in data, where values are column stats

        """
        column_descriptors = {}
        for x in self.columns:
            column_descriptors[x['name']] = x
        return column_descriptors

    def continuous_columns(self):
        """Returns list of column descriptors for the non-Discrete columns.

        Returns:
          list(dict): list of dicts, containing metadata about columns

        """
        return [x for x in self.columns if x['type'] != 'DiscreteColumn']

    def discrete_columns(self):
        """Returns list of column descriptors for the Discrete columns.

        Returns:
          list(dict): list of dicts, containing metadata about columns

        """
        return [x for x in self.columns if x['type'] == 'DiscreteColumn']

    def make_plot_choices(self):
        """Selects first two continuous columns for x,y during initial setup

        Returns:
          dict: x, y, and plot_type keys and values for initial setup

        """
        x, y = [x['name'] for x in self.continuous_columns()[:2]]
        return {'x': x, 'y': y, 'plot_type': 'scatter'}

    def set_plot(self):
        """Makes and sets the plot based on the current configuration of app."""

        self.update_xy_ranges(source=self.df)
        plot = self.make_plot()
        self.plot = plot
        curdoc()._add_all()

    def make_plot(self):
        """Makes the correct plot layout type, based on app's current config.

        Returns:
          PlotObject: one plot, grid of plots, or tabs of plots/grids of plots

        """

        if self.facet_tab:
            facets = self.make_facets(dimension='tab')

            # generate a list of panels, containing plot/plots for each facet
            tabs = [self.make_tab(content=self.create_plot_page(
                tab_facet=facet), tab_label=str(facet)) for facet in facets]
            return Tabs(tabs=tabs)
        else:
            return self.create_plot_page()

    def create_plot_page(self, tab_facet=None):
        """Generates a single visible page of a plot or plots.

        Args:
          tab_facet (DiscreteFacet or ContinuousFacet): a facet to filter on

        Returns:
          PlotObject: a single or grid of plots

        """
        # no faceting
        if all([len(self.facet_x) == 0,
                len(self.facet_y) == 0]):
            return self.make_single_plot(facet=tab_facet)

        # x xor y faceting
        if all([(len(self.facet_x) != 0) ^ (len(self.facet_y) != 0)]):
            return self.make_1d_facet_plot(facet=tab_facet)

        # x and y faceting
        if all([len(self.facet_x) != 0,
                len(self.facet_y) != 0]):
            return self.make_2d_facet_plot(facet=tab_facet)

    @staticmethod
    def make_tab(content, tab_label):
        """Creates a container for the contents of a tab.

        Args:
          content (PlotObject): the primary content of the tab
          tab_label (str): the text to place in the tab

        Returns:
          Panel: represents a single tab in a group of tabs

        """
        return Panel(child=content, title=tab_label)

    def make_facets(self, dimension):
        """Creates combination of all facets for the provided dimension

        Args:
          dimension (str): name of the dimension to create facets for

        Returns:
          list(list(DiscreteFacet or ContinuousFacet)): list of list of
            unique facet combinations

        """
        if dimension == 'x':
            facets = self.facet_x
        elif dimension == 'y':
            facets = self.facet_y
        else:
            facets = self.facet_tab

        # create facets for each column
        column_descriptor_dict = self.column_descriptor_dict()
        all_facets = [[]]
        for field in facets:

            # create facets from discrete columns
            if column_descriptor_dict[field]['type'] == 'DiscreteColumn':
                field_facets = [DiscreteFacet(field, val) for val in
                                np.unique(self.df[field].values)]

                # combine any facets as required
                all_facets = cross(all_facets, field_facets)
            else:
                # create quantile based discrete data and pairs of bins
                categorical, bins = pd.qcut(self.df[field], 4, retbins=True)
                cats = categorical.cat.categories
                bins = [[bins[idx], bins[idx + 1]] for idx in
                        range(len(bins) - 1)]
                bins[0][0] = None

                # create list of facets
                field_facets = [ContinuousFacet(field, value, bin) for
                                bin, value in zip(bins, cats)]

                # combine any facets as required
                all_facets = cross(all_facets, field_facets)

        return all_facets

    @staticmethod
    def facet_title(facets):
        """Joins list of facets by commas.

        Args:
          facets (list(DiscreteFacet or ContinuousFacet)): list of facets,
          which are a combination of column and unique value within it

        Returns:
          str: string representation of the combination of facets

        """
        title = ",".join([str(x) for x in facets])
        return title

    def facet_data(self, facets, df=None):
        """Filters data to the rows associated with the given facet.

        Args:
          facets (list(DiscreteFacet or ContinuousFacet)): list of facets,
          which are a combination of column and unique value within it
          df (DataFrame, optional): data to be filtered on

        Returns:
          DataFrame: filtered DataFrame based on provided facets

        """
        if df is None:
            df = self.filtered_df
        for f in facets:
            df = f.filter(df)
        return df

    def make_1d_facet_plot(self, facet=None):
        """Creates the faceted plots when a facet is added to the x axis.

        Returns:
          GridPlot: a grid of plots, where each plot has subset of data

        """
        if self.facet_x:
            all_facets = self.make_facets('x')
        else:
            all_facets = self.make_facets('y')

        plots = []

        # loop over facets and create single plots for data subset
        for facets in all_facets:
            title = self.facet_title(facets)

            if facet:
                facets += facet

            df = self.facet_data(facets, self.filtered_df)
            plot = self.make_single_plot(
                df=df, title=title, plot_height=200, plot_width=200,
                tools="pan,wheel_zoom,reset", facet=facets
            )
            plot.min_border = 0

            # append single plot to list of plots
            plots.append(plot)

        # create squarish grid based on number of plots
        chunk_size = int(np.ceil(np.sqrt(len(plots))))

        # create list of lists of plots, where each list of plots is a row
        grid_plots = []
        for i in range(0, len(plots), chunk_size):
            chunk = plots[i:i + chunk_size]
            grid_plots.append(chunk)

        self.hide_internal_axes(grid_plots)

        # return the grid as the plot
        return GridPlot(children=grid_plots, plot_width=200*chunk_size)

    def make_2d_facet_plot(self, facet=None):
        """Creates the grid of plots when there are both x and y facets.

        Returns:
          GridPlot: grid of x and y facet combinations

        """

        # ToDo: gracefully handle large combinations of facets
        all_facets_x = self.make_facets('x')
        all_facets_y = self.make_facets('y')

        grid_plots = []

        # y faceting down column
        for facets_y in all_facets_y:

            # x faceting across row
            row = []
            for facets_x in all_facets_x:

                # build the facets and title
                facets = facets_x + facets_y
                title = self.facet_title(facets)

                # must filter by any extra facets provided for facet tab
                if facet:
                    filter_facets = facets + facet
                else:
                    filter_facets = facets

                df = self.facet_data(filter_facets, self.filtered_df)
                plot = self.make_single_plot(
                    df=df, title=title, plot_height=200, plot_width=200,
                    tools="pan,wheel_zoom,reset", facet=facets
                )
                plot.min_border = 0
                plot.v_symmetry = False
                plot.h_symmetry = False
                row.append(plot)

            # append the row to the list of rows
            grid_plots.append(row)

            self.hide_internal_axes(grid_plots)

        # return the grid of plots as the plot
        return GridPlot(children=grid_plots, plot_width=200*len(all_facets_x))

    @staticmethod
    def hide_internal_axes(grid_plots):
        """Hides the internal axes for a grid of plots.

        Args:
          grid_plots (list(list(Figure))): list of rows (list), containing plots

        """
        for i, row in enumerate(grid_plots):
            is_bottom = i + 1 == len(grid_plots)
            next_bottom = i + 2 == len(grid_plots)

            if next_bottom:
                next_len = len(grid_plots[i + 1])
            else:
                next_len = None

            for j, plot in enumerate(row):

                if j != 0:
                    if is_bottom or j >= next_len:
                        hide_axes(plot, axes='y')
                    else:
                        hide_axes(plot)

                elif j == 0 and not is_bottom:
                    hide_axes(plot, axes='x')

    def make_single_plot(self, df=None, title=None,
                         plot_width=700, plot_height=680,
                         tools="pan,wheel_zoom,box_zoom,save,resize,"
                               "box_select,reset", facet=None):
        """Creates a plot based on the current app configuration.

        Args:
          df (DataFrame, optional): data to use for the plot
          title (str, optional): plot title
          plot_width (float, optional): width of plot in pixels
          plot_height (float, optional): height of plot in pixels
          tools (str, optional): comma separated string of tool names

        Returns:
          PlotObject: the generated plot

        """
        faceting = False

        # df is not provided when we are not faceting
        if df is None:
            df = self.filtered_df
        else:
            df = self.facet_data(facets=facet, df=df)
            faceting = True

        # check for tab faceting and filter if provided
        if facet:
            df = self.facet_data(facets=facet, df=df)

        # create column data source with filtered df
        source = ColumnDataSource(data=df)

        # get the helper class for the plot type selected
        plot_class = self.get_plot_class()

        # initialize the helper class
        plot = plot_class(source=source,
                          title_text_font_size="12pt",
                          plot_height=plot_height,
                          plot_width=plot_width,
                          tools=tools,
                          title=title,
                          x_range=self.x_range,
                          y_range=self.y_range,
                          facet=faceting,
                          crossfilter=self)

        # return the generated plot
        return plot.get_plot()

    def update_xy_ranges(self, source):
        """Updates common x_range, y_range to use for creating figures.

        Args:
          source (ColumnDataSource): the source to return correct range for

        """
        plt_cls = self.get_plot_class()
        x_range, y_range = plt_cls.make_xy_ranges(cf=self)

        # store x and y range from the plot class
        self.x_range = x_range
        self.y_range = y_range

    def plot_attribute_change(self, obj, attrname, old, new):
        """Updates app's attribute and plot when view configuration changes.

        Args:
          obj (Widget): the object that has an attribute change
          attrname (str): name of the attribute
          old (type): the previous value of unknown type
          new (type): the new value of unknown type

        """
        setattr(self, obj.name, new)
        self.set_plot()

    def facet_change(self, obj, attrname, old, new):
        """Updates plot when any facet configuration changes.

        Args:
          obj (Widget): the object that has an attribute change
          attrname (str): name of the attribute
          old (type): the previous value of unknown type
          new (type): the new value of unknown type

        """
        self.set_plot()

    @property
    def df(self):
        """The core data that is used by the app for plotting.

        Returns:
          DataFrame: the original data structure

        """
        if hasattr(self, '_df'):
            return self._df
        else:
            if self.data:
                return self.data.to_df()

    @property
    def filtered_df(self):
        """The subset of the data to use for plotting.

        Returns:
          DataFrame: the original data structure

        """
        # ToDo: shouldn't this just return self.df if there are no filters
        if hasattr(self, '_df'):
            return self._df
        else:
            if self.filtered_data:
                return self.filtered_data.to_df()

    def update(self, **kwargs):
        # ToDo: determine when this is called
        super(CrossFilter, self).update(**kwargs)
        self.setup_events()

    def setup_events(self):
        """Registers events each time the app changes state."""
        # ToDo: do we need to re-register events for everything this often

        # watch the app's filtering_columns attribute to setup filters
        self.on_change('filtering_columns', self, 'setup_filter_widgets')

        # register any available filter widget
        for obj in self.filter_widgets.values():
            if isinstance(obj, InputWidget):
                obj.on_change('value', self, 'handle_filter_selection')

        # watch app column data source attribute for changes
        for obj in self.filter_sources.values():
            obj.on_change('selected', self, 'handle_filter_selection')

        # selector event registration
        if self.plot_selector:
            self.plot_selector.on_change('value', self, 'plot_attribute_change')
        if self.x_selector:
            self.x_selector.on_change('value', self, 'plot_attribute_change')
        if self.y_selector:
            self.y_selector.on_change('value', self, 'plot_attribute_change')
        if self.agg_selector:
            self.agg_selector.on_change('value', self, 'plot_attribute_change')

        # register to watch the app's facet attributes
        self.on_change('facet_x', self, 'facet_change')
        self.on_change('facet_y', self, 'facet_change')
        self.on_change('facet_tab', self, 'facet_change')

    def handle_filter_selection(self, obj, attrname, old, new):
        """Filters the data source whenever a filter widget changes.

        Args:
          obj (Widget): the object that has an attribute change
          attrname (str): name of the attribute
          old (type): the previous value of unknown type
          new (type): the new value of unknown type

        """
        df = self.df

        # loop over the column metadata
        for descriptor in self.columns:
            colname = descriptor['name']

            # handle discrete selections
            if descriptor['type'] == 'DiscreteColumn' and \
                            colname in self.filter_widgets:
                selected = self.filter_widgets[colname].value
                if not selected:
                    continue
                if isinstance(selected, six.string_types):
                    df = df[colname == selected]
                else:
                    df = df[np.in1d(df[colname], selected)]

            # handle time or continuous selections
            elif descriptor['type'] in ('TimeColumn', 'ContinuousColumn') and \
                            colname in self.filter_widgets:
                obj = self.filter_sources[colname]

                # hack because we don't have true range selection
                if not obj.selected:
                    continue
                min_idx = np.min(obj.selected)
                max_idx = np.max(obj.selected)

                min_val = obj.data['centers'][min_idx]
                max_val = obj.data['centers'][max_idx]
                df = df[(df[colname] >= min_val) & (df[colname] <= max_val)]

        # update filtered data and force plot update
        for colname in self.data.column_names:
            self.filtered_data.data[colname] = df[colname]
            self.filtered_data._dirty = True
        self.set_plot()

    def clear_selections(self, obj, attrname, old, new):
        """Updates filter widgets and sources as they are removed.

        Args:
          obj (Widget): the object that has an attribute change
          attrname (str): name of the attribute
          old (type): the previous value of unknown type
          new (type): the new value of unknown type

        """
        diff = set(old) - set(new)
        column_descriptor_dict = self.column_descriptor_dict()

        # delete any removed filter widgets
        if len(diff) > 0:
            for col in diff:
                metadata = column_descriptor_dict[col]
                if metadata['type'] != 'DiscreteColumn':
                    del self.filter_sources[col]
                del self.filter_widgets[col]

        # update the data based on latest changes
        if diff:
            self.handle_filter_selection(obj, attrname, old, new)


    def setup_filter_widgets(self, obj, attrname, old, new):
        """Creates new filter widget each time a new column is added to filters.

        Args:
          obj (Widget): the object that has an attribute change
          attrname (str): name of the attribute
          old (type): the previous value of unknown type
          new (type): the new value of unknown type

        """
        self.clear_selections(obj, attrname, old, new)

        # add new widget as required for each column set to filter on
        column_descriptor_dict = self.column_descriptor_dict()
        for col in self.filtering_columns:

            metadata = column_descriptor_dict[col]
            if not col in self.filter_widgets:

                # discrete
                if metadata['type'] == 'DiscreteColumn':
                    select = MultiSelect.create(
                        name=col,
                        options=self.df[col].unique().tolist())
                    self.filter_widgets[col] = select

                # continuous
                else:
                    source = make_histogram_source(self.df[col])
                    self.filter_sources[col] = source
                    hist_plot = make_histogram(self.filter_sources[col],
                                               plot_width=200, plot_height=100,
                                               title_text_font_size='8pt',
                                               tools='box_select'
                    )
                    hist_plot.title = col
                    self.filter_widgets[col] = hist_plot

        curdoc()._add_all()

    def set_metadata(self):
        """Creates a list of dicts, containing summary info for each column.

        The descriptions are stored in the ``columns`` property.

        """
        descriptors = []

        columns = self.df.columns
        for c in columns:

            # get description for column from pandas DataFrame
            desc = self.df[c].describe()

            # DiscreteColumn
            if self.df[c].dtype == object:
                descriptors.append({
                    'type': "DiscreteColumn",
                    'name': c,
                    'count': desc['count'],
                    'unique': desc['unique'],
                    'top': desc['top'],
                    'freq': desc['freq'],
                })

            # TimeColumn
            elif self.df[c].dtype == np.datetime64:
                descriptors.append({
                    'type': "TimeColumn",
                    'name': c,
                    'count': desc['count'],
                    'unique': desc['unique'],
                    'first': desc['first'],
                    'last': desc['last'],
                })

            # ContinuousColumn
            else:
                descriptors.append({
                    'type': "ContinuousColumn",
                    'name': c,
                    'count': desc['count'],
                    'mean': "%.2f"%desc['mean'],
                    'std': "%.2f"%desc['std'],
                    'min': "%.2f"%desc['min'],
                    'max': "%.2f"%desc['max'],
                })

        self.columns = descriptors
