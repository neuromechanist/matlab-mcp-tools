# MATLAB MCP Tool

A Model Context Protocol (MCP) server that provides tools for developing and running MATLAB files. This tool integrates with Cline and other MCP-compatible clients to provide interactive MATLAB development capabilities.

## Prerequisites

- Python 3.10+
- MATLAB with Python Engine installed
- uv package manager (required)

## Features

1. **Execute MATLAB Scripts**
   - Run complete MATLAB scripts
   - Execute individual script sections
   - Maintain workspace context between executions
   - Capture and display plots

2. **Section-based Execution**
   - Execute specific sections of MATLAB files
   - Support for cell mode (%% delimited sections)
   - Maintain workspace context between sections

## Installation

### Quick Start (Recommended)

**One-command installation with auto-detection:**

```bash
./install-matlab-mcp.sh
```

That's it! The installer will:
- ✅ **Auto-detect MATLAB installations** (including external volumes like `/Volumes/S1/`)
- ✅ **Auto-install UV** package manager if needed
- ✅ **Create optimized virtual environment** with MATLAB-compatible Python version
- ✅ **Install all dependencies** including MATLAB Python engine
- ✅ **Generate MCP configuration** ready for Cursor/Claude Code
- ✅ **Verify installation** works correctly
- ✅ **Optionally configure Cursor** automatically

**Reduces installation time from 15+ minutes to ~2 minutes!**

### Advanced Installation

If you need custom configuration:

1. **Clone this repository:**

```bash
git clone [repository-url]
cd matlab-mcp-tools
```

2. **Set custom MATLAB path** (optional - installer auto-detects):

```bash
# Only needed if MATLAB is in unusual location
export MATLAB_PATH=/path/to/your/matlab/installation
```

3. **Run installer:**

```bash
./install-matlab-mcp.sh
```

### Legacy Installation (Manual)

<details>
<summary>Click to expand legacy manual installation steps</summary>

1. Install uv package manager:

```bash
# Install uv using Homebrew
brew install uv
# OR install using pip
pip install uv
```

2. Set MATLAB path environment variable:

```bash
# For macOS (auto-detection searches common locations)
export MATLAB_PATH=/Applications/MATLAB_R2024b.app

# For Windows (use Git Bash terminal)
export MATLAB_PATH="C:/Program Files/MATLAB/R2024b"
```

3. Run legacy setup script:

```bash
./scripts/setup-matlab-mcp.sh
```

4. Configure Cursor manually:

```bash
cp mcp-pip.json ~/.cursor/mcp.json
```

</details>

### Testing Installation

Test your installation:

```bash
./scripts/test-matlab-mcp.sh
```

**Installation complete!** The MATLAB MCP server is now ready to use with Cursor/Claude Code.

## Usage

1. Start the MCP server:
```bash
matlab-mcp-server
```

This is equivalent to running:
```bash
python -m matlab_mcp.server
```

You should see a startup message listing the available tools and confirming the server is running:
```
MATLAB MCP Server is running...
Available tools:
  - execute_script: Execute MATLAB code or script file
  - execute_script_section: Execute specific sections of a MATLAB script
  - get_script_sections: Get information about script sections
  - create_matlab_script: Create a new MATLAB script
  - get_workspace: Get current MATLAB workspace variables

Use the tools with Cline or other MCP-compatible clients.
```

2. Use the provided MCP configuration (see [Installation](#installation)) file to configure Cline/Cursor:
```json
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
```

Hint: You can find the MATLAB engine installation path by running `python -c "import matlab; print(matlab.__file__)"`.

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

## Examples

### 1. Simple Script Execution with Plot

This example demonstrates running a complete MATLAB script that generates a plot:

```matlab
% test_plot.m
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
```

To execute this script using the MCP tool:
```json
{
    "script": "test_plot.m",
    "isFile": true
}
```

The tool will execute the script and capture the generated plot, saving it to the output directory.

### 2. Section-Based Execution

This example shows how to execute specific sections of a MATLAB script:

```matlab
%% Section 1: Data Generation
% Generate sample data
x = linspace(0, 10, 100);
y = sin(x);

fprintf('Generated %d data points\n', length(x));

%% Section 2: Basic Statistics
% Calculate basic statistics
mean_y = mean(y);
std_y = std(y);
max_y = max(y);
min_y = min(y);

fprintf('Statistics:\n');
fprintf('Mean: %.4f\n', mean_y);
fprintf('Std Dev: %.4f\n', std_y);
fprintf('Max: %.4f\n', max_y);
fprintf('Min: %.4f\n', min_y);

%% Section 3: Plotting
% Create visualization
figure('Position', [100, 100, 800, 400]);

subplot(1, 2, 1);
plot(x, y, 'b-', 'LineWidth', 2);
title('Signal');
xlabel('x');
ylabel('y');
grid on;

subplot(1, 2, 2);
histogram(y, 20);
title('Distribution');
xlabel('Value');
ylabel('Count');
grid on;

sgtitle('Signal Analysis');
```

To execute specific sections:
```json
{
    "filePath": "section_test.m",
    "sectionStart": 1,
    "sectionEnd": 2
}
```

This will run sections 1 and 2, generating the data and calculating statistics. The output will include:
```
Generated 100 data points
Statistics:
Mean: 0.0000
Std Dev: 0.7071
Max: 1.0000
Min: -1.0000
```

## Output Directory

The tool creates `matlab_output` and `test_output` directories to store:
- Plot images generated during script execution
- Other temporary files

## Error Handling

- Script execution errors are captured and returned with detailed error messages
- Workspace state is preserved even after errors

## Installation Troubleshooting

The new `install-matlab-mcp.sh` installer handles most common issues automatically. If you encounter problems:

### Common Issues and Solutions

**1. MATLAB not found:**
- The installer auto-detects MATLAB in common locations
- If you have MATLAB in unusual location: `export MATLAB_PATH=/your/matlab/path`
- Supported locations include external volumes (e.g., `/Volumes/S1/Applications/`)

**2. UV package manager issues:**
- The installer automatically installs UV if needed
- For manual installation: `curl -LsSf https://astral.sh/uv/install.sh | sh`

**3. Python version compatibility:**
- Installer automatically selects MATLAB-compatible Python version
- MATLAB R2024b: Python 3.11, R2024a: Python 3.10, R2023x: Python 3.9

**4. Permission errors:**
- Run installer with appropriate permissions
- On Windows: use Git Bash with Admin privileges

**5. Configuration issues:**
- Use the auto-generated `mcp-pip.json` configuration
- Installer offers automatic Cursor configuration

### Legacy Issues (if using manual installation)

<details>
<summary>Click for legacy troubleshooting</summary>

1. Make sure `uv` is installed before running legacy scripts
2. For ENONET errors, ensure Python executable consistency:

```json
{
    "command": "bash",
    "args": ["-c", "source ~/.zshrc && /path/to/matlab-mcp-install/.venv/bin/matlab-mcp-server"]
}
```

3. MATLAB Python Engine compatibility: See [MATLAB Engine docs](https://www.mathworks.com/help/matlab/matlab-engine-for-python.html)

</details>

### Still Having Issues?

1. **Check installer output** for specific error messages
2. **Verify MATLAB license** is valid and active  
3. **Test manually**: `.venv/bin/matlab-mcp-server --help`
4. **Open an issue** with installer output if problem persists

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

This project is licensed under the BSD-3-Clause License. See the [LICENSE](LICENSE) file for details.
