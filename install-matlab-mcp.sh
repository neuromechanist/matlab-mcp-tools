#!/bin/bash
set -euo pipefail

# MATLAB MCP Tools - One-Command Installer
# Auto-detects MATLAB, installs UV if needed, sets up everything automatically

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_NAME=".venv"
VENV_PATH="$SCRIPT_DIR/$VENV_NAME"
MATLAB_PATH=""
PLATFORM=""

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Progress indicator
show_progress() {
    local task="$1"
    echo -e "\n${BLUE}▶${NC} $task"
}

# Detect operating system
detect_platform() {
    show_progress "Detecting platform"
    
    case "$(uname -s)" in
        Darwin)
            PLATFORM="macOS"
            log_info "Detected macOS"
            ;;
        Linux)
            PLATFORM="Linux"
            log_info "Detected Linux"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            PLATFORM="Windows"
            log_info "Detected Windows"
            ;;
        *)
            log_error "Unsupported platform: $(uname -s)"
            exit 1
            ;;
    esac
}

# Auto-detect MATLAB installation
detect_matlab() {
    show_progress "Auto-detecting MATLAB installation"
    
    local matlab_paths=()
    
    case "$PLATFORM" in
        "macOS")
            # Common macOS MATLAB locations
            matlab_paths=(
                "/Applications/MATLAB_R2024b.app"
                "/Applications/MATLAB_R2024a.app"
                "/Applications/MATLAB_R2023b.app"
                "/Applications/MATLAB_R2023a.app"
                "/Volumes/S1/Applications/MATLAB_R2024b.app"  # External volume
                "/Volumes/*/Applications/MATLAB_R*.app"        # Other external volumes
            )
            
            # Check for MATLAB in Applications and external volumes
            for pattern in "${matlab_paths[@]}"; do
                # Handle glob patterns
                if [[ "$pattern" == *"*"* ]]; then
                    for path in $pattern; do
                        if [[ -d "$path" && -x "$path/bin/matlab" ]]; then
                            MATLAB_PATH="$path"
                            log_success "Found MATLAB at: $MATLAB_PATH"
                            return 0
                        fi
                    done
                else
                    if [[ -d "$pattern" && -x "$pattern/bin/matlab" ]]; then
                        MATLAB_PATH="$pattern"
                        log_success "Found MATLAB at: $MATLAB_PATH"
                        return 0
                    fi
                fi
            done
            ;;
            
        "Linux")
            # Common Linux MATLAB locations
            matlab_paths=(
                "/usr/local/MATLAB/R2024b"
                "/usr/local/MATLAB/R2024a"
                "/usr/local/MATLAB/R2023b"
                "/usr/local/MATLAB/R2023a"
                "/opt/MATLAB/R2024b"
                "/opt/MATLAB/R2024a"
                "/home/$USER/MATLAB/R2024b"
                "/home/$USER/MATLAB/R2024a"
            )
            
            for path in "${matlab_paths[@]}"; do
                if [[ -d "$path" && -x "$path/bin/matlab" ]]; then
                    MATLAB_PATH="$path"
                    log_success "Found MATLAB at: $MATLAB_PATH"
                    return 0
                fi
            done
            ;;
            
        "Windows")
            # Common Windows MATLAB locations (using MSYS/Cygwin paths)
            matlab_paths=(
                "/c/Program Files/MATLAB/R2024b"
                "/c/Program Files/MATLAB/R2024a"
                "/c/Program Files/MATLAB/R2023b"
                "/c/Program Files/MATLAB/R2023a"
            )
            
            for path in "${matlab_paths[@]}"; do
                if [[ -d "$path" && -x "$path/bin/matlab.exe" ]]; then
                    MATLAB_PATH="$path"
                    log_success "Found MATLAB at: $MATLAB_PATH"
                    return 0
                fi
            done
            ;;
    esac
    
    # Try to find MATLAB in PATH
    if command -v matlab &> /dev/null; then
        local matlab_bin=$(which matlab)
        MATLAB_PATH="$(dirname "$(dirname "$matlab_bin")")"
        log_success "Found MATLAB via PATH at: $MATLAB_PATH"
        return 0
    fi
    
    # MATLAB not found
    log_error "MATLAB installation not found"
    log_info "Please install MATLAB or set MATLAB_PATH environment variable"
    log_info "Searched locations:"
    for path in "${matlab_paths[@]}"; do
        echo "  - $path"
    done
    exit 1
}

# Validate MATLAB installation
validate_matlab() {
    show_progress "Validating MATLAB installation"
    
    if [[ ! -d "$MATLAB_PATH" ]]; then
        log_error "MATLAB directory not found: $MATLAB_PATH"
        exit 1
    fi
    
    # Check for matlab executable
    local matlab_exe="$MATLAB_PATH/bin/matlab"
    if [[ "$PLATFORM" == "Windows" ]]; then
        matlab_exe="$MATLAB_PATH/bin/matlab.exe"
    fi
    
    if [[ ! -x "$matlab_exe" ]]; then
        log_error "MATLAB executable not found or not executable: $matlab_exe"
        exit 1
    fi
    
    # Check for Python engine directory
    local python_engine_dir="$MATLAB_PATH/extern/engines/python"
    if [[ ! -d "$python_engine_dir" ]]; then
        log_error "MATLAB Python engine not found: $python_engine_dir"
        log_info "Make sure MATLAB Python engine is installed"
        exit 1
    fi
    
    log_success "MATLAB installation validated"
}

# Install UV package manager if needed
install_uv() {
    show_progress "Checking UV package manager"
    
    if command -v uv &> /dev/null; then
        log_success "UV already installed: $(uv --version)"
        return 0
    fi
    
    log_info "UV not found, installing..."
    
    # Install UV using the official installer
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &> /dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        log_error "Neither curl nor wget found. Cannot install UV automatically."
        log_info "Please install UV manually: https://github.com/astral-sh/uv"
        exit 1
    fi
    
    # Source the UV environment
    export PATH="$HOME/.cargo/bin:$PATH"
    
    if command -v uv &> /dev/null; then
        log_success "UV installed successfully: $(uv --version)"
    else
        log_error "UV installation failed"
        exit 1
    fi
}

# Detect optimal Python version based on MATLAB
detect_python_version() {
    show_progress "Detecting optimal Python version for MATLAB"
    
    # Try to get MATLAB version info if possible
    local python_version="3.11"  # Default to 3.11 as it's widely supported
    
    # MATLAB version to Python version mapping
    # This is a simplified mapping - in practice, you'd want more sophisticated detection
    if [[ "$MATLAB_PATH" == *"R2024b"* ]]; then
        python_version="3.11"
    elif [[ "$MATLAB_PATH" == *"R2024a"* ]]; then
        python_version="3.10"
    elif [[ "$MATLAB_PATH" == *"R2023"* ]]; then
        python_version="3.9"
    fi
    
    log_info "Using Python $python_version for MATLAB compatibility"
    echo "$python_version"
}

# Setup virtual environment
setup_venv() {
    show_progress "Setting up virtual environment"
    
    local python_version=$(detect_python_version)
    
    if [[ -d "$VENV_PATH" ]]; then
        log_info "Virtual environment already exists at $VENV_PATH"
        log_info "Removing existing environment to ensure clean setup"
        rm -rf "$VENV_PATH"
    fi
    
    log_info "Creating new virtual environment with Python $python_version"
    uv venv "$VENV_PATH" --python "$python_version"
    
    if [[ ! -d "$VENV_PATH" ]]; then
        log_error "Failed to create virtual environment"
        exit 1
    fi
    
    log_success "Virtual environment created successfully"
}

# Install dependencies
install_dependencies() {
    show_progress "Installing dependencies"
    
    # Activate virtual environment
    source "$VENV_PATH/bin/activate"
    
    # Install MATLAB engine first
    log_info "Installing MATLAB Python engine"
    cd "$MATLAB_PATH/extern/engines/python"
    uv pip install . --quiet
    cd "$SCRIPT_DIR"
    
    # Install the MCP server package
    log_info "Installing MATLAB MCP server"
    uv pip install -e . --quiet
    
    log_success "Dependencies installed successfully"
}

# Generate MCP configuration
generate_config() {
    show_progress "Generating MCP configuration"
    
    local config_file="mcp-pip.json"
    
    cat > "$config_file" << EOF
{
  "mcpServers": {
    "matlab": {
      "command": "$VENV_PATH/bin/matlab-mcp-server",
      "args": [],
      "env": {
        "MATLAB_PATH": "$MATLAB_PATH",
        "PATH": "$MATLAB_PATH/bin:\$PATH"
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
    
    log_success "Configuration saved to $config_file"
}

# Verify installation
verify_installation() {
    show_progress "Verifying installation"
    
    # Check if the MCP server executable exists
    if [[ ! -x "$VENV_PATH/bin/matlab-mcp-server" ]]; then
        log_error "MCP server executable not found"
        exit 1
    fi
    
    # Try to run the server with --help to check if it works
    if "$VENV_PATH/bin/matlab-mcp-server" --help &> /dev/null; then
        log_success "MCP server executable works correctly"
    else
        log_warning "MCP server executable might have issues"
    fi
    
    log_success "Installation verification completed"
}

# Main installation function
main() {
    echo -e "${GREEN}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${GREEN}│                 MATLAB MCP Tools Installer                 │${NC}"
    echo -e "${GREEN}│                  One-Command Setup                         │${NC}"
    echo -e "${GREEN}└─────────────────────────────────────────────────────────────┘${NC}\n"
    
    # Check if MATLAB_PATH is provided as environment variable
    if [[ -n "${MATLAB_PATH:-}" ]]; then
        log_info "Using provided MATLAB_PATH: $MATLAB_PATH"
    fi
    
    # Run installation steps
    detect_platform
    
    # Only auto-detect if MATLAB_PATH not provided
    if [[ -z "${MATLAB_PATH:-}" ]]; then
        detect_matlab
    fi
    
    validate_matlab
    install_uv
    setup_venv
    install_dependencies
    generate_config
    verify_installation
    
    echo -e "\n${GREEN}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${GREEN}│                 Installation Complete!                     │${NC}"
    echo -e "${GREEN}└─────────────────────────────────────────────────────────────┘${NC}\n"
    
    log_success "MATLAB MCP server is ready to use!"
    echo
    log_info "Next steps:"
    echo "  1. Copy configuration to Claude/Cursor:"
    echo "     cp mcp-pip.json ~/.cursor/mcp.json"
    echo
    echo "  2. Start using MATLAB tools in Claude/Cursor!"
    echo
    echo "  3. To test manually:"
    echo "     $VENV_PATH/bin/matlab-mcp-server"
    echo
    log_info "Configuration saved to: $(pwd)/mcp-pip.json"
    log_info "MATLAB path detected: $MATLAB_PATH"
}

# Handle interruption
trap 'log_error "Installation interrupted"; exit 1' INT TERM

# Run main installation
main "$@"