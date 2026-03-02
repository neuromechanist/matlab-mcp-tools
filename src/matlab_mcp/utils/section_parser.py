"""Utility functions for parsing and executing MATLAB script sections."""

from pathlib import Path
from typing import List, Tuple


def parse_sections(file_path: Path) -> List[Tuple[int, int, str]]:
    """Parse a MATLAB script into sections.

    Sections are delimited by lines starting with '%%'. The section title
    is the text after '%%' on the same line (stripped of whitespace). Sections
    with no title text (bare '%%') get an empty string title.

    If code appears before the first '%%' marker, that code is collected as a
    leading 'Main' section. If no '%%' markers exist at all, the entire file
    is a single 'Main' section.

    Args:
        file_path: Path to the MATLAB script

    Returns:
        List of tuples containing (start_line, end_line, section_title)
        where line numbers are 0-based and end_line is inclusive.
        If no sections are found, returns a single section spanning the
        entire file titled 'Main'.
    """
    sections = []
    current_start = 0
    current_title = "Main"
    found_section_marker = False

    with open(file_path) as f:
        lines = f.readlines()

    if not lines:
        # Empty file: return a degenerate section with identical start/end
        return [(0, 0, "Main")]

    for i, line in enumerate(lines):
        # Only treat %% at the start of a line as a section marker.
        # Inline comments like "x = 1; %% note" are NOT section markers.
        if line.startswith("%%"):
            if not found_section_marker:
                # First %% encountered
                found_section_marker = True
                if i > 0:
                    # There is code before the first section marker; save it
                    # as the leading 'Main' section.
                    sections.append((current_start, i - 1, current_title))
            else:
                # End the previous section (which started at current_start)
                sections.append((current_start, i - 1, current_title))

            # Start a new section at this %% line
            current_start = i
            # Extract section title (everything after %% on the same line)
            current_title = line[2:].strip()

    # Add the final section (or the only section when no %% was found)
    sections.append((current_start, len(lines) - 1, current_title))

    # If no %% markers were found, the single appended section is the whole file.
    # Reset its title to 'Main' since current_title was never changed.
    if not found_section_marker:
        sections = [(0, len(lines) - 1, "Main")]

    return sections


def extract_section(
    file_path: Path, start_line: int, end_line: int, maintain_workspace: bool = True
) -> str:
    """Extract a section of MATLAB code from a file.

    The returned code includes the %% marker line (if any) since MATLAB treats
    it as a comment.  When maintain_workspace is False a 'clear;' statement is
    prepended so the section runs in an isolated workspace.

    Args:
        file_path: Path to the MATLAB script
        start_line: Starting line number (0-based, inclusive)
        end_line: Ending line number (0-based, inclusive)
        maintain_workspace: Whether to maintain workspace variables

    Returns:
        MATLAB code for the specified section
    """
    with open(file_path) as f:
        lines = f.readlines()

    # Extract the section lines
    section_lines = lines[start_line : end_line + 1]

    # If not maintaining workspace, add clear command at the start
    if not maintain_workspace:
        section_lines.insert(0, "clear;\n")

    return "".join(section_lines)


def get_section_info(file_path: Path) -> List[dict]:
    """Get information about sections in a MATLAB script.

    Args:
        file_path: Path to the MATLAB script

    Returns:
        List of dictionaries containing section information:
        {
            'title': section title,
            'start_line': starting line number (0-based),
            'end_line': ending line number (0-based, inclusive),
            'preview': first non-comment line of the section
        }
    """
    sections = parse_sections(file_path)
    section_info = []

    with open(file_path) as f:
        lines = f.readlines()

    for start, end, title in sections:
        # Find first non-comment line for preview
        preview = ""
        for line in lines[start : end + 1]:
            stripped = line.strip()
            if stripped and not stripped.startswith("%"):
                preview = stripped
                break

        section_info.append(
            {"title": title, "start_line": start, "end_line": end, "preview": preview}
        )

    return section_info
