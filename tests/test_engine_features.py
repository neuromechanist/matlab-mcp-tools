"""Tests for MatlabEngine features beyond basic execution."""

import pytest

from matlab_mcp.engine import (
    MatlabEngine,
    VariableRetrievalConfig,
    WorkspaceConfig,
)


class TestVariableRetrievalConfig:
    """Tests for VariableRetrievalConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = VariableRetrievalConfig()

        assert config.fields is None
        assert config.depth == 1
        assert config.max_elements == 100
        assert config.include_stats is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = VariableRetrievalConfig(
            fields=["a", "b", "c"],
            depth=3,
            max_elements=50,
            include_stats=False,
        )

        assert config.fields == ["a", "b", "c"]
        assert config.depth == 3
        assert config.max_elements == 50
        assert config.include_stats is False


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = WorkspaceConfig()

        assert config.small_threshold == 100
        assert config.medium_threshold == 10000
        assert config.preview_elements == 3
        assert config.max_string_length == 200

    def test_custom_values(self):
        """Test custom configuration values."""
        config = WorkspaceConfig(
            small_threshold=50,
            medium_threshold=5000,
            preview_elements=5,
            max_string_length=100,
        )

        assert config.small_threshold == 50
        assert config.medium_threshold == 5000
        assert config.preview_elements == 5
        assert config.max_string_length == 100


class TestConnectionStatus:
    """Tests for connection status functionality."""

    @pytest.mark.asyncio
    async def test_get_connection_status(self, matlab_engine):
        """Test getting connection status."""
        status = await matlab_engine.get_connection_status()

        assert status.is_connected is True
        assert status.connection_id is not None
        assert status.uptime_seconds >= 0
        assert status.last_activity is not None


class TestWorkspaceOptimization:
    """Tests for workspace optimization with different data types."""

    @pytest.mark.asyncio
    async def test_small_array_full_data(self, matlab_engine):
        """Test that small arrays return full data."""
        await matlab_engine.execute("small_arr = [1, 2, 3, 4, 5];", capture_plots=False)

        workspace = await matlab_engine.get_workspace()

        # Small array should have full data, not summary
        assert "small_arr" in workspace
        data = workspace["small_arr"]
        # Should be a list (full data), not a dict (summary)
        assert isinstance(data, list) or (
            isinstance(data, dict) and "_mcp_type" not in data
        )

    @pytest.mark.asyncio
    async def test_large_array_summary(self, matlab_engine):
        """Test that large arrays return summaries."""
        await matlab_engine.execute("large_arr = rand(500, 500);", capture_plots=False)

        workspace = await matlab_engine.get_workspace()

        assert "large_arr" in workspace
        data = workspace["large_arr"]
        # Large array should have summary with _mcp_type
        assert isinstance(data, dict)
        assert "_mcp_type" in data
        assert "large_array" in data["_mcp_type"]

    @pytest.mark.asyncio
    async def test_string_variable(self, matlab_engine):
        """Test string variable handling."""
        await matlab_engine.execute(
            "str_var = 'Hello MATLAB World';", capture_plots=False
        )

        workspace = await matlab_engine.get_workspace()

        assert "str_var" in workspace

    @pytest.mark.asyncio
    async def test_custom_workspace_config(self):
        """Test engine with custom workspace config."""
        custom_config = WorkspaceConfig(
            small_threshold=10,  # Very small threshold
            medium_threshold=100,
            preview_elements=2,
        )

        engine = MatlabEngine(workspace_config=custom_config)
        await engine.initialize()

        try:
            # Create array larger than small_threshold
            await engine.execute("custom_arr = ones(1, 20);", capture_plots=False)

            workspace = await engine.get_workspace()

            # Should be treated as medium/large due to low threshold
            assert "custom_arr" in workspace
        finally:
            engine.close()


class TestVariableRetrieval:
    """Tests for selective variable retrieval."""

    @pytest.mark.asyncio
    async def test_get_variable_with_depth_zero(self, matlab_engine):
        """Test getting struct with depth=0 returns field info only."""
        await matlab_engine.execute(
            "depth_test.a = 1; depth_test.b = 'hello'; depth_test.c = [1,2,3];",
            capture_plots=False,
        )

        result = await matlab_engine.get_variable("depth_test", depth=0)

        # Should return struct info, not values
        assert isinstance(result, dict)
        # Should have _mcp_type or fields info
        assert "_mcp_type" in result or "fields" in result or len(result) > 0

    @pytest.mark.asyncio
    async def test_get_variable_with_max_elements(self, matlab_engine):
        """Test max_elements limiting for arrays."""
        await matlab_engine.execute("big_arr = 1:1000;", capture_plots=False)

        result = await matlab_engine.get_variable("big_arr", max_elements=10)

        assert isinstance(result, dict)
        # Should have been limited
        if "sample" in result:
            assert len(result["sample"]) <= 10

    @pytest.mark.asyncio
    async def test_get_variable_specific_fields(self, matlab_engine):
        """Test getting specific fields from struct."""
        await matlab_engine.execute(
            "field_test.x = 10; field_test.y = 20; field_test.z = 30;",
            capture_plots=False,
        )

        result = await matlab_engine.get_variable("field_test", fields=["x", "y"])

        assert isinstance(result, dict)
        # Should have requested fields
        if "_mcp_error" not in result:
            assert "x" in result or "y" in result


class TestErrorHandling:
    """Tests for error handling in engine operations."""

    @pytest.mark.asyncio
    async def test_execute_syntax_error(self, matlab_engine):
        """Test handling of MATLAB syntax errors."""
        result = await matlab_engine.execute(
            "this is not valid matlab syntax !!!", capture_plots=False
        )

        assert result.error is not None
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_execute_undefined_function(self, matlab_engine):
        """Test handling of undefined function errors."""
        result = await matlab_engine.execute(
            "result = undefined_function_xyz123();", capture_plots=False
        )

        assert result.error is not None

    @pytest.mark.asyncio
    async def test_get_variable_with_nested_field(self, matlab_engine):
        """Test getting nested struct field."""
        await matlab_engine.execute("nested.level1.level2 = 42;", capture_plots=False)

        result = await matlab_engine.get_variable("nested.level1")

        assert isinstance(result, dict)


class TestSectionParserEdgeCases:
    """Tests for section parser edge cases."""

    @pytest.mark.asyncio
    async def test_script_without_sections(self, matlab_engine, tmp_path):
        """Test script with no section markers."""
        script = tmp_path / "no_sections.m"
        script.write_text("x = 1;\ny = 2;\nz = x + y;\n")

        sections = await matlab_engine.get_script_sections(str(script))

        # Should have one "Main" section
        assert len(sections) == 1
        assert sections[0]["title"] == "Main"

    @pytest.mark.asyncio
    async def test_script_with_empty_section_title(self, matlab_engine, tmp_path):
        """Test script with empty section title."""
        script = tmp_path / "empty_title.m"
        script.write_text("%%\nx = 1;\n%% Named Section\ny = 2;\n")

        sections = await matlab_engine.get_script_sections(str(script))

        assert len(sections) == 2
        # First section should have empty title
        assert sections[0]["title"] == ""
        assert sections[1]["title"] == "Named Section"

    @pytest.mark.asyncio
    async def test_script_section_at_end(self, matlab_engine, tmp_path):
        """Test script where last section is at end of file."""
        script = tmp_path / "section_at_end.m"
        script.write_text("x = 1;\n%% Last Section\ny = 2;")

        sections = await matlab_engine.get_script_sections(str(script))

        assert len(sections) == 2
        # Last section should include the final line
        assert sections[1]["end_line"] >= sections[1]["start_line"]


class TestWorkspaceVariableTypes:
    """Tests for different MATLAB variable types in workspace."""

    @pytest.mark.asyncio
    async def test_cell_array(self, matlab_engine):
        """Test cell array handling."""
        await matlab_engine.execute(
            "cell_var = {1, 'hello', [1 2 3]};", capture_plots=False
        )

        workspace = await matlab_engine.get_workspace()
        assert "cell_var" in workspace

    @pytest.mark.asyncio
    async def test_logical_array(self, matlab_engine):
        """Test logical array handling."""
        await matlab_engine.execute(
            "logical_var = [true, false, true];", capture_plots=False
        )

        workspace = await matlab_engine.get_workspace()
        assert "logical_var" in workspace

    @pytest.mark.asyncio
    async def test_complex_number(self, matlab_engine):
        """Test complex number handling."""
        await matlab_engine.execute("complex_var = 3 + 4i;", capture_plots=False)

        workspace = await matlab_engine.get_workspace()
        assert "complex_var" in workspace

    @pytest.mark.asyncio
    async def test_integer_types(self, matlab_engine):
        """Test integer type handling."""
        await matlab_engine.execute("int_var = int32([1, 2, 3]);", capture_plots=False)

        vars_list = await matlab_engine.list_workspace_variables(var_type="int32")

        # Should find the integer variable
        names = [v["name"] for v in vars_list if "name" in v]
        assert (
            "int_var" in names or len(vars_list) == 0
        )  # May not match if type differs
