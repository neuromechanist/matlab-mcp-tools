"""Tests for figure analysis module and MCP tools."""

import pytest

from matlab_mcp.figure_analysis import (
    DEFAULT_ANALYSIS_PROMPT,
    FigureAnalysisResult,
    FigureMetadata,
    PlotData,
    format_metadata_for_analysis,
    get_color_description,
)

# Import MCP tools for testing
from matlab_mcp.server import (
    analyze_figure,
    execute_script,
    get_analysis_prompt,
    get_figure_metadata,
    get_plot_data,
)


class TestFigureMetadataDataclass:
    """Tests for FigureMetadata dataclass."""

    def test_default_values(self):
        """Test default values are initialized correctly."""
        metadata = FigureMetadata(figure_number=1)

        assert metadata.figure_number == 1
        assert metadata.title == ""
        assert metadata.xlabel == ""
        assert metadata.ylabel == ""
        assert metadata.zlabel == ""
        assert metadata.xlim == []
        assert metadata.ylim == []
        assert metadata.zlim == []
        assert metadata.legend_entries == []
        assert metadata.colorbar_label == ""
        assert metadata.colorbar_limits == []
        assert metadata.num_subplots == 1
        assert metadata.num_lines == 0
        assert metadata.num_images == 0
        assert metadata.line_colors == []
        assert metadata.line_styles == []
        assert metadata.line_labels == []
        assert metadata.colormap_name == ""
        assert metadata.axes_properties == {}

    def test_custom_values(self):
        """Test with custom values."""
        metadata = FigureMetadata(
            figure_number=2,
            title="Test Plot",
            xlabel="Time (s)",
            ylabel="Amplitude (V)",
            xlim=[0, 10],
            ylim=[-1, 1],
            num_lines=3,
            line_colors=[[0, 0, 1], [1, 0, 0]],
            legend_entries=["Signal 1", "Signal 2"],
        )

        assert metadata.figure_number == 2
        assert metadata.title == "Test Plot"
        assert metadata.xlabel == "Time (s)"
        assert metadata.ylabel == "Amplitude (V)"
        assert metadata.xlim == [0, 10]
        assert metadata.ylim == [-1, 1]
        assert metadata.num_lines == 3
        assert len(metadata.line_colors) == 2
        assert len(metadata.legend_entries) == 2


class TestPlotDataDataclass:
    """Tests for PlotData dataclass."""

    def test_default_values(self):
        """Test default values for PlotData."""
        data = PlotData(line_index=1)

        assert data.line_index == 1
        assert data.xdata == []
        assert data.ydata == []
        assert data.zdata == []
        assert data.label == ""
        assert data.color == []
        assert data.style == "-"
        assert data.marker == "none"

    def test_custom_values(self):
        """Test PlotData with custom values."""
        data = PlotData(
            line_index=2,
            xdata=[1, 2, 3],
            ydata=[4, 5, 6],
            label="Test Line",
            color=[1, 0, 0],
            style="--",
            marker="o",
        )

        assert data.line_index == 2
        assert data.xdata == [1, 2, 3]
        assert data.ydata == [4, 5, 6]
        assert data.label == "Test Line"
        assert data.color == [1, 0, 0]
        assert data.style == "--"
        assert data.marker == "o"


class TestFigureAnalysisResultDataclass:
    """Tests for FigureAnalysisResult dataclass."""

    def test_default_values(self):
        """Test default values for FigureAnalysisResult."""
        result = FigureAnalysisResult(figure_number=1)

        assert result.figure_number == 1
        assert result.description == ""
        assert result.axes_analysis == ""
        assert result.color_analysis == ""
        assert result.data_interpretation == ""
        assert result.key_features == []
        assert result.suggestions == []
        assert result.raw_response == ""

    def test_custom_values(self):
        """Test FigureAnalysisResult with analysis data."""
        result = FigureAnalysisResult(
            figure_number=1,
            description="A time series plot",
            axes_analysis="X-axis shows time in seconds",
            color_analysis="Blue represents channel 1",
            data_interpretation="Data shows oscillatory behavior",
            key_features=["Peak at t=5s", "Baseline drift"],
            suggestions=["Add axis labels", "Increase font size"],
            raw_response="Full LLM response here...",
        )

        assert result.description == "A time series plot"
        assert len(result.key_features) == 2
        assert len(result.suggestions) == 2


class TestGetColorDescription:
    """Tests for get_color_description function."""

    def test_standard_colors(self):
        """Test recognition of standard colors."""
        assert get_color_description([0, 0, 1]) == "blue"
        assert get_color_description([1, 0, 0]) == "red"
        assert get_color_description([0, 1, 0]) == "green"
        assert get_color_description([0, 0, 0]) == "black"
        assert get_color_description([1, 1, 1]) == "white"
        assert get_color_description([1, 1, 0]) == "yellow"
        assert get_color_description([1, 0, 1]) == "magenta"
        assert get_color_description([0, 1, 1]) == "cyan"

    def test_matlab_default_blue(self):
        """Test MATLAB default blue color."""
        result = get_color_description([0, 0.4470, 0.7410])
        assert "blue" in result.lower()

    def test_matlab_default_orange(self):
        """Test MATLAB default orange color."""
        result = get_color_description([0.8500, 0.3250, 0.0980])
        assert "orange" in result.lower()

    def test_empty_input(self):
        """Test with empty input."""
        assert get_color_description([]) == "unknown"
        assert get_color_description(None) == "unknown"

    def test_invalid_input(self):
        """Test with invalid input."""
        assert get_color_description([1, 2]) == "unknown"

    def test_custom_color(self):
        """Test custom color returns RGB description."""
        result = get_color_description([0.3, 0.7, 0.2])
        assert "RGB" in result or "green" in result.lower()


class TestFormatMetadataForAnalysis:
    """Tests for format_metadata_for_analysis function."""

    def test_empty_metadata(self):
        """Test formatting with minimal metadata."""
        metadata = FigureMetadata(figure_number=1)
        result = format_metadata_for_analysis(metadata)

        assert "Figure Metadata" in result
        assert "Number of subplots" in result
        assert "Number of lines" in result

    def test_full_metadata(self):
        """Test formatting with full metadata."""
        metadata = FigureMetadata(
            figure_number=1,
            title="Test Plot",
            xlabel="Time (s)",
            ylabel="Amplitude (V)",
            xlim=[0, 10],
            ylim=[-1, 1],
            legend_entries=["Signal 1", "Signal 2"],
            colorbar_label="Intensity",
            colorbar_limits=[0, 100],
            num_subplots=2,
            num_lines=3,
            num_images=1,
            line_colors=[[0, 0, 1], [1, 0, 0]],
            line_labels=["Line A", "Line B"],
            colormap_name="viridis",
        )
        result = format_metadata_for_analysis(metadata)

        assert "Title" in result
        assert "Test Plot" in result
        assert "X-axis label" in result
        assert "Time (s)" in result
        assert "Y-axis label" in result
        assert "Amplitude (V)" in result
        assert "X-axis range" in result
        assert "Legend entries" in result
        assert "Colorbar label" in result
        assert "Colormap" in result
        assert "viridis" in result

    def test_3d_metadata(self):
        """Test formatting with 3D plot metadata."""
        metadata = FigureMetadata(
            figure_number=1,
            zlabel="Z Value",
            zlim=[0, 100],
        )
        result = format_metadata_for_analysis(metadata)

        assert "Z-axis label" in result
        assert "Z-axis range" in result


class TestDefaultAnalysisPrompt:
    """Tests for DEFAULT_ANALYSIS_PROMPT content."""

    def test_prompt_sections(self):
        """Test that prompt includes all required sections."""
        assert "AXES AND SCALES" in DEFAULT_ANALYSIS_PROMPT
        assert "COLORS AND THEIR MEANINGS" in DEFAULT_ANALYSIS_PROMPT
        assert "DATA INTERPRETATION" in DEFAULT_ANALYSIS_PROMPT
        assert "LEGEND AND LABELS" in DEFAULT_ANALYSIS_PROMPT
        assert "QUALITY ASSESSMENT" in DEFAULT_ANALYSIS_PROMPT

    def test_prompt_emphasizes_units(self):
        """Test that prompt asks about units."""
        assert "units" in DEFAULT_ANALYSIS_PROMPT.lower()

    def test_prompt_emphasizes_colors(self):
        """Test that prompt asks about color meanings."""
        assert "color" in DEFAULT_ANALYSIS_PROMPT.lower()
        assert "represent" in DEFAULT_ANALYSIS_PROMPT.lower()

    def test_prompt_asks_about_colorbar(self):
        """Test that prompt asks about colorbars."""
        assert "colorbar" in DEFAULT_ANALYSIS_PROMPT.lower()


class TestFigureMetadataExtraction:
    """Tests for figure metadata extraction from MATLAB."""

    @pytest.mark.asyncio
    async def test_extract_simple_plot_metadata(self):
        """Test extracting metadata from a simple plot."""
        # Create a simple plot
        await execute_script(
            """
            figure(99);
            clf;
            x = 0:0.1:10;
            plot(x, sin(x));
            xlabel('Time (s)');
            ylabel('Amplitude');
            title('Sine Wave');
            """,
            capture_plots=False,
        )

        result = await get_figure_metadata(figure_number=99)

        assert result["figure_number"] == 99
        assert result["num_lines"] >= 1

    @pytest.mark.asyncio
    async def test_extract_multiline_plot_metadata(self):
        """Test extracting metadata from plot with multiple lines."""
        await execute_script(
            """
            figure(98);
            clf;
            x = 0:0.1:5;
            plot(x, sin(x), 'b-', x, cos(x), 'r--');
            legend('sin', 'cos');
            """,
            capture_plots=False,
        )

        result = await get_figure_metadata(figure_number=98)

        assert result["figure_number"] == 98
        assert result["num_lines"] >= 2

    @pytest.mark.asyncio
    async def test_extract_labeled_axes(self):
        """Test that axis labels are extracted."""
        await execute_script(
            """
            figure(97);
            clf;
            plot([1, 2, 3], [4, 5, 6]);
            xlabel('X Label Test');
            ylabel('Y Label Test');
            """,
            capture_plots=False,
        )

        result = await get_figure_metadata(figure_number=97)

        assert result["xlabel"] == "X Label Test"
        assert result["ylabel"] == "Y Label Test"


class TestPlotDataExtraction:
    """Tests for plot data extraction from MATLAB."""

    @pytest.mark.asyncio
    async def test_extract_line_data(self):
        """Test extracting data from a plotted line."""
        await execute_script(
            """
            figure(96);
            clf;
            x = [1, 2, 3, 4, 5];
            y = [10, 20, 30, 40, 50];
            plot(x, y);
            """,
            capture_plots=False,
        )

        result = await get_plot_data(figure_number=96, line_index=1)

        assert result["line_index"] == 1
        assert len(result["xdata"]) == 5
        assert len(result["ydata"]) == 5
        assert result["xdata"][0] == 1.0
        assert result["ydata"][4] == 50.0

    @pytest.mark.asyncio
    async def test_extract_styled_line(self):
        """Test extracting styled line properties."""
        await execute_script(
            """
            figure(95);
            clf;
            plot([1, 2, 3], [1, 4, 9], 'r--o', 'DisplayName', 'Quadratic');
            """,
            capture_plots=False,
        )

        result = await get_plot_data(figure_number=95, line_index=1)

        assert result["line_index"] == 1
        assert result["style"] == "--"
        assert result["marker"] == "o"


class TestAnalyzeFigureTool:
    """Tests for analyze_figure MCP tool."""

    @pytest.mark.asyncio
    async def test_analyze_figure_returns_image(self):
        """Test that analyze_figure returns image data."""
        # Create figure with capture_plots=False to keep figure open
        await execute_script(
            """
            figure(94);
            clf;
            plot(1:10, rand(1, 10));
            title('Random Data');
            drawnow;
            """,
            capture_plots=False,
        )

        result = await analyze_figure(figure_number=94)

        assert "image" in result
        assert "prompt" in result
        assert result["image"] is not None

    @pytest.mark.asyncio
    async def test_analyze_figure_with_metadata(self):
        """Test that analyze_figure includes metadata."""
        # Create figure with capture_plots=False to keep figure open
        await execute_script(
            """
            figure(93);
            clf;
            plot([1, 2, 3], [4, 5, 6]);
            xlabel('X');
            ylabel('Y');
            drawnow;
            """,
            capture_plots=False,
        )

        result = await analyze_figure(figure_number=93, include_metadata=True)

        assert "metadata" in result
        assert result["metadata"]["figure_number"] == 93

    @pytest.mark.asyncio
    async def test_analyze_figure_custom_prompt(self):
        """Test analyze_figure with custom prompt."""
        # Create figure with capture_plots=False to keep figure open
        await execute_script(
            """
            figure(92);
            clf;
            plot(1:5);
            drawnow;
            """,
            capture_plots=False,
        )

        custom = "Focus only on the trend direction."
        result = await analyze_figure(figure_number=92, custom_prompt=custom)

        assert custom in result["prompt"]


class TestGetAnalysisPromptTool:
    """Tests for get_analysis_prompt MCP tool."""

    @pytest.mark.asyncio
    async def test_get_default_prompt(self):
        """Test getting the default analysis prompt."""
        result = await get_analysis_prompt()

        assert result == DEFAULT_ANALYSIS_PROMPT
        assert "AXES AND SCALES" in result
        assert "COLORS" in result

    @pytest.mark.asyncio
    async def test_get_prompt_with_additions(self):
        """Test getting prompt with custom additions."""
        additions = "Also identify any outliers in the data."

        result = await get_analysis_prompt(custom_additions=additions)

        assert DEFAULT_ANALYSIS_PROMPT in result
        assert additions in result
        assert "Additional instructions" in result
