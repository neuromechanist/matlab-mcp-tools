"""Tests for MATLAB lint module and MCP tool."""

import pytest

from matlab_mcp.lint import (
    MatlabLintResult,
    MatlabLintSummary,
    run_lint,
)
from matlab_mcp.server import matlab_lint

try:
    import importlib.util

    MATLAB_AVAILABLE = importlib.util.find_spec("matlab.engine") is not None
except Exception:
    MATLAB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not MATLAB_AVAILABLE, reason="MATLAB Engine not available"
)


# ---------------------------------------------------------------------------
# Dataclass unit tests (no MATLAB required, but the file is skipped at the
# module level when MATLAB is unavailable, keeping all tests together for
# cohesion).
# ---------------------------------------------------------------------------


class TestMatlabLintResultDataclass:
    """Tests for MatlabLintResult dataclass."""

    def test_required_fields(self):
        """Test that required fields are set correctly."""
        result = MatlabLintResult(
            line=10,
            column=5,
            severity="warning",
            id="NASGU",
            message="The value assigned here is unused.",
        )

        assert result.line == 10
        assert result.column == 5
        assert result.severity == "warning"
        assert result.id == "NASGU"
        assert result.message == "The value assigned here is unused."
        assert result.fix_suggestion is None

    def test_optional_fix_suggestion(self):
        """Test that fix_suggestion can be set."""
        result = MatlabLintResult(
            line=1,
            column=1,
            severity="error",
            id="ERR_SYNTAX",
            message="Syntax error.",
            fix_suggestion="Check the expression on line 1.",
        )

        assert result.fix_suggestion == "Check the expression on line 1."


class TestMatlabLintSummaryDataclass:
    """Tests for MatlabLintSummary dataclass."""

    def test_default_values(self):
        """Test that default values are zero and empty."""
        summary = MatlabLintSummary()

        assert summary.errors == 0
        assert summary.warnings == 0
        assert summary.info == 0
        assert summary.results == []

    def test_custom_values(self):
        """Test summary with populated results."""
        r = MatlabLintResult(
            line=3, column=1, severity="warning", id="NASGU", message="Unused."
        )
        summary = MatlabLintSummary(errors=0, warnings=1, info=0, results=[r])

        assert summary.warnings == 1
        assert len(summary.results) == 1
        assert summary.results[0].id == "NASGU"


# ---------------------------------------------------------------------------
# Integration tests (require real MATLAB)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine(matlab_engine):
    """Use the shared MATLAB engine fixture."""
    return matlab_engine


class TestRunLint:
    """Integration tests for run_lint() using real MATLAB checkcode."""

    @pytest.mark.asyncio
    async def test_clean_code_returns_no_errors(self, engine):
        """Linting clean MATLAB code should produce no error diagnostics."""
        code = "x = 1 + 1;\ndisp(x);\n"
        summary = await run_lint(engine, code)

        assert isinstance(summary, MatlabLintSummary)
        assert summary.errors == 0

    @pytest.mark.asyncio
    async def test_unused_variable_detected(self, engine):
        """Unused variable 'y' should trigger a NASGU warning."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        assert isinstance(summary, MatlabLintSummary)
        total = summary.errors + summary.warnings + summary.info
        assert total >= 1

        ids = [r.id for r in summary.results]
        assert any("NASGU" in msg_id for msg_id in ids), (
            f"Expected NASGU warning for unused variable, got IDs: {ids}"
        )

    @pytest.mark.asyncio
    async def test_results_have_correct_structure(self, engine):
        """Each result should have the expected fields with correct types."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        for result in summary.results:
            assert isinstance(result, MatlabLintResult)
            assert isinstance(result.line, int)
            assert isinstance(result.column, int)
            assert result.severity in ("error", "warning", "info")
            assert isinstance(result.id, str)
            assert isinstance(result.message, str)
            assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_lint_file_path(self, engine, tmp_path):
        """Linting a file path should work the same as inline code."""
        matlab_file = tmp_path / "lint_test.m"
        matlab_file.write_text("a = 1;\nb = 2;\nc = a + 1;\ndisp(c);\n")

        summary = await run_lint(engine, str(matlab_file))

        assert isinstance(summary, MatlabLintSummary)
        total = summary.errors + summary.warnings + summary.info
        assert total >= 1

    @pytest.mark.asyncio
    async def test_severity_filter_error_only(self, engine):
        """Filtering to 'error' should exclude warnings and info."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code, severity_filter="error")

        assert isinstance(summary, MatlabLintSummary)
        for result in summary.results:
            assert result.severity == "error", (
                f"Expected only errors, got: {result.severity} ({result.id})"
            )

    @pytest.mark.asyncio
    async def test_severity_filter_warning(self, engine):
        """Filtering to 'warning' should exclude info-level results."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code, severity_filter="warning")

        assert isinstance(summary, MatlabLintSummary)
        for result in summary.results:
            assert result.severity in ("warning", "error"), (
                f"Expected warning or error, got: {result.severity}"
            )

    @pytest.mark.asyncio
    async def test_summary_counts_match_results(self, engine):
        """The error/warning/info counts must sum to len(results)."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        total_counted = summary.errors + summary.warnings + summary.info
        assert total_counted == len(summary.results)


class TestMatlabLintMcpTool:
    """Integration tests for the matlab_lint MCP tool."""

    @pytest.mark.asyncio
    async def test_tool_returns_correct_keys(self):
        """The tool should return diagnostics, summary, and has_issues."""
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        assert "diagnostics" in result
        assert "summary" in result
        assert "has_issues" in result

    @pytest.mark.asyncio
    async def test_tool_summary_keys(self):
        """The summary dict should contain error, warning, info, and total."""
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        summary = result["summary"]
        assert "errors" in summary
        assert "warnings" in summary
        assert "info" in summary
        assert "total" in summary

    @pytest.mark.asyncio
    async def test_tool_diagnostic_keys(self):
        """Each diagnostic entry should contain the expected fields."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        result = await matlab_lint(code_or_file=code)

        for diag in result["diagnostics"]:
            assert "line" in diag
            assert "column" in diag
            assert "severity" in diag
            assert "id" in diag
            assert "message" in diag

    @pytest.mark.asyncio
    async def test_tool_clean_code_no_errors(self):
        """Clean code should return zero errors."""
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        assert result["summary"]["errors"] == 0
        assert result["has_issues"] == (result["summary"]["total"] > 0)

    @pytest.mark.asyncio
    async def test_tool_detects_unused_variable(self):
        """Tool should report diagnostics for code with an unused variable."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        result = await matlab_lint(code_or_file=code)

        assert result["has_issues"] is True
        ids = [d["id"] for d in result["diagnostics"]]
        assert any("NASGU" in i for i in ids), (
            f"Expected NASGU in diagnostic IDs, got: {ids}"
        )

    @pytest.mark.asyncio
    async def test_tool_severity_filter(self):
        """Passing severity_filter='error' should suppress warnings."""
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        result = await matlab_lint(code_or_file=code, severity_filter="error")

        for diag in result["diagnostics"]:
            assert diag["severity"] == "error"

    @pytest.mark.asyncio
    async def test_tool_lint_file_path(self, tmp_path):
        """Tool should accept an absolute file path."""
        matlab_file = tmp_path / "tool_test.m"
        matlab_file.write_text("a = 1;\nb = 2;\nc = a + 1;\ndisp(c);\n")

        result = await matlab_lint(code_or_file=str(matlab_file))

        assert "diagnostics" in result
        assert "summary" in result
        assert result["has_issues"] is True
