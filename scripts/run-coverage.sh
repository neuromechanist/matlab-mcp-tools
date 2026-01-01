#!/bin/bash
# Run tests with coverage and optionally upload to Codecov
# Usage: ./scripts/run-coverage.sh [--upload]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Set MATLAB path if not already set
export MATLAB_PATH="${MATLAB_PATH:-/Volumes/S1/Applications/MATLAB_R2025b.app}"

echo "Running tests with coverage..."
echo "MATLAB_PATH: $MATLAB_PATH"

# Run pytest with coverage
.venv/bin/python -m pytest tests/ \
    --cov=src/matlab_mcp \
    --cov-report=xml \
    --cov-report=term-missing \
    -v

echo ""
echo "Coverage report generated: coverage.xml"

# Upload to Codecov if --upload flag is provided
if [[ "$1" == "--upload" ]]; then
    echo ""
    echo "Uploading to Codecov..."

    # Check if codecov CLI exists
    if [[ -x "./codecov" ]]; then
        CODECOV_CLI="./codecov"
    elif command -v codecov &> /dev/null; then
        CODECOV_CLI="codecov"
    else
        echo "Codecov CLI not found. Installing..."
        curl -Os https://cli.codecov.io/latest/macos/codecov
        chmod +x codecov
        CODECOV_CLI="./codecov"
    fi

    # Upload with token from environment or prompt
    if [[ -z "$CODECOV_TOKEN" ]]; then
        echo "CODECOV_TOKEN not set. Please set it or provide as environment variable."
        echo "Example: CODECOV_TOKEN=xxx ./scripts/run-coverage.sh --upload"
        exit 1
    fi

    $CODECOV_CLI upload-process \
        -r neuromechanist/matlab-mcp-tools \
        -t "$CODECOV_TOKEN" \
        -f coverage.xml

    echo "Coverage uploaded to Codecov!"
else
    echo ""
    echo "To upload to Codecov, run:"
    echo "  CODECOV_TOKEN=xxx ./scripts/run-coverage.sh --upload"
fi
