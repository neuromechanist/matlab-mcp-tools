"""MATLAB lint module for MCP Tools.

This module provides functions for linting MATLAB code using checkcode (mlint)
and returning structured diagnostic results.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .engine import MatlabEngine

logger = logging.getLogger(__name__)

VALID_SEVERITY_FILTERS = {"all", "warning", "error"}
LintSeverity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class MatlabLintResult:
    """A single diagnostic result from MATLAB checkcode.

    Attributes:
        line: Line number where the issue was found
        column: Column number where the issue starts
        severity: Severity level ('error', 'warning', or 'info')
        msg_id: MATLAB checkcode message ID (e.g. 'NASGU', 'MCSUP')
        message: Human-readable description of the issue
        fix_suggestion: Optional suggested fix for the issue
    """

    line: int
    column: int
    severity: LintSeverity
    msg_id: str
    message: str
    fix_suggestion: Optional[str] = None


@dataclass
class MatlabLintSummary:
    """Summary of MATLAB checkcode lint results.

    Attributes:
        results: List of individual MatlabLintResult objects
    """

    results: list[MatlabLintResult] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for r in self.results if r.severity == "warning")

    @property
    def info(self) -> int:
        return sum(1 for r in self.results if r.severity == "info")


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
        % Run checkcode with -id flag so message IDs are available for
        % severity classification
        info = checkcode(filepath, '-id');

        % Parse results into struct array
        results = struct('line', {}, 'column', {}, 'severity', {}, ...
                        'id', {}, 'message', {});

        for i = 1:length(info)
            msg = info(i);

            % Use the severity field if checkcode provides it (numeric:
            % 0=info, 1=warning, 2=error). Otherwise infer from the
            % message ID prefix convention; this is a heuristic since
            % checkcode does not guarantee ID naming patterns.
            if isfield(msg, 'severity') && isnumeric(msg.severity)
                switch msg.severity
                    case 0
                        sev = 'info';
                    case 2
                        sev = 'error';
                    otherwise
                        sev = 'warning';
                end
            else
                sev = 'warning';
                if strncmp(msg.id, 'ERR', 3)
                    sev = 'error';
                elseif strncmp(msg.id, 'INFO', 4)
                    sev = 'info';
                end
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
        try
            delete(filepath);
        catch
            % Temp file will be cleaned up by OS; not critical
        end
    end
end
"""


async def run_lint(
    engine: MatlabEngine,
    code_or_file: str,
    severity_filter: str = "all",
) -> MatlabLintSummary:
    """Run MATLAB checkcode lint on code or a file and return structured results.

    This function invokes the mcp_lint MATLAB helper, writing it to the
    engine's helpers directory on first use.

    For inline code strings the input is passed via a MATLAB workspace variable
    to avoid quoting issues with newlines and special characters.

    Args:
        engine: MatlabEngine instance (must be initialized)
        code_or_file: MATLAB code string or absolute path to a .m file
        severity_filter: Minimum severity to report. One of:
            'all'     - report everything (default)
            'warning' - report warnings and errors only
            'error'   - report errors only

    Returns:
        MatlabLintSummary with counts and list of MatlabLintResult objects

    Raises:
        ValueError: If severity_filter is not a valid option
    """
    if severity_filter not in VALID_SEVERITY_FILTERS:
        raise ValueError(
            f"severity_filter must be one of {VALID_SEVERITY_FILTERS}, "
            f"got: {severity_filter!r}"
        )

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

        try:
            engine.eng.eval("clear _mcp_lint_input _mcp_lint_filter", nargout=0)
        except Exception as cleanup_exc:
            logger.debug("Failed to clean up lint workspace variables: %s", cleanup_exc)

        return _parse_lint_results(raw)

    except Exception as exc:
        logger.error("MATLAB lint failed: %s", exc, exc_info=True)
        error_result = MatlabLintResult(
            line=0,
            column=0,
            severity="error",
            msg_id="MCP_LINT_ERROR",
            message=str(exc),
        )
        return MatlabLintSummary(results=[error_result])


def _setup_lint_helper(engine: MatlabEngine) -> None:
    """Write the mcp_lint MATLAB helper to the helpers directory.

    Always writes to ensure the helper stays in sync with the Python code
    after package upgrades.
    """
    lint_helper = engine.helpers_dir / "mcp_lint.m"
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

    items = _normalise_struct_array(raw)

    for item in items:
        line = _get_field_int(item, "line", 0)
        column = _get_field_int(item, "column", 0)
        severity_raw = _get_field_str(item, "severity", "warning")
        msg_id = _get_field_str(item, "id", "")
        message = _get_field_str(item, "message", "")

        if severity_raw not in ("error", "warning", "info"):
            logger.warning(
                "Unknown lint severity %r for message %s, defaulting to 'warning'",
                severity_raw,
                msg_id,
            )
            severity_raw = "warning"

        result = MatlabLintResult(
            line=line,
            column=column,
            severity=severity_raw,
            msg_id=msg_id,
            message=message,
        )
        summary.results.append(result)

    return summary


def _normalise_struct_array(raw: object) -> list:
    """Convert a MATLAB struct or struct array to a Python list of items."""
    if isinstance(raw, (list, tuple)):
        return list(raw)
    # MATLAB Engine may return a single struct as a dict
    if isinstance(raw, dict):
        return [raw]
    logger.debug(
        "Unexpected MATLAB return type in lint results: %s (type: %s)",
        raw,
        type(raw).__name__,
    )
    return [raw]


def _get_field_int(item: object, field_name: str, default: int) -> int:
    """Extract an integer field from a dict or object."""
    val = _get_field(item, field_name, default)
    try:
        # MATLAB doubles may arrive as float, or as matlab.double which
        # stores values in a _data attribute (a flat sequence).
        if hasattr(val, "_data"):
            data = val._data
            return int(data[0]) if data else default
        return int(val)
    except (TypeError, ValueError, IndexError, OverflowError):
        return default


def _get_field_str(item: object, field_name: str, default: str) -> str:
    """Extract a string field from a dict or object."""
    val = _get_field(item, field_name, default)
    if val is None:
        return default
    return str(val)


def _get_field(item: object, field_name: str, default: object) -> object:
    """Get a field from a dict or object attribute."""
    if isinstance(item, dict):
        return item.get(field_name, default)
    return getattr(item, field_name, default)
