#!/usr/bin/env python3
"""
Test script to benchmark figure compression performance.

This script demonstrates the compression capabilities and measures
bandwidth reduction achieved through the optimization.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from matlab_mcp.engine import MatlabEngine
from matlab_mcp.models import CompressionConfig


async def test_compression_scenarios():
    """Test different compression scenarios and measure performance."""

    # Test configurations
    test_configs = [
        {
            "name": "Original (High Quality)",
            "config": CompressionConfig(
                quality=95,
                dpi=150,
                optimize_for="quality",
                use_file_reference=False,
                smart_optimization=False,
            ),
        },
        {
            "name": "Balanced Compression",
            "config": CompressionConfig(
                quality=75,
                dpi=150,
                optimize_for="size",
                use_file_reference=False,
                smart_optimization=True,
            ),
        },
        {
            "name": "High Compression",
            "config": CompressionConfig(
                quality=50,
                dpi=100,
                optimize_for="size",
                use_file_reference=False,
                smart_optimization=True,
            ),
        },
        {
            "name": "File Reference Mode",
            "config": CompressionConfig(
                quality=75,
                dpi=150,
                optimize_for="size",
                use_file_reference=True,
                smart_optimization=True,
            ),
        },
    ]

    # Test scripts to generate different plot types
    test_scripts = [
        {
            "name": "Simple Line Plot",
            "matlab_code": """
                x = 1:100;
                y = sin(x/10);
                figure; plot(x, y);
                title('Simple Line Plot');
                xlabel('X'); ylabel('Y');
            """,
        },
        {
            "name": "Complex Surface Plot",
            "matlab_code": """
                [X,Y] = meshgrid(-5:.5:5);
                Z = peaks(X,Y);
                figure; surf(X,Y,Z);
                title('Complex Surface Plot');
                xlabel('X'); ylabel('Y'); zlabel('Z');
                colorbar;
            """,
        },
        {
            "name": "Image-based Plot",
            "matlab_code": """
                data = rand(100, 100);
                figure; imagesc(data);
                title('Random Image Data');
                colormap('jet'); colorbar;
            """,
        },
    ]

    print("=== MATLAB MCP Figure Compression Benchmark ===\n")

    # Initialize MATLAB engine
    engine = MatlabEngine()
    await engine.initialize()

    results = []

    try:
        for script in test_scripts:
            print(f"Testing: {script['name']}")
            print("-" * 50)

            # Generate the plot
            await engine.execute(script["matlab_code"], capture_plots=False)

            for config_test in test_configs:
                config = config_test["config"]
                config_name = config_test["name"]

                start_time = time.time()

                # Capture figures with this configuration
                figures = await engine._capture_figures(config)

                end_time = time.time()
                processing_time = end_time - start_time

                if figures:
                    fig = figures[0]  # Take first figure

                    # Calculate sizes and compression ratio
                    original_size = fig.original_size or 0
                    compressed_size = fig.compressed_size or 0

                    if original_size > 0:
                        compression_ratio = (1 - compressed_size / original_size) * 100
                    else:
                        compression_ratio = 0

                    # For file reference mode, data transfer would be minimal
                    transfer_size = 0 if config.use_file_reference else compressed_size

                    result = {
                        "plot_type": script["name"],
                        "config": config_name,
                        "original_size_kb": original_size / 1024,
                        "compressed_size_kb": compressed_size / 1024,
                        "transfer_size_kb": transfer_size / 1024,
                        "compression_ratio": compression_ratio,
                        "processing_time": processing_time,
                        "quality": config.quality,
                        "dpi": config.dpi,
                        "smart_optimization": config.smart_optimization,
                    }

                    results.append(result)

                    print(f"  {config_name}:")
                    print(f"    Original Size: {result['original_size_kb']:.1f} KB")
                    print(f"    Compressed Size: {result['compressed_size_kb']:.1f} KB")
                    print(f"    Transfer Size: {result['transfer_size_kb']:.1f} KB")
                    print(f"    Compression Ratio: {result['compression_ratio']:.1f}%")
                    print(f"    Processing Time: {result['processing_time']:.3f}s")
                    print(f"    Quality/DPI: {result['quality']}/{result['dpi']}")
                    print()
                else:
                    print(f"  {config_name}: No figures generated")
                    print()

            # Clear figures for next test
            await engine.cleanup_figures()
            print()

        # Summary
        print("=== COMPRESSION SUMMARY ===")
        print()

        # Calculate average compression ratios by configuration
        config_summaries = {}
        for result in results:
            config = result["config"]
            if config not in config_summaries:
                config_summaries[config] = {
                    "total_original": 0,
                    "total_compressed": 0,
                    "total_transfer": 0,
                    "count": 0,
                }

            config_summaries[config]["total_original"] += result["original_size_kb"]
            config_summaries[config]["total_compressed"] += result["compressed_size_kb"]
            config_summaries[config]["total_transfer"] += result["transfer_size_kb"]
            config_summaries[config]["count"] += 1

        print("Average Results by Configuration:")
        print("-" * 40)

        for config, summary in config_summaries.items():
            avg_original = summary["total_original"] / summary["count"]
            avg_compressed = summary["total_compressed"] / summary["count"]
            avg_transfer = summary["total_transfer"] / summary["count"]

            compression_ratio = (
                (1 - avg_compressed / avg_original) * 100 if avg_original > 0 else 0
            )
            bandwidth_reduction = (
                (1 - avg_transfer / avg_original) * 100 if avg_original > 0 else 0
            )

            print(f"{config}:")
            print(f"  Average Original: {avg_original:.1f} KB")
            print(f"  Average Compressed: {avg_compressed:.1f} KB")
            print(f"  Average Transfer: {avg_transfer:.1f} KB")
            print(f"  Compression Ratio: {compression_ratio:.1f}%")
            print(f"  Bandwidth Reduction: {bandwidth_reduction:.1f}%")
            print()

        print("✅ Compression benchmark completed successfully!")

    except Exception as e:
        print(f"❌ Error during benchmark: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Clean up
        engine.close()


if __name__ == "__main__":
    # Set up environment
    os.environ.setdefault("MATLAB_PATH", "/Volumes/S1/Applications/MATLAB_R2024b.app")

    # Run benchmark
    asyncio.run(test_compression_scenarios())
