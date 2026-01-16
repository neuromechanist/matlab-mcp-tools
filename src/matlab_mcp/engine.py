"""MATLAB engine wrapper for MCP Tool."""

import io
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
from PIL import Image

from .converters import ConversionConfig, MatlabConverter
from .figure_analysis import (
    DEFAULT_ANALYSIS_PROMPT,
    MATLAB_GET_FIGURE_METADATA,
    MATLAB_GET_PLOT_DATA,
    FigureAnalysisResult,
    FigureMetadata,
    PlotData,
    format_metadata_for_analysis,
    get_color_description,
)
from .models import (
    CompressionConfig,
    ConnectionStatus,
    ExecutionResult,
    FigureData,
    FigureFormat,
    MemoryStatus,
    PerformanceConfig,
)
from .utils.section_parser import extract_section, parse_sections


class VariableRetrievalConfig:
    """Configuration for selective variable retrieval."""

    def __init__(
        self,
        fields: list[str] | None = None,
        depth: int = 1,
        max_elements: int = 100,
        include_stats: bool = True,
    ):
        self.fields = fields  # Specific fields to retrieve (for structs)
        self.depth = depth  # 0=info only, 1=values, 2+=nested
        self.max_elements = max_elements  # Max array elements to transfer
        self.include_stats = include_stats  # Include statistics for large arrays


class WorkspaceConfig:
    """Configuration for workspace data transfer optimization."""

    def __init__(
        self,
        small_threshold: int = 100,
        medium_threshold: int = 10000,
        preview_elements: int = 3,
        max_string_length: int = 200,
    ):
        self.small_threshold = small_threshold  # Elements: return full data
        self.medium_threshold = medium_threshold  # Elements: return sample + stats
        self.preview_elements = preview_elements  # Number of elements in preview
        self.max_string_length = (
            max_string_length  # Max string length before truncation
        )


class MatlabConnectionPool:
    """Connection pool manager for MATLAB engines."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not getattr(self, "_initialized", False):
            self.engines = {}  # connection_id -> engine mapping
            self.engine_usage = {}  # connection_id -> last_used timestamp
            self.max_connections = 3  # Maximum concurrent MATLAB connections
            self._initialized = True

    async def get_engine(self, connection_id: str = None) -> matlab.engine.MatlabEngine:
        """Get or create a MATLAB engine connection.

        Args:
            connection_id: Specific connection ID, creates new if None

        Returns:
            MATLAB engine instance
        """
        if connection_id and connection_id in self.engines:
            # Update last used time
            self.engine_usage[connection_id] = time.time()
            return self.engines[connection_id]

        # Create new connection if under limit
        if len(self.engines) < self.max_connections:
            new_id = connection_id or str(uuid.uuid4())
            engine = await self._create_engine()

            if engine:
                self.engines[new_id] = engine
                self.engine_usage[new_id] = time.time()
                return engine

        # Find least recently used connection to reuse
        if self.engines:
            oldest_id = min(self.engine_usage, key=self.engine_usage.get)
            self.engine_usage[oldest_id] = time.time()
            return self.engines[oldest_id]

        # Fallback: create single engine
        return await self._create_engine()

    async def _create_engine(self) -> Optional[matlab.engine.MatlabEngine]:
        """Create a new MATLAB engine instance."""
        try:
            # Try to find existing sessions first
            sessions = matlab.engine.find_matlab()
            if sessions:
                return matlab.engine.connect_matlab(sessions[0])
            else:
                return matlab.engine.start_matlab()
        except Exception as e:
            print(f"Error creating MATLAB engine: {e}", file=sys.stderr)
            return None

    def cleanup_idle_connections(self, idle_timeout: int = 300):
        """Remove connections that have been idle for too long.

        Args:
            idle_timeout: Idle timeout in seconds (default 5 minutes)
        """
        current_time = time.time()
        idle_connections = [
            conn_id
            for conn_id, last_used in self.engine_usage.items()
            if current_time - last_used > idle_timeout
        ]

        for conn_id in idle_connections:
            try:
                engine = self.engines.pop(conn_id)
                engine.quit()
                del self.engine_usage[conn_id]
                print(f"Cleaned up idle MATLAB connection: {conn_id}", file=sys.stderr)
            except Exception as e:
                print(f"Error cleaning up connection {conn_id}: {e}", file=sys.stderr)

    def close_all_connections(self):
        """Close all MATLAB engine connections."""
        for conn_id, engine in self.engines.items():
            try:
                engine.quit()
                print(f"Closed MATLAB connection: {conn_id}", file=sys.stderr)
            except Exception as e:
                print(f"Error closing connection {conn_id}: {e}", file=sys.stderr)

        self.engines.clear()
        self.engine_usage.clear()


class MatlabEngine:
    """Wrapper for MATLAB engine with enhanced functionality."""

    def __init__(
        self,
        config: Optional[PerformanceConfig] = None,
        workspace_config: Optional[WorkspaceConfig] = None,
        conversion_config: Optional[ConversionConfig] = None,
    ):
        """Initialize MATLAB engine wrapper.

        Args:
            config: Performance and reliability configuration
            workspace_config: Workspace optimization configuration
            conversion_config: MATLAB type conversion configuration (optional).
                If provided, uses the new centralized MatlabConverter for type
                conversions. If None, uses legacy conversion methods.
        """
        self.eng = None
        # Use .mcp directory in home for all outputs
        self.mcp_dir = Path.home() / ".mcp"
        self.output_dir = self.mcp_dir / "matlab" / "output"
        self.helpers_dir = self.mcp_dir / "matlab" / "helpers"
        self.output_dir.parent.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        self.helpers_dir.mkdir(exist_ok=True)
        self.matlab_path = os.getenv("MATLAB_PATH", "/Applications/MATLAB_R2024b.app")

        # Workspace optimization configuration
        self.workspace_config = workspace_config or WorkspaceConfig()

        # Performance and reliability configuration
        self.config = config or PerformanceConfig()
        self.connection_start_time = time.time()
        self.connection_id = str(uuid.uuid4())
        self.last_activity = time.time()

        # Type conversion configuration
        self.conversion_config = conversion_config
        self.converter = (
            MatlabConverter(conversion_config) if conversion_config else None
        )

        # Connection pool for improved performance
        self.connection_pool = MatlabConnectionPool()

        # Hot reloading for script development
        self.watched_files = {}  # file_path -> last_modified_time
        self.file_cache = {}  # file_path -> cached_content

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

                # Add MCP helpers to MATLAB path
                helpers_path = str(self.helpers_dir)
                print(
                    f"Adding MCP helpers to MATLAB path: {helpers_path}",
                    file=sys.stderr,
                )
                self.eng.addpath(helpers_path, nargout=0)

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

    def _analyze_figure_content(self, figure_num: int) -> dict:
        """Analyze figure content to determine optimal compression settings.

        Args:
            figure_num: Figure number to analyze

        Returns:
            Dictionary containing content analysis results
        """
        try:
            # Get figure handle and analyze its content
            analysis = {
                "has_image_data": False,
                "has_line_plots": False,
                "has_text": False,
                "has_patches": False,
                "complexity_score": 0,
                "recommended_quality": 75,
            }

            # Analyze figure children to understand content type
            children_cmd = f"get(figure({figure_num}), 'Children')"
            axes_handles = self.eng.eval(children_cmd, nargout=1)

            if axes_handles:
                for ax_idx in range(
                    len(axes_handles) if hasattr(axes_handles, "__len__") else 1
                ):
                    # Get axes children (plots, images, text, etc.)
                    ax_children_cmd = f"children = get(figure({figure_num}).Children({ax_idx + 1}), 'Children'); cellfun(@(x) class(x), children, 'UniformOutput', false)"

                    try:
                        child_types = self.eng.eval(ax_children_cmd, nargout=1)
                        if child_types:
                            for child_type in child_types:
                                child_type_str = str(child_type).lower()

                                if (
                                    "image" in child_type_str
                                    or "surface" in child_type_str
                                ):
                                    analysis["has_image_data"] = True
                                    analysis["complexity_score"] += 3
                                elif "line" in child_type_str:
                                    analysis["has_line_plots"] = True
                                    analysis["complexity_score"] += 1
                                elif "text" in child_type_str:
                                    analysis["has_text"] = True
                                    analysis["complexity_score"] += 1
                                elif "patch" in child_type_str:
                                    analysis["has_patches"] = True
                                    analysis["complexity_score"] += 2
                    except Exception:
                        # If analysis fails, use default values
                        pass

            # Determine recommended quality based on content
            if analysis["has_image_data"]:
                # Image data benefits from higher quality
                analysis["recommended_quality"] = 85
            elif analysis["has_patches"] or analysis["complexity_score"] > 5:
                # Complex plots benefit from medium-high quality
                analysis["recommended_quality"] = 75
            elif analysis["has_line_plots"] and not analysis["has_text"]:
                # Simple line plots can use lower quality
                analysis["recommended_quality"] = 65
            else:
                # Default medium quality
                analysis["recommended_quality"] = 70

            return analysis

        except Exception as e:
            print(f"Error analyzing figure content: {e}", file=sys.stderr)
            return {
                "has_image_data": False,
                "has_line_plots": True,  # Conservative default
                "has_text": False,
                "has_patches": False,
                "complexity_score": 2,
                "recommended_quality": 70,
            }

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

                    # Create a working copy of compression config for this figure
                    figure_compression_config = compression_config

                    # Apply smart optimization if enabled
                    if compression_config.smart_optimization:
                        content_analysis = self._analyze_figure_content(i + 1)

                        # Create optimized config based on content analysis
                        from copy import deepcopy

                        figure_compression_config = deepcopy(compression_config)
                        figure_compression_config.quality = content_analysis[
                            "recommended_quality"
                        ]

                        # Adjust DPI based on content complexity
                        if content_analysis["has_image_data"]:
                            # Higher DPI for images to preserve detail
                            figure_compression_config.dpi = min(
                                200, compression_config.dpi + 50
                            )
                        elif content_analysis["complexity_score"] <= 2:
                            # Lower DPI for simple plots to save space
                            figure_compression_config.dpi = max(
                                100, compression_config.dpi - 25
                            )

                    # Optimize MATLAB print parameters based on compression settings
                    print_args = [
                        f"'{png_file}'",
                        "'-dpng'",
                        f"'-r{figure_compression_config.dpi}'",
                    ]

                    # Choose renderer based on optimization target
                    if figure_compression_config.optimize_for == "size":
                        # Use OpenGL renderer for smaller files (rasterized)
                        print_args.append("'-opengl'")
                    else:
                        # Use painters renderer for better quality (vector-based)
                        print_args.append("'-painters'")

                    # Note: -tight/-loose/-fillpage options removed as they are deprecated
                    # or not supported for PNG format in newer MATLAB versions (R2025b+)

                    # Set figure properties for optimal compression
                    fig_optimization = (
                        f"fig = figure({i + 1}); "
                        f"set(fig, 'Color', 'white'); "  # White background compresses better
                        f"set(fig, 'InvertHardcopy', 'off'); "  # Preserve background color
                    )

                    # Additional optimizations based on quality setting
                    if figure_compression_config.quality < 70:
                        # For lower quality, reduce anti-aliasing
                        fig_optimization += "set(fig, 'GraphicsSmoothing', 'off'); "

                    print_cmd = f"print(figure({i + 1}), {', '.join(print_args)})"

                    # Apply optimizations and print
                    self.eng.eval(fig_optimization, nargout=0)
                    self.eng.eval(print_cmd, nargout=0)

                    # Get original file size before compression
                    original_size = png_file.stat().st_size

                    if figure_compression_config.use_file_reference:
                        # Apply compression and save to disk, return file path only
                        compressed_data = self._compress_png(
                            png_file, figure_compression_config
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
                            compression_config=figure_compression_config,
                            original_size=original_size,
                            compressed_size=compressed_size,
                        )
                    else:
                        # Return binary data as before
                        compressed_data = self._compress_png(
                            png_file, figure_compression_config
                        )
                        compressed_size = len(compressed_data)

                        figure_data = FigureData(
                            data=compressed_data,
                            format=FigureFormat.PNG,
                            compression_config=figure_compression_config,
                            original_size=original_size,
                            compressed_size=compressed_size,
                        )

                    figures.append(figure_data)

            return figures
        finally:
            # Always clean up, even if an error occurred
            await self.cleanup_figures()

    async def benchmark_compression(self, test_plots: bool = True) -> dict:
        """Benchmark figure compression performance.

        Args:
            test_plots: Whether to generate test plots for benchmarking

        Returns:
            Dictionary containing benchmark results
        """
        results = {"timestamp": time.time(), "test_configurations": [], "summary": {}}

        # Test configurations for benchmarking
        test_configs = [
            CompressionConfig(
                quality=95, dpi=150, optimize_for="quality", smart_optimization=False
            ),
            CompressionConfig(
                quality=75, dpi=150, optimize_for="size", smart_optimization=True
            ),
            CompressionConfig(
                quality=50, dpi=100, optimize_for="size", smart_optimization=True
            ),
        ]

        try:
            if test_plots:
                # Generate a test plot
                test_script = """
                x = linspace(0, 4*pi, 100);
                y = sin(x) + 0.1 * cos(10*x);
                figure;
                plot(x, y, 'b-', 'LineWidth', 2);
                title('Compression Test Plot');
                xlabel('X'); ylabel('Y');
                grid on;
                """
                await self.execute(test_script, capture_plots=False)

            # Test each configuration
            for i, config in enumerate(test_configs):
                start_time = time.time()
                figures = await self._capture_figures(config)
                end_time = time.time()

                if figures:
                    fig = figures[0]
                    processing_time = end_time - start_time

                    original_size = fig.original_size or 0
                    compressed_size = fig.compressed_size or 0
                    compression_ratio = (
                        (1 - compressed_size / original_size) * 100
                        if original_size > 0
                        else 0
                    )

                    config_result = {
                        "config_name": f"Config_{i + 1}",
                        "quality": config.quality,
                        "dpi": config.dpi,
                        "optimize_for": config.optimize_for,
                        "smart_optimization": config.smart_optimization,
                        "original_size_bytes": original_size,
                        "compressed_size_bytes": compressed_size,
                        "compression_ratio_percent": compression_ratio,
                        "processing_time_seconds": processing_time,
                    }

                    results["test_configurations"].append(config_result)

            # Calculate summary statistics
            if results["test_configurations"]:
                avg_compression = sum(
                    r["compression_ratio_percent"]
                    for r in results["test_configurations"]
                ) / len(results["test_configurations"])
                max_compression = max(
                    r["compression_ratio_percent"]
                    for r in results["test_configurations"]
                )
                avg_processing_time = sum(
                    r["processing_time_seconds"] for r in results["test_configurations"]
                ) / len(results["test_configurations"])

                results["summary"] = {
                    "average_compression_ratio": avg_compression,
                    "maximum_compression_ratio": max_compression,
                    "average_processing_time": avg_processing_time,
                    "configurations_tested": len(results["test_configurations"]),
                }

        except Exception as e:
            results["error"] = str(e)

        finally:
            await self.cleanup_figures()

        return results

    async def get_workspace(self) -> Dict[str, Any]:
        """Get current MATLAB workspace variables with smart summarization.

        For large arrays, returns metadata and preview instead of full data
        to dramatically reduce token usage.

        Returns:
            Dictionary of variable names and their optimized representations
        """
        workspace = {}
        var_names = self.eng.eval("who", nargout=1)

        # Use configurable thresholds
        SMALL_THRESHOLD = self.workspace_config.small_threshold
        MEDIUM_THRESHOLD = self.workspace_config.medium_threshold
        PREVIEW_ELEMENTS = self.workspace_config.preview_elements

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
                                # Handle different _data types
                                if hasattr(value._data, "tolist"):
                                    workspace[var] = value._data.tolist()
                                else:
                                    workspace[var] = list(value._data)
                            else:
                                workspace[var] = [list(row) for row in value]

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
                                        f"{var}(1:min({PREVIEW_ELEMENTS + 2},numel({var})))",
                                        nargout=1,
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
                                        f"{var}(1:min({PREVIEW_ELEMENTS},numel({var})))",
                                        nargout=1,
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
                        str_val = str(value)
                        max_len = self.workspace_config.max_string_length
                        workspace[var] = (
                            str_val[:max_len] + "..."
                            if len(str_val) > max_len
                            else str_val
                        )

            except Exception as e:
                workspace[var] = f"<Error reading variable: {str(e)}>"

        return workspace

    async def get_variable(
        self,
        name: str,
        fields: list[str] | None = None,
        depth: int = 1,
        max_elements: int = 100,
    ) -> dict:
        """Get a specific variable with selective field retrieval.

        Args:
            name: Variable name (can include field access like "EEG.chanlocs")
            fields: Specific fields to retrieve (for structs)
            depth: Retrieval depth (0=info only, 1=values, 2+=nested)
            max_elements: Maximum array elements to transfer

        Returns:
            Dictionary containing the variable data or info
        """
        await self.initialize()

        try:
            # Check if variable exists
            exists = self.eng.eval(f"exist('{name.split('.')[0]}', 'var')", nargout=1)
            if exists == 0:
                return {"_mcp_error": f"Variable '{name}' not found in workspace"}

            # Get the variable class
            var_class = self.eng.eval(f"class({name})", nargout=1)

            # Handle struct with specific fields
            if var_class == "struct" and fields:
                # Use our helper function
                fields_str = "{" + ", ".join(f"'{f}'" for f in fields) + "}"
                result = self.eng.eval(
                    f"mcp_get_fields({name}, {fields_str}, {max_elements})", nargout=1
                )
                return self._convert_matlab_value(result, depth, max_elements)

            # Handle struct without specific fields (get info or all)
            if var_class == "struct":
                if depth == 0:
                    # Info only
                    result = self.eng.eval(f"mcp_struct_info({name})", nargout=1)
                    return self._convert_matlab_value(result, 1, max_elements)
                else:
                    # Get all fields with limits
                    result = self.eng.eval(
                        f"mcp_get_fields({name}, fieldnames({name}), {max_elements})",
                        nargout=1,
                    )
                    return self._convert_matlab_value(result, depth - 1, max_elements)

            # Handle arrays
            value = self.eng.eval(name, nargout=1)
            return self._convert_matlab_value(value, depth, max_elements)

        except Exception as e:
            return {"_mcp_error": f"Error retrieving variable: {str(e)}"}

    async def get_struct_info(self, var_name: str) -> dict:
        """Get struct field information without transferring values.

        Args:
            var_name: Name of the struct variable

        Returns:
            Dictionary with field names, types, sizes, and memory usage
        """
        await self.initialize()

        try:
            # Check if variable exists and is a struct
            exists = self.eng.eval(
                f"exist('{var_name.split('.')[0]}', 'var')", nargout=1
            )
            if exists == 0:
                return {"_mcp_error": f"Variable '{var_name}' not found"}

            var_class = self.eng.eval(f"class({var_name})", nargout=1)
            if var_class != "struct":
                return {
                    "_mcp_error": f"Variable '{var_name}' is not a struct (is {var_class})"
                }

            # Use our helper function
            result = self.eng.eval(f"mcp_struct_info({var_name})", nargout=1)
            return self._convert_struct_info(result)

        except Exception as e:
            return {"_mcp_error": f"Error getting struct info: {str(e)}"}

    async def list_workspace_variables(
        self,
        pattern: str | None = None,
        var_type: str | None = None,
    ) -> list[dict]:
        """List workspace variables with optional filtering.

        Args:
            pattern: Regex pattern to filter variable names
            var_type: Filter by MATLAB class (e.g., 'struct', 'double')

        Returns:
            List of dictionaries with variable info
        """
        await self.initialize()
        import re

        try:
            # Get variable names using who (returns cell array of names)
            var_names = self.eng.eval("who", nargout=1)

            if not var_names:
                return []

            variables = []

            for name in var_names:
                # Apply pattern filter early
                if pattern:
                    if not re.search(pattern, name):
                        continue

                # Get variable info individually
                try:
                    var_class = self.eng.eval(f"class({name})", nargout=1)

                    # Apply type filter
                    if var_type:
                        if var_class.lower() != var_type.lower():
                            continue

                    # Get size
                    size_result = self.eng.eval(f"size({name})", nargout=1)
                    size = (
                        list(size_result._data)
                        if hasattr(size_result, "_data")
                        else list(size_result)
                    )

                    # Estimate bytes based on size and type
                    bytes_val = 0
                    try:
                        numel = self.eng.eval(f"numel({name})", nargout=1)
                        # Estimate bytes per element based on type
                        bytes_per_element = {
                            "double": 8,
                            "single": 4,
                            "int64": 8,
                            "uint64": 8,
                            "int32": 4,
                            "uint32": 4,
                            "int16": 2,
                            "uint16": 2,
                            "int8": 1,
                            "uint8": 1,
                            "logical": 1,
                            "char": 2,
                        }.get(var_class, 8)
                        bytes_val = int(numel * bytes_per_element)
                    except Exception:
                        pass

                    var_info = {
                        "name": name,
                        "class": var_class,
                        "size": size,
                        "bytes": bytes_val,
                        "is_struct": var_class == "struct",
                        "is_numeric": var_class
                        in [
                            "double",
                            "single",
                            "int8",
                            "int16",
                            "int32",
                            "int64",
                            "uint8",
                            "uint16",
                            "uint32",
                            "uint64",
                        ],
                        "is_cell": var_class == "cell",
                    }
                    variables.append(var_info)

                except Exception:
                    # Skip variables that can't be queried
                    continue

            return variables

        except Exception as e:
            return [{"_mcp_error": f"Error listing variables: {str(e)}"}]

    def _extract_var_info(self, item) -> dict | None:
        """Extract variable info from a MATLAB struct.

        Args:
            item: MATLAB struct with variable info

        Returns:
            Dictionary with variable info or None if extraction fails
        """
        try:
            # Handle struct with _fieldnames attribute
            if hasattr(item, "_fieldnames"):
                return {
                    "name": str(getattr(item, "name", "")),
                    "class": str(getattr(item, "var_class", "")),
                    "size": list(getattr(item, "var_size", []))
                    if hasattr(getattr(item, "var_size", None), "__iter__")
                    else [],
                    "bytes": int(getattr(item, "bytes", 0)),
                    "is_struct": bool(getattr(item, "is_struct", False)),
                    "is_numeric": bool(getattr(item, "is_numeric", False)),
                    "is_cell": bool(getattr(item, "is_cell", False)),
                }
            # Handle dict-like access
            elif isinstance(item, dict):
                return {
                    "name": str(item.get("name", "")),
                    "class": str(item.get("var_class", item.get("class", ""))),
                    "size": list(item.get("var_size", item.get("size", []))),
                    "bytes": int(item.get("bytes", 0)),
                    "is_struct": bool(item.get("is_struct", False)),
                    "is_numeric": bool(item.get("is_numeric", False)),
                    "is_cell": bool(item.get("is_cell", False)),
                }
            return None
        except Exception:
            return None

    def convert_value(self, value: Any, depth: int = 1, max_elements: int = 100) -> Any:
        """Convert MATLAB value to Python using configured converter.

        If a conversion_config was provided at initialization, uses the new
        centralized MatlabConverter. Otherwise, falls back to legacy conversion.

        Args:
            value: MATLAB value to convert
            depth: Maximum recursion depth for nested structures
            max_elements: Maximum array elements before summarizing

        Returns:
            Python native type (dict, list, float, str, etc.)
        """
        if self.converter is not None:
            return self.converter.convert(value, depth)
        else:
            return self._convert_matlab_value(value, depth, max_elements)

    def _convert_matlab_value(
        self, value, depth: int = 1, max_elements: int = 100
    ) -> any:
        """Convert MATLAB value to Python with depth and size limits (legacy).

        Args:
            value: MATLAB value to convert
            depth: Remaining depth for nested conversion
            max_elements: Maximum array elements

        Returns:
            Python representation of the value
        """
        import matlab

        # Handle None
        if value is None:
            return None

        # Handle matlab.double arrays
        if isinstance(value, matlab.double):
            size = value.size
            total_elements = 1
            for dim in size:
                total_elements *= dim

            if total_elements <= max_elements:
                # Small enough to return full data
                if len(size) == 2 and (size[0] == 1 or size[1] == 1):
                    return list(value._data)
                else:
                    return [list(row) for row in value]
            else:
                # Return summary for large arrays
                flat_data = list(value._data)
                return {
                    "_mcp_type": "large_array",
                    "class": "double",
                    "size": list(size),
                    "numel": total_elements,
                    "sample": flat_data[: min(max_elements, len(flat_data))],
                    "statistics": {
                        "min": min(flat_data),
                        "max": max(flat_data),
                        "mean": sum(flat_data) / len(flat_data),
                    },
                }

        # Handle MATLAB structs
        if hasattr(value, "_fieldnames"):
            if depth <= 0:
                # Return field names only
                return {
                    "_mcp_type": "struct",
                    "fields": list(value._fieldnames),
                }

            # Convert struct fields
            result = {}
            for field in value._fieldnames:
                field_val = getattr(value, field)
                result[field] = self._convert_matlab_value(
                    field_val, depth - 1, max_elements
                )
            return result

        # Handle strings
        if isinstance(value, str):
            if len(value) > 500:
                return {
                    "_mcp_type": "truncated_string",
                    "length": len(value),
                    "preview": value[:500],
                }
            return value

        # Handle lists/tuples
        if isinstance(value, (list, tuple)):
            if len(value) <= max_elements:
                return [
                    self._convert_matlab_value(v, depth - 1, max_elements)
                    for v in value
                ]
            else:
                return {
                    "_mcp_type": "large_list",
                    "length": len(value),
                    "sample": [
                        self._convert_matlab_value(v, depth - 1, max_elements)
                        for v in value[:max_elements]
                    ],
                }

        # Handle dicts
        if isinstance(value, dict):
            return {
                k: self._convert_matlab_value(v, depth - 1, max_elements)
                for k, v in value.items()
            }

        # Handle primitives
        if isinstance(value, (int, float, bool)):
            return value

        # Fallback: convert to string
        try:
            return str(value)
        except Exception:
            return f"<unconvertible: {type(value).__name__}>"

    def _convert_struct_info(self, info) -> dict:
        """Convert struct info from MATLAB to Python dict.

        Args:
            info: MATLAB struct info from mcp_struct_info (dict or struct)

        Returns:
            Dictionary with field information
        """
        import matlab

        result = {}

        # Handle dict (common case with newer MATLAB engine)
        if isinstance(info, dict):
            for field_name, field_data in info.items():
                if isinstance(field_data, dict):
                    field_info = {}
                    for prop, val in field_data.items():
                        if isinstance(val, str):
                            field_info[prop] = val
                        elif isinstance(val, matlab.double):
                            # Convert matlab.double to list
                            field_info[prop] = list(val._data)
                        elif isinstance(val, (int, float, bool)):
                            field_info[prop] = val
                        elif isinstance(val, list):
                            field_info[prop] = val
                        else:
                            field_info[prop] = str(val)
                    result[field_name] = field_info
                else:
                    result[field_name] = str(field_data)
            return result

        # Handle MATLAB struct with _fieldnames (older MATLAB engine)
        if hasattr(info, "_fieldnames"):
            for field in info._fieldnames:
                field_data = getattr(info, field)
                field_info = {}

                if hasattr(field_data, "_fieldnames"):
                    for prop in field_data._fieldnames:
                        val = getattr(field_data, prop)
                        if isinstance(val, str):
                            field_info[prop] = val
                        elif hasattr(val, "_data"):
                            field_info[prop] = list(val._data)
                        elif isinstance(val, (int, float, bool)):
                            field_info[prop] = val
                        elif isinstance(val, list):
                            field_info[prop] = val
                        else:
                            field_info[prop] = str(val)
                elif isinstance(field_data, dict):
                    field_info = self._convert_struct_info({"_": field_data})["_"]

                result[field] = field_info

        return result

    async def get_memory_status(self) -> MemoryStatus:
        """Get current workspace memory status."""
        try:
            # Get workspace info using whos
            workspace_info = self.eng.eval("whos", nargout=1)

            if not workspace_info:
                return MemoryStatus(
                    total_size_mb=0.0,
                    variable_count=0,
                    largest_variable=None,
                    largest_variable_size_mb=0.0,
                    memory_limit_mb=self.config.memory_limit_mb,
                    near_limit=False,
                )

            total_bytes = 0
            variable_info = []

            for var_info in workspace_info:
                var_bytes = var_info.get("bytes", 0)
                total_bytes += var_bytes
                variable_info.append(
                    {
                        "name": var_info.get("name", "Unknown"),
                        "size_mb": var_bytes / (1024 * 1024),
                        "bytes": var_bytes,
                    }
                )

            # Sort by size to find largest variable
            variable_info.sort(key=lambda x: x["bytes"], reverse=True)

            largest_variable = variable_info[0]["name"] if variable_info else None
            largest_variable_size_mb = (
                variable_info[0]["size_mb"] if variable_info else 0.0
            )

            total_size_mb = total_bytes / (1024 * 1024)

            # Check if near memory limit
            near_limit = False
            if self.config.memory_limit_mb:
                near_limit = total_size_mb > (self.config.memory_limit_mb * 0.8)

            return MemoryStatus(
                total_size_mb=total_size_mb,
                variable_count=len(variable_info),
                largest_variable=largest_variable,
                largest_variable_size_mb=largest_variable_size_mb,
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
        """Check if memory usage exceeds configured limit."""
        if not self.config.memory_limit_mb:
            return False

        memory_status = await self.get_memory_status()
        return memory_status.total_size_mb > self.config.memory_limit_mb

    async def clear_large_variables(self, threshold_mb: float = 50.0) -> List[str]:
        """Clear variables larger than the specified threshold."""
        try:
            workspace_info = self.eng.eval("whos", nargout=1)
            if not workspace_info:
                return []

            cleared_vars = []
            for var_info in workspace_info:
                var_name = var_info.get("name", "")
                var_bytes = var_info.get("bytes", 0)
                var_size_mb = var_bytes / (1024 * 1024)

                if var_size_mb > threshold_mb:
                    try:
                        self.eng.eval(f"clear {var_name}", nargout=0)
                        cleared_vars.append(var_name)
                        print(
                            f"Cleared large variable: {var_name} ({var_size_mb:.1f} MB)",
                            file=sys.stderr,
                        )
                    except Exception as e:
                        print(
                            f"Error clearing variable {var_name}: {e}", file=sys.stderr
                        )

            return cleared_vars

        except Exception as e:
            print(f"Error clearing large variables: {e}", file=sys.stderr)
            return []

    async def get_connection_status(self) -> ConnectionStatus:
        """Get current connection status information."""
        is_connected = self.eng is not None
        uptime = time.time() - self.connection_start_time

        return ConnectionStatus(
            is_connected=is_connected,
            connection_id=self.connection_id,
            uptime_seconds=uptime,
            last_activity=self.last_activity,
        )

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

    async def execute_section_by_index(
        self,
        file_path: str,
        section_index: int,
        maintain_workspace: bool = True,
        capture_plots: bool = True,
        ctx: Optional[Context] = None,
    ) -> ExecutionResult:
        """Execute a specific section of a MATLAB script by its index.

        Args:
            file_path: Path to the MATLAB script (absolute or relative)
            section_index: 0-based index of the section to execute
            maintain_workspace: Whether to maintain workspace between sections
            capture_plots: Whether to capture generated plots
            ctx: MCP context for progress reporting

        Returns:
            ExecutionResult containing output, workspace state, and figures
        """
        script_path = Path(file_path)
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {file_path}")

        # Parse sections from the file
        sections = parse_sections(script_path)

        if not sections:
            raise ValueError(f"No sections found in {file_path}")

        if section_index < 0 or section_index >= len(sections):
            raise IndexError(
                f"Section index {section_index} out of range. "
                f"Script has {len(sections)} section(s) (0 to {len(sections) - 1})."
            )

        start_line, end_line, title = sections[section_index]

        if ctx:
            ctx.info(
                f"Executing section {section_index}: '{title}' (lines {start_line}-{end_line})"
            )

        return await self.execute_section(
            file_path,
            (start_line, end_line),
            maintain_workspace=maintain_workspace,
            capture_plots=capture_plots,
            ctx=ctx,
        )

    async def execute_section_by_title(
        self,
        file_path: str,
        section_title: str,
        maintain_workspace: bool = True,
        capture_plots: bool = True,
        ctx: Optional[Context] = None,
    ) -> ExecutionResult:
        """Execute a specific section of a MATLAB script by its title.

        Args:
            file_path: Path to the MATLAB script (absolute or relative)
            section_title: Title of the section to execute (case-insensitive partial match)
            maintain_workspace: Whether to maintain workspace between sections
            capture_plots: Whether to capture generated plots
            ctx: MCP context for progress reporting

        Returns:
            ExecutionResult containing output, workspace state, and figures
        """
        script_path = Path(file_path)
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {file_path}")

        # Parse sections from the file
        sections = parse_sections(script_path)

        if not sections:
            raise ValueError(f"No sections found in {file_path}")

        # Find section by title (case-insensitive partial match)
        search_title = section_title.lower().strip()
        matching_sections = []

        for idx, (start_line, end_line, title) in enumerate(sections):
            if search_title in title.lower():
                matching_sections.append((idx, start_line, end_line, title))

        if not matching_sections:
            section_titles = [s[2] for s in sections]
            raise ValueError(
                f"No section matching '{section_title}' found. "
                f"Available sections: {section_titles}"
            )

        if len(matching_sections) > 1:
            matches = [m[3] for m in matching_sections]
            raise ValueError(
                f"Multiple sections match '{section_title}': {matches}. "
                "Please be more specific."
            )

        idx, start_line, end_line, title = matching_sections[0]

        if ctx:
            ctx.info(
                f"Executing section {idx}: '{title}' (lines {start_line}-{end_line})"
            )

        return await self.execute_section(
            file_path,
            (start_line, end_line),
            maintain_workspace=maintain_workspace,
            capture_plots=capture_plots,
            ctx=ctx,
        )

    async def get_script_sections(self, file_path: str) -> list[dict]:
        """Get information about sections in a MATLAB script.

        Args:
            file_path: Path to the MATLAB script (absolute or relative)

        Returns:
            List of dictionaries with section information:
            [
                {
                    "index": 0,
                    "title": "Section Title",
                    "start_line": 0,
                    "end_line": 15,
                    "preview": "x = linspace(0, 10, 100);"
                },
                ...
            ]
        """
        script_path = Path(file_path)
        if not script_path.exists():
            raise FileNotFoundError(f"Script not found: {file_path}")

        sections = parse_sections(script_path)

        with open(script_path) as f:
            lines = f.readlines()

        section_info = []
        for idx, (start, end, title) in enumerate(sections):
            # Find first non-comment line for preview
            preview = ""
            for line in lines[start : end + 1]:
                stripped = line.strip()
                if stripped and not stripped.startswith("%"):
                    preview = stripped[:80]  # Limit preview length
                    break

            section_info.append(
                {
                    "index": idx,
                    "title": title,
                    "start_line": start,
                    "end_line": end,
                    "preview": preview,
                }
            )

        return section_info

    def _setup_figure_analysis_helpers(self) -> None:
        """Set up MATLAB helper functions for figure analysis."""
        # Write helper functions to the helpers directory
        metadata_helper = self.helpers_dir / "mcp_get_figure_metadata.m"
        plot_data_helper = self.helpers_dir / "mcp_get_plot_data.m"

        if not metadata_helper.exists():
            metadata_helper.write_text(MATLAB_GET_FIGURE_METADATA)

        if not plot_data_helper.exists():
            plot_data_helper.write_text(MATLAB_GET_PLOT_DATA)

    async def get_figure_metadata(self, figure_number: int = 1) -> FigureMetadata:
        """Extract comprehensive metadata from a MATLAB figure.

        This extracts information about axes, labels, colors, legends, and
        other properties directly from the MATLAB figure object.

        Args:
            figure_number: MATLAB figure number (default: 1)

        Returns:
            FigureMetadata object with extracted properties
        """
        await self.initialize()
        self._setup_figure_analysis_helpers()

        try:
            # Check if figure exists
            fig_exists = self.eng.eval(
                f"ishandle({figure_number}) && strcmp(get({figure_number}, 'Type'), 'figure')",
                nargout=1,
            )

            if not fig_exists:
                return FigureMetadata(
                    figure_number=figure_number,
                    axes_properties={"error": f"Figure {figure_number} does not exist"},
                )

            # Call the helper function
            result = self.eng.eval(
                f"mcp_get_figure_metadata({figure_number})", nargout=1
            )

            # Convert MATLAB struct to FigureMetadata
            # Handle both dict (newer MATLAB Engine) and object (older versions)
            metadata = FigureMetadata(figure_number=figure_number)

            def get_field(obj, field_name, default=None):
                """Get field from dict or object."""
                if isinstance(obj, dict):
                    return obj.get(field_name, default)
                return getattr(obj, field_name, default)

            def to_flat_list(val):
                """Convert MATLAB array to flat Python list."""
                if val is None:
                    return []
                if hasattr(val, "_data"):
                    # matlab.double object - use _data directly
                    if hasattr(val._data, "tolist"):
                        return val._data.tolist()
                    return list(val._data)
                if isinstance(val, (list, tuple)) and val:
                    # Check if first element is matlab.double
                    first = val[0]
                    if hasattr(first, "_data"):
                        if hasattr(first._data, "tolist"):
                            return first._data.tolist()
                        return list(first._data)
                    # Check if nested list
                    if isinstance(first, (list, tuple)):
                        return list(first)
                return list(val) if val else []

            if get_field(result, "error"):
                metadata.axes_properties = {"error": str(get_field(result, "error"))}
                return metadata

            # Extract fields from result
            title_val = get_field(result, "title")
            if title_val:
                metadata.title = str(title_val)
            xlabel_val = get_field(result, "xlabel")
            if xlabel_val:
                metadata.xlabel = str(xlabel_val)
            ylabel_val = get_field(result, "ylabel")
            if ylabel_val:
                metadata.ylabel = str(ylabel_val)
            zlabel_val = get_field(result, "zlabel")
            if zlabel_val:
                metadata.zlabel = str(zlabel_val)

            xlim_val = get_field(result, "xlim")
            if xlim_val:
                metadata.xlim = to_flat_list(xlim_val)
            ylim_val = get_field(result, "ylim")
            if ylim_val:
                metadata.ylim = to_flat_list(ylim_val)
            zlim_val = get_field(result, "zlim")
            if zlim_val:
                metadata.zlim = to_flat_list(zlim_val)

            legend_val = get_field(result, "legend_entries")
            if legend_val:
                if isinstance(legend_val, str):
                    metadata.legend_entries = [legend_val]
                else:
                    metadata.legend_entries = list(legend_val)

            colorbar_label_val = get_field(result, "colorbar_label")
            if colorbar_label_val:
                metadata.colorbar_label = str(colorbar_label_val)
            colorbar_limits_val = get_field(result, "colorbar_limits")
            if colorbar_limits_val:
                metadata.colorbar_limits = list(colorbar_limits_val)

            num_subplots_val = get_field(result, "num_subplots")
            if num_subplots_val is not None:
                metadata.num_subplots = int(num_subplots_val)
            num_lines_val = get_field(result, "num_lines")
            if num_lines_val is not None:
                metadata.num_lines = int(num_lines_val)
            num_images_val = get_field(result, "num_images")
            if num_images_val is not None:
                metadata.num_images = int(num_images_val)

            line_colors_val = get_field(result, "line_colors")
            if line_colors_val:
                # Handle nested matlab.double arrays
                colors = []
                for c in line_colors_val:
                    if isinstance(c, (list, tuple)) and c:
                        first = c[0]
                        if hasattr(first, "_data"):
                            if hasattr(first._data, "tolist"):
                                colors.append(first._data.tolist())
                            else:
                                colors.append(list(first._data))
                        else:
                            colors.append(
                                list(first)
                                if isinstance(first, (list, tuple))
                                else to_flat_list(c)
                            )
                    elif hasattr(c, "_data"):
                        if hasattr(c._data, "tolist"):
                            colors.append(c._data.tolist())
                        else:
                            colors.append(list(c._data))
                    else:
                        colors.append(list(c) if c else [])
                metadata.line_colors = colors
            line_styles_val = get_field(result, "line_styles")
            if line_styles_val:
                metadata.line_styles = list(line_styles_val)
            line_labels_val = get_field(result, "line_labels")
            if line_labels_val:
                metadata.line_labels = list(line_labels_val)

            colormap_name_val = get_field(result, "colormap_name")
            if colormap_name_val:
                metadata.colormap_name = str(colormap_name_val)

            return metadata

        except Exception as e:
            return FigureMetadata(
                figure_number=figure_number,
                axes_properties={"error": f"Error extracting metadata: {str(e)}"},
            )

    async def get_plot_data(
        self, figure_number: int = 1, line_index: int = 1
    ) -> PlotData:
        """Extract data points from a plotted line in a figure.

        Args:
            figure_number: MATLAB figure number (default: 1)
            line_index: 1-based index of the line to extract (default: 1)

        Returns:
            PlotData object with x, y, z coordinates and line properties
        """
        await self.initialize()
        self._setup_figure_analysis_helpers()

        try:
            # Call the helper function
            result = self.eng.eval(
                f"mcp_get_plot_data({figure_number}, {line_index})", nargout=1
            )

            plot_data = PlotData(line_index=line_index)

            # Handle both dict (newer MATLAB Engine) and object (older versions)
            def get_field(obj, field_name, default=None):
                """Get field from dict or object."""
                if isinstance(obj, dict):
                    return obj.get(field_name, default)
                return getattr(obj, field_name, default)

            error_val = get_field(result, "error")
            if error_val:
                plot_data.label = f"Error: {error_val}"
                return plot_data

            def to_flat_list(val):
                """Convert MATLAB array to flat Python list."""
                if val is None:
                    return []
                if hasattr(val, "_data"):
                    # matlab.double object - use _data directly
                    if hasattr(val._data, "tolist"):
                        return val._data.tolist()
                    return list(val._data)
                if hasattr(val, "tolist"):
                    result = val.tolist()
                    # Flatten if 2D (row vector)
                    if result and isinstance(result[0], list):
                        return result[0]
                    return result
                return list(val)

            xdata_val = get_field(result, "xdata")
            if xdata_val is not None:
                plot_data.xdata = to_flat_list(xdata_val)

            ydata_val = get_field(result, "ydata")
            if ydata_val is not None:
                plot_data.ydata = to_flat_list(ydata_val)

            zdata_val = get_field(result, "zdata")
            if zdata_val is not None:
                data = to_flat_list(zdata_val)
                if data:  # Only set if non-empty
                    plot_data.zdata = data

            label_val = get_field(result, "label")
            if label_val:
                plot_data.label = str(label_val)

            color_val = get_field(result, "color")
            if color_val is not None:
                plot_data.color = list(color_val)

            style_val = get_field(result, "style")
            if style_val:
                plot_data.style = str(style_val)

            marker_val = get_field(result, "marker")
            if marker_val:
                plot_data.marker = str(marker_val)

            return plot_data

        except Exception as e:
            return PlotData(line_index=line_index, label=f"Error: {str(e)}")

    async def prepare_figure_for_analysis(
        self,
        figure_number: int = 1,
        custom_prompt: str | None = None,
        include_metadata: bool = True,
    ) -> dict:
        """Prepare a figure for LLM vision analysis.

        This method captures the figure as an image and prepares context
        including metadata and a structured prompt for analysis.

        Args:
            figure_number: MATLAB figure number to analyze
            custom_prompt: Custom analysis prompt (uses default if None)
            include_metadata: Whether to include extracted metadata as context

        Returns:
            Dictionary with:
            - figure: FigureData object with captured image
            - metadata: FigureMetadata object (if include_metadata=True)
            - prompt: The full prompt including metadata context
        """
        await self.initialize()

        result = {
            "figure_number": figure_number,
            "figure": None,
            "metadata": None,
            "prompt": custom_prompt or DEFAULT_ANALYSIS_PROMPT,
        }

        try:
            # Check if figure exists
            fig_exists = self.eng.eval(
                f"ishandle({figure_number}) && strcmp(get({figure_number}, 'Type'), 'figure')",
                nargout=1,
            )

            if not fig_exists:
                result["error"] = f"Figure {figure_number} does not exist"
                return result

            # Capture figure as PNG with high quality for analysis
            png_file = self.output_dir / f"analysis_figure_{figure_number}.png"

            # Use high quality settings for analysis
            self.eng.eval(
                f"fig = figure({figure_number}); "
                f"set(fig, 'Color', 'white'); "
                f"set(fig, 'InvertHardcopy', 'off');",
                nargout=0,
            )

            # Print with high resolution for clear analysis
            self.eng.eval(
                f"print(figure({figure_number}), '{png_file}', '-dpng', '-r150', '-painters')",
                nargout=0,
            )

            # Read the image data and create FigureData object
            with open(png_file, "rb") as f:
                image_data = f.read()

            result["figure"] = FigureData(
                data=image_data,
                file_path=str(png_file),
                format=FigureFormat.PNG,
            )

            # Extract metadata if requested
            metadata = None
            if include_metadata:
                metadata = await self.get_figure_metadata(figure_number)
                result["metadata"] = metadata

                # Add metadata context to the prompt
                metadata_context = format_metadata_for_analysis(metadata)
                if metadata_context:
                    result["prompt"] = (
                        f"{metadata_context}\n\n---\n\n{result['prompt']}"
                    )

            return result

        except Exception as e:
            result["error"] = f"Error preparing figure: {str(e)}"
            return result

    async def analyze_figure_with_llm(
        self,
        figure_number: int = 1,
        custom_prompt: str | None = None,
        include_metadata: bool = True,
    ) -> FigureAnalysisResult:
        """Analyze a figure using LLM vision capabilities.

        This method prepares the figure and returns structured data that can
        be sent to an LLM for visual analysis. The actual LLM call should be
        made by the MCP client.

        Args:
            figure_number: MATLAB figure number to analyze
            custom_prompt: Custom analysis prompt (uses detailed default if None)
            include_metadata: Whether to include extracted metadata as context

        Returns:
            FigureAnalysisResult with prepared analysis data

        Note:
            The returned result includes image data and prompts. The actual
            LLM vision analysis should be performed by the MCP client using
            the returned data.
        """
        prep_result = await self.prepare_figure_for_analysis(
            figure_number=figure_number,
            custom_prompt=custom_prompt,
            include_metadata=include_metadata,
        )

        analysis_result = FigureAnalysisResult(figure_number=figure_number)

        if "error" in prep_result:
            analysis_result.description = f"Error: {prep_result['error']}"
            return analysis_result

        # The prompt already includes metadata context from prepare_figure_for_analysis
        analysis_result.raw_response = prep_result["prompt"]
        analysis_result.description = (
            "Figure prepared for analysis. Use the image data with an LLM vision "
            "model to get the full analysis."
        )

        # Store metadata analysis
        if prep_result["metadata"]:
            meta = prep_result["metadata"]
            if meta.xlabel or meta.ylabel:
                analysis_result.axes_analysis = (
                    f"X-axis: {meta.xlabel or 'unlabeled'}, "
                    f"Y-axis: {meta.ylabel or 'unlabeled'}"
                )
            if meta.line_colors:
                color_info = []
                for i, color in enumerate(meta.line_colors):
                    label = (
                        meta.line_labels[i]
                        if i < len(meta.line_labels)
                        else f"Line {i + 1}"
                    )
                    color_info.append(f"{label}: {get_color_description(color)}")
                analysis_result.color_analysis = "; ".join(color_info)

        return analysis_result

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
