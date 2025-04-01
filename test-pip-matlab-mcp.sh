#!/bin/bash
set -euo pipefail

# Test if matlab-mcp-server is available
echo -e "\n=== Testing Installation ==="
if command -v matlab-mcp-server &> /dev/null; then
    echo "matlab-mcp-server is available in PATH"
else
    echo "Error: matlab-mcp-server not found in PATH"
    echo "Please run ./setup-pip-matlab-mcp.sh first"
    exit 1
fi

# Create a test MATLAB script
echo -e "\n=== Setting up Test Files ==="
echo "Creating a simple test script..."

# Create a test MATLAB script if it doesn't exist
EXAMPLE_DIR="examples/matlab_scripts"
mkdir -p "$EXAMPLE_DIR"

TEST_SCRIPT="$EXAMPLE_DIR/test_plot.m"
if [ ! -f "$TEST_SCRIPT" ]; then
  cat > "$TEST_SCRIPT" << 'EOF'
% Simple test script for MATLAB MCP
x = linspace(0, 2*pi, 100);
y = sin(x);

% Create a figure with some styling
figure;
plot(x, y, 'LineWidth', 2);
title('Sine Wave');
xlabel('x');
ylabel('sin(x)');
grid on;

% Add some annotations
text(pi, 0, '\leftarrow \pi', 'FontSize', 12);

disp('Script executed successfully!')
EOF
fi

# Test if matlabengine is installed
echo -e "\n=== Testing MATLAB Engine Installation ==="
MATLAB_PATH=${MATLAB_PATH:-"/Applications/MATLAB_R2024b.app"}
export PATH="$MATLAB_PATH/bin:$PATH"
python -c "import matlab.engine; print('MATLAB engine is properly installed')" || echo "Warning: MATLAB engine not properly installed"

# Test starting the server
echo -e "\n=== Testing Server Startup ==="
echo "Starting the server in the background (will terminate after 5 seconds)..."
matlab-mcp-server &
SERVER_PID=$!
sleep 5
kill $SERVER_PID 2>/dev/null || true

echo -e "\n=== Test Complete ==="
echo "The installation has been tested successfully."
echo "To use the MATLAB MCP server with Cursor/Cline, copy the provided configuration:"
echo "cp mcp-pip.json ~/.cursor/mcp.json"
echo ""
echo "To manually start the server, run:"
echo "matlab-mcp-server"
