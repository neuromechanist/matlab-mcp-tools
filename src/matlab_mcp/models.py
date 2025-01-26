"""Data models for MATLAB MCP Tool."""

from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class ScriptExecution(BaseModel):
    """Model for script execution parameters."""
    script: str = Field(
        description="MATLAB code or file path to execute"
    )
    is_file: bool = Field(
        default=False,
        description="Whether script parameter is a file path"
    )
    workspace_vars: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Variables to inject into MATLAB workspace"
    )
    capture_plots: bool = Field(
        default=True,
        description="Whether to capture and return generated plots"
    )


class SectionExecution(BaseModel):
    """Model for section-based execution parameters."""
    file_path: str = Field(
        description="Path to the MATLAB file"
    )
    section_range: Tuple[int, int] = Field(
        description="Start and end line numbers of the section"
    )
    maintain_workspace: bool = Field(
        default=True,
        description="Whether to maintain workspace between sections"
    )


class DebugConfig(BaseModel):
    """Model for debug configuration."""
    script: str = Field(
        description="Path to MATLAB script to debug"
    )
    breakpoints: List[int] = Field(
        description="Line numbers to set breakpoints"
    )
    watch_vars: Optional[List[str]] = Field(
        default=None,
        description="Variables to watch during debugging"
    )


class ExecutionResult(BaseModel):
    """Model for execution results."""
    output: str = Field(
        description="Text output from MATLAB execution"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if execution failed"
    )
    workspace: Dict[str, Any] = Field(
        default_factory=dict,
        description="Current MATLAB workspace variables"
    )
    figures: List[bytes] = Field(
        default_factory=list,
        description="Generated plot images in PNG format"
    )
