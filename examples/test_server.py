"""Test script for MATLAB MCP server."""

import asyncio
from pathlib import Path

from matlab_mcp.server import MatlabServer


async def test_basic_execution():
    """Test basic MATLAB script execution."""
    print("Testing MATLAB MCP Server...")
    
    server = MatlabServer()
    
    # Test direct command execution
    print("\nTesting direct command execution...")
    result = await server.engine.execute(
        "a = 5; b = 10; c = a + b; fprintf('Sum: %d\\n', c)"
    )
    print(f"Output: {result.output}")
    print(f"Workspace: {result.workspace}")
    
    # Test script file execution
    print("\nTesting script file execution...")
    script_path = Path("examples/matlab_scripts/test_plot.m")
    if not script_path.exists():
        print(f"Error: Script not found at {script_path}")
        return
        
    result = await server.engine.execute(
        str(script_path),
        is_file=True
    )
    print(f"Output: {result.output}")
    print(f"Workspace: {result.workspace}")
    print(f"Number of figures captured: {len(result.figures)}")
    
    # Save captured figures
    output_dir = Path("test_output")
    output_dir.mkdir(exist_ok=True)
    
    for i, fig_data in enumerate(result.figures):
        output_path = output_dir / f"figure_{i}.png"
        output_path.write_bytes(fig_data)
        print(f"Saved figure to: {output_path}")
    
    # Clean up
    server.engine.cleanup()
    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_basic_execution())
