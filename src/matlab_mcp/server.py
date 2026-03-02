"""MATLAB MCP Server implementation."""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import Context, FastMCP, Image

from .engine import MatlabEngine
from .figure_analysis import DEFAULT_ANALYSIS_PROMPT
from .matlab_compat import validate_environment
from .models import CompressionConfig, FigureData


def _figure_to_image(fig: FigureData) -> Image:
    """Convert FigureData to MCP Image, handling both data and file path references.

    Args:
        fig: FigureData object containing either binary data or file path

    Returns:
        MCP Image object
    """
    if fig.data is not None:
        # Binary data available - use it directly
        return Image(data=fig.data, format=fig.format.value)
    elif fig.file_path is not None:
        # File path reference - read the file
        try:
            with open(fig.file_path, "rb") as f:
                data = f.read()
            return Image(data=data, format=fig.format.value)
        except Exception as e:
            print(f"Error reading figure file {fig.file_path}: {e}", file=sys.stderr)
            # Return empty image as fallback
            return Image(data=b"", format=fig.format.value)
    else:
        # No data or file path - return empty image
        return Image(data=b"", format=fig.format.value)


# Configure logging based on debug mode
debug_mode = os.getenv("MATLAB_MCP_DEBUG", "").lower() in ("true", "1", "yes")

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG if debug_mode else logging.WARNING,
    format="%(message)s",
    force=True,
)

# Configure MCP loggers to be completely silent unless in debug mode
for logger_name in ["mcp", "mcp.server", "mcp.client", "mcp.shared"]:
    logger = logging.getLogger(logger_name)
    if not debug_mode:
        logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.DEBUG if debug_mode else logging.CRITICAL)
    logger.propagate = False

# Create FastMCP instance at module level
mcp = FastMCP(
    "MATLAB",
    dependencies=["matlabengine"],
    debug=debug_mode,
    instructions="MATLAB MCP server providing access to MATLAB engine functionality.",
)

# Log startup mode
if debug_mode:
    logging.debug("Starting in DEBUG mode")
else:
    print("MATLAB MCP Server starting (set MATLAB_MCP_DEBUG=true for debug output)")


# Module-level singleton instance and lock, this is a test to see if it works
# _instance = None
# _instance_lock = asyncio.Lock()


class MatlabServer:
    """MCP server providing MATLAB integration."""

    _instance = None

    @classmethod
    def get_instance(cls):
        """Get singleton instance of MatlabServer."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize the MATLAB MCP server."""
        self.engine = MatlabEngine()
        self._initialized = False

        # Use .mcp directory in home for all files
        self.mcp_dir = Path.home() / ".mcp"
        self.scripts_dir = self.mcp_dir / "matlab" / "scripts"
        self.scripts_dir.parent.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(exist_ok=True)

    # @classmethod
    # async def get_instance(cls):
    #     """Get singleton instance of MatlabServer."""
    #     global _instance
    #     async with _instance_lock:
    #         if _instance is None:
    #             _instance = cls()
    #         return _instance

    async def initialize(self) -> None:
        """Initialize server and engine if not already initialized."""
        if not self._initialized:
            try:
                await self.engine.initialize()
                self._initialized = True
            except Exception as e:
                logging.error(f"Failed to initialize MATLAB engine: {str(e)}")
                raise

    def close(self):
        """Clean up server resources."""
        print("\nShutting down MATLAB MCP Server...")
        try:
            if self.engine is not None:
                self.engine.close()
                self.engine = None
            self._initialized = False
            self.__class__._instance = None
        except Exception as e:
            logging.error(f"Error during shutdown: {str(e)}")
            raise

    # def close(self) -> None:
    #     """Clean up server resources on process exit."""
    #     if self.engine is not None:
    #         self.engine.close()
    #         self.engine = None
    #     if self._timeout_task:
    #         self._timeout_task.cancel()
    #         self._timeout_task = None


# Define tools at module level
@mcp.tool()
async def execute_script(
    script: str,
    is_file: bool = False,
    workspace_vars: Optional[Dict[str, Any]] = None,
    capture_plots: bool = True,
    compression_config: Optional[CompressionConfig] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute MATLAB code and return results with plots.

    Returns a dictionary containing:
    - output: Command output text
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Executing MATLAB {'file' if is_file else 'code'}")

    result = await server.engine.execute(
        script,
        is_file=is_file,
        workspace_vars=workspace_vars,
        capture_plots=capture_plots,
        compression_config=compression_config,
        ctx=ctx,
    )

    # Convert FigureData to MCP Image objects
    figures = [_figure_to_image(fig) for fig in result.figures]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures,
    }


@mcp.tool()
async def execute_section(
    file_path: str,
    section_range: Tuple[int, int],
    maintain_workspace: bool = True,
    capture_plots: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a specific section of a MATLAB script by line range.

    Consider using execute_section_by_index or execute_section_by_title for
    easier section selection. Use get_script_sections to see available sections.

    Args:
        file_path: Full path to the MATLAB script (or script name in ~/.mcp/matlab/scripts/)
        section_range: Tuple of (start_line, end_line) for the section (0-based)
        maintain_workspace: Whether to maintain workspace between sections
        capture_plots: Whether to capture generated plots

    Returns a dictionary containing:
    - output: Section execution output
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    # Support both full paths and script names in scripts_dir
    script_path = Path(file_path)
    if not script_path.is_absolute():
        # Try scripts_dir first
        scripts_path = server.scripts_dir / file_path
        if scripts_path.exists():
            script_path = scripts_path
        # Otherwise treat as relative to cwd

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {file_path}")

    if ctx:
        ctx.info(f"Executing section (lines {section_range[0]}-{section_range[1]})")

    result = await server.engine.execute_section(
        str(script_path),
        section_range,
        maintain_workspace=maintain_workspace,
        capture_plots=capture_plots,
        ctx=ctx,
    )

    # Convert FigureData to MCP Image objects
    figures = [_figure_to_image(fig) for fig in result.figures]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures,
    }


@mcp.tool()
async def execute_section_by_index(
    file_path: str,
    section_index: int,
    maintain_workspace: bool = True,
    capture_plots: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a specific section of a MATLAB script by its index.

    This is the recommended way to execute sections. Use get_script_sections
    first to see available sections and their indices.

    Args:
        file_path: Full path to the MATLAB script (or script name in ~/.mcp/matlab/scripts/)
        section_index: 0-based index of the section to execute
        maintain_workspace: Whether to maintain workspace between sections
        capture_plots: Whether to capture generated plots

    Examples:
        - execute_section_by_index("/path/to/script.m", 0)
          Execute the first section

        - execute_section_by_index("my_script.m", 2)
          Execute the third section of my_script.m in scripts directory

    Returns a dictionary containing:
    - output: Section execution output
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    # Support both full paths and script names in scripts_dir
    script_path = Path(file_path)
    if not script_path.is_absolute():
        scripts_path = server.scripts_dir / file_path
        if scripts_path.exists():
            script_path = scripts_path

    if ctx:
        ctx.info(f"Executing section index {section_index}")

    result = await server.engine.execute_section_by_index(
        str(script_path),
        section_index,
        maintain_workspace=maintain_workspace,
        capture_plots=capture_plots,
        ctx=ctx,
    )

    # Convert FigureData to MCP Image objects
    figures = [_figure_to_image(fig) for fig in result.figures]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures,
    }


@mcp.tool()
async def execute_section_by_title(
    file_path: str,
    section_title: str,
    maintain_workspace: bool = True,
    capture_plots: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a specific section of a MATLAB script by its title.

    Finds and executes the section whose title contains the given string
    (case-insensitive partial match).

    Args:
        file_path: Full path to the MATLAB script (or script name in ~/.mcp/matlab/scripts/)
        section_title: Title or partial title of the section to execute
        maintain_workspace: Whether to maintain workspace between sections
        capture_plots: Whether to capture generated plots

    Examples:
        - execute_section_by_title("/path/to/script.m", "Load Data")
          Execute the section titled "Load Data" or "Load Data from File", etc.

        - execute_section_by_title("analysis.m", "plot")
          Execute the section with "plot" in its title

    Returns a dictionary containing:
    - output: Section execution output
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    # Support both full paths and script names in scripts_dir
    script_path = Path(file_path)
    if not script_path.is_absolute():
        scripts_path = server.scripts_dir / file_path
        if scripts_path.exists():
            script_path = scripts_path

    if ctx:
        ctx.info(f"Finding and executing section: '{section_title}'")

    result = await server.engine.execute_section_by_title(
        str(script_path),
        section_title,
        maintain_workspace=maintain_workspace,
        capture_plots=capture_plots,
        ctx=ctx,
    )

    # Convert FigureData to MCP Image objects
    figures = [_figure_to_image(fig) for fig in result.figures]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures,
    }


@mcp.tool()
async def get_workspace(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Get current MATLAB workspace variables.

    Returns a dictionary mapping variable names to their values.
    Complex MATLAB types are converted to Python types where possible.
    Large arrays return summaries with statistics instead of full data.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Fetching MATLAB workspace")

    return await server.engine.get_workspace()


@mcp.tool()
async def get_variable(
    name: str,
    fields: Optional[List[str]] = None,
    depth: int = 1,
    max_elements: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a specific MATLAB variable with selective retrieval.

    This is the preferred way to access complex structs like EEGLAB's EEG.
    Instead of transferring the entire struct, you can:
    - Request only specific fields
    - Control the depth of nested struct retrieval
    - Limit array sizes to prevent token explosion

    Args:
        name: Variable name. Can include field access like "EEG.chanlocs"
        fields: List of specific fields to retrieve (for structs only)
        depth: Retrieval depth. 0=info only (field names), 1=values, 2+=nested
        max_elements: Maximum array elements to transfer (default 100)

    Examples:
        - get_variable("EEG", fields=["nbchan", "srate", "pnts"])
          Returns only the scalar properties, not the huge data array

        - get_variable("EEG.chanlocs", depth=0)
          Returns field names of chanlocs without values

        - get_variable("EEG.event", fields=["type", "latency"], max_elements=10)
          Returns first 10 events with only type and latency fields
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Getting variable: {name}")

    return await server.engine.get_variable(
        name=name,
        fields=fields,
        depth=depth,
        max_elements=max_elements,
    )


@mcp.tool()
async def get_struct_info(
    var_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get struct field information without transferring values.

    Essential for exploring unknown MATLAB structs before deciding
    which fields to retrieve. Returns field names, types, sizes,
    and memory usage for each field.

    Args:
        var_name: Name of the struct variable (e.g., "EEG" or "EEG.chanlocs")

    Returns:
        Dictionary with field information:
        {
            "field_name": {
                "class": "double",
                "size": [32, 30504],
                "numel": 976128,
                "bytes": 7809024,
                "is_struct": false,
                "is_numeric": true
            },
            ...
        }

    Example:
        info = get_struct_info("EEG")
        # Now you know EEG.data is huge but EEG.nbchan is small
        # Use get_variable("EEG", fields=["nbchan", "srate"]) for small fields
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Getting struct info for: {var_name}")

    return await server.engine.get_struct_info(var_name)


@mcp.tool()
async def list_workspace_variables(
    pattern: Optional[str] = None,
    var_type: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """List workspace variables with optional filtering.

    Useful for discovering what variables exist without retrieving them.
    Supports regex pattern matching and type filtering.

    Args:
        pattern: Regex pattern to filter variable names (e.g., "^EEG" for EEG*)
        var_type: Filter by MATLAB class (e.g., "struct", "double", "cell")

    Returns:
        List of variable info dictionaries:
        [
            {
                "name": "EEG",
                "class": "struct",
                "size": [1, 1],
                "bytes": 15000000,
                "is_struct": true,
                "is_numeric": false
            },
            ...
        ]

    Examples:
        - list_workspace_variables(pattern="^EEG")
          List all variables starting with "EEG"

        - list_workspace_variables(var_type="struct")
          List all struct variables

        - list_workspace_variables(pattern="data", var_type="double")
          List all numeric arrays with "data" in the name
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Listing workspace variables")

    return await server.engine.list_workspace_variables(
        pattern=pattern,
        var_type=var_type,
    )


@mcp.tool()
async def get_script_sections(
    file_path: str, ctx: Optional[Context] = None
) -> List[Dict[str, Any]]:
    """Get information about sections in a MATLAB script.

    Use this tool before execute_section_by_index or execute_section_by_title
    to see what sections are available.

    Args:
        file_path: Full path to the MATLAB script (or script name in ~/.mcp/matlab/scripts/)

    Returns a list of dictionaries containing:
    - index: Section index (0-based) for use with execute_section_by_index
    - title: Section title for use with execute_section_by_title
    - start_line: Section start line number (0-based)
    - end_line: Section end line number (0-based)
    - preview: First non-comment line of the section

    Examples:
        - get_script_sections("/path/to/analysis.m")
          Returns sections from any MATLAB script

        - get_script_sections("my_script.m")
          Returns sections from script in ~/.mcp/matlab/scripts/
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    # Support both full paths and script names in scripts_dir
    script_path = Path(file_path)
    if not script_path.is_absolute():
        scripts_path = server.scripts_dir / file_path
        if scripts_path.exists():
            script_path = scripts_path

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {file_path}")

    if ctx:
        ctx.info(f"Getting sections for script: {file_path}")

    # Use the engine's method for consistency
    return await server.engine.get_script_sections(str(script_path))


@mcp.tool()
async def create_matlab_script(
    script_name: str, code: str, ctx: Optional[Context] = None
) -> str:
    """Create a new MATLAB script file.

    Returns the path to the created script file.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    # Remove .m extension if present for validation
    base_name = script_name[:-2] if script_name.endswith(".m") else script_name

    if not base_name.isidentifier():
        raise ValueError("Script name must be a valid MATLAB identifier")

    # Ensure .m extension is present
    if not script_name.endswith(".m"):
        script_name = f"{script_name}.m"

    script_path = server.scripts_dir / script_name
    script_path.write_text(code)

    if ctx:
        ctx.info(f"Created MATLAB script: {script_path}")

    return str(script_path)


@mcp.tool()
async def get_figure_metadata(
    figure_number: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract metadata from a MATLAB figure.

    Retrieves comprehensive information about a figure including:
    - Title, axis labels, and axis limits
    - Legend entries and colorbar information
    - Number and colors of lines/surfaces
    - Colormap name (if identifiable)

    This is useful for understanding figure contents programmatically
    or for preparing context for LLM-based figure analysis.

    Args:
        figure_number: MATLAB figure number to analyze (default: 1)

    Returns:
        Dictionary with figure metadata:
        {
            "figure_number": 1,
            "title": "My Plot",
            "xlabel": "Time (s)",
            "ylabel": "Amplitude (V)",
            "xlim": [0, 10],
            "ylim": [-1, 1],
            "num_lines": 3,
            "line_colors": ["blue", "red", "green"],
            "legend_entries": ["Signal 1", "Signal 2", "Signal 3"],
            ...
        }
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Getting metadata for figure {figure_number}")

    metadata = await server.engine.get_figure_metadata(figure_number)

    # Convert dataclass to dict for JSON serialization
    return {
        "figure_number": metadata.figure_number,
        "title": metadata.title,
        "xlabel": metadata.xlabel,
        "ylabel": metadata.ylabel,
        "zlabel": metadata.zlabel,
        "xlim": metadata.xlim,
        "ylim": metadata.ylim,
        "zlim": metadata.zlim,
        "legend_entries": metadata.legend_entries,
        "colorbar_label": metadata.colorbar_label,
        "colorbar_limits": metadata.colorbar_limits,
        "num_subplots": metadata.num_subplots,
        "num_lines": metadata.num_lines,
        "num_images": metadata.num_images,
        "line_colors": metadata.line_colors,
        "line_styles": metadata.line_styles,
        "line_labels": metadata.line_labels,
        "colormap_name": metadata.colormap_name,
    }


@mcp.tool()
async def get_plot_data(
    figure_number: int = 1,
    line_index: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract raw data from a plotted line in a MATLAB figure.

    Retrieves the X, Y (and Z for 3D plots) data from a specific line
    object in a figure. Useful for:
    - Exporting plot data for further analysis
    - Verifying plotted values
    - Recreating plots in other tools

    Args:
        figure_number: MATLAB figure number (default: 1)
        line_index: 1-based index of the line to extract (default: 1)

    Returns:
        Dictionary with line data:
        {
            "line_index": 1,
            "xdata": [0, 1, 2, 3, ...],
            "ydata": [0.1, 0.5, 0.3, ...],
            "zdata": [],  # Empty for 2D plots
            "label": "My Signal",
            "color": [0, 0.447, 0.741],
            "style": "-",
            "marker": "none"
        }
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Getting data for line {line_index} in figure {figure_number}")

    plot_data = await server.engine.get_plot_data(figure_number, line_index)

    return {
        "line_index": plot_data.line_index,
        "xdata": plot_data.xdata,
        "ydata": plot_data.ydata,
        "zdata": plot_data.zdata,
        "label": plot_data.label,
        "color": plot_data.color,
        "style": plot_data.style,
        "marker": plot_data.marker,
    }


@mcp.tool()
async def analyze_figure(
    figure_number: int = 1,
    custom_prompt: Optional[str] = None,
    include_metadata: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Prepare a MATLAB figure for LLM vision analysis.

    Captures a figure as an image and prepares an analysis prompt that
    emphasizes understanding:
    - Axes, scales, and units
    - Colors and their meanings (what each color represents)
    - Data interpretation and patterns
    - Legend and labels
    - Quality assessment

    The returned image and prompt can be used with vision-capable LLMs
    to get detailed figure analysis.

    Args:
        figure_number: MATLAB figure number to analyze (default: 1)
        custom_prompt: Optional custom prompt (replaces default if provided)
        include_metadata: Whether to include extracted metadata in prompt (default: True)

    Returns:
        Dictionary containing:
        - image: MCP Image object of the figure
        - prompt: Analysis prompt (includes metadata if requested)
        - metadata: Figure metadata dict (if include_metadata=True)

    Example usage:
        result = analyze_figure(1, include_metadata=True)
        # Use result["image"] and result["prompt"] with a vision LLM
        # The prompt emphasizes axes, units, colors, and their meanings
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Preparing figure {figure_number} for analysis")

    # Get the prepared analysis data
    analysis_data = await server.engine.prepare_figure_for_analysis(
        figure_number=figure_number,
        custom_prompt=custom_prompt,
        include_metadata=include_metadata,
    )

    # Check for errors
    if "error" in analysis_data:
        return {
            "error": analysis_data["error"],
            "prompt": analysis_data.get("prompt", ""),
        }

    # Convert FigureData to MCP Image
    figure_data = analysis_data.get("figure")
    if figure_data is None:
        return {
            "error": "Failed to capture figure",
            "prompt": analysis_data.get("prompt", ""),
        }

    image = _figure_to_image(figure_data)

    result = {
        "image": image,
        "prompt": analysis_data["prompt"],
    }

    if include_metadata:
        metadata = analysis_data["metadata"]
        result["metadata"] = {
            "figure_number": metadata.figure_number,
            "title": metadata.title,
            "xlabel": metadata.xlabel,
            "ylabel": metadata.ylabel,
            "xlim": metadata.xlim,
            "ylim": metadata.ylim,
            "num_lines": metadata.num_lines,
            "line_colors": metadata.line_colors,
            "legend_entries": metadata.legend_entries,
        }

    return result


@mcp.tool()
async def get_analysis_prompt(
    custom_additions: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> str:
    """Get the default figure analysis prompt.

    Returns the standard prompt used for LLM-based figure analysis,
    which emphasizes:
    1. Axes and scales (labels, units, ranges, scale type)
    2. Colors and meanings (what each color represents)
    3. Data interpretation (plot type, trends, patterns)
    4. Legend and labels (categories, conditions)
    5. Quality assessment (clarity, suggestions)

    Args:
        custom_additions: Optional text to append to the default prompt

    Returns:
        The analysis prompt string
    """
    if ctx:
        ctx.info("Getting default analysis prompt")

    prompt = DEFAULT_ANALYSIS_PROMPT

    if custom_additions:
        prompt = f"{prompt}\n\nAdditional instructions:\n{custom_additions}"

    return prompt


# Define resources at module level
@mcp.resource("matlab://scripts/{script_name}")
async def get_script_content(script_name: str) -> str:
    """Get the content of a MATLAB script."""
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}")

    return script_path.read_text()


def run_server():
    """Run the MCP server."""
    server = MatlabServer.get_instance()

    def signal_handler(signum, frame):
        print("\nReceived signal to shutdown...")
        server.close()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("MATLAB MCP Server is starting...")

    # Validate Python/MATLAB version compatibility (warn but do not block)
    # Use stderr to avoid corrupting MCP stdio transport
    try:
        env_status = validate_environment()
        if not env_status["compatible"]:
            print(
                "WARNING: Python/MATLAB version compatibility issue detected.",
                file=sys.stderr,
            )
            for rec in env_status["recommendations"]:
                print(f"  {rec}", file=sys.stderr)
        elif debug_mode:
            for rec in env_status["recommendations"]:
                logging.debug(rec)
    except Exception as _compat_err:
        logging.debug("Could not validate MATLAB compatibility: %s", _compat_err)

    try:
        # Initialize server first
        asyncio.run(server.initialize())
        print("MATLAB engine initialized successfully")

        # Configure MCP logging to suppress request processing messages
        mcp_logger = logging.getLogger("mcp")
        mcp_logger.setLevel(logging.WARNING)

        print("Server is running and ready to accept connections")
        print("Use the tools with Cline or other MCP-compatible clients")
        print("Press Ctrl+C to shutdown gracefully")

        # Run the MCP server with stdio transport
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt...")
        server.close()
    except Exception as e:
        print(f"\nError: {str(e)}")
        server.close()
        raise  # Re-raise to show full error trace


def main():
    """Entry point for the MATLAB MCP server."""
    # Initialize singleton instance
    MatlabServer.get_instance()
    run_server()


if __name__ == "__main__":
    main()
