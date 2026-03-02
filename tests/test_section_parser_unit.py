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

    def test_section_marker_at_first_line(self, tmp_path):
        """Test script where %% is the very first line."""
        content = """%% Only Section
x = 1;
y = 2;
"""
        script = tmp_path / "first_line.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 1
        assert sections[0][0] == 0
        assert sections[0][2] == "Only Section"

    def test_code_before_first_section_marker(self, tmp_path):
        """Test that code before the first %% is captured as a 'Main' section."""
        content = """x = 1;
y = 2;
%% Section A
z = 3;
%% Section B
w = 4;
"""
        script = tmp_path / "preamble.m"
        script.write_text(content)
        sections = parse_sections(script)

        # The leading code plus two explicit sections
        assert len(sections) == 3
        assert sections[0][2] == "Main"
        # Main section covers lines 0 and 1
        assert sections[0][0] == 0
        assert sections[0][1] == 1
        assert sections[1][2] == "Section A"
        assert sections[2][2] == "Section B"

    def test_empty_section_title(self, tmp_path):
        """Test section with bare %% (no title text)."""
        content = """%% Section 1
x = 1;
%%
%% Section 3
z = 3;
"""
        script = tmp_path / "empty_title.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 3
        assert sections[0][2] == "Section 1"
        assert sections[1][2] == ""
        assert sections[2][2] == "Section 3"

    def test_back_to_back_section_markers(self, tmp_path):
        """Test consecutive %% markers create single-line empty sections."""
        content = """%% Section 1
x = 1;
%%
%%
%% Section 4
z = 3;
"""
        script = tmp_path / "consecutive.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 4
        # The two empty sections each span exactly one line
        assert sections[1][0] == sections[1][1]
        assert sections[2][0] == sections[2][1]

    def test_trailing_whitespace_in_title(self, tmp_path):
        """Test that trailing whitespace in section titles is stripped."""
        content = """%% Section 1
x = 1;
%% Section 2\t
y = 2;
"""
        script = tmp_path / "trailing.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert sections[0][2] == "Section 1"
        assert sections[1][2] == "Section 2"

    def test_last_section_includes_all_remaining_lines(self, tmp_path):
        """Test that the last section captures all remaining lines."""
        content = """%% Section 1
x = 1;
%% Section 2
y = 2;
more = 3;
last = 4;"""
        script = tmp_path / "no_trailing_newline.m"
        script.write_text(content)
        sections = parse_sections(script)

        assert len(sections) == 2
        # Last section must reach the final line (5, 0-based)
        assert sections[1][1] == 5

    def test_inline_percent_percent_not_treated_as_section(self, tmp_path):
        """Test that %% in the middle of a line is NOT a section marker."""
        content = """x = 1; %% this is not a section
%% Real Section
y = 2;
"""
        script = tmp_path / "inline_marker.m"
        script.write_text(content)
        sections = parse_sections(script)

        # Only the line-initial %% creates a section
        assert len(sections) == 2
        assert sections[0][2] == "Main"
        assert sections[1][2] == "Real Section"

    def test_empty_file(self, tmp_path):
        """Test parsing an empty file."""
        script = tmp_path / "empty.m"
        script.write_text("")
        sections = parse_sections(script)

        assert len(sections) == 1
        assert sections[0][2] == "Main"

    def test_sections_are_contiguous(self, script_with_sections):
        """Test that sections cover lines without overlap or gap."""
        sections = parse_sections(script_with_sections)

        for i in range(len(sections) - 1):
            _, end, _ = sections[i]
            next_start, _, _ = sections[i + 1]
            # Adjacent sections must share a boundary:
            # end of section i is one before start of section i+1
            assert end + 1 == next_start, (
                f"Gap or overlap between section {i} (end={end}) "
                f"and section {i + 1} (start={next_start})"
            )


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

    def test_extract_section_includes_marker_line(self, tmp_path):
        """Test that the %% marker line is included in the extracted code."""
        content = """%% My Section
x = 42;
"""
        script = tmp_path / "marker.m"
        script.write_text(content)
        # Section spans lines 0-1
        code = extract_section(script, 0, 1)

        assert "%% My Section" in code
        assert "x = 42" in code

    def test_extract_single_line_section(self, tmp_path):
        """Test extracting a single-line section (bare %%)."""
        content = """%% Section 1
x = 1;
%%
%% Section 3
z = 3;
"""
        script = tmp_path / "single_line.m"
        script.write_text(content)
        sections = parse_sections(script)
        # Middle section is the bare %% at line 2
        start, end, _ = sections[1]
        assert start == end
        code = extract_section(script, start, end)
        assert code.strip().startswith("%%")


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

    def test_section_info_preamble_title(self, tmp_path):
        """Test that code before the first %% reports title 'Main'."""
        content = """x = 1;
%% Named Section
y = 2;
"""
        script = tmp_path / "preamble_info.m"
        script.write_text(content)
        info = get_section_info(script)

        assert info[0]["title"] == "Main"
        assert info[1]["title"] == "Named Section"
