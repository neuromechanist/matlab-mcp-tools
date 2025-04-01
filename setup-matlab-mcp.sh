#!/bin/bash
set -euo pipefail

# Define variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MATLAB_PATH=${MATLAB_PATH}
VENV_NAME=".venv"
VENV_PATH="$SCRIPT_DIR/$VENV_NAME"

# Print header
echo "Setting up matlab-mcp-server with uv and pip"
echo "MATLAB path: $MATLAB_PATH"
echo "Project dir: $SCRIPT_DIR"

# Check if MATLAB exists
if [ ! -d "$MATLAB_PATH" ]; then
    echo "Error: MATLAB not found at $MATLAB_PATH"
    echo "Please set the MATLAB_PATH environment variable to the correct location"
    exit 1
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv package manager not found"
    echo "Please install uv first: https://github.com/astral-sh/uv"
    echo "You can install it with: pip install uv"
    exit 1
fi

# Create a virtual environment if it doesn't exist
echo -e "\nSetting up virtual environment"
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating new virtual environment with uv"
    uv venv "$VENV_PATH" --python 3.11 # TODO: make this dynamic based on the version of MATLAB
else
    echo "Virtual environment already exists at $VENV_PATH"
fi

# Activate the virtual environment
echo "Activating virtual environment"
source "$VENV_PATH/bin/activate"

# Install matlabengine first from MATLAB installation
echo -e "\nInstalling MATLAB engine"
cd "$MATLAB_PATH/extern/engines/python"
uv pip install .
cd "$SCRIPT_DIR"

# Build and install the package with pip
echo -e "\nBuilding and installing matlab-mcp-server with uv pip"
uv pip install -e .

# Test if the installation was successful
echo -e "\nTesting installation"
# Only check if the command exists in the virtual environment
if command -v "$VENV_PATH/bin/matlab-mcp-server" &> /dev/null; then
    echo "Installation successful! matlab-mcp-server is available in the virtual environment"
else
    echo "Warning: matlab-mcp-server not found in virtual environment"
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
echo "$VENV_PATH/bin/matlab-mcp-server"
