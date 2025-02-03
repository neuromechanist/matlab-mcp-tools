"""MATLAB MCP Server implementation."""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from pydantic import Field

from mcp.server.fastmcp import FastMCP, Image, Context

from .engine import MatlabEngine
from .utils.section_parser import get_section_info


# Configure logging based on debug mode
debug_mode = os.getenv('MATLAB_MCP_DEBUG', '').lower() in ('true', '1', 'yes')

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG if debug_mode else logging.WARNING,
    format='%(message)s',
    force=True
)

# Configure MCP loggers to be completely silent unless in debug mode
for logger_name in ['mcp', 'mcp.server', 'mcp.client', 'mcp.shared']:
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
    instructions="MATLAB MCP server providing access to MATLAB engine functionality."
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
    script: str = Field(description="MATLAB code or script to execute"),
    is_file: bool = Field(description="Whether script is a file path", default=False),
    workspace_vars: Optional[Dict[str, Any]] = Field(
        description="Variables to inject into workspace",
        default=None
    ),
    capture_plots: bool = Field(
        description="Whether to capture generated plots",
        default=True
    ),
    ctx: Optional[Context] = None
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
        ctx=ctx
    )

    # Convert FigureData to MCP Image objects
    figures = [
        Image(data=fig.data, format=fig.format.value)
        for fig in result.figures
    ]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures
    }


@mcp.tool()
async def execute_section(
    script_name: str = Field(description="Name of the script file"),
    section_range: Tuple[int, int] = Field(
        description="Start and end line numbers for the section"
    ),
    maintain_workspace: bool = Field(
        description="Keep workspace between sections",
        default=True
    ),
    capture_plots: bool = Field(
        description="Whether to capture generated plots",
        default=True
    ),
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
    """Execute a specific section of a MATLAB script.

    Returns a dictionary containing:
    - output: Section execution output
    - error: Error message if any
    - workspace: Current workspace variables
    - figures: List of generated plots
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}.m"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}.m not found")

    if ctx:
        ctx.info(f"Executing section (lines {section_range[0]}-{section_range[1]})")

    result = await server.engine.execute_section(
        str(script_path),
        section_range,
        maintain_workspace=maintain_workspace,
        capture_plots=capture_plots,
        ctx=ctx
    )

    # Convert FigureData to MCP Image objects
    figures = [
        Image(data=fig.data, format=fig.format.value)
        for fig in result.figures
    ]

    return {
        "output": result.output,
        "error": result.error,
        "workspace": result.workspace,
        "figures": figures
    }


@mcp.tool()
async def get_workspace(
    ctx: Optional[Context] = None
) -> Dict[str, Any]:
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
    script_name: str = Field(description="Name of the script file"),
    ctx: Optional[Context] = None
) -> List[Dict[str, Any]]:
    """Get information about sections in a MATLAB script.

    Returns a list of dictionaries containing:
    - start_line: Section start line number
    - end_line: Section end line number
    - title: Section title if any
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}.m"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}.m not found")

    if ctx:
        ctx.info(f"Getting sections for script: {script_name}")

    return get_section_info(script_path)


@mcp.tool()
async def create_matlab_script(
    script_name: str = Field(description="Name of the script (without .m extension)"),
    code: str = Field(description="MATLAB code to save"),
    ctx: Optional[Context] = None
) -> str:
    """Create a new MATLAB script file.

    Returns the path to the created script file.
    """
    server = MatlabServer.get_instance()
    await server.initialize()

    if not script_name.isidentifier():
        raise ValueError("Script name must be a valid MATLAB identifier")

    script_path = server.scripts_dir / f"{script_name}.m"
    script_path.write_text(code)

    if ctx:
        ctx.info(f"Created MATLAB script: {script_path}")

    return str(script_path)


# Define resources at module level
@mcp.resource("matlab://scripts/{script_name}")
async def get_script_content(script_name: str) -> str:
    """Get the content of a MATLAB script."""
    server = MatlabServer.get_instance()
    await server.initialize()

    script_path = server.scripts_dir / f"{script_name}.m"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}.m not found")

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
        mcp_logger = logging.getLogger('mcp')
        mcp_logger.setLevel(logging.WARNING)

        print("Server is running and ready to accept connections")
        print("Use the tools with Cline or other MCP-compatible clients")
        print("Press Ctrl+C to shutdown gracefully")

        # Run the MCP server with stdio transport
        mcp.run(transport='stdio')
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
