"""Centralized MATLAB type converters for automatic dict serialization.

This module provides converters similar to scipy.io.loadmat and mat73 for
converting MATLAB types (matlab.double, matlab.struct, etc.) to Python
native types.

References:
- scipy.io.loadmat: https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.loadmat.html
- mat73: https://github.com/skjerns/mat7.3
"""

from dataclasses import dataclass
from typing import Any, Optional

import matlab


class AttrDict(dict):
    """Dict that allows attribute-style access like MATLAB structs.

    This provides a familiar interface for users coming from MATLAB,
    where struct fields are accessed as attributes (e.g., s.field).

    Example:
        >>> d = AttrDict({'x': 1, 'y': 2})
        >>> d.x
        1
        >>> d['x']
        1
    """

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{key}'"
            ) from None

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{key}'"
            ) from None


@dataclass
class ConversionConfig:
    """Configuration for MATLAB type conversion.

    Attributes:
        max_array_size: Arrays larger than this become summaries with metadata.
            Set to None for no limit (convert all arrays fully).
        squeeze_matrices: Remove singleton dimensions from arrays.
        use_attrdict: Use AttrDict for structs (enables attribute-style access).
        include_metadata: Add _type, _size fields for truncated/large values.
        depth_limit: Maximum recursion depth for nested structures.
        sample_size: Number of elements to include in large array samples.
    """

    max_array_size: int = 1000
    squeeze_matrices: bool = True
    use_attrdict: bool = False
    include_metadata: bool = True
    depth_limit: int = 10
    sample_size: int = 100


class MatlabConverter:
    """Convert MATLAB types to Python native types.

    This converter handles recursive conversion of MATLAB values including:
    - matlab.double arrays (to lists or summaries)
    - MATLAB structs (to dicts or AttrDicts)
    - Nested structures (recursive conversion with depth limit)
    - Cell arrays (to lists)

    Example:
        >>> converter = MatlabConverter()
        >>> result = converter.convert(matlab_value)

        >>> # With custom config
        >>> config = ConversionConfig(max_array_size=500, use_attrdict=True)
        >>> converter = MatlabConverter(config)
        >>> result = converter.convert(matlab_struct)
    """

    def __init__(self, config: Optional[ConversionConfig] = None):
        """Initialize converter with configuration.

        Args:
            config: Conversion configuration. Uses defaults if None.
        """
        self.config = config or ConversionConfig()

    def convert(self, value: Any, depth: Optional[int] = None) -> Any:
        """Recursively convert MATLAB value to Python native types.

        Args:
            value: MATLAB value to convert (matlab.double, struct, etc.)
            depth: Current recursion depth. Uses config.depth_limit if None.

        Returns:
            Python native type (dict, list, float, str, etc.)
        """
        if depth is None:
            depth = self.config.depth_limit

        # Handle None
        if value is None:
            return None

        # Handle primitive types first (these don't need depth checks)
        if isinstance(value, (int, float, bool)):
            return value

        if isinstance(value, str):
            return value

        # For complex types, check depth limit
        if depth <= 0:
            return self._make_truncated_value(value)

        # Handle matlab.double arrays
        if isinstance(value, matlab.double):
            return self._convert_array(value)

        # Handle MATLAB struct (has _fieldnames attribute)
        if hasattr(value, "_fieldnames"):
            return self._convert_struct(value, depth)

        # Handle dict (recursive conversion)
        if isinstance(value, dict):
            return self._convert_dict(value, depth)

        # Handle list/tuple (recursive conversion)
        if isinstance(value, (list, tuple)):
            return self._convert_sequence(value, depth)

        # Handle other matlab types with _data attribute
        if hasattr(value, "_data"):
            return self._convert_matlab_data(value)

        # Fallback: convert to string representation
        return str(value)

    def _convert_array(self, arr: matlab.double) -> Any:
        """Convert matlab.double array to list or summary.

        Args:
            arr: MATLAB double array

        Returns:
            List of values, or dict summary for large arrays
        """
        size = arr.size
        total_elements = 1
        for dim in size:
            total_elements *= dim

        # Check if array should be converted fully or summarized
        if (
            self.config.max_array_size is not None
            and total_elements > self.config.max_array_size
        ):
            return self._make_array_summary(arr, size, total_elements)

        # Convert full array
        return self._array_to_list(arr, size)

    def _array_to_list(self, arr: matlab.double, size: tuple) -> Any:
        """Convert array data to Python list.

        Args:
            arr: MATLAB array
            size: Array dimensions

        Returns:
            Python list (possibly nested for multi-dimensional arrays)
        """
        # Handle different _data types (some MATLAB versions don't have tolist)
        if hasattr(arr._data, "tolist"):
            data = arr._data.tolist()
        else:
            data = list(arr._data)

        # Squeeze singleton dimensions if configured
        if self.config.squeeze_matrices and len(size) == 2:
            if size[0] == 1 or size[1] == 1:
                return data

        # For 2D arrays, reshape to nested list
        if len(size) == 2 and size[0] > 1 and size[1] > 1:
            rows, cols = size
            return [data[i * cols : (i + 1) * cols] for i in range(rows)]

        return data

    def _make_array_summary(
        self, arr: matlab.double, size: tuple, total_elements: int
    ) -> dict:
        """Create summary dict for large arrays.

        Args:
            arr: MATLAB array
            size: Array dimensions
            total_elements: Total number of elements

        Returns:
            Dict with array metadata and sample data
        """
        # Get sample data
        sample_size = min(self.config.sample_size, total_elements)
        if hasattr(arr._data, "tolist"):
            sample = arr._data[:sample_size].tolist()
        else:
            sample = list(arr._data)[:sample_size]

        # Calculate statistics if possible
        try:
            data_list = list(arr._data)
            stats = {
                "min": min(data_list),
                "max": max(data_list),
                "mean": sum(data_list) / len(data_list),
            }
        except (TypeError, ValueError):
            stats = None

        summary = {
            "_mcp_type": "large_array",
            "dimensions": list(size),
            "total_elements": total_elements,
            "data_type": "double",
            "sample_data": sample,
        }

        if stats:
            summary["statistics"] = stats

        if self.config.include_metadata:
            summary["memory_usage_mb"] = round(total_elements * 8 / (1024 * 1024), 2)

        return summary

    def _convert_struct(self, struct: Any, depth: int) -> dict:
        """Convert MATLAB struct to dict or AttrDict.

        Args:
            struct: MATLAB struct with _fieldnames attribute
            depth: Current recursion depth

        Returns:
            Dict or AttrDict with converted field values
        """
        result = {}

        for field_name in struct._fieldnames:
            field_value = getattr(struct, field_name)
            result[field_name] = self.convert(field_value, depth - 1)

        if self.config.use_attrdict:
            return AttrDict(result)

        return result

    def _convert_dict(self, d: dict, depth: int) -> dict:
        """Recursively convert dict values.

        Args:
            d: Dictionary to convert
            depth: Current recursion depth

        Returns:
            Dict with converted values
        """
        result = {k: self.convert(v, depth - 1) for k, v in d.items()}

        if self.config.use_attrdict:
            return AttrDict(result)

        return result

    def _convert_sequence(self, seq: Any, depth: int) -> list:
        """Recursively convert list/tuple values.

        Args:
            seq: Sequence to convert
            depth: Current recursion depth

        Returns:
            List with converted values
        """
        return [self.convert(item, depth - 1) for item in seq]

    def _convert_matlab_data(self, value: Any) -> Any:
        """Convert other MATLAB types with _data attribute.

        Args:
            value: MATLAB value with _data attribute

        Returns:
            Converted Python value
        """
        data = value._data
        if hasattr(data, "tolist"):
            return data.tolist()
        elif hasattr(data, "__iter__"):
            return list(data)
        else:
            return data

    def _make_truncated_value(self, value: Any) -> dict:
        """Create truncated value marker for depth limit.

        Args:
            value: Value that hit depth limit

        Returns:
            Dict indicating truncation
        """
        return {
            "_mcp_truncated": True,
            "_mcp_type": type(value).__name__,
        }


# Convenience functions for common use cases


def convert_matlab_value(
    value: Any,
    max_array_size: int = 1000,
    use_attrdict: bool = False,
    depth_limit: int = 10,
) -> Any:
    """Convert a MATLAB value to Python native types.

    This is a convenience function for one-off conversions.

    Args:
        value: MATLAB value to convert
        max_array_size: Arrays larger than this become summaries
        use_attrdict: Use AttrDict for structs
        depth_limit: Maximum recursion depth

    Returns:
        Python native type

    Example:
        >>> result = convert_matlab_value(matlab_struct, use_attrdict=True)
        >>> result.field_name  # Attribute-style access
    """
    config = ConversionConfig(
        max_array_size=max_array_size,
        use_attrdict=use_attrdict,
        depth_limit=depth_limit,
    )
    converter = MatlabConverter(config)
    return converter.convert(value)


def convert_workspace(
    workspace: dict,
    max_array_size: int = 1000,
    depth_limit: int = 10,
) -> dict:
    """Convert an entire MATLAB workspace to Python native types.

    Args:
        workspace: Dict of variable names to MATLAB values
        max_array_size: Arrays larger than this become summaries
        depth_limit: Maximum recursion depth

    Returns:
        Dict of variable names to Python native values

    Example:
        >>> workspace = engine.get_workspace()
        >>> converted = convert_workspace(workspace)
    """
    config = ConversionConfig(
        max_array_size=max_array_size,
        depth_limit=depth_limit,
    )
    converter = MatlabConverter(config)

    return {name: converter.convert(value) for name, value in workspace.items()}
