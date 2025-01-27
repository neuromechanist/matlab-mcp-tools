# MATLAB MCP Tool

A Model Context Protocol (MCP) server that provides tools for developing and running MATLAB files. This tool integrates with Cline and other MCP-compatible clients to provide interactive MATLAB development capabilities.

## Prerequisites

- Python 3.8+
- MATLAB with Python Engine installed

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

1. Clone this repository:
```bash
git clone [repository-url]
cd matlab-mcp-tools
```

2. Create and activate a conda environment:
```bash
conda create -n matlab-mcp python=3.8
conda activate matlab-mcp
```

3. Install the package and its dependencies:
```bash
pip install -e .
```

4. Install MATLAB Engine for Python:
```bash
# Navigate to MATLAB engine directory
cd /Applications/MATLAB_R2024b.app/extern/engines/python

# Install MATLAB engine
python setup.py install
```

5. Add MATLAB to system PATH:
```bash
export PATH="/Applications/MATLAB_R2024b.app/:$PATH"
```

## Usage

1. Start the MCP server:
```bash
python -m matlab_mcp.server
```

2. Configure Cline to use the MATLAB MCP server by adding to your Cline configuration:
```json
{
  "mcpServers": {
    "matlab": {
      "command": "python",
      "args": ["-m", "matlab_mcp.server"],
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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

BSD-3-Clause
