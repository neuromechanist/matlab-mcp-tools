"""Test section execution tools with real EEGLAB tutorial scripts.

NO MOCKS - All tests use real MATLAB/EEGLAB data via shared session engine.
"""

import pytest


class TestGetScriptSections:
    """Test get_script_sections on EEGLAB tutorial scripts."""

    @pytest.mark.asyncio
    async def test_eeglab_history_has_sections(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """eeglab_history.m should have multiple sections with titles."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        sections = await eeglab_loaded_engine.get_script_sections(script)
        assert len(sections) >= 2, "Expected at least 2 sections"
        for sec in sections:
            assert "index" in sec
            assert "title" in sec
            assert "start_line" in sec
            assert "end_line" in sec

    @pytest.mark.asyncio
    async def test_section_titles_present(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Sections should have meaningful titles from %% comments."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        sections = await eeglab_loaded_engine.get_script_sections(script)
        titles = [s["title"] for s in sections]
        # First section should be about getting started
        assert any("started" in t.lower() or "history" in t.lower() for t in titles)

    @pytest.mark.asyncio
    async def test_nonexistent_file_error(self, eeglab_loaded_engine):
        """get_script_sections on a missing file should raise or return error."""
        with pytest.raises(FileNotFoundError):
            await eeglab_loaded_engine.get_script_sections("/tmp/no_such_file.m")


class TestExecuteSectionByIndex:
    """Test execute_section_by_index with EEGLAB scripts."""

    @pytest.mark.asyncio
    async def test_execute_first_section(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Executing the first section should succeed without error."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        result = await eeglab_loaded_engine.execute_section_by_index(
            script, section_index=0, capture_plots=False
        )
        assert result.error is None, f"Section execution error: {result.error}"

    @pytest.mark.asyncio
    async def test_invalid_section_index(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Executing with an out-of-range index should raise IndexError."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        with pytest.raises(IndexError):
            await eeglab_loaded_engine.execute_section_by_index(
                script, section_index=999, capture_plots=False
            )


class TestExecuteSectionByTitle:
    """Test execute_section_by_title with partial title matching."""

    @pytest.mark.asyncio
    async def test_partial_title_match(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Should match a section by partial, case-insensitive title."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        # "Reduce sampling rate" is a known section title
        result = await eeglab_loaded_engine.execute_section_by_title(
            script, section_title="reduce sampling", capture_plots=False
        )
        assert result.error is None, f"Section execution error: {result.error}"

    @pytest.mark.asyncio
    async def test_no_matching_title(self, eeglab_loaded_engine, tutorial_scripts_path):
        """A title that matches nothing should raise ValueError."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        with pytest.raises(ValueError):
            await eeglab_loaded_engine.execute_section_by_title(
                script, section_title="xyzzy_nonexistent_title", capture_plots=False
            )


class TestSequentialSectionExecution:
    """Test that workspace state persists across sequential section executions."""

    @pytest.mark.asyncio
    async def test_workspace_preserved_between_sections(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Variables created in one section should be available in subsequent ones."""
        script = str(tutorial_scripts_path / "eeglab_history.m")

        # Execute first section (loads data, creates EEG variable)
        result = await eeglab_loaded_engine.execute_section_by_index(
            script, section_index=0, capture_plots=False
        )
        assert result.error is None, f"Section 0 error: {result.error}"

        # EEG should exist in workspace
        variables = await eeglab_loaded_engine.list_workspace_variables(pattern="^EEG$")
        names = [v["name"] for v in variables]
        assert "EEG" in names, "EEG not found after executing first section"

        # Execute second section (resampling) -- uses EEG from first section
        result = await eeglab_loaded_engine.execute_section_by_index(
            script, section_index=1, capture_plots=False
        )
        assert result.error is None, f"Section 1 error: {result.error}"


class TestExecuteSection:
    """Test execute_section with explicit line ranges."""

    @pytest.mark.asyncio
    async def test_line_range_execution(
        self, eeglab_loaded_engine, tutorial_scripts_path
    ):
        """Executing a specific line range should work."""
        script = str(tutorial_scripts_path / "eeglab_history.m")
        sections = await eeglab_loaded_engine.get_script_sections(script)
        assert len(sections) > 0

        # Use the line range from the first section
        sec = sections[0]
        result = await eeglab_loaded_engine.execute_section(
            script,
            section_range=(sec["start_line"], sec["end_line"]),
            capture_plots=False,
        )
        assert result.error is None, f"Line range execution error: {result.error}"
