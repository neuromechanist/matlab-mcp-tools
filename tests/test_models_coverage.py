"""Tests for models module to ensure complete coverage."""

from matlab_mcp.models import (
    CompressionConfig,
    ConnectionStatus,
    EnhancedError,
    ExecutionResult,
    FigureData,
    FigureFormat,
    MemoryStatus,
    PerformanceConfig,
)


class TestCompressionConfig:
    """Tests for CompressionConfig model."""

    def test_default_config(self):
        """Test default compression configuration."""
        config = CompressionConfig()

        assert config.quality == 75
        assert config.dpi == 150
        assert config.optimize_for == "size"
        assert config.use_file_reference is False
        assert config.smart_optimization is True

    def test_custom_config(self):
        """Test custom compression configuration."""
        config = CompressionConfig(
            quality=90,
            dpi=300,
            optimize_for="quality",
            use_file_reference=True,
            smart_optimization=False,
        )

        assert config.quality == 90
        assert config.dpi == 300
        assert config.optimize_for == "quality"
        assert config.use_file_reference is True
        assert config.smart_optimization is False


class TestFigureData:
    """Tests for FigureData model."""

    def test_figure_data_with_bytes(self):
        """Test FigureData with binary data."""
        data = FigureData(
            data=b"\x89PNG\r\n",
            format=FigureFormat.PNG,
        )

        assert data.data == b"\x89PNG\r\n"
        assert data.format == FigureFormat.PNG
        assert data.file_path is None

    def test_figure_data_with_path(self):
        """Test FigureData with file path."""
        data = FigureData(
            file_path="/tmp/figure.png",
            format=FigureFormat.PNG,
        )

        assert data.file_path == "/tmp/figure.png"
        assert data.data is None


class TestConnectionStatus:
    """Tests for ConnectionStatus model."""

    def test_connection_status_creation(self):
        """Test ConnectionStatus creation."""
        status = ConnectionStatus(
            is_connected=True,
            connection_id="test-123",
            uptime_seconds=100.5,
            last_activity=1234567890.0,
        )

        assert status.is_connected is True
        assert status.connection_id == "test-123"
        assert status.uptime_seconds == 100.5
        assert status.last_activity == 1234567890.0

    def test_connection_status_disconnected(self):
        """Test ConnectionStatus when disconnected."""
        status = ConnectionStatus(
            is_connected=False,
            connection_id=None,
            uptime_seconds=0.0,
            last_activity=0.0,
        )

        assert status.is_connected is False
        assert status.connection_id is None


class TestEnhancedError:
    """Tests for EnhancedError model."""

    def test_enhanced_error_creation(self):
        """Test EnhancedError creation."""
        error = EnhancedError(
            error_type="MATLAB",
            message="Undefined function 'foo'",
            line_number=10,
            context_lines=["x = foo()"],
            stack_trace="Error in script at line 10",
        )

        assert error.error_type == "MATLAB"
        assert error.message == "Undefined function 'foo'"
        assert error.line_number == 10
        assert "foo()" in error.context_lines[0]
        assert error.stack_trace is not None

    def test_enhanced_error_with_defaults(self):
        """Test EnhancedError with default values."""
        error = EnhancedError(
            error_type="Python",
            message="Import error",
            line_number=None,
            stack_trace=None,
        )

        assert error.error_type == "Python"
        assert error.message == "Import error"
        assert error.line_number is None
        assert error.context_lines == []
        assert error.timestamp > 0


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_execution_result_success(self):
        """Test successful execution result."""
        result = ExecutionResult(
            output="x = 5",
            error=None,
            workspace={"x": 5},
            figures=[],
        )

        assert result.output == "x = 5"
        assert result.error is None
        assert result.workspace == {"x": 5}
        assert result.figures == []

    def test_execution_result_with_error(self):
        """Test execution result with error."""
        result = ExecutionResult(
            output="",
            error="Syntax error",
            workspace={},
            figures=[],
        )

        assert result.error == "Syntax error"

    def test_execution_result_with_memory_status(self):
        """Test execution result with memory status."""
        memory = MemoryStatus(
            total_size_mb=50.0,
            variable_count=3,
            largest_variable="data",
            largest_variable_size_mb=25.0,
            memory_limit_mb=1024,
            near_limit=False,
        )

        result = ExecutionResult(
            output="",
            workspace={},
            figures=[],
            memory_status=memory,
        )

        assert result.memory_status is not None
        assert result.memory_status.total_size_mb == 50.0


class TestFigureFormat:
    """Tests for FigureFormat enum."""

    def test_all_formats(self):
        """Test all figure formats exist."""
        assert FigureFormat.PNG is not None
        assert FigureFormat.SVG is not None

    def test_format_values(self):
        """Test format string values."""
        assert FigureFormat.PNG.value == "png"
        assert FigureFormat.SVG.value == "svg"


class TestPerformanceConfig:
    """Tests for PerformanceConfig model."""

    def test_default_performance_config(self):
        """Test default performance config values."""
        config = PerformanceConfig()

        assert config.memory_limit_mb == 1024
        assert config.execution_timeout_seconds == 30
        assert config.enable_hot_reload is False
        assert config.enable_enhanced_errors is True

    def test_custom_performance_config(self):
        """Test custom performance config."""
        config = PerformanceConfig(
            memory_limit_mb=512,
            execution_timeout_seconds=60,
            enable_hot_reload=True,
            enable_enhanced_errors=False,
        )

        assert config.memory_limit_mb == 512
        assert config.execution_timeout_seconds == 60
        assert config.enable_hot_reload is True
        assert config.enable_enhanced_errors is False

    def test_none_memory_limit(self):
        """Test None memory limit."""
        config = PerformanceConfig(memory_limit_mb=None)

        assert config.memory_limit_mb is None


class TestMemoryStatusModel:
    """Tests for MemoryStatus model fields."""

    def test_memory_status_all_fields(self):
        """Test all MemoryStatus fields."""
        status = MemoryStatus(
            total_size_mb=100.0,
            variable_count=5,
            largest_variable="matrix",
            largest_variable_size_mb=50.0,
            memory_limit_mb=1024,
            near_limit=False,
        )

        assert status.total_size_mb == 100.0
        assert status.variable_count == 5
        assert status.largest_variable == "matrix"
        assert status.largest_variable_size_mb == 50.0
        assert status.memory_limit_mb == 1024
        assert status.near_limit is False

    def test_memory_status_no_largest(self):
        """Test MemoryStatus with no largest variable."""
        status = MemoryStatus(
            total_size_mb=0.0,
            variable_count=0,
            largest_variable=None,
            largest_variable_size_mb=0.0,
            memory_limit_mb=None,
            near_limit=False,
        )

        assert status.largest_variable is None
        assert status.memory_limit_mb is None
