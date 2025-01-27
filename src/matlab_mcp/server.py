"""MATLAB MCP Server implementation."""

import logging
import os
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List

from mcp.server.fastmcp import FastMCP, Image, Context

from .engine import MatlabEngine
from .utils.section_parser import get_section_info


# Configure logging to avoid duplicate messages
class DuplicateFilter(logging.Filter):
    """Filter out duplicate log messages."""
    def __init__(self):
        super().__init__()
        self.last_log = None
        
    def filter(self, record):
        current_log = record.getMessage()
        if current_log == self.last_log:
            return False
        self.last_log = current_log
        return True


logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(message)s'))
handler.addFilter(DuplicateFilter())
logger.handlers = [handler]  # Replace any existing handlers


class MatlabServer:
    """MCP server providing MATLAB integration."""
    
    def __init__(self):
        """Initialize the MATLAB MCP server."""
        self.mcp = FastMCP(
            "MATLAB",
            dependencies=[
                "mcp[cli]",
                "matlabengine"
            ],
            debug=False,  # Disable debug logging
            capabilities={
                "tools": {
                    "listChanged": True
                },
                "resources": {
                    "listChanged": True,
                    "subscribe": True
                }
            }
        )
        self.engine = MatlabEngine()
        # Use .mcp directory in home for all files
        self.mcp_dir = Path.home() / ".mcp"
        self.scripts_dir = self.mcp_dir / "matlab" / "scripts"
        self.scripts_dir.parent.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(exist_ok=True)
        
        self._setup_tools()
        self._setup_resources()
    
    def _setup_tools(self):
        """Set up MCP tools for MATLAB operations."""

        @self.mcp.tool()
        async def get_script_sections(
            script_name: str,
            ctx: Context = None
        ) -> List[dict]:
            """Get information about sections in a MATLAB script.
            
            Args:
                script_name: Name of the script (without .m extension)
                ctx: MCP context for progress reporting
            
            Returns:
                List of dictionaries containing section information
            """
            script_path = self.scripts_dir / f"{script_name}.m"
            if not script_path.exists():
                raise FileNotFoundError(f"Script {script_name}.m not found")
                
            if ctx:
                ctx.info(f"Getting sections for script: {script_name}")
                
            return get_section_info(script_path)

        @self.mcp.tool()
        async def execute_script_section(
            script_name: str,
            section_range: tuple[int, int],
            maintain_workspace: bool = True,
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Execute a specific section of a MATLAB script.
            
            Args:
                script_name: Name of the script (without .m extension)
                section_range: Tuple of (start_line, end_line) for the section
                maintain_workspace: Whether to maintain workspace between sections
                ctx: MCP context for progress reporting
            
            Returns:
                Dictionary containing execution results
            """
            script_path = self.scripts_dir / f"{script_name}.m"
            if not script_path.exists():
                raise FileNotFoundError(f"Script {script_name}.m not found")
                
            result = await self.engine.execute_section(
                str(script_path),
                section_range,
                maintain_workspace=maintain_workspace,
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
        
        @self.mcp.tool()
        async def execute_script(
            script: str,
            is_file: bool = False,
            workspace_vars: Optional[Dict[str, Any]] = None,
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Execute a MATLAB script or command.
            
            Args:
                script: MATLAB code or file path
                is_file: Whether script is a file path
                workspace_vars: Variables to inject into workspace
                ctx: MCP context for progress reporting
            
            Returns:
                Dictionary containing execution results
            """
            result = await self.engine.execute(
                script,
                is_file=is_file,
                workspace_vars=workspace_vars,
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

        @self.mcp.tool()
        async def create_matlab_script(
            script_name: str,
            code: str,
            ctx: Context = None
        ) -> str:
            """Create a new MATLAB script file.
            
            Args:
                script_name: Name of the script (without .m extension)
                code: MATLAB code to save
                ctx: MCP context for progress reporting
            
            Returns:
                Path to the created script
            """
            if not script_name.isidentifier():
                raise ValueError("Script name must be a valid MATLAB identifier")
            
            script_path = self.scripts_dir / f"{script_name}.m"
            script_path.write_text(code)
            
            if ctx:
                ctx.info(f"Created MATLAB script: {script_path}")
            
            return str(script_path)

        @self.mcp.tool()
        async def get_workspace(
            ctx: Context = None
        ) -> Dict[str, Any]:
            """Get current MATLAB workspace variables.
            
            Args:
                ctx: MCP context for progress reporting
            
            Returns:
                Dictionary of workspace variables
            """
            if ctx:
                ctx.info("Fetching MATLAB workspace")
            return await self.engine.get_workspace()

    def _setup_resources(self):
        """Set up MCP resources for MATLAB scripts."""
        
        @self.mcp.resource("matlab://scripts/{script_name}")
        async def get_script_content(script_name: str) -> str:
            """Get the content of a MATLAB script.
            
            Args:
                script_name: Name of the script (without .m extension)
            
            Returns:
                Content of the MATLAB script
            """
            script_path = self.scripts_dir / f"{script_name}.m"
            if not script_path.exists():
                raise FileNotFoundError(f"Script {script_name}.m not found")
            
            return script_path.read_text()

    def close(self):
        """Clean up server resources."""
        print("\nShutting down MATLAB MCP Server...")
        try:
            if self.engine is not None:
                self.engine.close()
                self.engine = None
            # Force kill any remaining MATLAB processes
            os.system("pkill -f MATLAB")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")
        finally:
            os._exit(0)  # Force immediate exit, cannot be caught by other threads

    def run(self):
        """Run the MCP server."""
        def signal_handler(signum, frame):
            print("\nReceived signal to shutdown...")
            self.close()  # This will call os._exit(0)
            
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        print("MATLAB MCP Server is running...")
        print("Available tools:")
        print("  - execute_script: Execute MATLAB code or script file")
        print("  - execute_script_section: Execute specific sections of a MATLAB script")
        print("  - get_script_sections: Get information about script sections")
        print("  - create_matlab_script: Create a new MATLAB script")
        print("  - get_workspace: Get current MATLAB workspace variables")
        print("\nUse the tools with Cline or other MCP-compatible clients.")
        print("Press Ctrl+C to shutdown gracefully")
        
        try:
            # Let FastMCP handle its own event loop
            self.mcp.run(transport='stdio')
        except KeyboardInterrupt:
            print("\nReceived keyboard interrupt...")
            self.close()  # This will call os._exit(0)
        except Exception as e:
            print(f"\nError: {str(e)}")
            self.close()  # This will call os._exit(0)


def main():
    """Entry point for the MATLAB MCP server."""
    server = MatlabServer()
    server.run()


if __name__ == "__main__":
    main()
