# MATLAB MCP Tool

A Model Context Protocol (MCP) server that provides tools for developing and running MATLAB files. This tool integrates with Cline and other MCP-compatible clients to provide interactive MATLAB development capabilities.

## Prerequisites

- Python 3.8+
- MATLAB with Python Engine installed
- uv package manager (recommended)

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

### Using pip (Recommended)

1. Clone this repository:

```bash
git clone [repository-url]
cd matlab-mcp-tools
```

2. Set the MATLAB path environment variable if your MATLAB is not in the default location:

```bash
# For macOS (default is /Applications/MATLAB_R2024b.app)
export MATLAB_PATH=/path/to/your/matlab/installation

# For Windows use Git Bash terminal (default might be C:\Program Files\MATLAB\R2024b)
# Also use forward slashes and double quotes for paths with spaces
# export MATLAB_PATH="C:/path/to/your/matlab/installation"
```

3. Run the setup script to install the package with pip:

```bash
./setup-pip-matlab-mcp.sh
```

4. Configure Cline/Cursor by copying the provided MCP configuration:

```bash
# For macOS/Linux
cp mcp-pip.json ~/.cursor/mcp.json

# For Windows
# copy mcp-pip.json %USERPROFILE%\.cursor\mcp.json
```

5. Test the installation:

```bash
./test-pip-matlab-mcp.sh
```

After setup, you can run the MATLAB MCP server using:

```bash
matlab-mcp-server
```

Troubleshooting: See [Installation Troubleshooting](#installation-troubleshooting) for common issues and solutions. Don't hesitate to open an issue on the repository if you encounter an issue that is not listed, and a PR if you have a solution.

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

1. Note that the `setup-pip-matlab-mcp.sh` script is designed to be run from the root of the repository.
2. The script is dependent on `pip` and `python` being installed. So make sure you have those installed.
3. If the scripts run, but you get an ENONET error, make sure that the Python executable used to run the install script is the same Python executable that Cline/Cursor is using. Otherwise, you can specify the Python executable in the MCP configuration file within the `command` and `args` keys. For example:

```json
{
      "command": "bash",
      "args": ["-c", "source $(conda info --base)/etc/profile.d/conda.sh && conda activate target_environment && matlab-mcp-server"],
}
```

In this case, the `target_environment` is the name of the Conda environment that was used to install the `matlab-mcp-tools` package.

4. Running the `setup-pip-matlab-mcp.sh` in Windows requires using Git Bash terminal with ADMIN privileges. This is because the script needs to install the `matlab-mcp-tools` package using `pip` and this requires admin privileges.

5. Matlab Python Engine requires specific versions of Python and MATLAB. See the [Matlab Python Engine](https://www.mathworks.com/help/matlab/matlab-engine-for-python.html) and the [Python Versions Compatibility](https://www.mathworks.com/support/requirements/python-compatibility.html) documentations for more information.

6. Matlab requires a license to be running to use the Python Engine.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

This project is licensed under the BSD-3-Clause License. See the [LICENSE](LICENSE) file for details.
