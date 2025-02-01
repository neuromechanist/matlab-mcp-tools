"""Test MATLAB MCP server initialization and cleanup."""

import asyncio
import os
from pathlib import Path

from matlab_mcp.server import MatlabServer
from matlab_mcp.models import FigureFormat


async def test_server_initialization():
    """Test server initialization sequence."""
    print("\nTesting server initialization...")
    
    server = MatlabServer()
    
    # Test initial state
    assert not server._initialized
    assert server.engine.eng is None
    
    # Test initialization
    await server.initialize()
    assert server._initialized
    assert server.engine.eng is not None
    print("Server initialization successful")
    
    # Clean up
    server.close()


async def test_figure_cleanup():
    """Test figure capture and cleanup."""
    print("\nTesting figure capture and cleanup...")
    
    server = MatlabServer()
    await server.initialize()
    
    # Create a test plot
    result = await server.engine.execute(
        "figure; plot(1:10); title('Test Plot')",
        capture_plots=True
    )
    
    # Verify figures were captured
    assert len(result.figures) > 0
    assert any(fig.format == FigureFormat.PNG for fig in result.figures)
    assert any(fig.format == FigureFormat.SVG for fig in result.figures)
    print("Figure capture successful")
    
    # Verify figures were cleaned up in MATLAB
    fig_count = server.engine.eng.eval('length(get(groot, "Children"))', nargout=1)
    assert fig_count == 0
    print("Figure cleanup successful")
    
    # Verify temporary files were cleaned up
    output_dir = server.engine.output_dir
    assert not any(output_dir.glob("figure_*.png"))
    assert not any(output_dir.glob("figure_*.svg"))
    print("Temporary file cleanup successful")
    
    # Clean up
    server.close()


async def test_concurrent_requests():
    """Test handling of concurrent protocol requests."""
    print("\nTesting concurrent protocol requests...")
    
    server = MatlabServer()
    
    # Simulate concurrent protocol requests
    results = await asyncio.gather(
        server._list_tools(),
        server._list_resources(),
        server._list_resource_templates()
    )
    
    # Verify all requests completed successfully
    assert all(result is not None for result in results)
    print("Concurrent request handling successful")
    
    # Verify server was initialized only once
    assert server._initialized
    assert server.engine.eng is not None
    print("Single initialization verified")
    
    # Clean up
    server.close()


async def run_tests():
    """Run all initialization and cleanup tests."""
    try:
        await test_server_initialization()
        await test_figure_cleanup()
        await test_concurrent_requests()
        print("\nAll initialization and cleanup tests passed!")
        
    except Exception as e:
        print(f"\nTest failed: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(run_tests())
