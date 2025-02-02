"""Test EMG simulation using MATLAB MCP server."""

import asyncio
import os
from pathlib import Path
from matlab_mcp.server import MatlabServer


async def test_emg():
    """Test EMG simulation."""
    print("\nTesting EMG simulation...")
    
    server = MatlabServer()
    await server.initialize()
    
    try:
        # Add matlab_scripts directory to MATLAB path
        script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'matlab_scripts'))
        print(f"Adding script directory to path: {script_dir}")
        await server.engine.execute(f"addpath(genpath('{script_dir}'))")
        
        # Verify the path was added
        await server.engine.execute("path")
        
        print("Running EMG simulation...")
        # Run the EMG simulation
        result = await server.engine.execute(
            "simulate_emg",
            capture_plots=True
        )
        print(f"Simulation complete. Result: {result}")
        
        # Save captured figures
        output_dir = Path("test_output")
        output_dir.mkdir(exist_ok=True)
        
        print(f"Number of figures captured: {len(result.figures)}")
        if len(result.figures) > 0:
            print("EMG simulation and plotting successful!")
            print("Saving figures...")
            for i, fig_data in enumerate(result.figures):
                output_path = output_dir / f"emg_figure_{i}.{fig_data.format}"
                output_path.write_bytes(fig_data.data)
                print(f"Saved figure to: {output_path}")
        else:
            print("No figures were captured")
            
    except Exception as e:
        print(f"Test failed: {str(e)}")
        raise
    finally:
        # Clean up
        server.close()


if __name__ == "__main__":
    asyncio.run(test_emg())
