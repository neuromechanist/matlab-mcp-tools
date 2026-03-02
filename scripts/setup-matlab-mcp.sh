#!/bin/bash
set -euo pipefail

# Define variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_NAME=".venv"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_DIR/$VENV_NAME"

# ---------------------------------------------------------------------------
# MATLAB-Python compatibility table
# Format: MATLAB_VERSION PYTHON_VERSIONS(colon-separated) ENGINE_PREFIX
# ---------------------------------------------------------------------------
declare -A MATLAB_PYTHON_VERSIONS=(
    ["R2025b"]="3.12:3.11:3.10:3.9"
    ["R2025a"]="3.12:3.11:3.10:3.9"
    ["R2024b"]="3.12:3.11:3.10:3.9"
    ["R2024a"]="3.11:3.10:3.9"
    ["R2023b"]="3.11:3.10:3.9"
    ["R2023a"]="3.10:3.9:3.8"
    ["R2022b"]="3.10:3.9:3.8"
)

declare -A MATLAB_ENGINE_VERSION=(
    ["R2025b"]="25.2"
    ["R2025a"]="25.1"
    ["R2024b"]="24.2"
    ["R2024a"]="24.1"
    ["R2023b"]="23.2"
    ["R2023a"]="9.14"
    ["R2022b"]="9.13"
)

# ---------------------------------------------------------------------------
# Auto-detect MATLAB installation
# ---------------------------------------------------------------------------
auto_detect_matlab() {
    local found_path=""

    if [[ "$(uname)" == "Darwin" ]]; then
        # Check /Applications (globs sort alphabetically; keep last = newest)
        for p in /Applications/MATLAB_R*.app; do
            [ -d "$p" ] && found_path="$p"
        done
        # Check volumes if not found yet
        if [ -z "$found_path" ]; then
            for vol in /Volumes/*/Applications/MATLAB_R*.app; do
                [ -d "$vol" ] && found_path="$vol"
            done
        fi
    elif [[ "$(uname)" == "Linux" ]]; then
        for p in /usr/local/MATLAB/R*; do
            [ -d "$p" ] && found_path="$p"
        done
    fi

    echo "$found_path"
}

extract_matlab_version() {
    local path="$1"
    local name
    name="$(basename "$path")"
    # Match R followed by 4 digits and a/b, e.g. R2024b
    echo "$name" | grep -oE 'R[0-9]{4}[ab]' | head -1
}

# ---------------------------------------------------------------------------
# Determine MATLAB path
# ---------------------------------------------------------------------------
MATLAB_PATH="${MATLAB_PATH:-}"

if [ -z "$MATLAB_PATH" ]; then
    echo "MATLAB_PATH not set, auto-detecting..."
    MATLAB_PATH="$(auto_detect_matlab)"
fi

if [ -z "$MATLAB_PATH" ] || [ ! -d "$MATLAB_PATH" ]; then
    echo "Error: MATLAB installation not found."
    echo "Please set the MATLAB_PATH environment variable to your MATLAB directory."
    echo "Example: export MATLAB_PATH=/Applications/MATLAB_R2024b.app"
    exit 1
fi

echo "Detected MATLAB at: $MATLAB_PATH"

# ---------------------------------------------------------------------------
# Extract MATLAB version
# ---------------------------------------------------------------------------
MATLAB_VERSION="$(extract_matlab_version "$MATLAB_PATH")"

if [ -z "$MATLAB_VERSION" ]; then
    echo "Warning: Could not determine MATLAB version from path: $MATLAB_PATH"
    echo "Falling back to Python 3.11 and unpinned matlabengine"
    PYTHON_VERSION="3.11"
    ENGINE_PIN=""
else
    echo "Detected MATLAB version: $MATLAB_VERSION"

    # Look up compatible Python versions
    COMPAT_VERSIONS="${MATLAB_PYTHON_VERSIONS[$MATLAB_VERSION]:-}"
    ENGINE_PREFIX="${MATLAB_ENGINE_VERSION[$MATLAB_VERSION]:-}"

    if [ -z "$COMPAT_VERSIONS" ]; then
        echo "Warning: Unknown MATLAB version $MATLAB_VERSION, falling back to Python 3.11"
        PYTHON_VERSION="3.11"
        ENGINE_PIN=""
    else
        # Select first (most recent) compatible Python version
        PYTHON_VERSION="${COMPAT_VERSIONS%%:*}"
        if [ -n "$ENGINE_PREFIX" ]; then
            ENGINE_PIN="matlabengine==${ENGINE_PREFIX}.*"
        else
            ENGINE_PIN=""
        fi
    fi
fi

echo "Selected Python version: $PYTHON_VERSION"
if [ -n "${ENGINE_PIN:-}" ]; then
    echo "Will pin: $ENGINE_PIN"
fi

# Print header
echo ""
echo "Setting up matlab-mcp-server with uv"
echo "MATLAB path: $MATLAB_PATH"
echo "Project dir: $SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Check uv
# ---------------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    echo "Error: uv package manager not found"
    echo "Please install uv first: https://github.com/astral-sh/uv"
    echo "You can install it with: curl -Ls https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# ---------------------------------------------------------------------------
# Create virtual environment
# ---------------------------------------------------------------------------
echo ""
echo "Setting up virtual environment"
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating new virtual environment with Python $PYTHON_VERSION"
    uv venv "$VENV_PATH" --python "$PYTHON_VERSION"
else
    echo "Virtual environment already exists at $VENV_PATH"
    echo "To recreate with correct Python version, remove it first:"
    echo "  rm -rf $VENV_PATH"
fi

# Activate the virtual environment
echo "Activating virtual environment"
source "$VENV_PATH/bin/activate"

# ---------------------------------------------------------------------------
# Install matlabengine
# ---------------------------------------------------------------------------
echo ""
echo "Installing MATLAB engine"

if [ -d "$MATLAB_PATH/extern/engines/python" ]; then
    # Install from local MATLAB installation (always authoritative)
    cd "$MATLAB_PATH/extern/engines/python"
    uv pip install .
    cd "$SCRIPT_DIR"
elif [ -n "${ENGINE_PIN:-}" ]; then
    # Fallback: install pinned version from PyPI
    echo "Local MATLAB engine directory not found, installing from PyPI: $ENGINE_PIN"
    uv pip install "$ENGINE_PIN"
else
    echo "Warning: Could not find MATLAB engine directory or determine version."
    echo "Installing unpinned matlabengine from PyPI (may not match your MATLAB)"
    uv pip install matlabengine
fi

# ---------------------------------------------------------------------------
# Install the package
# ---------------------------------------------------------------------------
echo ""
echo "Building and installing matlab-mcp-server"
uv pip install -e .

# ---------------------------------------------------------------------------
# Verify installation
# ---------------------------------------------------------------------------
echo ""
echo "Testing installation"
if command -v "$VENV_PATH/bin/matlab-mcp-server" &> /dev/null; then
    echo "Installation successful! matlab-mcp-server is available"
else
    echo "Warning: matlab-mcp-server not found in virtual environment"
    echo "Please check the logs for more information"
    exit 1
fi

# ---------------------------------------------------------------------------
# Update MCP configuration
# ---------------------------------------------------------------------------
echo ""
echo "Updating MCP configuration"
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

echo ""
echo "Setup complete!"
echo ""
echo "Summary:"
echo "  MATLAB:  $MATLAB_PATH ($MATLAB_VERSION)"
echo "  Python:  $PYTHON_VERSION"
if [ -n "${ENGINE_PIN:-}" ]; then
    echo "  Engine:  $ENGINE_PIN"
fi
echo ""
echo "To use the MATLAB MCP server with Cursor/Cline, copy the configuration:"
echo "  cp mcp-pip.json ~/.cursor/mcp.json"
echo ""
echo "To manually start the server:"
echo "  $VENV_PATH/bin/matlab-mcp-server"
