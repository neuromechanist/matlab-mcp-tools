"""Data models for MATLAB MCP Tool."""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class FigureFormat(str, Enum):
    """Supported figure formats."""

    PNG = "png"
    SVG = "svg"


class CompressionConfig(BaseModel):
    """Configuration for figure compression."""

    quality: int = Field(
        default=75,
        ge=1,
        le=100,
        description="Compression quality (1-100, higher is better quality)",
    )
    dpi: int = Field(
        default=150, ge=50, le=600, description="Resolution in DPI (dots per inch)"
    )
    optimize_for: str = Field(
        default="size", description="Optimization target: 'size' or 'quality'"
    )


class FigureData(BaseModel):
    """Model for figure data with compression support."""

    data: Optional[bytes] = Field(
        default=None, description="Raw figure data (None if using file_path)"
    )
    file_path: Optional[str] = Field(
        default=None, description="Path to figure file (alternative to data)"
    )
    format: FigureFormat = Field(description="Figure format")
    compression_config: Optional[CompressionConfig] = Field(
        default=None, description="Compression settings used"
    )
    original_size: Optional[int] = Field(
        default=None, description="Original file size in bytes"
    )
    compressed_size: Optional[int] = Field(
        default=None, description="Compressed file size in bytes"
    )


class ScriptExecution(BaseModel):
    """Model for script execution parameters."""

    script: str = Field(description="MATLAB code or file path to execute")
    is_file: bool = Field(
        default=False, description="Whether script parameter is a file path"
    )
    workspace_vars: Optional[Dict[str, Any]] = Field(
        default=None, description="Variables to inject into MATLAB workspace"
    )
    capture_plots: bool = Field(
        default=True, description="Whether to capture and return generated plots"
    )
    compression_config: Optional[CompressionConfig] = Field(
        default=None, description="Figure compression settings"
    )


class SectionExecution(BaseModel):
    """Model for section-based execution parameters."""

    file_path: str = Field(description="Path to the MATLAB file")
    section_range: Tuple[int, int] = Field(
        description="Start and end line numbers of the section"
    )
    maintain_workspace: bool = Field(
        default=True, description="Whether to maintain workspace between sections"
    )


class DebugConfig(BaseModel):
    """Model for debug configuration."""

    script: str = Field(description="Path to MATLAB script to debug")
    breakpoints: List[int] = Field(description="Line numbers to set breakpoints")
    watch_vars: Optional[List[str]] = Field(
        default=None, description="Variables to watch during debugging"
    )


class ExecutionResult(BaseModel):
    """Model for execution results."""

    output: str = Field(description="Text output from MATLAB execution")
    error: Optional[str] = Field(
        default=None, description="Error message if execution failed"
    )
    workspace: Dict[str, Any] = Field(
        default_factory=dict, description="Current MATLAB workspace variables"
    )
    figures: List[FigureData] = Field(
        default_factory=list, description="Generated plot images in PNG and SVG formats"
    )
