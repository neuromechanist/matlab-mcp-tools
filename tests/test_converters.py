"""Tests for MATLAB type converters module."""

import pytest

from matlab_mcp.converters import (
    AttrDict,
    ConversionConfig,
    MatlabConverter,
    convert_matlab_value,
    convert_workspace,
)


class TestAttrDict:
    """Tests for AttrDict class."""

    def test_dict_access(self):
        """Test standard dict access."""
        d = AttrDict({"x": 1, "y": 2})

        assert d["x"] == 1
        assert d["y"] == 2

    def test_attribute_access(self):
        """Test attribute-style access."""
        d = AttrDict({"x": 1, "y": 2})

        assert d.x == 1
        assert d.y == 2

    def test_attribute_set(self):
        """Test setting via attribute."""
        d = AttrDict()
        d.x = 10
        d.y = 20

        assert d["x"] == 10
        assert d.y == 20

    def test_attribute_delete(self):
        """Test deleting via attribute."""
        d = AttrDict({"x": 1, "y": 2})
        del d.x

        assert "x" not in d
        assert d.y == 2

    def test_missing_attribute_error(self):
        """Test AttributeError for missing key."""
        d = AttrDict({"x": 1})

        with pytest.raises(AttributeError):
            _ = d.nonexistent

    def test_delete_missing_attribute_error(self):
        """Test AttributeError when deleting missing key."""
        d = AttrDict({"x": 1})

        with pytest.raises(AttributeError):
            del d.nonexistent

    def test_nested_attrdict(self):
        """Test nested AttrDict access."""
        d = AttrDict({"outer": AttrDict({"inner": 42})})

        assert d.outer.inner == 42


class TestConversionConfig:
    """Tests for ConversionConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ConversionConfig()

        assert config.max_array_size == 1000
        assert config.squeeze_matrices is True
        assert config.use_attrdict is False
        assert config.include_metadata is True
        assert config.depth_limit == 10
        assert config.sample_size == 100

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ConversionConfig(
            max_array_size=500,
            squeeze_matrices=False,
            use_attrdict=True,
            include_metadata=False,
            depth_limit=5,
            sample_size=50,
        )

        assert config.max_array_size == 500
        assert config.squeeze_matrices is False
        assert config.use_attrdict is True
        assert config.include_metadata is False
        assert config.depth_limit == 5
        assert config.sample_size == 50


class TestMatlabConverterBasic:
    """Tests for MatlabConverter with basic types."""

    def test_convert_none(self):
        """Test converting None."""
        converter = MatlabConverter()

        assert converter.convert(None) is None

    def test_convert_string(self):
        """Test converting string."""
        converter = MatlabConverter()

        assert converter.convert("hello") == "hello"

    def test_convert_int(self):
        """Test converting integer."""
        converter = MatlabConverter()

        assert converter.convert(42) == 42

    def test_convert_float(self):
        """Test converting float."""
        converter = MatlabConverter()

        assert converter.convert(3.14) == 3.14

    def test_convert_bool(self):
        """Test converting boolean."""
        converter = MatlabConverter()

        assert converter.convert(True) is True
        assert converter.convert(False) is False

    def test_convert_list(self):
        """Test converting list."""
        converter = MatlabConverter()

        result = converter.convert([1, 2, 3])
        assert result == [1, 2, 3]

    def test_convert_dict(self):
        """Test converting dict."""
        converter = MatlabConverter()

        result = converter.convert({"a": 1, "b": 2})
        assert result == {"a": 1, "b": 2}

    def test_convert_nested_dict(self):
        """Test converting nested dict."""
        converter = MatlabConverter()

        result = converter.convert({"outer": {"inner": 42}})
        assert result == {"outer": {"inner": 42}}


class TestMatlabConverterWithAttrDict:
    """Tests for MatlabConverter with AttrDict output."""

    def test_dict_to_attrdict(self):
        """Test converting dict to AttrDict."""
        config = ConversionConfig(use_attrdict=True)
        converter = MatlabConverter(config)

        result = converter.convert({"x": 1, "y": 2})

        assert isinstance(result, AttrDict)
        assert result.x == 1
        assert result.y == 2

    def test_nested_attrdict(self):
        """Test nested AttrDict conversion."""
        config = ConversionConfig(use_attrdict=True)
        converter = MatlabConverter(config)

        result = converter.convert({"outer": {"inner": 42}})

        assert isinstance(result, AttrDict)
        assert isinstance(result.outer, AttrDict)
        assert result.outer.inner == 42


class TestMatlabConverterDepthLimit:
    """Tests for depth limit handling."""

    def test_depth_limit_truncation(self):
        """Test that depth limit causes truncation."""
        config = ConversionConfig(depth_limit=2)
        converter = MatlabConverter(config)

        # With depth=2: outer(depth=2) -> inner(depth=1) -> deep(depth=0, truncated)
        result = converter.convert({"outer": {"inner": {"deep": 1}}})

        # The innermost "deep" dict should be truncated
        assert result["outer"]["inner"]["_mcp_truncated"] is True

    def test_custom_depth_in_call(self):
        """Test passing custom depth to convert call."""
        converter = MatlabConverter()

        # With depth=0, should immediately truncate
        result = converter.convert({"x": 1}, depth=0)

        assert result["_mcp_truncated"] is True

    def test_depth_limit_preserves_values(self):
        """Test that depth limit preserves primitive values."""
        config = ConversionConfig(depth_limit=1)
        converter = MatlabConverter(config)

        # depth=1 allows one level of dict, but nested dicts get truncated
        result = converter.convert({"x": 1, "nested": {"y": 2}})

        assert result["x"] == 1
        assert result["nested"]["_mcp_truncated"] is True


class TestMatlabConverterWithMatlab:
    """Tests for MatlabConverter with actual MATLAB types."""

    @pytest.mark.asyncio
    async def test_convert_matlab_double(self, matlab_engine):
        """Test converting matlab.double array."""
        await matlab_engine.execute("test_arr = [1, 2, 3, 4, 5];", capture_plots=False)

        # Get raw value

        raw_value = matlab_engine.eng.workspace["test_arr"]

        converter = MatlabConverter()
        result = converter.convert(raw_value)

        assert isinstance(result, list)
        assert result == [1.0, 2.0, 3.0, 4.0, 5.0]

    @pytest.mark.asyncio
    async def test_convert_matlab_struct(self, matlab_engine):
        """Test converting MATLAB struct."""
        await matlab_engine.execute(
            "test_struct.x = 10; test_struct.y = 20;", capture_plots=False
        )

        raw_value = matlab_engine.eng.workspace["test_struct"]

        converter = MatlabConverter()
        result = converter.convert(raw_value)

        assert isinstance(result, dict)
        assert result["x"] == 10.0
        assert result["y"] == 20.0

    @pytest.mark.asyncio
    async def test_convert_nested_struct(self, matlab_engine):
        """Test converting nested MATLAB struct."""
        await matlab_engine.execute("nested.level1.value = 42;", capture_plots=False)

        raw_value = matlab_engine.eng.workspace["nested"]

        converter = MatlabConverter()
        result = converter.convert(raw_value)

        assert isinstance(result, dict)
        assert result["level1"]["value"] == 42.0

    @pytest.mark.asyncio
    async def test_convert_large_array_summary(self, matlab_engine):
        """Test that large arrays become summaries."""
        await matlab_engine.execute("large_arr = ones(100, 100);", capture_plots=False)

        raw_value = matlab_engine.eng.workspace["large_arr"]

        # Use small max_array_size to trigger summary
        config = ConversionConfig(max_array_size=100)
        converter = MatlabConverter(config)
        result = converter.convert(raw_value)

        assert isinstance(result, dict)
        assert result["_mcp_type"] == "large_array"
        assert result["total_elements"] == 10000
        assert "sample_data" in result
        assert "statistics" in result

    @pytest.mark.asyncio
    async def test_convert_struct_to_attrdict(self, matlab_engine):
        """Test converting struct with AttrDict enabled."""
        await matlab_engine.execute(
            "attr_s.name = 'test'; attr_s.value = 123;", capture_plots=False
        )

        raw_value = matlab_engine.eng.workspace["attr_s"]

        config = ConversionConfig(use_attrdict=True)
        converter = MatlabConverter(config)
        result = converter.convert(raw_value)

        assert isinstance(result, AttrDict)
        assert result.name == "test"
        assert result.value == 123.0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_convert_matlab_value_basic(self):
        """Test convert_matlab_value with basic type."""
        result = convert_matlab_value({"x": 1, "y": 2})

        assert result == {"x": 1, "y": 2}

    def test_convert_matlab_value_with_attrdict(self):
        """Test convert_matlab_value with AttrDict."""
        result = convert_matlab_value({"x": 1}, use_attrdict=True)

        assert isinstance(result, AttrDict)
        assert result.x == 1

    def test_convert_workspace_basic(self):
        """Test convert_workspace with basic types."""
        workspace = {"var1": 1, "var2": "hello", "var3": [1, 2, 3]}

        result = convert_workspace(workspace)

        assert result == {"var1": 1, "var2": "hello", "var3": [1, 2, 3]}


class TestEngineWithConverter:
    """Tests for MatlabEngine with converter integration."""

    @pytest.mark.asyncio
    async def test_engine_with_conversion_config(self):
        """Test creating engine with conversion config."""
        from matlab_mcp.engine import MatlabEngine

        config = ConversionConfig(use_attrdict=True, max_array_size=500)
        engine = MatlabEngine(conversion_config=config)

        await engine.initialize()

        try:
            assert engine.converter is not None
            assert engine.conversion_config is not None
            assert engine.conversion_config.use_attrdict is True
        finally:
            engine.close()

    @pytest.mark.asyncio
    async def test_engine_convert_value_method(self, matlab_engine):
        """Test engine's convert_value method."""
        await matlab_engine.execute("cv_test = [1, 2, 3];", capture_plots=False)

        raw_value = matlab_engine.eng.workspace["cv_test"]

        # Using legacy conversion (no converter configured)
        result = matlab_engine.convert_value(raw_value)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_engine_with_converter_converts_structs(self):
        """Test engine with converter handles structs correctly."""
        from matlab_mcp.engine import MatlabEngine

        config = ConversionConfig(use_attrdict=True, depth_limit=5)
        engine = MatlabEngine(conversion_config=config)

        await engine.initialize()

        try:
            await engine.execute("conv_s.a = 1; conv_s.b = 2;", capture_plots=False)

            raw_value = engine.eng.workspace["conv_s"]
            # Use higher depth to fully convert struct fields
            result = engine.convert_value(raw_value, depth=5)

            assert isinstance(result, AttrDict)
            assert result.a == 1.0
        finally:
            engine.close()
