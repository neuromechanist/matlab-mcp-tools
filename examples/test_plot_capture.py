"""Test script for MATLAB plot capture functionality."""

import asyncio
import os
import traceback
from pathlib import Path
import sys

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from matlab_mcp.server import MatlabServer
from matlab_mcp.models import FigureFormat


async def test_plot_capture():
    """Test plot capture in both PNG and SVG formats."""
    # Set MATLAB environment
    matlab_path = os.getenv('MATLAB_PATH', '/Applications/MATLAB_R2024a.app')
    print(f"MATLAB_PATH: {matlab_path}")

    # Ask user for correct MATLAB path if default doesn't exist
    if not os.path.exists(matlab_path):
        print(f"MATLAB not found at {matlab_path}")
        print("Please enter the correct path to your MATLAB installation:")
        matlab_path = input().strip()
        if not matlab_path:
            print("No path provided, exiting...")
            return
        if not os.path.exists(matlab_path):
            print(f"Path {matlab_path} does not exist, exiting...")
            return
        os.environ['MATLAB_PATH'] = matlab_path
        print(f"Set MATLAB_PATH to: {matlab_path}")

    server = MatlabServer()
    print("Created MatlabServer instance")

    try:
        print("Initializing MATLAB engine...")
        await server.engine.initialize()
        print("MATLAB engine initialized")

        # Execute test plot script
        script_path = Path(__file__).parent / "matlab_scripts" / "test_plot.m"
        if not script_path.exists():
            print(f"Test script not found at {script_path}")
            return

        print(f"Executing script: {script_path}")
        result = await server.engine.execute(
            str(script_path),
            is_file=True,
            capture_plots=True
        )

        if result.error:
            print(f"Error executing script: {result.error}")
            return

        # Verify we got both PNG and SVG versions
        png_figures = [f for f in result.figures if f.format == FigureFormat.PNG]
        svg_figures = [f for f in result.figures if f.format == FigureFormat.SVG]

        print(f"Generated {len(png_figures)} PNG figures")
        print(f"Generated {len(svg_figures)} SVG figures")

        # Save figures to verify content
        output_dir = Path("test_output")
        output_dir.mkdir(exist_ok=True)

        for i, fig in enumerate(result.figures):
            ext = ".png" if fig.format == FigureFormat.PNG else ".svg"
            output_file = output_dir / f"figure_{i}{ext}"
            output_file.write_bytes(fig.data)
            print(f"Saved {output_file}")

    except Exception as e:
        print("Error during execution:")
        print(traceback.format_exc())

    finally:
        print("Cleaning up MATLAB engine...")
        server.engine.cleanup()
        print("Cleanup complete")


if __name__ == "__main__":
    asyncio.run(test_plot_capture())
