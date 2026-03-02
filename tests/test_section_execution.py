"""Tests for improved section execution functionality."""

from pathlib import Path

import pytest

from matlab_mcp.utils.section_parser import parse_sections


@pytest.fixture
def sample_script_with_sections(tmp_path):
    """Create a sample MATLAB script with sections for testing."""
    script_content = """%% Section 1 - Initialize
x = 1:10;
y = x.^2;

%% Section 2 - Plot Data
figure;
plot(x, y);
title('Sample Plot');

%% Section 3 - Compute Statistics
mean_val = mean(y);
std_val = std(y);

%% Final Section
disp('Done');
"""
    script_path = tmp_path / "test_sections.m"
    script_path.write_text(script_content)
    return script_path


@pytest.fixture
def eeglab_script():
    """Path to EEGLAB study_script.m for real-world testing."""
    path = (
        Path(__file__).parent.parent.parent
        / "eeglab"
        / "tutorial_scripts"
        / "study_script.m"
    )
    if not path.exists():
        pytest.skip("EEGLAB tutorial scripts not found")
    return path


# ---------------------------------------------------------------------------
# Parser-only tests (no MATLAB engine required)
# ---------------------------------------------------------------------------


class TestSectionParserEdgeCases:
    """Edge-case tests for parse_sections that don't require MATLAB."""

    def test_script_with_four_sections(self, sample_script_with_sections):
        """Sample script should parse into exactly 4 sections."""
        sections = parse_sections(sample_script_with_sections)
        assert len(sections) == 4

    def test_section_titles_correct(self, sample_script_with_sections):
        """Section titles should be stripped and correctly extracted."""
        sections = parse_sections(sample_script_with_sections)
        titles = [s[2] for s in sections]
        assert titles[0] == "Section 1 - Initialize"
        assert titles[1] == "Section 2 - Plot Data"
        assert titles[2] == "Section 3 - Compute Statistics"
        assert titles[3] == "Final Section"

    def test_sections_are_contiguous(self, sample_script_with_sections):
        """Sections must cover all lines with no gap or overlap."""
        sections = parse_sections(sample_script_with_sections)
        for i in range(len(sections) - 1):
            _, end, _ = sections[i]
            next_start, _, _ = sections[i + 1]
            assert end + 1 == next_start

    def test_preamble_before_first_marker(self, tmp_path):
        """Lines before the first %% marker are returned as a 'Main' section."""
        content = """% Script header
clear;
%% Step 1
x = 1;
"""
        script = tmp_path / "preamble.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 2
        assert sections[0][2] == "Main"
        assert sections[0][0] == 0
        assert sections[0][1] == 1  # lines 0 and 1
        assert sections[1][2] == "Step 1"

    def test_empty_title_section(self, tmp_path):
        """Bare %% with no text should produce an empty-string title."""
        content = """%% Section A
x = 1;
%%
y = 2;
"""
        script = tmp_path / "empty_title.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 2
        assert sections[0][2] == "Section A"
        assert sections[1][2] == ""

    def test_inline_percent_percent_ignored(self, tmp_path):
        """A %% not at the start of a line must not create a new section."""
        content = """x = 1; %% inline comment
%% Real Section
y = 2;
"""
        script = tmp_path / "inline.m"
        script.write_text(content)
        sections = parse_sections(script)

        # Line 0 has inline %% -> treated as preamble 'Main'
        # Line 1 is the only real section marker
        assert len(sections) == 2
        assert sections[0][2] == "Main"
        assert sections[1][2] == "Real Section"


# ---------------------------------------------------------------------------
# Engine tests (require MATLAB)
# ---------------------------------------------------------------------------


class TestGetScriptSections:
    """Tests for get_script_sections functionality."""

    @pytest.mark.asyncio
    async def test_get_sections_from_sample_script(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test section detection in sample script."""
        sections = await matlab_engine.get_script_sections(
            str(sample_script_with_sections)
        )

        assert len(sections) == 4
        assert sections[0]["title"] == "Section 1 - Initialize"
        assert sections[0]["index"] == 0
        assert sections[1]["title"] == "Section 2 - Plot Data"
        assert sections[2]["title"] == "Section 3 - Compute Statistics"
        assert sections[3]["title"] == "Final Section"

    @pytest.mark.asyncio
    async def test_get_sections_from_eeglab_script(self, matlab_engine, eeglab_script):
        """Test section detection in real EEGLAB script."""
        sections = await matlab_engine.get_script_sections(str(eeglab_script))

        # study_script.m has multiple sections
        assert len(sections) >= 10

        # Check that each section has required fields
        for section in sections:
            assert "index" in section
            assert "title" in section
            assert "start_line" in section
            assert "end_line" in section
            assert "preview" in section

    @pytest.mark.asyncio
    async def test_sections_include_preview(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that sections include code preview."""
        sections = await matlab_engine.get_script_sections(
            str(sample_script_with_sections)
        )

        # First section should have preview of first code line
        assert "x = 1:10" in sections[0]["preview"]

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_error(self, matlab_engine):
        """Test that nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            await matlab_engine.get_script_sections("/nonexistent/path/script.m")


class TestExecuteSectionByIndex:
    """Tests for execute_section_by_index functionality."""

    @pytest.mark.asyncio
    async def test_execute_first_section(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test executing first section by index."""
        result = await matlab_engine.execute_section_by_index(
            str(sample_script_with_sections), section_index=0, capture_plots=False
        )

        assert result.error is None or result.error == ""
        # Check that variables were created
        assert "x" in result.workspace or "y" in result.workspace

    @pytest.mark.asyncio
    async def test_execute_with_workspace_maintenance(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that workspace is maintained between sections."""
        # Execute first section
        await matlab_engine.execute_section_by_index(
            str(sample_script_with_sections),
            section_index=0,
            maintain_workspace=True,
            capture_plots=False,
        )

        # Execute third section (which uses x, y from first)
        result = await matlab_engine.execute_section_by_index(
            str(sample_script_with_sections),
            section_index=2,
            maintain_workspace=True,
            capture_plots=False,
        )

        assert result.error is None or result.error == ""
        # Should have computed statistics
        assert "mean_val" in result.workspace or "std_val" in result.workspace

    @pytest.mark.asyncio
    async def test_invalid_index_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that invalid index raises IndexError."""
        with pytest.raises(IndexError) as exc_info:
            await matlab_engine.execute_section_by_index(
                str(sample_script_with_sections), section_index=99
            )
        assert "out of range" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_negative_index_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that negative index raises IndexError."""
        with pytest.raises(IndexError):
            await matlab_engine.execute_section_by_index(
                str(sample_script_with_sections), section_index=-1
            )

    @pytest.mark.asyncio
    async def test_error_message_includes_range(
        self, matlab_engine, sample_script_with_sections
    ):
        """IndexError message must tell the user the valid range."""
        with pytest.raises(IndexError) as exc_info:
            await matlab_engine.execute_section_by_index(
                str(sample_script_with_sections), section_index=100
            )
        msg = str(exc_info.value)
        # Message should mention valid range (0 to N-1)
        assert "0" in msg or "range" in msg.lower()


class TestExecuteSectionByTitle:
    """Tests for execute_section_by_title functionality."""

    @pytest.mark.asyncio
    async def test_execute_by_exact_title(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test executing section by exact title match."""
        result = await matlab_engine.execute_section_by_title(
            str(sample_script_with_sections),
            section_title="Section 1 - Initialize",
            capture_plots=False,
        )

        assert result.error is None or result.error == ""
        assert "x" in result.workspace or "y" in result.workspace

    @pytest.mark.asyncio
    async def test_execute_by_partial_title(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test executing section by partial title match."""
        result = await matlab_engine.execute_section_by_title(
            str(sample_script_with_sections),
            section_title="Statistics",
            capture_plots=False,
            maintain_workspace=True,
        )

        assert result.error is None or result.error == ""

    @pytest.mark.asyncio
    async def test_case_insensitive_match(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that title matching is case-insensitive."""
        result = await matlab_engine.execute_section_by_title(
            str(sample_script_with_sections),
            section_title="FINAL section",
            capture_plots=False,
        )

        assert result.error is None or result.error == ""

    @pytest.mark.asyncio
    async def test_nonexistent_title_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that nonexistent title raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await matlab_engine.execute_section_by_title(
                str(sample_script_with_sections), section_title="Nonexistent Section"
            )
        assert "No section matching" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_ambiguous_title_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that ambiguous title raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await matlab_engine.execute_section_by_title(
                str(sample_script_with_sections),
                section_title="Section",  # Matches multiple sections
            )
        assert "Multiple sections match" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_title_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that an empty section_title raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await matlab_engine.execute_section_by_title(
                str(sample_script_with_sections),
                section_title="",
            )
        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_title_raises_error(
        self, matlab_engine, sample_script_with_sections
    ):
        """Test that a whitespace-only section_title raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await matlab_engine.execute_section_by_title(
                str(sample_script_with_sections),
                section_title="   ",
            )
        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_error_message_lists_available_sections(
        self, matlab_engine, sample_script_with_sections
    ):
        """Error for missing title should list the available section titles."""
        with pytest.raises(ValueError) as exc_info:
            await matlab_engine.execute_section_by_title(
                str(sample_script_with_sections),
                section_title="nonexistent_xyz",
            )
        msg = str(exc_info.value)
        assert "Available sections" in msg


class TestArbitraryFilePaths:
    """Tests for arbitrary file path support."""

    @pytest.mark.asyncio
    async def test_absolute_path(self, matlab_engine, sample_script_with_sections):
        """Test section execution with absolute file path."""
        sections = await matlab_engine.get_script_sections(
            str(sample_script_with_sections)
        )
        assert len(sections) > 0

    @pytest.mark.asyncio
    async def test_eeglab_tutorial_script(self, matlab_engine, eeglab_script):
        """Test section detection in EEGLAB tutorial script."""
        sections = await matlab_engine.get_script_sections(str(eeglab_script))

        # Check specific sections we know exist
        titles = [s["title"] for s in sections]

        # study_script.m has sections like "import data and create study"
        assert any("import" in t.lower() or "study" in t.lower() for t in titles)
