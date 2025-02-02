"""Simple test script for MATLAB engine functionality."""

import asyncio
from pathlib import Path
import sys

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from matlab_mcp.engine import MatlabEngine


async def test_engine():
    """Test basic MATLAB engine functionality."""
    engine = MatlabEngine()

    try:
        # Initialize engine
        await engine.initialize()

        # Run a simple MATLAB command
        result = await engine.execute('2 + 2')
        print(f"2 + 2 = {result.output}")

        # Try plotting
        script_path = Path(__file__).parent / "matlab_scripts" / "test_plot.m"
        if script_path.exists():
            print(f"\nExecuting plot script: {script_path}")
            result = await engine.execute(
                str(script_path),
                is_file=True,
                capture_plots=True
            )
            print(f"Generated {len(result.figures)} figures")

            # Save figures
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)

            for i, fig in enumerate(result.figures):
                ext = ".png" if fig.format.value == "png" else ".svg"
                output_file = output_dir / f"figure_{i}{ext}"
                output_file.write_bytes(fig.data)
                print(f"Saved {output_file}")

    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        engine.close()


if __name__ == "__main__":
    asyncio.run(test_engine())
