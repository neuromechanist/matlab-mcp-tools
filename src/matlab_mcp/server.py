"""MATLAB MCP Server implementation."""

from pathlib import Path
from typing import Dict, Any, Optional

from mcp.server.fastmcp import FastMCP, Image, Context

from .engine import MatlabEngine


class MatlabServer:
    """MCP server providing MATLAB integration."""
    
    def __init__(self):
        """Initialize the MATLAB MCP server."""
        self.mcp = FastMCP(
            "MATLAB",
            dependencies=[
                "mcp[cli]",
                "matlabengine"
            ]
        )
        self.engine = MatlabEngine()
        self.scripts_dir = Path("matlab_scripts")
        self.scripts_dir.mkdir(exist_ok=True)
        
        self._setup_tools()
        self._setup_resources()
    
    def _setup_tools(self):
        """Set up MCP tools for MATLAB operations."""
        
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
            
            # Convert raw bytes to MCP Image objects
            figures = [
                Image(data=fig_data, format='png')
                for fig_data in result.figures
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

    def run(self):
        """Run the MCP server."""
        self.mcp.run()


def main():
    """Entry point for the MATLAB MCP server."""
    server = MatlabServer()
    server.run()


if __name__ == "__main__":
    main()
