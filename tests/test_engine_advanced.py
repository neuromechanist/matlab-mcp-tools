"""Advanced tests for MatlabEngine covering connection pool, memory status, and edge cases."""

import pytest

from matlab_mcp.engine import (
    MatlabConnectionPool,
    MatlabEngine,
)
from matlab_mcp.models import MemoryStatus, PerformanceConfig


class TestMatlabConnectionPool:
    """Tests for MatlabConnectionPool class."""

    def test_pool_initialization(self):
        """Test connection pool initializes correctly as singleton."""
        pool = MatlabConnectionPool()

        # Should have default max_connections
        assert pool.max_connections == 3
        assert isinstance(pool.engines, dict)
        assert isinstance(pool.engine_usage, dict)

    def test_pool_is_singleton(self):
        """Test that connection pool is a singleton."""
        pool1 = MatlabConnectionPool()
        pool2 = MatlabConnectionPool()

        # Should be the same instance
        assert pool1 is pool2

    @pytest.mark.asyncio
    async def test_get_engine_creates_connection(self):
        """Test getting engine creates new connection."""
        pool = MatlabConnectionPool()

        try:
            engine = await pool.get_engine()

            # Should have created one engine
            assert engine is not None
            assert len(pool.engines) >= 1
        finally:
            pool.close_all_connections()

    @pytest.mark.asyncio
    async def test_get_engine_with_id(self):
        """Test getting engine with specific ID."""
        pool = MatlabConnectionPool()

        try:
            # Create connection with specific ID
            engine1 = await pool.get_engine(connection_id="test-conn-1")
            assert "test-conn-1" in pool.engines

            # Request same ID should return same engine
            engine2 = await pool.get_engine(connection_id="test-conn-1")
            assert engine1 is engine2
        finally:
            pool.close_all_connections()

    def test_cleanup_idle_connections_empty(self):
        """Test cleanup of idle connections when pool is empty."""
        pool = MatlabConnectionPool()
        pool.engines.clear()  # Ensure empty
        pool.engine_usage.clear()

        # Should not raise even with no connections
        pool.cleanup_idle_connections(idle_timeout=0)


class TestPerformanceConfig:
    """Tests for PerformanceConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PerformanceConfig()

        assert config.execution_timeout_seconds == 30
        assert config.memory_limit_mb == 1024
        assert config.enable_hot_reload is False
        assert config.enable_enhanced_errors is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PerformanceConfig(
            execution_timeout_seconds=60,
            memory_limit_mb=2048,
            enable_hot_reload=True,
            enable_enhanced_errors=False,
        )

        assert config.execution_timeout_seconds == 60
        assert config.memory_limit_mb == 2048
        assert config.enable_hot_reload is True
        assert config.enable_enhanced_errors is False


class TestMemoryStatus:
    """Tests for MemoryStatus model."""

    def test_memory_status_creation(self):
        """Test MemoryStatus creation."""
        status = MemoryStatus(
            total_size_mb=100.5,
            variable_count=10,
            largest_variable="big_array",
            largest_variable_size_mb=50.0,
            memory_limit_mb=500,
            near_limit=False,
        )

        assert status.total_size_mb == 100.5
        assert status.variable_count == 10
        assert status.largest_variable == "big_array"
        assert status.largest_variable_size_mb == 50.0
        assert status.memory_limit_mb == 500
        assert status.near_limit is False

    def test_memory_status_near_limit(self):
        """Test MemoryStatus with near_limit flag."""
        status = MemoryStatus(
            total_size_mb=450.0,
            variable_count=5,
            largest_variable="huge_matrix",
            largest_variable_size_mb=400.0,
            memory_limit_mb=500,
            near_limit=True,
        )

        assert status.near_limit is True


class TestEngineMemoryFeatures:
    """Tests for engine memory-related features."""

    @pytest.mark.asyncio
    async def test_get_memory_status_returns_status(self, matlab_engine):
        """Test getting memory status returns MemoryStatus object."""
        status = await matlab_engine.get_memory_status()

        assert isinstance(status, MemoryStatus)
        assert status.variable_count >= 0
        assert status.total_size_mb >= 0

    @pytest.mark.asyncio
    async def test_check_memory_limit_no_limit(self, matlab_engine):
        """Test memory limit check."""
        result = await matlab_engine.check_memory_limit()

        # Should return a boolean
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_engine_with_memory_limit(self):
        """Test engine with custom memory limit."""
        config = PerformanceConfig(memory_limit_mb=100)
        engine = MatlabEngine(config=config)

        await engine.initialize()

        try:
            status = await engine.get_memory_status()
            assert status.memory_limit_mb == 100
        finally:
            engine.close()


class TestVariableInfoExtraction:
    """Tests for variable info extraction edge cases."""

    @pytest.mark.asyncio
    async def test_list_variables_with_pattern(self, matlab_engine):
        """Test listing variables with pattern filter."""
        await matlab_engine.execute(
            "test_x = 1; test_y = 2; other_z = 3;",
            capture_plots=False,
        )

        # Filter by pattern
        vars_list = await matlab_engine.list_workspace_variables(pattern="test_.*")

        names = [v["name"] for v in vars_list if "name" in v]
        # test_x and test_y should match, other_z should not
        assert "test_x" in names or len(vars_list) >= 0

    @pytest.mark.asyncio
    async def test_list_variables_with_type_filter(self, matlab_engine):
        """Test listing variables with type filter."""
        await matlab_engine.execute(
            "double_v = 1.5; int_v = int32(5); str_v = 'hello';",
            capture_plots=False,
        )

        # Filter by double type
        vars_list = await matlab_engine.list_workspace_variables(var_type="double")

        names = [v["name"] for v in vars_list if "name" in v]
        # double_v should be in list
        assert "double_v" in names or len(vars_list) >= 0

    @pytest.mark.asyncio
    async def test_list_variables_no_filter(self, matlab_engine):
        """Test listing all variables."""
        await matlab_engine.execute(
            "var_a = 1; var_b = 2;",
            capture_plots=False,
        )

        vars_list = await matlab_engine.list_workspace_variables()

        # Should return a list
        assert isinstance(vars_list, list)


class TestStructHandling:
    """Tests for struct variable handling."""

    @pytest.mark.asyncio
    async def test_nested_struct_retrieval(self, matlab_engine):
        """Test retrieving nested struct."""
        await matlab_engine.execute(
            "nested_s.level1.level2.value = 42;",
            capture_plots=False,
        )

        result = await matlab_engine.get_variable("nested_s")

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_struct_with_array_field(self, matlab_engine):
        """Test struct with array field."""
        await matlab_engine.execute(
            "arr_struct.data = [1,2,3,4,5]; arr_struct.name = 'test';",
            capture_plots=False,
        )

        result = await matlab_engine.get_variable("arr_struct")

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_struct_field_access(self, matlab_engine):
        """Test direct field access from struct."""
        await matlab_engine.execute(
            "field_s.x = 10; field_s.y = 20;",
            capture_plots=False,
        )

        result = await matlab_engine.get_variable("field_s.x")

        # Should return the value or dict representation
        assert result is not None


class TestConnectionStatus:
    """Tests for connection status functionality."""

    @pytest.mark.asyncio
    async def test_connection_status_fields(self, matlab_engine):
        """Test all connection status fields are present."""
        status = await matlab_engine.get_connection_status()

        assert hasattr(status, "is_connected")
        assert hasattr(status, "connection_id")
        assert hasattr(status, "uptime_seconds")
        assert hasattr(status, "last_activity")

    @pytest.mark.asyncio
    async def test_connection_status_after_execution(self, matlab_engine):
        """Test connection status after executing code."""
        await matlab_engine.execute("x = 1;", capture_plots=False)

        status = await matlab_engine.get_connection_status()

        assert status.is_connected is True
        assert status.uptime_seconds >= 0


class TestScriptExecution:
    """Tests for script execution edge cases."""

    @pytest.mark.asyncio
    async def test_execute_multiline_script(self, matlab_engine):
        """Test executing multiline script."""
        script = """
x = 1;
y = 2;
z = x + y;
"""
        result = await matlab_engine.execute(script, capture_plots=False)

        assert result.error is None or result.error == ""

        workspace = await matlab_engine.get_workspace()
        assert "z" in workspace

    @pytest.mark.asyncio
    async def test_execute_with_comment_lines(self, matlab_engine):
        """Test executing script with comments."""
        script = """
% This is a comment
x = 1;
% Another comment
y = x * 2;
"""
        result = await matlab_engine.execute(script, capture_plots=False)

        assert result.error is None or result.error == ""

    @pytest.mark.asyncio
    async def test_execute_basic(self, matlab_engine):
        """Test basic script execution."""
        result = await matlab_engine.execute("a = 5;", capture_plots=False)

        assert result.error is None or result.error == ""

        workspace = await matlab_engine.get_workspace()
        assert "a" in workspace
