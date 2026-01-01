"""Unit tests for section_parser module."""

import pytest

from matlab_mcp.utils.section_parser import (
    extract_section,
    get_section_info,
    parse_sections,
)


@pytest.fixture
def script_with_sections(tmp_path):
    """Create a script with multiple sections."""
    content = """%% First Section
x = 1;
y = 2;

%% Second Section
z = x + y;

%% Third Section
disp(z);
"""
    script = tmp_path / "sections.m"
    script.write_text(content)
    return script


@pytest.fixture
def script_without_sections(tmp_path):
    """Create a script without section markers."""
    content = """x = 1;
y = 2;
z = x + y;
"""
    script = tmp_path / "no_sections.m"
    script.write_text(content)
    return script


@pytest.fixture
def script_only_comments(tmp_path):
    """Create a script with only comments in a section."""
    content = """%% Comment Only Section
% This is a comment
% Another comment

%% Code Section
x = 1;
"""
    script = tmp_path / "comments.m"
    script.write_text(content)
    return script


class TestParseSections:
    """Tests for parse_sections function."""

    def test_parse_multiple_sections(self, script_with_sections):
        """Test parsing script with multiple sections."""
        sections = parse_sections(script_with_sections)

        assert len(sections) == 3
        assert sections[0][2] == "First Section"
        assert sections[1][2] == "Second Section"
        assert sections[2][2] == "Third Section"

    def test_parse_no_sections(self, script_without_sections):
        """Test parsing script without section markers."""
        sections = parse_sections(script_without_sections)

        # Should return one "Main" section
        assert len(sections) == 1
        assert sections[0][2] == "Main"

    def test_section_line_numbers(self, script_with_sections):
        """Test that section line numbers are correct."""
        sections = parse_sections(script_with_sections)

        # First section starts at line 0
        assert sections[0][0] == 0
        # Each section starts where the %% marker is
        for start, end, _ in sections:
            assert start <= end


class TestExtractSection:
    """Tests for extract_section function."""

    def test_extract_first_section(self, script_with_sections):
        """Test extracting the first section."""
        code = extract_section(script_with_sections, 0, 3)

        assert "x = 1" in code
        assert "y = 2" in code

    def test_extract_with_clear(self, script_with_sections):
        """Test extracting section without maintaining workspace."""
        code = extract_section(script_with_sections, 0, 3, maintain_workspace=False)

        assert "clear;" in code

    def test_extract_maintains_workspace_by_default(self, script_with_sections):
        """Test that workspace is maintained by default."""
        code = extract_section(script_with_sections, 0, 3)

        assert "clear;" not in code


class TestGetSectionInfo:
    """Tests for get_section_info function."""

    def test_get_section_info_with_preview(self, script_with_sections):
        """Test that section info includes preview."""
        info = get_section_info(script_with_sections)

        assert len(info) == 3
        # First section should have preview
        assert info[0]["preview"] == "x = 1;"
        assert info[0]["title"] == "First Section"

    def test_get_section_info_comment_only_section(self, script_only_comments):
        """Test section with only comments has empty preview."""
        info = get_section_info(script_only_comments)

        # First section has only comments
        assert info[0]["preview"] == ""
        # Second section has code
        assert info[1]["preview"] == "x = 1;"

    def test_get_section_info_fields(self, script_with_sections):
        """Test that all required fields are present."""
        info = get_section_info(script_with_sections)

        for section in info:
            assert "title" in section
            assert "start_line" in section
            assert "end_line" in section
            assert "preview" in section

    def test_section_info_line_ordering(self, script_with_sections):
        """Test that sections don't overlap."""
        info = get_section_info(script_with_sections)

        for i in range(len(info) - 1):
            # Current section end should be before next section start
            assert info[i]["end_line"] < info[i + 1]["start_line"]
