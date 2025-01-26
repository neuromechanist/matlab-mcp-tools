"""MATLAB engine wrapper for MCP Tool."""

import os
from pathlib import Path
import subprocess
import sys
from typing import Optional, Dict, Any, List
import matlab.engine
from mcp.server.fastmcp import Context

from .models import ExecutionResult


class MatlabEngine:
    """Wrapper for MATLAB engine with enhanced functionality."""
    
    def __init__(self):
        """Initialize MATLAB engine wrapper."""
        self.eng = None
        self.output_dir = Path("matlab_output")
        self.matlab_path = os.getenv('MATLAB_PATH', '/Applications/MATLAB_R2024a.app')
        
    async def initialize(self) -> None:
        """Initialize MATLAB engine if not already running."""
        if self.eng is not None:
            return
            
        try:
            self.eng = matlab.engine.start_matlab()
        except ImportError:
            # Try to install MATLAB engine if not found
            if not os.path.exists(self.matlab_path):
                raise RuntimeError(
                    f"MATLAB installation not found at {self.matlab_path}. "
                    "Please set MATLAB_PATH environment variable."
                )
            
            engine_setup = Path(self.matlab_path) / "extern/engines/python/setup.py"
            if not engine_setup.exists():
                raise RuntimeError(
                    f"MATLAB Python engine setup not found at {engine_setup}. "
                    "Please verify your MATLAB installation."
                )
            
            print(f"Installing MATLAB engine from {engine_setup}...", file=sys.stderr)
            try:
                subprocess.run(
                    [sys.executable, str(engine_setup), "install"],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print("MATLAB engine installed successfully.", file=sys.stderr)
                self.eng = matlab.engine.start_matlab()
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to install MATLAB engine: {e.stderr}\n"
                    "Please try installing manually."
                )
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        
        # Add current directory to MATLAB path
        self.eng.addpath(str(Path.cwd()))

    async def execute(
        self,
        script: str,
        is_file: bool = False,
        workspace_vars: Optional[Dict[str, Any]] = None,
        capture_plots: bool = True,
        ctx: Optional[Context] = None
    ) -> ExecutionResult:
        """Execute a MATLAB script or command.
        
        Args:
            script: MATLAB code or file path
            is_file: Whether script is a file path
            workspace_vars: Variables to inject into workspace
            capture_plots: Whether to capture generated plots
            ctx: MCP context for progress reporting
        
        Returns:
            ExecutionResult containing output, workspace state, and figures
        """
        await self.initialize()
        
        try:
            # Clear existing figures if capturing plots
            if capture_plots:
                self.eng.close('all', nargout=0)
            
            # Set workspace variables
            if workspace_vars:
                for name, value in workspace_vars.items():
                    if isinstance(value, (int, float)):
                        self.eng.workspace[name] = matlab.double([value])
                    elif isinstance(value, list):
                        if all(isinstance(x, (int, float)) for x in value):
                            self.eng.workspace[name] = matlab.double(value)
                        else:
                            self.eng.workspace[name] = value
                    else:
                        self.eng.workspace[name] = value

            # Execute script
            if is_file:
                script_path = Path(script)
                if not script_path.exists():
                    raise FileNotFoundError(f"Script not found: {script}")
                if ctx:
                    ctx.info(f"Executing MATLAB script: {script_path}")
                output = self.eng.run(str(script_path), nargout=0)
            else:
                if ctx:
                    ctx.info("Executing MATLAB command")
                output = self.eng.eval(script, nargout=0)

            # Capture figures if requested
            figures = []
            if capture_plots:
                figures = await self._capture_figures()
            
            # Get workspace state
            workspace = await self.get_workspace()

            return ExecutionResult(
                output=str(output) if output else "",
                workspace=workspace,
                figures=figures
            )
            
        except Exception as e:
            if ctx:
                ctx.error(f"MATLAB execution error: {str(e)}")
            return ExecutionResult(
                output="",
                error=str(e),
                workspace={},
                figures=[]
            )

    async def _capture_figures(self) -> List[bytes]:
        """Capture current MATLAB figures as PNG images.
        
        Returns:
            List of PNG image data for each figure
        """
        figures = []
        fig_handles = self.eng.eval('get(groot, "Children")', nargout=1)
        
        if fig_handles:
            for i, _ in enumerate(fig_handles):
                temp_file = self.output_dir / f"figure_{i}.png"
                self.eng.eval(f"saveas(figure({i+1}), '{temp_file}')", nargout=0)
                
                with open(temp_file, 'rb') as f:
                    figures.append(f.read())
                
                temp_file.unlink()  # Clean up temp file
                
        return figures

    async def get_workspace(self) -> Dict[str, Any]:
        """Get current MATLAB workspace variables.
        
        Returns:
            Dictionary of variable names and their values
        """
        workspace = {}
        var_names = self.eng.eval('who', nargout=1)
        
        for var in var_names:
            try:
                value = self.eng.workspace[var]
                if isinstance(value, matlab.double):
                    try:
                        # Get the size of the array
                        size = value.size
                        if len(size) == 2 and (size[0] == 1 or size[1] == 1):
                            # 1D array
                            workspace[var] = value._data.tolist()
                        else:
                            # 2D array
                            workspace[var] = [row.tolist() for row in value]
                    except Exception:
                        workspace[var] = str(value)
                else:
                    try:
                        workspace[var] = value._data.tolist()
                    except Exception:
                        workspace[var] = str(value)
            except Exception as e:
                workspace[var] = f"<Error reading variable: {str(e)}>"
                
        return workspace

    def cleanup(self) -> None:
        """Clean up MATLAB engine and resources."""
        if self.eng is not None:
            self.eng.quit()
            self.eng = None
