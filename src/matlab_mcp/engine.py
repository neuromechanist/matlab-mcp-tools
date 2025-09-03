"""MATLAB engine wrapper for MCP Tool."""

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import matlab.engine
from mcp.server.fastmcp import Context
from PIL import Image

from .models import CompressionConfig, ExecutionResult, FigureData, FigureFormat
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
        compression_config: Optional[CompressionConfig] = None,
        ctx: Optional[Context] = None,
    ) -> ExecutionResult:
        """Execute a MATLAB script or command.

        Args:
            script: MATLAB code or file path
            is_file: Whether script is a file path
            workspace_vars: Variables to inject into workspace
            capture_plots: Whether to capture generated plots
            compression_config: Optional compression settings for figures
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
                figures = await self._capture_figures(compression_config)

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

    def _compress_png(
        self, png_path: Path, compression_config: CompressionConfig
    ) -> bytes:
        """Compress PNG image using PIL/Pillow with optimization.

        Args:
            png_path: Path to the original PNG file
            compression_config: Compression settings

        Returns:
            Compressed PNG data as bytes
        """
        with Image.open(png_path) as img:
            # Convert to RGB if necessary (removes alpha channel which increases file size)
            if img.mode in ("RGBA", "LA", "P"):
                # Create white background for transparency
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(
                    img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
                )
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # Apply compression based on quality setting
            buffer = io.BytesIO()

            # Map quality (1-100) to PNG compression level (0-9, where 9 is max compression)
            # Higher quality = lower compression level for PNG
            png_compress_level = max(
                0, min(9, int((100 - compression_config.quality) / 11))
            )

            img.save(
                buffer, format="PNG", optimize=True, compress_level=png_compress_level
            )

            return buffer.getvalue()

    async def _capture_figures(
        self, compression_config: Optional[CompressionConfig] = None
    ) -> List[FigureData]:
        """Capture current MATLAB figures with optimized compression.

        Args:
            compression_config: Optional compression settings. If None, uses defaults.

        Returns:
            List of FigureData containing optimized PNG figures
        """
        if compression_config is None:
            compression_config = CompressionConfig()

        try:
            figures = []
            fig_handles = self.eng.eval('get(groot, "Children")', nargout=1)

            if fig_handles:
                for i, _ in enumerate(fig_handles):
                    # Generate optimized PNG with compression settings
                    png_file = self.output_dir / f"figure_{i}.png"

                    # Optimize MATLAB print parameters based on compression settings
                    print_args = [
                        f"'{png_file}'",
                        "'-dpng'",
                        f"'-r{compression_config.dpi}'",
                    ]

                    # Choose renderer based on optimization target
                    if compression_config.optimize_for == "size":
                        # Use OpenGL renderer for smaller files (rasterized)
                        print_args.append("'-opengl'")
                    else:
                        # Use painters renderer for better quality (vector-based)
                        print_args.append("'-painters'")

                    # Add compression-friendly settings
                    if compression_config.quality < 50:
                        # For low quality, use loose bounds to reduce file size
                        print_args.append("'-loose'")
                    else:
                        # For higher quality, use tight bounds
                        print_args.append("'-tight'")

                    # Remove unnecessary margins for smaller files
                    print_args.append("'-fillpage'")

                    # Set figure properties for optimal compression
                    fig_optimization = (
                        f"fig = figure({i + 1}); "
                        f"set(fig, 'Color', 'white'); "  # White background compresses better
                        f"set(fig, 'InvertHardcopy', 'off'); "  # Preserve background color
                    )

                    # Additional optimizations based on quality setting
                    if compression_config.quality < 70:
                        # For lower quality, reduce anti-aliasing
                        fig_optimization += "set(fig, 'GraphicsSmoothing', 'off'); "

                    print_cmd = f"print(figure({i + 1}), {', '.join(print_args)})"

                    # Apply optimizations and print
                    self.eng.eval(fig_optimization, nargout=0)
                    self.eng.eval(print_cmd, nargout=0)

                    # Get original file size before compression
                    original_size = png_file.stat().st_size

                    if compression_config.use_file_reference:
                        # Apply compression and save to disk, return file path only
                        compressed_data = self._compress_png(
                            png_file, compression_config
                        )
                        compressed_size = len(compressed_data)

                        # Save compressed data to new file
                        compressed_file = self.output_dir / f"figure_{i}_compressed.png"
                        with open(compressed_file, "wb") as f:
                            f.write(compressed_data)

                        figure_data = FigureData(
                            data=None,  # No binary data, use file path instead
                            file_path=str(compressed_file),
                            format=FigureFormat.PNG,
                            compression_config=compression_config,
                            original_size=original_size,
                            compressed_size=compressed_size,
                        )
                    else:
                        # Return binary data as before
                        compressed_data = self._compress_png(
                            png_file, compression_config
                        )
                        compressed_size = len(compressed_data)

                        figure_data = FigureData(
                            data=compressed_data,
                            format=FigureFormat.PNG,
                            compression_config=compression_config,
                            original_size=original_size,
                            compressed_size=compressed_size,
                        )

                    figures.append(figure_data)

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
