"""MATLAB engine wrapper for MCP Tool."""

import asyncio
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import matlab.engine
from mcp.server.fastmcp import Context

from .models import (
    ExecutionResult,
    FigureData,
    FigureFormat,
    MemoryStatus,
    PerformanceConfig,
)
from .utils.section_parser import extract_section


class MatlabEngine:
    """Wrapper for MATLAB engine with enhanced functionality."""

    def __init__(self, config: Optional[PerformanceConfig] = None):
        """Initialize MATLAB engine wrapper."""
        self.eng = None
        # Use .mcp directory in home for all outputs
        self.mcp_dir = Path.home() / ".mcp"
        self.output_dir = self.mcp_dir / "matlab" / "output"
        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.matlab_path = os.getenv("MATLAB_PATH", "/Applications/MATLAB_R2024b.app")

        # Performance and reliability configuration
        self.config = config or PerformanceConfig()
        self.connection_start_time = time.time()
        self.connection_id = str(uuid.uuid4())
        self.last_activity = time.time()

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
                    ) from None

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

    async def _execute_with_timeout(
        self, matlab_command: str, timeout_seconds: Optional[int] = None
    ) -> str:
        """Execute MATLAB command with timeout protection.

        Args:
            matlab_command: MATLAB command to execute
            timeout_seconds: Timeout in seconds, uses config default if None

        Returns:
            Command output

        Raises:
            TimeoutError: If command exceeds timeout
            matlab.engine.MatlabExecutionError: If MATLAB execution fails
        """
        if self.eng is None:
            raise RuntimeError("MATLAB engine not initialized")

        timeout = timeout_seconds or self.config.execution_timeout_seconds

        if not timeout:
            # No timeout configured, execute normally
            return self.eng.eval(matlab_command, nargout=0)

        # Create a result container and exception container
        result = {"output": None, "error": None, "completed": False}

        def execute_command():
            """Execute the MATLAB command in a separate thread."""
            try:
                output = self.eng.eval(matlab_command, nargout=0)
                result["output"] = output
                result["completed"] = True
            except Exception as e:
                result["error"] = e
                result["completed"] = True

        # Start execution in a separate thread
        execution_thread = threading.Thread(target=execute_command, daemon=True)
        execution_thread.start()

        # Wait for completion or timeout
        start_time = time.time()
        while not result["completed"] and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)  # Check every 100ms

        if not result["completed"]:
            # Timeout occurred - try to interrupt MATLAB
            try:
                # Send Ctrl+C to MATLAB process
                self.eng.eval("dbquit all", nargout=0)
            except Exception:
                pass  # May fail if MATLAB is hung

            raise TimeoutError(
                f"MATLAB execution timed out after {timeout} seconds. "
                "Command may be stuck in infinite loop."
            )

        if result["error"]:
            raise result["error"]

        return result["output"]

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

        # Track execution time
        start_time = time.time()

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

            # Check memory limit before execution
            if self.config.memory_limit_mb:
                memory_exceeded = await self.check_memory_limit()
                if memory_exceeded:
                    if ctx:
                        ctx.warning("Memory limit exceeded, clearing large variables")
                    cleared = await self.clear_large_variables()
                    print(
                        f"Cleared {len(cleared)} large variables to free memory",
                        file=sys.stderr,
                    )

            # Execute script with timeout protection
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
                # Use timeout-protected execution
                output = await self._execute_with_timeout(script)

            # Update last activity time
            self.last_activity = time.time()
            execution_time = self.last_activity - start_time

            # Capture figures if requested
            figures = []
            if capture_plots:
                figures = await self._capture_figures()

            # Get workspace state and memory status
            workspace = await self.get_workspace()
            memory_status = await self.get_memory_status()

            return ExecutionResult(
                output=str(output) if output else "",
                workspace=workspace,
                figures=figures,
                execution_time_seconds=execution_time,
                memory_status=memory_status,
            )

        except TimeoutError as e:
            execution_time = time.time() - start_time
            error_msg = f"Execution Timeout: {str(e)}"
            print(error_msg, file=sys.stderr)
            if ctx:
                ctx.error(error_msg)

            # Try to get memory status even after timeout
            try:
                memory_status = await self.get_memory_status()
            except Exception:
                memory_status = None

            return ExecutionResult(
                output="",
                error=error_msg,
                workspace={},
                figures=[],
                execution_time_seconds=execution_time,
                memory_status=memory_status,
            )
        except matlab.engine.MatlabExecutionError as e:
            execution_time = time.time() - start_time
            error_msg = f"MATLAB Error: {str(e)}"
            print(error_msg, file=sys.stderr)
            if ctx:
                ctx.error(error_msg)

            # Try to get memory status even after error
            try:
                memory_status = await self.get_memory_status()
            except Exception:
                memory_status = None

            return ExecutionResult(
                output="",
                error=error_msg,
                workspace={},
                figures=[],
                execution_time_seconds=execution_time,
                memory_status=memory_status,
            )
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Python Error: {str(e)}"
            print(error_msg, file=sys.stderr)
            if ctx:
                ctx.error(error_msg)

            # Try to get memory status even after error
            try:
                memory_status = await self.get_memory_status()
            except Exception:
                memory_status = None

            return ExecutionResult(
                output="",
                error=error_msg,
                workspace={},
                figures=[],
                execution_time_seconds=execution_time,
                memory_status=memory_status,
            )

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
        """Get current MATLAB workspace variables.

        Returns:
            Dictionary of variable names and their values
        """
        workspace = {}
        var_names = self.eng.eval("who", nargout=1)

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

    async def get_memory_status(self) -> MemoryStatus:
        """Get current workspace memory status.

        Returns:
            MemoryStatus containing memory usage information
        """
        if self.eng is None:
            return MemoryStatus(
                total_size_mb=0.0,
                variable_count=0,
                largest_variable=None,
                largest_variable_size_mb=0.0,
                memory_limit_mb=self.config.memory_limit_mb,
                near_limit=False,
            )

        try:
            # Get workspace information using MATLAB's whos command
            workspace_info = self.eng.eval("whos", nargout=1)

            total_bytes = 0
            variable_count = 0
            largest_var_name = None
            largest_var_size = 0

            if workspace_info:
                for var_info in workspace_info:
                    var_size = var_info["bytes"]
                    total_bytes += var_size
                    variable_count += 1

                    if var_size > largest_var_size:
                        largest_var_size = var_size
                        largest_var_name = var_info["name"]

            total_size_mb = total_bytes / (1024 * 1024)
            largest_size_mb = largest_var_size / (1024 * 1024)

            # Check if near memory limit (80% threshold)
            near_limit = False
            if self.config.memory_limit_mb:
                near_limit = total_size_mb > (self.config.memory_limit_mb * 0.8)

            return MemoryStatus(
                total_size_mb=total_size_mb,
                variable_count=variable_count,
                largest_variable=largest_var_name,
                largest_variable_size_mb=largest_size_mb,
                memory_limit_mb=self.config.memory_limit_mb,
                near_limit=near_limit,
            )

        except Exception as e:
            print(f"Error getting memory status: {e}", file=sys.stderr)
            return MemoryStatus(
                total_size_mb=0.0,
                variable_count=0,
                largest_variable=None,
                largest_variable_size_mb=0.0,
                memory_limit_mb=self.config.memory_limit_mb,
                near_limit=False,
            )

    async def check_memory_limit(self) -> bool:
        """Check if workspace memory usage exceeds configured limit.

        Returns:
            True if memory limit is exceeded, False otherwise
        """
        if not self.config.memory_limit_mb:
            return False

        memory_status = await self.get_memory_status()
        return memory_status.total_size_mb > self.config.memory_limit_mb

    async def clear_large_variables(self, threshold_mb: float = 100.0) -> List[str]:
        """Clear variables larger than specified threshold.

        Args:
            threshold_mb: Size threshold in MB

        Returns:
            List of cleared variable names
        """
        if self.eng is None:
            return []

        try:
            cleared_vars = []
            workspace_info = self.eng.eval("whos", nargout=1)

            if workspace_info:
                for var_info in workspace_info:
                    var_size_mb = var_info["bytes"] / (1024 * 1024)
                    if var_size_mb > threshold_mb:
                        var_name = var_info["name"]
                        self.eng.eval(f"clear {var_name}", nargout=0)
                        cleared_vars.append(var_name)
                        print(
                            f"Cleared variable '{var_name}' ({var_size_mb:.1f} MB)",
                            file=sys.stderr,
                        )

            return cleared_vars

        except Exception as e:
            print(f"Error clearing large variables: {e}", file=sys.stderr)
            return []

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
