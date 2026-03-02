"""MATLAB lint module for MCP Tools.

This module provides functions for linting MATLAB code using checkcode (mlint)
and returning structured diagnostic results.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MatlabLintResult:
    """A single diagnostic result from MATLAB checkcode.

    Attributes:
        line: Line number where the issue was found
        column: Column number where the issue starts
        severity: Severity level ('error', 'warning', or 'info')
        id: MATLAB checkcode message ID (e.g. 'NASGU', 'MCSUP')
        message: Human-readable description of the issue
        fix_suggestion: Optional suggested fix for the issue
    """

    line: int
    column: int
    severity: str
    id: str
    message: str
    fix_suggestion: Optional[str] = None


@dataclass
class MatlabLintSummary:
    """Summary of MATLAB checkcode lint results.

    Attributes:
        errors: Number of error-level diagnostics
        warnings: Number of warning-level diagnostics
        info: Number of info-level diagnostics
        results: List of individual MatlabLintResult objects
    """

    errors: int = 0
    warnings: int = 0
    info: int = 0
    results: list = field(default_factory=list)


# MATLAB helper function for running checkcode and returning structured results
MATLAB_LINT_HELPER = """
function results = mcp_lint(code_or_file, severity_filter)
% MCP_LINT Run checkcode on MATLAB code and return structured results
%   results = mcp_lint(code_or_file) runs checkcode on file or inline code
%   results = mcp_lint(code_or_file, severity_filter) filters by severity
%
%   For inline code: writes to temp file, runs checkcode, cleans up
%   For file paths: runs checkcode directly
%
%   Returns struct array with fields: line, column, severity, id, message

    if nargin < 2
        severity_filter = 'all';
    end

    % Determine if input is file path or code string
    is_file = exist(code_or_file, 'file') == 2;

    if is_file
        filepath = code_or_file;
        cleanup_needed = false;
    else
        % Write code to temp file
        filepath = [tempname '.m'];
        fid = fopen(filepath, 'w');
        fprintf(fid, '%s', code_or_file);
        fclose(fid);
        cleanup_needed = true;
    end

    try
        % Run checkcode with -id flag to include message IDs
        info = checkcode(filepath, '-id');

        % Parse results into struct array
        results = struct('line', {}, 'column', {}, 'severity', {}, ...
                        'id', {}, 'message', {});

        for i = 1:length(info)
            msg = info(i);
            % Determine severity from message ID prefix
            sev = 'warning';
            if strncmp(msg.id, 'ERR', 3)
                sev = 'error';
            elseif strncmp(msg.id, 'INFO', 4)
                sev = 'info';
            end

            % Apply severity filter
            include = true;
            if strcmp(severity_filter, 'error') && ~strcmp(sev, 'error')
                include = false;
            elseif strcmp(severity_filter, 'warning') && strcmp(sev, 'info')
                include = false;
            end

            if include
                results(end+1).line = msg.line;
                results(end).column = msg.column(1);
                results(end).severity = sev;
                results(end).id = msg.id;
                results(end).message = msg.message;
            end
        end

    catch ex
        results = struct('line', 0, 'column', 0, 'severity', 'error', ...
                        'id', 'MCP_LINT_ERROR', 'message', ex.message);
    end

    if cleanup_needed && exist(filepath, 'file')
        delete(filepath);
    end
end
"""


async def run_lint(
    engine: object,
    code_or_file: str,
    severity_filter: str = "all",
) -> MatlabLintSummary:
    """Run MATLAB checkcode lint on code or a file and return structured results.

    This function uses the mcp_lint MATLAB helper if available. It writes the
    helper to the engine's helpers directory on first use.

    For inline code strings the input is passed via a MATLAB workspace variable
    to avoid quoting issues with newlines and special characters.

    Args:
        engine: MatlabEngine instance (must be initialized)
        code_or_file: MATLAB code string or absolute path to a .m file
        severity_filter: Minimum severity to report. One of:
            'all'     - report everything (default)
            'info'    - report info, warnings, and errors
            'warning' - report warnings and errors only
            'error'   - report errors only

    Returns:
        MatlabLintSummary with counts and list of MatlabLintResult objects
    """
    await engine.initialize()
    _setup_lint_helper(engine)

    try:
        # Pass inputs via workspace variables to avoid quoting/newline issues
        engine.eng.workspace["_mcp_lint_input"] = code_or_file
        engine.eng.workspace["_mcp_lint_filter"] = severity_filter

        raw = engine.eng.eval(
            "mcp_lint(_mcp_lint_input, _mcp_lint_filter)",
            nargout=1,
        )

        # Clean up temporary workspace variables
        try:
            engine.eng.eval("clear _mcp_lint_input _mcp_lint_filter", nargout=0)
        except Exception:
            pass

        return _parse_lint_results(raw)

    except Exception as exc:
        # Return a single error result describing what went wrong
        error_result = MatlabLintResult(
            line=0,
            column=0,
            severity="error",
            id="MCP_LINT_ERROR",
            message=str(exc),
        )
        return MatlabLintSummary(errors=1, results=[error_result])


def _setup_lint_helper(engine: object) -> None:
    """Write the mcp_lint MATLAB helper to the helpers directory if needed."""
    lint_helper = engine.helpers_dir / "mcp_lint.m"
    if not lint_helper.exists():
        lint_helper.write_text(MATLAB_LINT_HELPER)


def _parse_lint_results(raw: object) -> MatlabLintSummary:
    """Convert MATLAB checkcode output to a MatlabLintSummary.

    Args:
        raw: The raw value returned from the MATLAB mcp_lint function.
             This is a struct array (or a single struct) from the MATLAB engine.

    Returns:
        MatlabLintSummary populated with MatlabLintResult objects
    """
    summary = MatlabLintSummary()

    if raw is None:
        return summary

    # Normalise to a list of dicts / objects
    items = _normalise_struct_array(raw)

    for item in items:
        line = _get_field_int(item, "line", 0)
        column = _get_field_int(item, "column", 0)
        severity = _get_field_str(item, "severity", "warning")
        msg_id = _get_field_str(item, "id", "")
        message = _get_field_str(item, "message", "")

        result = MatlabLintResult(
            line=line,
            column=column,
            severity=severity,
            id=msg_id,
            message=message,
        )
        summary.results.append(result)

        if severity == "error":
            summary.errors += 1
        elif severity == "info":
            summary.info += 1
        else:
            summary.warnings += 1

    return summary


def _normalise_struct_array(raw: object) -> list:
    """Convert a MATLAB struct or struct array to a Python list of items."""
    if isinstance(raw, (list, tuple)):
        return list(raw)
    # Single struct returned as dict by newer MATLAB Engine versions
    if isinstance(raw, dict):
        return [raw]
    # Older engine may return an object - treat as single item
    return [raw]


def _get_field_int(item: object, field: str, default: int) -> int:
    """Extract an integer field from a dict or object."""
    val = _get_field(item, field, default)
    try:
        # MATLAB doubles come back as float or matlab.double
        if hasattr(val, "_data"):
            data = val._data
            return int(data[0]) if data else default
        return int(val)
    except (TypeError, ValueError, IndexError):
        return default


def _get_field_str(item: object, field: str, default: str) -> str:
    """Extract a string field from a dict or object."""
    val = _get_field(item, field, default)
    if val is None:
        return default
    return str(val)


def _get_field(item: object, field: str, default: object) -> object:
    """Get a field from a dict or object attribute."""
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)
