"""Data models for MATLAB MCP Tool."""

import time
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
    use_file_reference: bool = Field(
        default=False,
        description="Return file path instead of binary data to reduce bandwidth",
    )
    smart_optimization: bool = Field(
        default=True,
        description="Analyze plot content to automatically optimize compression settings",
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


class PerformanceConfig(BaseModel):
    """Model for performance and reliability configuration."""

    memory_limit_mb: Optional[int] = Field(
        default=1024, description="Memory limit in MB for workspace variables"
    )
    execution_timeout_seconds: Optional[int] = Field(
        default=30, description="Timeout for script execution in seconds"
    )
    enable_hot_reload: bool = Field(
        default=False, description="Enable hot reloading for script development"
    )
    enable_enhanced_errors: bool = Field(
        default=True, description="Enable enhanced error reporting with context"
    )


class MemoryStatus(BaseModel):
    """Model for memory status information."""

    total_size_mb: float = Field(description="Total workspace memory usage in MB")
    variable_count: int = Field(description="Number of variables in workspace")
    largest_variable: Optional[str] = Field(description="Name of largest variable")
    largest_variable_size_mb: float = Field(
        description="Size of largest variable in MB"
    )
    memory_limit_mb: Optional[int] = Field(description="Current memory limit")
    near_limit: bool = Field(description="Whether memory usage is near limit")


class ConnectionStatus(BaseModel):
    """Model for connection status information."""

    is_connected: bool = Field(description="Whether MATLAB engine is connected")
    connection_id: Optional[str] = Field(description="Unique connection identifier")
    uptime_seconds: float = Field(description="Connection uptime in seconds")
    last_activity: float = Field(description="Timestamp of last activity")


class EnhancedError(BaseModel):
    """Model for enhanced error information."""

    error_type: str = Field(description="Type of error (MATLAB or Python)")
    message: str = Field(description="Error message")
    line_number: Optional[int] = Field(description="Line number where error occurred")
    context_lines: List[str] = Field(
        default_factory=list, description="Surrounding code lines for context"
    )
    stack_trace: Optional[str] = Field(description="Full stack trace if available")
    timestamp: float = Field(default_factory=time.time, description="Error timestamp")


class ExecutionResult(BaseModel):
    """Model for execution results."""

    output: str = Field(description="Text output from MATLAB execution")
    error: Optional[str] = Field(
        default=None, description="Error message if execution failed"
    )
    enhanced_error: Optional[EnhancedError] = Field(
        default=None, description="Enhanced error information with context"
    )
    workspace: Dict[str, Any] = Field(
        default_factory=dict, description="Current MATLAB workspace variables"
    )
    figures: List[FigureData] = Field(
        default_factory=list, description="Generated plot images in PNG and SVG formats"
    )
    execution_time_seconds: float = Field(
        default=0.0, description="Execution time in seconds"
    )
    memory_status: Optional[MemoryStatus] = Field(
        default=None, description="Memory usage information"
    )
