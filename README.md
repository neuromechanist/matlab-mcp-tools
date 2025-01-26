# MATLAB MCP Tool

A Model Context Protocol (MCP) server that provides tools for developing, running, and debugging MATLAB files. This tool integrates with Cline and other MCP-compatible clients to provide interactive MATLAB development capabilities.

## Prerequisites

- Python 3.8+
- MATLAB with Python Engine installed
- MCP SDK for Python (`pip install modelcontextprotocol`)
- MATLAB Engine for Python (`pip install matlabengine`)

## Features

1. **Execute MATLAB Scripts**
   - Run complete MATLAB scripts
   - Execute individual script sections
   - Maintain workspace context between executions
   - Capture and display plots

2. **Interactive Debugging**
   - Set breakpoints in MATLAB scripts
   - Debug script execution
   - Inspect workspace variables

3. **Section-based Execution**
   - Execute specific sections of MATLAB files
   - Support for cell mode (%% delimited sections)
   - Maintain workspace context between sections

## Installation

1. Clone this repository:
```bash
git clone [repository-url]
cd matlab-mcp-tool
```

2. Create and activate a conda environment:
```bash
conda create -n matlab-mcp python=3.8
conda activate matlab-mcp
```

3. Install dependencies:
```bash
pip install modelcontextprotocol matlabengine
```

## Usage

1. Start the MCP server:
```bash
python src/matlab_bridge.py
```

2. Configure Cline to use the MATLAB MCP server by adding to your Cline configuration:
```json
{
  "mcpServers": {
    "matlab": {
      "command": "python",
      "args": ["/path/to/matlab-mcp-tool/src/matlab_bridge.py"],
      "env": {
        "PYTHONPATH": "/path/to/matlab/engine/installation"
      }
    }
  }
}
```

3. Available Tools:

- **execute_matlab_script**
  ```json
  {
    "script": "x = 1:10;\nplot(x, x.^2);",
    "isFile": false
  }
  ```

- **execute_matlab_section**
  ```json
  {
    "filePath": "analysis.m",
    "sectionStart": 1,
    "sectionEnd": 10
  }
  ```

- **debug_matlab_script**
  ```json
  {
    "script": "debug_script.m",
    "breakpoints": [5, 10, 15]
  }
  ```

## Output Directory

The tool creates an `output` directory in the current working directory to store:
- Plot images generated during script execution
- Debug output files
- Other temporary files

## Error Handling

- Script execution errors are captured and returned with detailed error messages
- Workspace state is preserved even after errors
- Debug sessions are properly cleaned up

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

BSD-3-Clause
