#!/bin/bash
set -euo pipefail

# Define variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATLAB_PATH=${MATLAB_PATH}

# Print header
echo "Setting up matlab-mcp-server with pip"
echo "MATLAB path: $MATLAB_PATH"
echo "Project dir: $SCRIPT_DIR"

# Check if MATLAB exists
if [ ! -d "$MATLAB_PATH" ]; then
    echo "Error: MATLAB not found at $MATLAB_PATH"
    echo "Please set the MATLAB_PATH environment variable to the correct location"
    exit 1
fi

# Install matlabengine first from MATLAB installation
echo -e "\nInstalling MATLAB engine"
cd "$MATLAB_PATH/extern/engines/python"
python -m pip install .
cd "$SCRIPT_DIR"

# Build and install the package with pip
echo -e "\nBuilding and installing matlab-mcp-server with pip"
pip install -e .

# Test if the installation was successful
echo -e "\nTesting installation"
if command -v matlab-mcp-server &> /dev/null; then
    echo "Installation successful! matlab-mcp-server is available in PATH"
else
    echo "Warning: matlab-mcp-server not found in PATH"
    echo "Please check the logs for more information"
    exit 1
fi

# Update the MCP configuration
echo -e "\nUpdating MCP configuration"
cat > mcp-pip.json << EOF
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp-server",
      "args": [],
      "env": {
        "MATLAB_PATH": "${MATLAB_PATH}",
        "PATH": "${MATLAB_PATH}/bin:${PATH}"
      },
      "disabled": false,
      "autoApprove": [
        "list_tools",
        "get_script_sections"
      ]
    }
  }
}
EOF

echo -e "\nSetup complete!"
echo "To use the MATLAB MCP server with Cursor/Cline, copy the provided configuration:"
echo "cp mcp-pip.json ~/.cursor/mcp.json"
echo ""
echo "To manually start the server, run:"
echo "matlab-mcp-server"
