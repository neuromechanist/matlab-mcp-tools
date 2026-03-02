"""Test figure analysis tools with real EEGLAB plots.

NO MOCKS - All tests use real MATLAB/EEGLAB data via shared session engine.
Figure/plot tests use the epoched+ICA dataset; lint tests use the continuous dataset.
"""

import pytest

from matlab_mcp.figure_analysis import FigureMetadata, PlotData
from matlab_mcp.lint import run_lint


class TestFigureMetadataExtraction:
    """Test get_figure_metadata and get_plot_data with EEGLAB plots."""

    @pytest.mark.asyncio
    async def test_topoplot_metadata(self, eeglab_epochs_engine):
        """Generate topoplot and verify figure metadata extraction."""
        # Close any existing figures, then generate ERP topoplot
        code = (
            "close all; "
            "pop_topoplot(EEG_epochs, 1, [100 200 300], "
            "'ERP Topoplots', [1 3]);"
        )
        result = await eeglab_epochs_engine.execute(code, capture_plots=False)
        assert result.error is None, f"Topoplot generation error: {result.error}"

        metadata = await eeglab_epochs_engine.get_figure_metadata(figure_number=1)
        assert isinstance(metadata, FigureMetadata)
        assert metadata.figure_number == 1
        # Topoplot should have subplots (one per time point)
        assert metadata.num_subplots >= 1

    @pytest.mark.asyncio
    async def test_erpimage_metadata(self, eeglab_epochs_engine):
        """Generate ERP image and verify metadata extraction."""
        code = "close all; pop_erpimage(EEG_epochs, 1, 14, [], 'Cz', 10, 1, {});"
        result = await eeglab_epochs_engine.execute(code, capture_plots=False)
        assert result.error is None, f"ERP image error: {result.error}"

        metadata = await eeglab_epochs_engine.get_figure_metadata(figure_number=1)
        assert isinstance(metadata, FigureMetadata)
        assert metadata.figure_number == 1

    @pytest.mark.asyncio
    async def test_simple_plot_data(self, eeglab_epochs_engine):
        """Generate a simple ERP plot and extract plot data."""
        # Plot the ERP at channel 14 (Cz)
        code = (
            "close all; "
            "figure; "
            "plot(EEG_epochs.times, mean(EEG_epochs.data(14,:,:), 3)); "
            "xlabel('Time (ms)'); ylabel('Amplitude (uV)'); "
            "title('ERP at Cz');"
        )
        result = await eeglab_epochs_engine.execute(code, capture_plots=False)
        assert result.error is None, f"Plot generation error: {result.error}"

        plot_data = await eeglab_epochs_engine.get_plot_data(
            figure_number=1, line_index=1
        )
        assert isinstance(plot_data, PlotData)
        assert plot_data.line_index == 1
        assert len(plot_data.xdata) > 0
        assert len(plot_data.ydata) > 0
        assert len(plot_data.xdata) == len(plot_data.ydata)

    @pytest.mark.asyncio
    async def test_simple_plot_metadata(self, eeglab_epochs_engine):
        """Verify metadata for a simple labeled plot."""
        code = (
            "close all; "
            "figure; "
            "plot(EEG_epochs.times, mean(EEG_epochs.data(14,:,:), 3)); "
            "xlabel('Time (ms)'); ylabel('Amplitude (uV)'); "
            "title('ERP at Cz');"
        )
        result = await eeglab_epochs_engine.execute(code, capture_plots=False)
        assert result.error is None

        metadata = await eeglab_epochs_engine.get_figure_metadata(figure_number=1)
        assert metadata.title == "ERP at Cz"
        assert metadata.xlabel == "Time (ms)"
        assert metadata.ylabel == "Amplitude (uV)"
        assert metadata.num_lines >= 1


class TestAnalyzeFigure:
    """Test prepare_figure_for_analysis with EEGLAB plots."""

    @pytest.mark.asyncio
    async def test_analyze_figure_returns_prompt_and_data(self, eeglab_epochs_engine):
        """analyze_figure should return figure data and an analysis prompt."""
        code = (
            "close all; "
            "figure; "
            "plot(EEG_epochs.times, mean(EEG_epochs.data(14,:,:), 3)); "
            "title('ERP for analysis');"
        )
        result = await eeglab_epochs_engine.execute(code, capture_plots=False)
        assert result.error is None

        analysis = await eeglab_epochs_engine.prepare_figure_for_analysis(
            figure_number=1
        )
        assert "figure" in analysis
        assert "prompt" in analysis
        assert isinstance(analysis["prompt"], str)
        assert len(analysis["prompt"]) > 0


class TestLintOnEeglabCode:
    """Test matlab_lint on real EEGLAB code."""

    @pytest.mark.asyncio
    async def test_lint_eeglab_tutorial_script(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Lint should handle EEGLAB tutorial script without crashing."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        summary = await run_lint(eeglab_loaded_engine, script)
        # Should return a valid summary (may or may not have issues)
        assert hasattr(summary, "results")
        assert isinstance(summary.results, list)

    @pytest.mark.asyncio
    async def test_lint_inline_eeglab_code(self, eeglab_loaded_engine):
        """Lint inline EEGLAB code snippet."""
        code = "EEG = pop_loadset('test.set');\ndata = EEG.data;"
        summary = await run_lint(eeglab_loaded_engine, code)
        assert hasattr(summary, "results")
        assert isinstance(summary.results, list)
