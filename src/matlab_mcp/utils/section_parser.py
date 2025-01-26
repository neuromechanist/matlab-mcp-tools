"""Utility functions for parsing and executing MATLAB script sections."""

from pathlib import Path
from typing import List, Tuple


def parse_sections(file_path: Path) -> List[Tuple[int, int, str]]:
    """Parse a MATLAB script into sections.
    
    Args:
        file_path: Path to the MATLAB script
        
    Returns:
        List of tuples containing (start_line, end_line, section_title)
        for each section in the script. If no sections are found, returns
        a single section spanning the entire file.
    """
    sections = []
    current_start = 0
    current_title = "Main"
    
    with open(file_path) as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        if line.startswith('%%'):
            # If we found a section marker, end the previous section
            if current_start < i:
                sections.append((current_start, i - 1, current_title))
            
            # Start a new section
            current_start = i
            # Extract section title (everything after %% on the same line)
            current_title = line[2:].strip()
    
    # Add the final section
    if current_start < len(lines):
        sections.append((current_start, len(lines) - 1, current_title))
    
    # If no sections were found, treat the entire file as one section
    if not sections:
        sections = [(0, len(lines) - 1, "Main")]
    
    return sections


def extract_section(
    file_path: Path,
    start_line: int,
    end_line: int,
    maintain_workspace: bool = True
) -> str:
    """Extract a section of MATLAB code from a file.
    
    Args:
        file_path: Path to the MATLAB script
        start_line: Starting line number (0-based)
        end_line: Ending line number (0-based)
        maintain_workspace: Whether to maintain workspace variables
        
    Returns:
        MATLAB code for the specified section
    """
    with open(file_path) as f:
        lines = f.readlines()
    
    # Extract the section lines
    section_lines = lines[start_line:end_line + 1]
    
    # If not maintaining workspace, add clear command at the start
    if not maintain_workspace:
        section_lines.insert(0, 'clear;\n')
    
    return ''.join(section_lines)


def get_section_info(file_path: Path) -> List[dict]:
    """Get information about sections in a MATLAB script.
    
    Args:
        file_path: Path to the MATLAB script
        
    Returns:
        List of dictionaries containing section information:
        {
            'title': section title,
            'start_line': starting line number,
            'end_line': ending line number,
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
        for line in lines[start:end + 1]:
            stripped = line.strip()
            if stripped and not stripped.startswith('%'):
                preview = stripped
                break
        
        section_info.append({
            'title': title,
            'start_line': start,
            'end_line': end,
            'preview': preview
        })
    
    return section_info
