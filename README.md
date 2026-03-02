# MATLAB MCP Tool

A Model Context Protocol (MCP) server that provides tools for developing and running MATLAB files. Integrates with Claude Code, Cursor, and other MCP-compatible clients.

## Prerequisites

- Python 3.10+
- MATLAB with Python Engine installed
- uv package manager (required)

## Features

1. **Script Execution** - Run complete scripts, individual sections (by index, title, or line range), maintain workspace context between executions, capture plots
2. **Workspace Management** - Get full workspace, retrieve specific variables with field/depth/size control, inspect struct metadata, list and filter variables by name pattern or type
3. **Figure Analysis** - Extract figure metadata (axes, labels, legends), get raw plot data, prepare figures for LLM-based analysis with custom prompts
4. **Code Quality** - Lint MATLAB code via `checkcode` with severity filtering, supports inline code and file paths
5. **Script Management** - Create scripts, list sections with previews, read script content via MCP resource

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

You should see a startup message confirming the server is running with 15 tools available.

2. Configure your MCP client. For **Claude Code**, add to `.mcp.json`:

```json
{
  "mcpServers": {
    "matlab": {
      "command": "/path/to/matlab-mcp-tools/.venv/bin/matlab-mcp-server",
      "env": {
        "MATLAB_PATH": "/Applications/MATLAB_R2024b.app"
      }
    }
  }
}
```

For **Cursor**, use the auto-generated `mcp-pip.json` or add to `~/.cursor/mcp.json`.

Hint: Find the MATLAB engine path with `python -c "import matlab; print(matlab.__file__)"`.

3. **Available Tools (15):**

| Category | Tool | Description |
|----------|------|-------------|
| Scripts | `execute_script` | Run MATLAB code or script file |
| | `execute_section` | Execute by line range |
| | `execute_section_by_index` | Execute by section index (0-based) |
| | `execute_section_by_title` | Execute by section title (partial match) |
| | `get_script_sections` | List sections with titles and previews |
| | `create_matlab_script` | Create a new .m file |
| Workspace | `get_workspace` | Get all workspace variables |
| | `get_variable` | Get specific variable (with field/depth/size control) |
| | `get_struct_info` | Get struct field metadata without data transfer |
| | `list_workspace_variables` | List/filter variables by name pattern or type |
| Figures | `get_figure_metadata` | Extract axes, labels, legends, subplot info |
| | `get_plot_data` | Get raw x/y/z data from plot lines |
| | `analyze_figure` | Prepare figure image + metadata for LLM analysis |
| | `get_analysis_prompt` | Get/customize the figure analysis prompt |
| Quality | `matlab_lint` | Run checkcode on code or files |

**Resource:** `matlab://scripts/{script_name}` - Read script content

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

To execute this script using the `execute_script` tool:
```json
{
    "script": "test_plot.m",
    "is_file": true
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

To execute specific sections using `execute_section_by_index`:
```json
{
    "file_path": "section_test.m",
    "section_index": 0
}
```

Or by title using `execute_section_by_title`:
```json
{
    "file_path": "section_test.m",
    "section_title": "Data Generation"
}
```

The output will include:
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
