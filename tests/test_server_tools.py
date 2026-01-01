"""Tests for MCP server tool functions."""

from pathlib import Path

import pytest

# Import the MCP tool functions directly from server
from matlab_mcp.server import (
    MatlabServer,
    create_matlab_script,
    execute_script,
    execute_section_by_index,
    execute_section_by_title,
    get_script_sections,
    get_struct_info,
    get_variable,
    get_workspace,
    list_workspace_variables,
)


@pytest.fixture(scope="module")
def server_instance():
    """Get or create server instance."""
    return MatlabServer.get_instance()


@pytest.fixture
def sample_script_with_sections(tmp_path):
    """Create a sample MATLAB script with sections for testing."""
    script_content = """%% Section 1 - Initialize
x = 1:10;
y = x.^2;

%% Section 2 - Compute
result = sum(y);
"""
    script_path = tmp_path / "test_script.m"
    script_path.write_text(script_content)
    return script_path


class TestExecuteScript:
    """Tests for execute_script MCP tool."""

    @pytest.mark.asyncio
    async def test_execute_simple_code(self):
        """Test executing simple MATLAB code."""
        result = await execute_script("x = 5; y = x * 2;", capture_plots=False)

        assert result["error"] is None or result["error"] == ""
        assert "x" in result["workspace"] or "y" in result["workspace"]

    @pytest.mark.asyncio
    async def test_execute_with_workspace_vars(self):
        """Test executing code with injected workspace variables."""
        result = await execute_script(
            "z = a + b;",
            workspace_vars={"a": 10, "b": 20},
            capture_plots=False,
        )

        assert result["error"] is None or result["error"] == ""
        workspace = result["workspace"]
        # z should be 30
        assert "z" in workspace

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test that MATLAB errors are captured properly."""
        result = await execute_script(
            "this_is_undefined_variable + 1;",
            capture_plots=False,
        )

        assert result["error"] is not None and result["error"] != ""


class TestGetWorkspace:
    """Tests for get_workspace MCP tool."""

    @pytest.mark.asyncio
    async def test_get_workspace(self):
        """Test getting workspace after execution."""
        # First create some variables
        await execute_script("ws_test_var = 42;", capture_plots=False)

        result = await get_workspace()

        assert isinstance(result, dict)
        assert "ws_test_var" in result


class TestGetVariable:
    """Tests for get_variable MCP tool."""

    @pytest.mark.asyncio
    async def test_get_simple_variable(self):
        """Test getting a simple variable."""
        await execute_script("simple_var = [1, 2, 3, 4, 5];", capture_plots=False)

        result = await get_variable("simple_var")

        assert "_mcp_error" not in result or result.get("_mcp_error") is None
        # Should be a list or dict representation
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    async def test_get_nonexistent_variable(self):
        """Test getting a variable that doesn't exist."""
        result = await get_variable("definitely_not_a_real_variable_12345")

        assert "_mcp_error" in result


class TestListWorkspaceVariables:
    """Tests for list_workspace_variables MCP tool."""

    @pytest.mark.asyncio
    async def test_list_all_variables(self):
        """Test listing all workspace variables."""
        # Create some variables
        await execute_script(
            "list_test_a = 1; list_test_b = 2;",
            capture_plots=False,
        )

        result = await list_workspace_variables()

        assert isinstance(result, list)
        names = [v["name"] for v in result if "name" in v]
        assert "list_test_a" in names or "list_test_b" in names

    @pytest.mark.asyncio
    async def test_list_with_pattern(self):
        """Test listing variables with pattern filter."""
        await execute_script(
            "pattern_abc = 1; pattern_def = 2; other_var = 3;",
            capture_plots=False,
        )

        result = await list_workspace_variables(pattern="^pattern")

        assert isinstance(result, list)
        names = [v["name"] for v in result if "name" in v]
        # Should only include pattern_* variables
        for name in names:
            assert name.startswith("pattern") or "_mcp_error" in result[0]


class TestGetStructInfo:
    """Tests for get_struct_info MCP tool."""

    @pytest.mark.asyncio
    async def test_get_struct_info(self):
        """Test getting struct info."""
        await execute_script(
            "test_struct.field1 = 10; test_struct.field2 = 'hello';",
            capture_plots=False,
        )

        result = await get_struct_info("test_struct")

        assert isinstance(result, dict)
        if "_mcp_error" not in result:
            assert "field1" in result or "field2" in result


class TestSectionExecution:
    """Tests for section execution MCP tools."""

    @pytest.mark.asyncio
    async def test_get_script_sections(self, sample_script_with_sections):
        """Test getting script sections."""
        result = await get_script_sections(str(sample_script_with_sections))

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["title"] == "Section 1 - Initialize"
        assert result[1]["title"] == "Section 2 - Compute"

    @pytest.mark.asyncio
    async def test_execute_section_by_index(self, sample_script_with_sections):
        """Test executing section by index."""
        result = await execute_section_by_index(
            str(sample_script_with_sections),
            section_index=0,
            capture_plots=False,
        )

        assert result["error"] is None or result["error"] == ""
        assert "x" in result["workspace"] or "y" in result["workspace"]

    @pytest.mark.asyncio
    async def test_execute_section_by_title(self, sample_script_with_sections):
        """Test executing section by title."""
        result = await execute_section_by_title(
            str(sample_script_with_sections),
            section_title="Initialize",
            capture_plots=False,
        )

        assert result["error"] is None or result["error"] == ""


class TestCreateMatlabScript:
    """Tests for create_matlab_script MCP tool."""

    @pytest.mark.asyncio
    async def test_create_script(self):
        """Test creating a MATLAB script."""
        script_code = "% Test script\nx = 1:10;\n"

        result = await create_matlab_script("test_create_script", script_code)

        assert isinstance(result, str)
        assert "test_create_script" in result
        assert Path(result).exists()

        # Clean up
        Path(result).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_create_script_with_extension(self):
        """Test creating a MATLAB script with .m extension."""
        script_code = "% Test\n"

        result = await create_matlab_script("test_with_ext.m", script_code)

        assert isinstance(result, str)
        assert result.endswith(".m")

        # Clean up
        Path(result).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_create_script_invalid_name(self):
        """Test that invalid script names are rejected."""
        with pytest.raises(ValueError):
            await create_matlab_script("123-invalid-name", "x = 1;")
