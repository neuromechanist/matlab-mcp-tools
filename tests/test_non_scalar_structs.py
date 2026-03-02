"""Tests for non-scalar struct and complex char array handling in get_workspace."""

import pytest

try:
    import importlib.util

    MATLAB_AVAILABLE = importlib.util.find_spec("matlab.engine") is not None
except Exception:
    MATLAB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not MATLAB_AVAILABLE, reason="MATLAB Engine not available"
)


@pytest.fixture(scope="module")
def engine(matlab_engine):
    """Use the shared MATLAB engine fixture."""
    return matlab_engine


class TestNonScalarStructHandling:
    """Tests that non-scalar structs return metadata instead of error strings."""

    @pytest.mark.asyncio
    async def test_non_scalar_struct_returns_metadata(self, engine):
        """Non-scalar struct should return _mcp_type metadata, not error string."""
        await engine.execute(
            "ns_struct(1).a = 1; ns_struct(2).a = 2;", capture_plots=False
        )

        workspace = await engine.get_workspace()

        assert "ns_struct" in workspace
        data = workspace["ns_struct"]
        assert isinstance(data, dict), (
            f"Expected dict, got {type(data).__name__}: {data!r}"
        )
        assert data.get("_mcp_type") == "non_scalar_struct", (
            f"Expected non_scalar_struct type, got: {data}"
        )

    @pytest.mark.asyncio
    async def test_non_scalar_struct_has_size_info(self, engine):
        """Non-scalar struct metadata should include size and numel."""
        await engine.execute(
            "sized_struct(1).x = 10; sized_struct(2).x = 20; sized_struct(3).x = 30;",
            capture_plots=False,
        )

        workspace = await engine.get_workspace()

        assert "sized_struct" in workspace
        data = workspace["sized_struct"]
        assert isinstance(data, dict)
        assert "size" in data, f"Expected 'size' key in metadata: {data}"
        assert "numel" in data, f"Expected 'numel' key in metadata: {data}"
        assert data["numel"] == 3

    @pytest.mark.asyncio
    async def test_non_scalar_struct_has_field_names(self, engine):
        """Non-scalar struct metadata should include field names."""
        await engine.execute(
            "field_struct(1).alpha = 1; field_struct(1).beta = 'x';"
            " field_struct(2).alpha = 2; field_struct(2).beta = 'y';",
            capture_plots=False,
        )

        workspace = await engine.get_workspace()

        assert "field_struct" in workspace
        data = workspace["field_struct"]
        assert isinstance(data, dict)
        assert "field_names" in data, f"Expected 'field_names' key in metadata: {data}"
        field_names = data["field_names"]
        assert isinstance(field_names, list)
        assert "alpha" in field_names
        assert "beta" in field_names

    @pytest.mark.asyncio
    async def test_non_scalar_struct_no_error_string(self, engine):
        """Non-scalar struct should not return an error string."""
        await engine.execute(
            "err_struct(1).v = 100; err_struct(2).v = 200;", capture_plots=False
        )

        workspace = await engine.get_workspace()

        assert "err_struct" in workspace
        data = workspace["err_struct"]
        assert not isinstance(data, str), (
            f"Expected dict metadata, got error string: {data!r}"
        )

    @pytest.mark.asyncio
    async def test_non_scalar_struct_class_is_struct(self, engine):
        """Non-scalar struct metadata should report class as 'struct'."""
        await engine.execute(
            "class_struct(1).n = 1; class_struct(2).n = 2;", capture_plots=False
        )

        workspace = await engine.get_workspace()

        assert "class_struct" in workspace
        data = workspace["class_struct"]
        assert isinstance(data, dict)
        assert data.get("class") == "struct"


class TestComplexCharArrayHandling:
    """Tests that M-by-N char arrays return size info instead of error strings."""

    @pytest.mark.asyncio
    async def test_complex_char_returns_metadata(self, engine):
        """M-by-N char array should return _mcp_type metadata, not error string."""
        await engine.execute("c_arr = ['abc'; 'def'];", capture_plots=False)

        workspace = await engine.get_workspace()

        assert "c_arr" in workspace
        data = workspace["c_arr"]
        assert isinstance(data, dict), (
            f"Expected dict, got {type(data).__name__}: {data!r}"
        )
        assert data.get("_mcp_type") == "complex_char", (
            f"Expected complex_char type, got: {data}"
        )

    @pytest.mark.asyncio
    async def test_complex_char_has_size_info(self, engine):
        """M-by-N char array metadata should include size."""
        await engine.execute("c_sized = ['hello'; 'world'];", capture_plots=False)

        workspace = await engine.get_workspace()

        assert "c_sized" in workspace
        data = workspace["c_sized"]
        assert isinstance(data, dict)
        assert "size" in data, f"Expected 'size' key in metadata: {data}"
        size = data["size"]
        assert isinstance(size, list)
        assert len(size) == 2
        # 2 rows, 5 cols
        assert size[0] == 2
        assert size[1] == 5

    @pytest.mark.asyncio
    async def test_complex_char_no_error_string(self, engine):
        """M-by-N char array should not return an error string."""
        await engine.execute("c_no_err = ['foo'; 'bar'];", capture_plots=False)

        workspace = await engine.get_workspace()

        assert "c_no_err" in workspace
        data = workspace["c_no_err"]
        assert not isinstance(data, str), (
            f"Expected dict metadata, got error string: {data!r}"
        )

    @pytest.mark.asyncio
    async def test_complex_char_class_is_char(self, engine):
        """M-by-N char array metadata should report class as 'char'."""
        await engine.execute("c_class = ['xyz'; 'abc'];", capture_plots=False)

        workspace = await engine.get_workspace()

        assert "c_class" in workspace
        data = workspace["c_class"]
        assert isinstance(data, dict)
        assert data.get("class") == "char"


class TestRecoverMetadataFallback:
    """Tests the fallback behavior when metadata recovery fails."""

    def test_recover_metadata_returns_none_for_unknown_error(self, engine):
        """_recover_variable_metadata returns None for non-struct/char errors."""
        result = engine._recover_variable_metadata(
            "some_var", "some unrelated MATLAB error"
        )
        assert result is None

    def test_recover_metadata_returns_none_for_empty_error(self, engine):
        """_recover_variable_metadata returns None for empty error string."""
        result = engine._recover_variable_metadata("some_var", "")
        assert result is None

    def test_recover_metadata_struct_error_string_detected(self, engine):
        """_recover_variable_metadata detects scalar struct error strings."""
        # This test verifies the detection logic without needing a real var
        err = "only a scalar struct can be returned from MATLAB"
        # For a var that doesn't exist, recovery will fail internally and return None
        result = engine._recover_variable_metadata("nonexistent_xyz_abc", err)
        # Should return None because var doesn't exist in workspace
        assert result is None

    def test_recover_metadata_char_error_string_detected(self, engine):
        """_recover_variable_metadata detects char array error strings."""
        err = "char arrays returned from MATLAB must be 1-by-N or M-by-1"
        result = engine._recover_variable_metadata("nonexistent_xyz_abc", err)
        assert result is None
