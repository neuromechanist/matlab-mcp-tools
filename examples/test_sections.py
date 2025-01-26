"""Test script for MATLAB section execution."""

import asyncio
from pathlib import Path

from matlab_mcp.server import MatlabServer
from matlab_mcp.utils.section_parser import get_section_info


async def test_section_execution():
    """Test section-based MATLAB script execution."""
    print("Testing MATLAB Section Execution...")
    
    server = MatlabServer()
    
    # Test section parsing
    print("\nTesting section parsing...")
    script_path = Path("examples/matlab_scripts/section_test.m")
    if not script_path.exists():
        print(f"Error: Script not found at {script_path}")
        return
        
    sections = get_section_info(script_path)
    print(f"Found {len(sections)} sections:")
    for section in sections:
        print(f"- {section['title']} (lines {section['start_line']}-{section['end_line']})")
        print(f"  Preview: {section['preview']}")
    
    # Test executing each section
    print("\nExecuting sections one by one...")
    for section in sections:
        print(f"\nExecuting section: {section['title']}")
        result = await server.engine.execute_section(
            str(script_path),
            (section['start_line'], section['end_line'])
        )
        
        print("Output:")
        print(result.output)
        
        print("Workspace variables:")
        for var, value in result.workspace.items():
            print(f"- {var}: {value}")
            
        if result.figures:
            print(f"Generated {len(result.figures)} figures")
            
            # Save figures
            output_dir = Path("test_output")
            output_dir.mkdir(exist_ok=True)
            
            for i, fig_data in enumerate(result.figures):
                output_path = output_dir / f"section_{section['start_line']}_figure_{i}.png"
                output_path.write_bytes(fig_data)
                print(f"Saved figure to: {output_path}")
    
    # Clean up
    server.engine.cleanup()
    print("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_section_execution())
