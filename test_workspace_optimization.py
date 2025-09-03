#!/usr/bin/env python3
"""
Test script for measuring and benchmarking workspace optimization.
Tests current vs optimized workspace transfer to measure token reduction.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from matlab_mcp.engine import MatlabEngine


def count_tokens(text: str) -> int:
    """Estimate token count using character-based approximation (4 chars ~ 1 token)."""
    return len(text) // 4


def measure_json_size(data: Dict[str, Any]) -> tuple[int, int]:
    """Measure the JSON size and estimate token count."""
    json_str = json.dumps(data, default=str)
    byte_size = len(json_str.encode("utf-8"))
    estimated_tokens = count_tokens(json_str)
    return byte_size, estimated_tokens


async def test_current_implementation():
    """Test current workspace implementation with various array sizes."""
    print("=== Testing Current Workspace Implementation ===")

    engine = MatlabEngine()
    await engine.initialize()

    test_cases = [
        ("small_matrix", "small_matrix = ones(10, 10);"),
        ("medium_matrix", "medium_matrix = rand(100, 100);"),
        ("large_matrix", "large_matrix = rand(1000, 1000);"),
        # ("huge_matrix", "huge_matrix = rand(2000, 2000);"),  # Comment out initially
    ]

    results = {}

    for name, matlab_code in test_cases:
        print(f"\n--- Testing {name} ---")

        # Create the matrix in MATLAB
        result = await engine.execute(matlab_code)
        if result.error:
            print(f"Error creating {name}: {result.error}")
            continue

        # Get workspace
        workspace = await engine.get_workspace()

        # Measure size and tokens
        byte_size, token_count = measure_json_size(workspace)

        print(f"Variable: {name}")
        print(f"JSON size: {byte_size:,} bytes ({byte_size / 1024 / 1024:.2f} MB)")
        print(f"Estimated tokens: {token_count:,}")

        # Show structure for large matrix
        if name == "large_matrix":
            print("Optimized structure:")
            import json

            print(json.dumps(workspace[name], indent=2))

        results[name] = {
            "byte_size": byte_size,
            "token_count": token_count,
            "workspace_keys": list(workspace.keys()),
        }

    engine.close()
    return results


async def test_matrix_sizes():
    """Test various matrix sizes to understand scaling."""
    print("\n=== Matrix Size Scaling Analysis ===")

    engine = MatlabEngine()
    await engine.initialize()

    sizes = [(10, 10), (50, 50), (100, 100), (200, 200), (500, 500), (1000, 1000)]

    for rows, cols in sizes:
        elements = rows * cols
        matlab_code = f"test_matrix = rand({rows}, {cols});"

        print(f"\nTesting {rows}x{cols} matrix ({elements:,} elements)")

        # Create matrix
        result = await engine.execute(matlab_code)
        if result.error:
            print(f"Error: {result.error}")
            continue

        # Get workspace
        workspace = await engine.get_workspace()

        # Measure
        byte_size, token_count = measure_json_size(workspace)

        print(f"  Size: {byte_size:,} bytes")
        print(f"  Tokens: {token_count:,}")
        print(f"  Tokens per element: {token_count / elements:.2f}")

        # Clear the variable to avoid accumulation
        await engine.execute("clear test_matrix;")

    engine.close()


if __name__ == "__main__":
    print("MATLAB Workspace Optimization Test")
    print("=" * 50)

    # Test current implementation
    current_results = asyncio.run(test_current_implementation())

    # Test scaling
    asyncio.run(test_matrix_sizes())

    print("\n=== Summary of Current Implementation ===")
    for name, data in current_results.items():
        print(f"{name}: {data['token_count']:,} tokens, {data['byte_size']:,} bytes")
