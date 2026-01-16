"""Figure analysis module for MATLAB MCP Tools.

This module provides functions for analyzing MATLAB figures using LLM vision
capabilities and extracting metadata from figure properties.
"""

from dataclasses import dataclass, field


@dataclass
class FigureMetadata:
    """Metadata extracted from a MATLAB figure.

    Attributes:
        figure_number: MATLAB figure number
        title: Figure or axes title
        xlabel: X-axis label
        ylabel: Y-axis label
        zlabel: Z-axis label (for 3D plots)
        xlim: X-axis limits [min, max]
        ylim: Y-axis limits [min, max]
        zlim: Z-axis limits (for 3D plots)
        legend_entries: List of legend text entries
        colorbar_label: Colorbar label if present
        colorbar_limits: Colorbar limits [min, max]
        num_subplots: Number of subplot axes
        num_lines: Number of line objects
        num_images: Number of image objects
        line_colors: List of RGB colors for each line
        line_styles: List of line styles
        line_labels: List of line display names
        colormap_name: Name of colormap if applicable
        axes_properties: Additional axes properties
    """

    figure_number: int
    title: str = ""
    xlabel: str = ""
    ylabel: str = ""
    zlabel: str = ""
    xlim: list = field(default_factory=list)
    ylim: list = field(default_factory=list)
    zlim: list = field(default_factory=list)
    legend_entries: list = field(default_factory=list)
    colorbar_label: str = ""
    colorbar_limits: list = field(default_factory=list)
    num_subplots: int = 1
    num_lines: int = 0
    num_images: int = 0
    line_colors: list = field(default_factory=list)
    line_styles: list = field(default_factory=list)
    line_labels: list = field(default_factory=list)
    colormap_name: str = ""
    axes_properties: dict = field(default_factory=dict)


@dataclass
class PlotData:
    """Data extracted from a plotted line or surface.

    Attributes:
        line_index: Index of the line (1-based)
        xdata: X coordinates
        ydata: Y coordinates
        zdata: Z coordinates (for 3D plots)
        label: Display name/label of the line
        color: RGB color of the line
        style: Line style (-, --, :, etc.)
        marker: Marker type
    """

    line_index: int
    xdata: list = field(default_factory=list)
    ydata: list = field(default_factory=list)
    zdata: list = field(default_factory=list)
    label: str = ""
    color: list = field(default_factory=list)
    style: str = "-"
    marker: str = "none"


@dataclass
class FigureAnalysisResult:
    """Result from LLM-based figure analysis.

    Attributes:
        figure_number: MATLAB figure number analyzed
        description: General description of the figure
        axes_analysis: Analysis of axes, scales, and units
        color_analysis: Analysis of colors and their meanings
        data_interpretation: Interpretation of the plotted data
        key_features: Notable features identified
        suggestions: Suggestions for improvement or clarity
        raw_response: Full raw response from LLM
    """

    figure_number: int
    description: str = ""
    axes_analysis: str = ""
    color_analysis: str = ""
    data_interpretation: str = ""
    key_features: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    raw_response: str = ""


# MATLAB code for extracting figure metadata
MATLAB_GET_FIGURE_METADATA = """
function metadata = mcp_get_figure_metadata(fig_num)
    % Extract comprehensive metadata from a MATLAB figure
    % Returns a struct with figure properties

    try
        fig = figure(fig_num);
        metadata = struct();
        metadata.figure_number = fig_num;

        % Get all axes in the figure
        all_axes = findobj(fig, 'Type', 'axes');
        metadata.num_subplots = length(all_axes);

        if isempty(all_axes)
            metadata.title = '';
            metadata.xlabel = '';
            metadata.ylabel = '';
            metadata.zlabel = '';
            metadata.xlim = [];
            metadata.ylim = [];
            metadata.zlim = [];
            metadata.legend_entries = {};
            metadata.colorbar_label = '';
            metadata.colorbar_limits = [];
            metadata.num_lines = 0;
            metadata.num_images = 0;
            metadata.line_colors = {};
            metadata.line_styles = {};
            metadata.line_labels = {};
            metadata.colormap_name = '';
            return;
        end

        % Use the first/main axes for primary metadata
        ax = all_axes(1);

        % Get title
        title_obj = get(ax, 'Title');
        if ~isempty(title_obj)
            metadata.title = get(title_obj, 'String');
            if iscell(metadata.title)
                metadata.title = strjoin(metadata.title, ' ');
            end
        else
            metadata.title = '';
        end

        % Get axis labels
        xlabel_obj = get(ax, 'XLabel');
        ylabel_obj = get(ax, 'YLabel');
        zlabel_obj = get(ax, 'ZLabel');

        metadata.xlabel = '';
        metadata.ylabel = '';
        metadata.zlabel = '';

        if ~isempty(xlabel_obj)
            lbl = get(xlabel_obj, 'String');
            if iscell(lbl)
                metadata.xlabel = strjoin(lbl, ' ');
            else
                metadata.xlabel = char(lbl);
            end
        end

        if ~isempty(ylabel_obj)
            lbl = get(ylabel_obj, 'String');
            if iscell(lbl)
                metadata.ylabel = strjoin(lbl, ' ');
            else
                metadata.ylabel = char(lbl);
            end
        end

        if ~isempty(zlabel_obj)
            lbl = get(zlabel_obj, 'String');
            if iscell(lbl)
                metadata.zlabel = strjoin(lbl, ' ');
            else
                metadata.zlabel = char(lbl);
            end
        end

        % Get axis limits
        metadata.xlim = get(ax, 'XLim');
        metadata.ylim = get(ax, 'YLim');
        try
            metadata.zlim = get(ax, 'ZLim');
        catch
            metadata.zlim = [];
        end

        % Get legend entries
        leg = findobj(fig, 'Type', 'Legend');
        if ~isempty(leg)
            metadata.legend_entries = get(leg(1), 'String');
            if ~iscell(metadata.legend_entries)
                metadata.legend_entries = {metadata.legend_entries};
            end
        else
            metadata.legend_entries = {};
        end

        % Get colorbar info
        cb = findobj(fig, 'Type', 'ColorBar');
        if ~isempty(cb)
            cb_label = get(cb(1), 'Label');
            if ~isempty(cb_label)
                metadata.colorbar_label = get(cb_label, 'String');
            else
                metadata.colorbar_label = '';
            end
            metadata.colorbar_limits = get(cb(1), 'Limits');
        else
            metadata.colorbar_label = '';
            metadata.colorbar_limits = [];
        end

        % Count and analyze line objects
        lines = findobj(ax, 'Type', 'Line');
        metadata.num_lines = length(lines);
        metadata.line_colors = {};
        metadata.line_styles = {};
        metadata.line_labels = {};

        for i = 1:length(lines)
            color = get(lines(i), 'Color');
            metadata.line_colors{i} = color;
            metadata.line_styles{i} = get(lines(i), 'LineStyle');
            disp_name = get(lines(i), 'DisplayName');
            if isempty(disp_name)
                metadata.line_labels{i} = sprintf('Line %d', i);
            else
                metadata.line_labels{i} = disp_name;
            end
        end

        % Count image objects
        images = findobj(ax, 'Type', 'Image');
        surfaces = findobj(ax, 'Type', 'Surface');
        metadata.num_images = length(images) + length(surfaces);

        % Get colormap name
        cmap = colormap(ax);
        % Try to identify common colormaps
        metadata.colormap_name = 'custom';
        known_maps = {'parula', 'jet', 'hsv', 'hot', 'cool', 'spring', 'summer', ...
                      'autumn', 'winter', 'gray', 'bone', 'copper', 'pink', 'viridis'};
        for j = 1:length(known_maps)
            try
                ref_map = eval(known_maps{j});
                if size(cmap, 1) == size(ref_map, 1)
                    if max(abs(cmap(:) - ref_map(:))) < 0.01
                        metadata.colormap_name = known_maps{j};
                        break;
                    end
                end
            catch
                % Colormap not available, skip
            end
        end

    catch ME
        metadata = struct();
        metadata.error = ME.message;
        metadata.figure_number = fig_num;
    end
end
"""

MATLAB_GET_PLOT_DATA = """
function data = mcp_get_plot_data(fig_num, line_index)
    % Extract data from a specific line in a figure
    % line_index is 1-based

    try
        fig = figure(fig_num);
        ax = findobj(fig, 'Type', 'axes');

        if isempty(ax)
            data = struct('error', 'No axes found in figure');
            return;
        end

        lines = findobj(ax(1), 'Type', 'Line');

        if isempty(lines)
            data = struct('error', 'No lines found in figure');
            return;
        end

        if line_index > length(lines) || line_index < 1
            data = struct('error', sprintf('Line index %d out of range (1-%d)', line_index, length(lines)));
            return;
        end

        line = lines(line_index);
        data = struct();
        data.line_index = line_index;
        data.xdata = get(line, 'XData');
        data.ydata = get(line, 'YData');

        try
            data.zdata = get(line, 'ZData');
        catch
            data.zdata = [];
        end

        data.label = get(line, 'DisplayName');
        if isempty(data.label)
            data.label = sprintf('Line %d', line_index);
        end

        data.color = get(line, 'Color');
        data.style = get(line, 'LineStyle');
        data.marker = get(line, 'Marker');

    catch ME
        data = struct('error', ME.message);
    end
end
"""


# Default prompt for figure analysis emphasizing axes, units, colors
DEFAULT_ANALYSIS_PROMPT = """Analyze this MATLAB figure in detail. Pay special attention to:

1. **AXES AND SCALES**:
   - What are the X and Y axis labels? Include any units shown.
   - What are the axis ranges/limits?
   - Is the scale linear or logarithmic?
   - Are there any special axis formatting (scientific notation, date/time)?

2. **COLORS AND THEIR MEANINGS**:
   - What colors are used in the plot?
   - What does each color represent (different conditions, groups, variables)?
   - Is there a colorbar? What does it represent and what are its limits/units?
   - Is the color scheme appropriate for the data type?

3. **DATA INTERPRETATION**:
   - What type of plot is this (line plot, scatter, heatmap, bar chart, etc.)?
   - What trends or patterns are visible in the data?
   - Are there any notable peaks, valleys, or outliers?
   - What is the main message or finding shown by this figure?

4. **LEGEND AND LABELS**:
   - Is there a legend? What categories/conditions does it show?
   - Is the title informative?
   - Are all elements clearly labeled?

5. **QUALITY ASSESSMENT**:
   - Is the figure clear and readable?
   - Any suggestions for improving clarity or presentation?

Provide a structured analysis addressing each of these points."""


def get_color_description(rgb: list) -> str:
    """Convert RGB values to a human-readable color name.

    Args:
        rgb: List of [R, G, B] values (0-1 range)

    Returns:
        Human-readable color description
    """
    if not rgb or len(rgb) < 3:
        return "unknown"

    r, g, b = rgb[0], rgb[1], rgb[2]

    # Common MATLAB colors
    colors = {
        (0, 0, 1): "blue",
        (1, 0, 0): "red",
        (0, 1, 0): "green",
        (0, 0, 0): "black",
        (1, 1, 1): "white",
        (1, 1, 0): "yellow",
        (1, 0, 1): "magenta",
        (0, 1, 1): "cyan",
        (0.5, 0.5, 0.5): "gray",
        (1, 0.5, 0): "orange",
        (0.5, 0, 0.5): "purple",
        (0.6350, 0.0780, 0.1840): "dark red (MATLAB default)",
        (0, 0.4470, 0.7410): "blue (MATLAB default)",
        (0.8500, 0.3250, 0.0980): "orange (MATLAB default)",
        (0.9290, 0.6940, 0.1250): "yellow (MATLAB default)",
        (0.4940, 0.1840, 0.5560): "purple (MATLAB default)",
        (0.4660, 0.6740, 0.1880): "green (MATLAB default)",
        (0.3010, 0.7450, 0.9330): "light blue (MATLAB default)",
    }

    # Find closest color
    min_dist = float("inf")
    closest_name = "custom"

    for (cr, cg, cb), name in colors.items():
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < min_dist:
            min_dist = dist
            closest_name = name

    # If very close match, return the name
    if min_dist < 0.05:
        return closest_name

    # Otherwise describe as RGB
    return f"RGB({r:.2f}, {g:.2f}, {b:.2f}) - similar to {closest_name}"


def format_metadata_for_analysis(metadata: FigureMetadata) -> str:
    """Format figure metadata as context for LLM analysis.

    Args:
        metadata: FigureMetadata object

    Returns:
        Formatted string with metadata context
    """
    lines = ["## Figure Metadata (extracted from MATLAB):\n"]

    if metadata.title:
        lines.append(f"- **Title**: {metadata.title}")
    if metadata.xlabel:
        lines.append(f"- **X-axis label**: {metadata.xlabel}")
    if metadata.ylabel:
        lines.append(f"- **Y-axis label**: {metadata.ylabel}")
    if metadata.zlabel:
        lines.append(f"- **Z-axis label**: {metadata.zlabel}")

    if metadata.xlim and len(metadata.xlim) >= 2:
        lines.append(f"- **X-axis range**: {metadata.xlim[0]} to {metadata.xlim[1]}")
    if metadata.ylim and len(metadata.ylim) >= 2:
        lines.append(f"- **Y-axis range**: {metadata.ylim[0]} to {metadata.ylim[1]}")
    if metadata.zlim and len(metadata.zlim) >= 2:
        lines.append(f"- **Z-axis range**: {metadata.zlim[0]} to {metadata.zlim[1]}")

    if metadata.legend_entries:
        lines.append(f"- **Legend entries**: {', '.join(metadata.legend_entries)}")

    if metadata.colorbar_label:
        lines.append(f"- **Colorbar label**: {metadata.colorbar_label}")
    if metadata.colorbar_limits and len(metadata.colorbar_limits) >= 2:
        lines.append(
            f"- **Colorbar range**: {metadata.colorbar_limits[0]} to {metadata.colorbar_limits[1]}"
        )

    lines.append(f"- **Number of subplots**: {metadata.num_subplots}")
    lines.append(f"- **Number of lines**: {metadata.num_lines}")
    lines.append(f"- **Number of images/surfaces**: {metadata.num_images}")

    if metadata.line_colors:
        color_desc = []
        for i, color in enumerate(metadata.line_colors):
            label = (
                metadata.line_labels[i]
                if i < len(metadata.line_labels)
                else f"Line {i + 1}"
            )
            color_name = get_color_description(color)
            color_desc.append(f"{label}: {color_name}")
        lines.append(f"- **Line colors**: {'; '.join(color_desc)}")

    if metadata.colormap_name and metadata.colormap_name != "custom":
        lines.append(f"- **Colormap**: {metadata.colormap_name}")

    return "\n".join(lines)
