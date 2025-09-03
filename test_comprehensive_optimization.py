#!/usr/bin/env python3
"""
Comprehensive test suite for workspace optimization with different data types and configurations.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from matlab_mcp.engine import MatlabEngine, WorkspaceConfig


def count_tokens(text: str) -> int:
    """Estimate token count using character-based approximation (4 chars ~ 1 token)."""
    return len(text) // 4


def measure_json_size(data: dict) -> tuple[int, int]:
    """Measure the JSON size and estimate token count."""
    json_str = json.dumps(data, default=str)
    byte_size = len(json_str.encode("utf-8"))
    estimated_tokens = count_tokens(json_str)
    return byte_size, estimated_tokens


async def test_different_data_types():
    """Test optimization with various MATLAB data types."""
    print("=== Testing Different MATLAB Data Types ===")

    engine = MatlabEngine()
    await engine.initialize()

    test_cases = [
        ("tiny_array", "tiny_array = [1, 2, 3];"),  # Small array
        ("small_matrix", "small_matrix = rand(5, 5);"),  # Small 2D
        ("medium_array", "medium_array = ones(1, 500);"),  # Medium 1D
        ("large_matrix", "large_matrix = rand(500, 500);"),  # Large 2D
        ("integer_array", "integer_array = int32(1:1000);"),  # Integer type
        ("logical_array", "logical_array = true(100, 100);"),  # Logical type
        (
            "complex_array",
            "complex_array = complex(rand(200, 200), rand(200, 200));",
        ),  # Complex
        ("string_var", "string_var = 'This is a test string variable';"),  # String
        ("cell_array", "cell_array = {1, 'hello', [1 2 3]};"),  # Cell array
    ]

    results = {}
    total_original_estimate = 0
    total_optimized = 0

    for name, matlab_code in test_cases:
        print(f"\n--- Testing {name} ---")

        # Create the variable in MATLAB
        result = await engine.execute(matlab_code)
        if result.error:
            print(f"Error creating {name}: {result.error}")
            continue

        # Get workspace
        workspace = await engine.get_workspace()

        # Measure size and tokens
        byte_size, token_count = measure_json_size(workspace)

        # Estimate original size if this was fully serialized
        if name in workspace:
            var_info = workspace[name]
            if isinstance(var_info, dict) and "_mcp_type" in var_info:
                # This is an optimized representation - estimate original size
                elements = var_info.get("total_elements", 1)
                # Rough estimate: 20 chars per number in JSON
                original_estimate = elements * 20
                compression_ratio = (
                    (1 - byte_size / original_estimate) * 100
                    if original_estimate > 0
                    else 0
                )
                print(f"  Original estimate: ~{original_estimate:,} bytes")
                print(f"  Compressed to: {byte_size:,} bytes")
                print(f"  Compression: {compression_ratio:.2f}%")
                total_original_estimate += original_estimate
            else:
                print(f"  Full data returned: {byte_size:,} bytes")
                total_original_estimate += byte_size

        print(f"  Actual size: {byte_size:,} bytes")
        print(f"  Tokens: {token_count:,}")

        total_optimized += byte_size
        results[name] = {"byte_size": byte_size, "token_count": token_count}

    # Overall compression summary
    if total_original_estimate > 0:
        overall_compression = (1 - total_optimized / total_original_estimate) * 100
        print("\n=== Overall Compression Summary ===")
        print(f"Estimated original total: {total_original_estimate:,} bytes")
        print(f"Optimized total: {total_optimized:,} bytes")
        print(f"Overall compression: {overall_compression:.2f}%")

    engine.close()
    return results


async def test_configurable_thresholds():
    """Test optimization with different threshold configurations."""
    print("\n\n=== Testing Configurable Thresholds ===")

    # Test with very aggressive compression
    aggressive_config = WorkspaceConfig(
        small_threshold=10,  # Only tiny arrays get full data
        medium_threshold=100,  # Very small medium threshold
        preview_elements=2,  # Minimal preview
        max_string_length=50,  # Short strings
    )

    # Test with conservative compression
    conservative_config = WorkspaceConfig(
        small_threshold=1000,  # Larger arrays get full data
        medium_threshold=50000,  # Higher medium threshold
        preview_elements=10,  # More preview elements
        max_string_length=500,  # Longer strings
    )

    test_matrix_code = "test_array = rand(200, 200);"  # 40K elements

    for config_name, config in [
        ("Aggressive", aggressive_config),
        ("Conservative", conservative_config),
    ]:
        print(f"\n--- {config_name} Configuration ---")
        print(f"  Small threshold: {config.small_threshold} elements")
        print(f"  Medium threshold: {config.medium_threshold} elements")
        print(f"  Preview elements: {config.preview_elements}")

        engine = MatlabEngine(workspace_config=config)
        await engine.initialize()

        # Create test array
        result = await engine.execute(test_matrix_code)
        if result.error:
            print(f"Error: {result.error}")
            continue

        workspace = await engine.get_workspace()
        byte_size, token_count = measure_json_size(workspace)

        print(f"  Result size: {byte_size:,} bytes")
        print(f"  Tokens: {token_count:,}")

        # Show the structure
        if "test_array" in workspace:
            var_data = workspace["test_array"]
            if isinstance(var_data, dict):
                print(f"  Type: {var_data.get('_mcp_type', 'full_data')}")
                if "sample_data" in var_data:
                    print(f"  Sample elements: {len(var_data['sample_data'])}")

        engine.close()


async def run_all_tests():
    """Run the complete test suite."""
    print("MATLAB Workspace Comprehensive Optimization Test")
    print("=" * 60)

    # Test different data types
    type_results = await test_different_data_types()

    # Test configurable thresholds
    await test_configurable_thresholds()

    print("\n" + "=" * 60)
    print("COMPREHENSIVE TEST COMPLETE")

    return type_results


if __name__ == "__main__":
    asyncio.run(run_all_tests())
