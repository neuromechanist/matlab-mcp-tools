"""MATLAB engine wrapper for MCP Tool."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import matlab.engine
from mcp.server.fastmcp import Context

from .models import ExecutionResult, FigureData, FigureFormat
from .utils.section_parser import extract_section


class MatlabEngine:
    """Wrapper for MATLAB engine with enhanced functionality."""

    def __init__(self):
        """Initialize MATLAB engine wrapper."""
        self.eng = None
        # Use .mcp directory in home for all outputs
        self.mcp_dir = Path.home() / ".mcp"
        self.output_dir = self.mcp_dir / "matlab" / "output"
        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.matlab_path = os.getenv("MATLAB_PATH", "/Applications/MATLAB_R2024b.app")

    async def initialize(self) -> None:
        """Initialize MATLAB engine if not already running."""
        if self.eng is not None:
            return

        try:
            print("\n=== MATLAB Engine Initialization ===", file=sys.stderr)
            print(f"MATLAB_PATH: {self.matlab_path}", file=sys.stderr)
            print(f"Python executable: {sys.executable}", file=sys.stderr)
            print(f"matlab.engine path: {matlab.engine.__file__}", file=sys.stderr)
            print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
            print(f"PYTHONPATH: {os.getenv('PYTHONPATH', 'Not set')}", file=sys.stderr)

            # Verify MATLAB installation
            if not os.path.exists(self.matlab_path):
                raise RuntimeError(
                    f"MATLAB installation not found at {self.matlab_path}. "
                    "Please verify MATLAB_PATH environment variable."
                )

            # Try to find all available MATLAB sessions
            try:
                sessions = matlab.engine.find_matlab()
                print(f"Available MATLAB sessions: {sessions}", file=sys.stderr)
            except Exception as e:
                print(f"Error finding MATLAB sessions: {e}", file=sys.stderr)
                sessions = []

            # Try to connect to existing session or start new one
            try:
                if sessions:
                    print(
                        "\nFound existing MATLAB sessions, attempting to connect...",
                        file=sys.stderr,
                    )
                    self.eng = matlab.engine.connect_matlab(sessions[0])
                else:
                    print(
                        "\nNo existing sessions found, starting new MATLAB session...",
                        file=sys.stderr,
                    )
                    self.eng = matlab.engine.start_matlab()

                if self.eng is None:
                    raise RuntimeError("MATLAB engine failed to start (returned None)")

                # Test basic MATLAB functionality
                ver = self.eng.version()
                print(f"Connected to MATLAB version: {ver}", file=sys.stderr)

                # Add current directory to MATLAB path
                cwd = str(Path.cwd())
                print(
                    f"Adding current directory to MATLAB path: {cwd}", file=sys.stderr
                )
                self.eng.addpath(cwd, nargout=0)

                print("MATLAB engine initialized successfully", file=sys.stderr)
                return

            except Exception as e:
                print(f"Error starting MATLAB engine: {e}", file=sys.stderr)
                # Try to install MATLAB engine if not found
                engine_setup = Path(self.matlab_path) / "extern/engines/python/setup.py"
                if not engine_setup.exists():
                    raise RuntimeError(
                        f"MATLAB Python engine setup not found at {engine_setup}. "
                        "Please verify your MATLAB installation."
                    ) from e

                print(
                    f"Attempting to install MATLAB engine from {engine_setup}...",
                    file=sys.stderr,
                )
                try:
                    result = subprocess.run(
                        [sys.executable, str(engine_setup), "install"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    print("MATLAB engine installed successfully.", file=sys.stderr)
                    print(result.stdout, file=sys.stderr)

                    # Try starting engine again after installation
                    self.eng = matlab.engine.start_matlab()
                    if self.eng is None:
                        raise RuntimeError(
                            "MATLAB engine failed to start after installation"
                        )

                    ver = self.eng.version()
                    print(f"Connected to MATLAB version: {ver}", file=sys.stderr)
                    print(
                        "MATLAB engine initialized successfully after installation",
                        file=sys.stderr,
                    )
                except subprocess.CalledProcessError as e:
                    raise RuntimeError(
                        f"Failed to install MATLAB engine:\n"
                        f"stdout: {e.stdout}\n"
                        f"stderr: {e.stderr}\n"
                        "Please try installing manually."
                    ) from e
        except (ImportError, RuntimeError) as e:
            print(f"Error starting MATLAB engine: {str(e)}", file=sys.stderr)
            # Try to install MATLAB engine if not found
            if not os.path.exists(self.matlab_path):
                raise RuntimeError(
                    f"MATLAB installation not found at {self.matlab_path}. "
                    "Please set MATLAB_PATH environment variable."
                ) from e

            engine_setup = Path(self.matlab_path) / "extern/engines/python/setup.py"
            if not engine_setup.exists():
                raise RuntimeError(
                    f"MATLAB Python engine setup not found at {engine_setup}. "
                    "Please verify your MATLAB installation."
                ) from e

            print(f"Installing MATLAB engine from {engine_setup}...", file=sys.stderr)
            try:
                subprocess.run(
                    [sys.executable, str(engine_setup), "install"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("MATLAB engine installed successfully.", file=sys.stderr)
                self.eng = matlab.engine.start_matlab()
                if self.eng is None:
                    raise RuntimeError(
                        "MATLAB engine failed to start after installation"
                    )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to install MATLAB engine: {e.stderr}\n"
                    "Please try installing manually."
                ) from e

        # Create output directory
        self.output_dir.mkdir(exist_ok=True)

        # Add current directory to MATLAB path
        if self.eng is not None:
            self.eng.addpath(str(Path.cwd()))
        else:
            raise RuntimeError("MATLAB engine is still None after initialization")

    async def execute(
        self,
        script: str,
        is_file: bool = False,
        workspace_vars: Optional[Dict[str, Any]] = None,
        capture_plots: bool = True,
        ctx: Optional[Context] = None,
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
                self.eng.close("all", nargout=0)

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
                    print(f"Executing MATLAB command: {script}", file=sys.stderr)
                # Don't pass stdout/stderr to eval since we're not in a terminal
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
                figures=figures,
            )

        except matlab.engine.MatlabExecutionError as e:
            error_msg = f"MATLAB Error: {str(e)}"
            print(error_msg, file=sys.stderr)
            if ctx:
                ctx.error(error_msg)
            return ExecutionResult(output="", error=error_msg, workspace={}, figures=[])
        except Exception as e:
            error_msg = f"Python Error: {str(e)}"
            print(error_msg, file=sys.stderr)
            if ctx:
                ctx.error(error_msg)
            return ExecutionResult(output="", error=error_msg, workspace={}, figures=[])

    async def cleanup_figures(self) -> None:
        """Clean up MATLAB figures and temporary files."""
        if self.eng is not None:
            try:
                # Close all figures
                self.eng.eval("close all", nargout=0)
                # Clear temporary files
                for ext in ["png", "svg"]:
                    for file in self.output_dir.glob(f"figure_*.{ext}"):
                        try:
                            file.unlink()
                        except Exception as e:
                            print(f"Error cleaning up {file}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error during figure cleanup: {e}", file=sys.stderr)

    async def _capture_figures(self) -> List[FigureData]:
        """Capture current MATLAB figures in both PNG and SVG formats with proper cleanup.

        Returns:
            List of FigureData containing both PNG and SVG versions of each figure
        """
        try:
            figures = []
            fig_handles = self.eng.eval('get(groot, "Children")', nargout=1)

            if fig_handles:
                for i, _ in enumerate(fig_handles):
                    figure_data = []

                    # Save as PNG
                    png_file = self.output_dir / f"figure_{i}.png"
                    self.eng.eval(f"saveas(figure({i + 1}), '{png_file}')", nargout=0)
                    with open(png_file, "rb") as f:
                        figure_data.append(
                            FigureData(data=f.read(), format=FigureFormat.PNG)
                        )

                    # Save as SVG
                    svg_file = self.output_dir / f"figure_{i}.svg"
                    self.eng.eval(
                        f"set(figure({i + 1}), 'Renderer', 'painters'); "
                        f"saveas(figure({i + 1}), '{svg_file}', 'svg')",
                        nargout=0,
                    )
                    with open(svg_file, "rb") as f:
                        figure_data.append(
                            FigureData(data=f.read(), format=FigureFormat.SVG)
                        )

                    figures.extend(figure_data)

            return figures
        finally:
            # Always clean up, even if an error occurred
            await self.cleanup_figures()

    async def get_workspace(self) -> Dict[str, Any]:
        """Get current MATLAB workspace variables with smart summarization.

        For large arrays, returns metadata and preview instead of full data
        to dramatically reduce token usage.

        Returns:
            Dictionary of variable names and their optimized representations
        """
        workspace = {}
        var_names = self.eng.eval("who", nargout=1)

        # Size thresholds for different handling strategies
        SMALL_THRESHOLD = 100  # Elements: return full data
        MEDIUM_THRESHOLD = 10000  # Elements: return sample + stats

        for var in var_names:
            try:
                value = self.eng.workspace[var]

                if isinstance(value, matlab.double):
                    try:
                        # Get array dimensions and total elements
                        size = value.size
                        total_elements = 1
                        for dim in size:
                            total_elements *= dim

                        # Smart classification based on size
                        if total_elements <= SMALL_THRESHOLD:
                            # Small arrays: return full data (current behavior)
                            if len(size) == 2 and (size[0] == 1 or size[1] == 1):
                                workspace[var] = value._data.tolist()
                            else:
                                workspace[var] = [row.tolist() for row in value]

                        elif total_elements <= MEDIUM_THRESHOLD:
                            # Medium arrays: return summary with statistics
                            workspace[var] = {
                                "_mcp_type": "medium_array",
                                "dimensions": list(size),
                                "total_elements": total_elements,
                                "data_type": "double",
                                "statistics": {
                                    "min": float(
                                        self.eng.eval(f"min({var}(:))", nargout=1)
                                    ),
                                    "max": float(
                                        self.eng.eval(f"max({var}(:))", nargout=1)
                                    ),
                                    "mean": float(
                                        self.eng.eval(f"mean({var}(:))", nargout=1)
                                    ),
                                },
                                "sample_data": [
                                    float(x)
                                    for x in self.eng.eval(
                                        f"{var}(1:min(5,numel({var})))", nargout=1
                                    )._data
                                ],
                                "memory_usage_mb": round(
                                    total_elements * 8 / (1024 * 1024), 2
                                ),
                            }

                        else:
                            # Large arrays: return metadata and minimal preview only
                            workspace[var] = {
                                "_mcp_type": "large_array",
                                "dimensions": list(size),
                                "total_elements": total_elements,
                                "data_type": "double",
                                "statistics": {
                                    "min": float(
                                        self.eng.eval(f"min({var}(:))", nargout=1)
                                    ),
                                    "max": float(
                                        self.eng.eval(f"max({var}(:))", nargout=1)
                                    ),
                                    "mean": float(
                                        self.eng.eval(f"mean({var}(:))", nargout=1)
                                    ),
                                },
                                "sample_data": [
                                    float(x)
                                    for x in self.eng.eval(
                                        f"{var}(1:min(3,numel({var})))", nargout=1
                                    )._data
                                ],
                                "memory_usage_mb": round(
                                    total_elements * 8 / (1024 * 1024), 2
                                ),
                                "compression_note": f"Array too large ({total_elements:,} elements) - showing summary only",
                            }

                    except Exception as e:
                        workspace[var] = f"<Error processing array: {str(e)}>"

                else:
                    # Handle non-double types - use original behavior for now
                    try:
                        workspace[var] = value._data.tolist()
                    except Exception:
                        workspace[var] = (
                            str(value)[:200] + "..."
                            if len(str(value)) > 200
                            else str(value)
                        )

            except Exception as e:
                workspace[var] = f"<Error reading variable: {str(e)}>"

        return workspace

    async def execute_section(
        self,
        file_path: str,
        section_range: tuple[int, int],
        maintain_workspace: bool = True,
        capture_plots: bool = True,
        ctx: Optional[Context] = None,
    ) -> ExecutionResult:
        """Execute a specific section of a MATLAB script.

        Args:
            file_path: Path to the MATLAB script
            section_range: Tuple of (start_line, end_line) for the section
            maintain_workspace: Whether to maintain workspace between sections
            capture_plots: Whether to capture generated plots
            ctx: MCP context for progress reporting

        Returns:
            ExecutionResult containing output, workspace state, and figures
        """
        script_path = Path(file_path)
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {file_path}")

        # Extract the section code
        section_code = extract_section(
            script_path, section_range[0], section_range[1], maintain_workspace
        )

        if ctx:
            ctx.info(f"Executing section (lines {section_range[0]}-{section_range[1]})")

        # Execute the section
        return await self.execute(
            section_code, is_file=False, capture_plots=capture_plots, ctx=ctx
        )

    def close(self) -> None:
        """Clean up MATLAB engine and resources."""
        if self.eng is not None:
            try:
                # Clean up figures first
                self.eng.eval("close all", nargout=0)
                # Then quit the engine
                self.eng.quit()
            except Exception as e:
                print(f"Error during engine cleanup: {e}", file=sys.stderr)
            finally:
                self.eng = None
