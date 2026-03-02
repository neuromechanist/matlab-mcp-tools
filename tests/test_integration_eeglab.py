"""End-to-end integration tests with real EEGLAB pipeline.

NO MOCKS - All tests use real MATLAB/EEGLAB data via shared session engine.
Tests a full neuroscience workflow: load, filter, epoch, plot, inspect.
"""

import tempfile
from pathlib import Path

import pytest


class TestFullPipeline:
    """Test a complete EEG processing pipeline through MCP tools."""

    @pytest.mark.asyncio
    async def test_pipeline_load_filter_epoch_plot(
        self, eeglab_loaded_engine, sample_data_path
    ):
        """Execute a multi-step EEG pipeline and verify workspace at each stage."""
        engine = eeglab_loaded_engine

        # Stage 1: Reload fresh continuous data (other tests may have modified EEG)
        reload_code = f"EEG = pop_loadset('{sample_data_path / 'eeglab_data.set'}');"
        result = await engine.execute(reload_code, capture_plots=False)
        assert result.error is None, f"Reload error: {result.error}"

        eeg_info = await engine.get_variable(
            "EEG", fields=["nbchan", "srate", "pnts", "trials"]
        )
        assert eeg_info["nbchan"] == 32
        assert eeg_info["srate"] == 128
        assert eeg_info["trials"] == 1  # continuous

        # Stage 2: High-pass filter at 1 Hz
        filter_code = "EEG = pop_eegfilt(EEG, 1, 0, [], [0]);"
        result = await engine.execute(filter_code, capture_plots=False)
        assert result.error is None, f"Filter error: {result.error}"

        # Verify: same dimensions, still continuous
        post_filter = await engine.get_variable(
            "EEG", fields=["nbchan", "pnts", "trials"]
        )
        assert post_filter["nbchan"] == 32
        assert post_filter["trials"] == 1

        # Stage 3: Epoch around 'square' events
        epoch_code = (
            "EEG = pop_epoch(EEG, {'square'}, [-1 2], "
            "'newname', 'Epochs', 'epochinfo', 'yes');"
        )
        result = await engine.execute(epoch_code, capture_plots=False)
        assert result.error is None, f"Epoch error: {result.error}"

        post_epoch = await engine.get_variable(
            "EEG", fields=["nbchan", "trials", "pnts"]
        )
        assert post_epoch["nbchan"] == 32
        assert post_epoch["trials"] > 1, "Should have multiple epochs"
        # 3 seconds at 128 Hz = 384 points
        assert post_epoch["pnts"] == 384

        # Stage 4: Remove baseline
        baseline_code = "EEG = pop_rmbase(EEG, [-1000 0]);"
        result = await engine.execute(baseline_code, capture_plots=False)
        assert result.error is None, f"Baseline error: {result.error}"

        # Stage 5: Generate a plot and verify figure metadata
        plot_code = (
            "close all; figure; "
            "plot(EEG.times, mean(EEG.data(14,:,:), 3)); "
            "xlabel('Time (ms)'); ylabel('uV'); title('ERP at Cz');"
        )
        result = await engine.execute(plot_code, capture_plots=False)
        assert result.error is None, f"Plot error: {result.error}"

        metadata = await engine.get_figure_metadata(figure_number=1)
        assert metadata.title == "ERP at Cz"
        assert metadata.num_lines >= 1

        # Stage 6: Verify workspace listing shows expected variables
        variables = await engine.list_workspace_variables()
        var_names = [v["name"] for v in variables]
        assert "EEG" in var_names

        # Reload continuous data to restore state for other tests
        reload_code = f"EEG = pop_loadset('{sample_data_path / 'eeglab_data.set'}');"
        result = await engine.execute(reload_code, capture_plots=False)
        assert result.error is None


class TestScriptedPipeline:
    """Test pipeline via script creation and section execution."""

    @pytest.mark.asyncio
    async def test_create_and_execute_pipeline_script(
        self, eeglab_loaded_engine, sample_data_path
    ):
        """Create a multi-section script, execute sections, verify workspace."""
        engine = eeglab_loaded_engine

        # Create a temporary MATLAB script with sections
        script_content = f"""\
%% Load Data
EEG_pipe = pop_loadset('{sample_data_path / "eeglab_data.set"}');

%% Filter Data
EEG_pipe = pop_eegfilt(EEG_pipe, 1, 0, [], [0]);

%% Inspect Data
pipe_info.nbchan = EEG_pipe.nbchan;
pipe_info.srate = EEG_pipe.srate;
pipe_info.pnts = EEG_pipe.pnts;
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".m", delete=False, dir="/tmp"
        ) as f:
            f.write(script_content)
            script_path = f.name

        try:
            # Verify sections are parsed
            sections = await engine.get_script_sections(script_path)
            assert len(sections) == 3
            titles = [s["title"] for s in sections]
            assert "Load Data" in titles
            assert "Filter Data" in titles
            assert "Inspect Data" in titles

            # Execute section 0: Load
            result = await engine.execute_section_by_index(
                script_path, section_index=0, capture_plots=False
            )
            assert result.error is None, f"Load section error: {result.error}"

            # Verify EEG_pipe exists
            pipe_info = await engine.get_variable(
                "EEG_pipe", fields=["nbchan", "srate"]
            )
            assert pipe_info["nbchan"] == 32

            # Execute section 1: Filter
            result = await engine.execute_section_by_index(
                script_path, section_index=1, capture_plots=False
            )
            assert result.error is None, f"Filter section error: {result.error}"

            # Execute section 2: Inspect
            result = await engine.execute_section_by_index(
                script_path, section_index=2, capture_plots=False
            )
            assert result.error is None, f"Inspect section error: {result.error}"

            # Verify pipe_info struct was created
            info = await engine.get_variable("pipe_info")
            assert info["nbchan"] == 32
            assert info["srate"] == 128

        finally:
            Path(script_path).unlink(missing_ok=True)


class TestErrorRecovery:
    """Test that workspace is preserved after errors."""

    @pytest.mark.asyncio
    async def test_workspace_survives_error(self, eeglab_loaded_engine):
        """After executing bad code, workspace should still be intact."""
        engine = eeglab_loaded_engine

        # Verify EEG exists before the error
        pre = await engine.get_variable("EEG", fields=["nbchan"])
        assert pre["nbchan"] == 32

        # Execute code that will error
        result = await engine.execute(
            "this_function_does_not_exist(42);", capture_plots=False
        )
        assert result.error is not None

        # EEG should still be accessible
        post = await engine.get_variable("EEG", fields=["nbchan", "srate"])
        assert post["nbchan"] == 32
        assert post["srate"] == 128

    @pytest.mark.asyncio
    async def test_continue_pipeline_after_error(self, eeglab_loaded_engine):
        """Should be able to continue normal operations after an error."""
        engine = eeglab_loaded_engine

        # Trigger an error
        await engine.execute("nonexistent_func();", capture_plots=False)

        # Should still be able to run valid code
        result = await engine.execute("x_test = 42;", capture_plots=False)
        assert result.error is None

        val = await engine.get_variable("x_test")
        assert val == 42 or (isinstance(val, dict) and val.get("x_test") == 42)

        # Clean up
        await engine.execute("clear x_test;", capture_plots=False)
