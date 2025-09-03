"""MATLAB MCP Server implementation."""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp.server.fastmcp import Context, FastMCP, Image
from pydantic import Field

from .engine import MatlabEngine
from .models import PerformanceConfig
from .utils.section_parser import get_section_info

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
        # Initialize with performance config
        config = PerformanceConfig()
        self.engine = MatlabEngine(config)
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
    script: str = Field(description="MATLAB code or script to execute"),
    is_file: bool = Field(
        description="Whether script is a file path. If True, script is read from file, make sure to"
        " use the full path. Also, if True, it is RECOMMENDED to use the 'get_script_sections' tool"
        " to get the section ranges first, and then use the 'execute_section' tool to execute"
        " the file section by section.",
        default=False,
    ),
    workspace_vars: Optional[Dict[str, Any]] = None,
    capture_plots: bool = Field(
        description="Whether to capture generated plots", default=True
    ),
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
        ctx=ctx,
    )

    # Convert FigureData to MCP Image objects
    figures = [Image(data=fig.data, format=fig.format.value) for fig in result.figures]

    response = {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures,
        "execution_time_seconds": result.execution_time_seconds,
    }

    # Add memory status if available
    if result.memory_status:
        response["memory_status"] = {
            "total_size_mb": result.memory_status.total_size_mb,
            "variable_count": result.memory_status.variable_count,
            "largest_variable": result.memory_status.largest_variable,
            "largest_variable_size_mb": result.memory_status.largest_variable_size_mb,
            "near_limit": result.memory_status.near_limit,
        }

    # Add enhanced error information if available
    if result.enhanced_error:
        response["enhanced_error"] = {
            "error_type": result.enhanced_error.error_type,
            "line_number": result.enhanced_error.line_number,
            "context_lines": result.enhanced_error.context_lines,
            "stack_trace": result.enhanced_error.stack_trace,
        }

    return response


@mcp.tool()
async def execute_section(
    script_name: str = Field(
        description="Name of the script file, the script name should include the full path"
    ),
    section_range: Tuple[int, int] = Field(
        description="Start and end line numbers for the section"
    ),
    maintain_workspace: bool = Field(
        description="Keep workspace between sections", default=True
    ),
    capture_plots: bool = Field(
        description="Whether to capture generated plots", default=True
    ),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a specific section of a MATLAB script.
    To use this tool, you should first the use the `get_script_sections` tool to get the section ranges.

    Returns a dictionary containing:
    - output: Section execution output
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name} not found")

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
    figures = [Image(data=fig.data, format=fig.format.value) for fig in result.figures]

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
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Fetching MATLAB workspace")

    return await server.engine.get_workspace()


@mcp.tool()
async def get_script_sections(
    script_name: str = Field(
        description="Name of the script file, the script name should include the full path"
    ),
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Get information about sections in a MATLAB script.

    Returns a list of dictionaries containing:
    - start_line: Section start line number
    - end_line: Section end line number
    - title: Section title if any
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}not found")

    if ctx:
        ctx.info(f"Getting sections for script: {script_name}")

    return get_section_info(script_path)


@mcp.tool()
async def create_matlab_script(
    script_name: str = Field(
        description="Name of the script (include the .m in the name)"
    ),
    code: str = Field(description="MATLAB code to save"),
    ctx: Optional[Context] = None,
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
async def get_memory_status(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Get current workspace memory usage information.

    Returns memory status including total usage, variable count, and largest variables.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Getting memory status")

    status = await server.engine.get_memory_status()

    return {
        "total_size_mb": status.total_size_mb,
        "variable_count": status.variable_count,
        "largest_variable": status.largest_variable,
        "largest_variable_size_mb": status.largest_variable_size_mb,
        "memory_limit_mb": status.memory_limit_mb,
        "near_limit": status.near_limit,
    }


@mcp.tool()
async def clear_large_variables(
    threshold_mb: float = Field(
        description="Size threshold in MB for variables to clear", default=100.0
    ),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Clear variables larger than specified threshold to free memory.

    Returns list of cleared variables and their sizes.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Clearing variables larger than {threshold_mb} MB")

    cleared_vars = await server.engine.clear_large_variables(threshold_mb)

    return {"cleared_variables": cleared_vars, "count": len(cleared_vars)}


@mcp.tool()
async def get_connection_status(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Get current MATLAB engine connection status.

    Returns connection information including uptime and activity.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Getting connection status")

    status = await server.engine.get_connection_status()

    return {
        "is_connected": status.is_connected,
        "connection_id": status.connection_id,
        "uptime_seconds": status.uptime_seconds,
        "last_activity": status.last_activity,
    }


@mcp.tool()
async def inspect_variable(
    var_name: str = Field(description="Name of variable to inspect"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a specific workspace variable.

    Returns variable details including size, type, and value preview.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Inspecting variable: {var_name}")

    return await server.engine.inspect_variable(var_name)


@mcp.tool()
async def get_variable_summary(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Get summary of all workspace variables sorted by memory usage.

    Returns list of all variables with their sizes and types.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Getting variable summary")

    return await server.engine.get_variable_summary()


@mcp.tool()
async def find_large_variables(
    threshold_mb: float = Field(description="Size threshold in MB", default=10.0),
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Find variables larger than specified threshold.

    Returns list of large variables with their information.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Finding variables larger than {threshold_mb} MB")

    return await server.engine.find_large_variables(threshold_mb)


@mcp.tool()
async def search_variables(
    pattern: str = Field(description="Search pattern (supports wildcards * and ?)"),
    ctx: Optional[Context] = None,
) -> List[Dict[str, Any]]:
    """Search for variables matching a pattern.

    Returns list of matching variables with their information.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Searching variables with pattern: {pattern}")

    return await server.engine.search_variables(pattern)


@mcp.tool()
async def watch_file(
    file_path: str = Field(description="Path to file to watch for changes"),
    ctx: Optional[Context] = None,
) -> str:
    """Start watching a file for changes (hot reloading).

    Returns confirmation message.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Starting to watch file: {file_path}")

    await server.engine.watch_file(file_path)

    return f"Now watching file for changes: {file_path}"


@mcp.tool()
async def unwatch_file(
    file_path: str = Field(description="Path to file to stop watching"),
    ctx: Optional[Context] = None,
) -> str:
    """Stop watching a file for changes.

    Returns confirmation message.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info(f"Stopping file watch: {file_path}")

    await server.engine.unwatch_file(file_path)

    return f"Stopped watching file: {file_path}"


@mcp.tool()
async def get_watched_files(ctx: Optional[Context] = None) -> List[str]:
    """Get list of files currently being watched for changes.

    Returns list of watched file paths.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Getting watched files list")

    return await server.engine.get_watched_files()


@mcp.tool()
async def check_watched_files(ctx: Optional[Context] = None) -> List[str]:
    """Check all watched files for changes.

    Returns list of files that have changed since last check.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Checking watched files for changes")

    return await server.engine.check_all_watched_files()


@mcp.tool()
async def cleanup_idle_connections(ctx: Optional[Context] = None) -> str:
    """Clean up idle MATLAB connections from the connection pool.

    Returns confirmation message.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if ctx:
        ctx.info("Cleaning up idle connections")

    await server.engine.cleanup_idle_connections()

    return "Idle connections cleaned up successfully"


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
