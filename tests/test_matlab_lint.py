"""Tests for MATLAB lint module and MCP tool."""

import pytest

from matlab_mcp.lint import (
    VALID_SEVERITY_FILTERS,
    MatlabLintResult,
    MatlabLintSummary,
    _normalise_struct_array,
    _parse_lint_results,
    run_lint,
)
from matlab_mcp.server import matlab_lint

try:
    import importlib.util

    MATLAB_AVAILABLE = importlib.util.find_spec("matlab.engine") is not None
except (ImportError, ModuleNotFoundError, ValueError):
    MATLAB_AVAILABLE = False


# ---------------------------------------------------------------------------
# Dataclass and pure-function unit tests (no MATLAB required)
# ---------------------------------------------------------------------------


class TestMatlabLintResultDataclass:
    """Tests for MatlabLintResult dataclass."""

    def test_required_fields(self):
        result = MatlabLintResult(
            line=10,
            column=5,
            severity="warning",
            msg_id="NASGU",
            message="The value assigned here is unused.",
        )

        assert result.line == 10
        assert result.column == 5
        assert result.severity == "warning"
        assert result.msg_id == "NASGU"
        assert result.message == "The value assigned here is unused."
        assert result.fix_suggestion is None

    def test_optional_fix_suggestion(self):
        result = MatlabLintResult(
            line=1,
            column=1,
            severity="error",
            msg_id="ERR_SYNTAX",
            message="Syntax error.",
            fix_suggestion="Check the expression on line 1.",
        )

        assert result.fix_suggestion == "Check the expression on line 1."

    def test_frozen_immutability(self):
        result = MatlabLintResult(
            line=1, column=1, severity="warning", msg_id="TEST", message="test"
        )
        with pytest.raises(AttributeError):
            result.line = 5


class TestMatlabLintSummaryDataclass:
    """Tests for MatlabLintSummary dataclass."""

    def test_default_values(self):
        summary = MatlabLintSummary()

        assert summary.errors == 0
        assert summary.warnings == 0
        assert summary.info == 0
        assert summary.results == []

    def test_computed_counts(self):
        results = [
            MatlabLintResult(
                line=1, column=1, severity="error", msg_id="E1", message="err"
            ),
            MatlabLintResult(
                line=2, column=1, severity="warning", msg_id="W1", message="warn"
            ),
            MatlabLintResult(
                line=3, column=1, severity="warning", msg_id="W2", message="warn2"
            ),
            MatlabLintResult(
                line=4, column=1, severity="info", msg_id="I1", message="info"
            ),
        ]
        summary = MatlabLintSummary(results=results)

        assert summary.errors == 1
        assert summary.warnings == 2
        assert summary.info == 1


class TestNormaliseStructArray:
    """Tests for _normalise_struct_array with real Python values."""

    def test_list_input(self):
        assert _normalise_struct_array([{"a": 1}]) == [{"a": 1}]

    def test_tuple_input(self):
        assert _normalise_struct_array(({"a": 1},)) == [{"a": 1}]

    def test_dict_input(self):
        assert _normalise_struct_array({"a": 1}) == [{"a": 1}]

    def test_single_object_fallback(self):
        class Obj:
            pass

        obj = Obj()
        result = _normalise_struct_array(obj)
        assert result == [obj]


class TestParseLintResults:
    """Tests for _parse_lint_results."""

    def test_none_returns_empty_summary(self):
        summary = _parse_lint_results(None)
        assert isinstance(summary, MatlabLintSummary)
        assert len(summary.results) == 0

    def test_dict_with_valid_fields(self):
        raw = {
            "line": 5,
            "column": 3,
            "severity": "warning",
            "id": "NASGU",
            "message": "Unused variable.",
        }
        summary = _parse_lint_results(raw)
        assert len(summary.results) == 1
        assert summary.results[0].msg_id == "NASGU"
        assert summary.warnings == 1

    def test_list_of_dicts(self):
        raw = [
            {
                "line": 1,
                "column": 1,
                "severity": "error",
                "id": "ERR1",
                "message": "Error.",
            },
            {
                "line": 2,
                "column": 1,
                "severity": "info",
                "id": "INFO1",
                "message": "Info.",
            },
        ]
        summary = _parse_lint_results(raw)
        assert len(summary.results) == 2
        assert summary.errors == 1
        assert summary.info == 1


class TestSeverityFilterValidation:
    """Tests for severity_filter input validation."""

    def test_valid_filters(self):
        assert "all" in VALID_SEVERITY_FILTERS
        assert "warning" in VALID_SEVERITY_FILTERS
        assert "error" in VALID_SEVERITY_FILTERS

    def test_info_is_not_valid(self):
        assert "info" not in VALID_SEVERITY_FILTERS


# ---------------------------------------------------------------------------
# Integration tests (require real MATLAB)
# ---------------------------------------------------------------------------

needs_matlab = pytest.mark.skipif(
    not MATLAB_AVAILABLE, reason="MATLAB Engine not available"
)


@needs_matlab
class TestRunLint:
    """Integration tests for run_lint() using real MATLAB checkcode."""

    @pytest.fixture(scope="class")
    def engine(self, matlab_engine):
        return matlab_engine

    @pytest.mark.asyncio
    async def test_clean_code_returns_no_errors(self, engine):
        code = "x = 1 + 1;\ndisp(x);\n"
        summary = await run_lint(engine, code)

        assert isinstance(summary, MatlabLintSummary)
        assert summary.errors == 0

    @pytest.mark.asyncio
    async def test_unused_variable_detected(self, engine):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        assert isinstance(summary, MatlabLintSummary)
        total = summary.errors + summary.warnings + summary.info
        assert total >= 1

        ids = [r.msg_id for r in summary.results]
        assert any("NASGU" in msg_id for msg_id in ids), (
            f"Expected NASGU warning for unused variable, got IDs: {ids}"
        )

    @pytest.mark.asyncio
    async def test_results_have_correct_structure(self, engine):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        for result in summary.results:
            assert isinstance(result, MatlabLintResult)
            assert isinstance(result.line, int)
            assert isinstance(result.column, int)
            assert result.severity in ("error", "warning", "info")
            assert isinstance(result.msg_id, str)
            assert isinstance(result.message, str)
            assert len(result.message) > 0

    @pytest.mark.asyncio
    async def test_lint_file_path(self, engine, tmp_path):
        matlab_file = tmp_path / "lint_test.m"
        matlab_file.write_text("a = 1;\nb = 2;\nc = a + 1;\ndisp(c);\n")

        summary = await run_lint(engine, str(matlab_file))

        assert isinstance(summary, MatlabLintSummary)
        total = summary.errors + summary.warnings + summary.info
        assert total >= 1

    @pytest.mark.asyncio
    async def test_severity_filter_error_only(self, engine):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code, severity_filter="error")

        assert isinstance(summary, MatlabLintSummary)
        for result in summary.results:
            assert result.severity == "error", (
                f"Expected only errors, got: {result.severity} ({result.msg_id})"
            )

    @pytest.mark.asyncio
    async def test_severity_filter_warning(self, engine):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code, severity_filter="warning")

        assert isinstance(summary, MatlabLintSummary)
        for result in summary.results:
            assert result.severity in ("warning", "error"), (
                f"Expected warning or error, got: {result.severity}"
            )

    @pytest.mark.asyncio
    async def test_invalid_severity_filter_raises(self, engine):
        with pytest.raises(ValueError, match="severity_filter must be one of"):
            await run_lint(engine, "x = 1;\n", severity_filter="banana")

    @pytest.mark.asyncio
    async def test_summary_counts_match_results(self, engine):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        summary = await run_lint(engine, code)

        total_counted = summary.errors + summary.warnings + summary.info
        assert total_counted == len(summary.results)

    @pytest.mark.asyncio
    async def test_code_with_special_characters(self, engine):
        code = "s = 'hello world';\ndisp(s);\n% This is a comment\n"
        summary = await run_lint(engine, code)
        assert isinstance(summary, MatlabLintSummary)

    @pytest.mark.asyncio
    async def test_empty_code_string(self, engine):
        summary = await run_lint(engine, "")
        assert isinstance(summary, MatlabLintSummary)


@needs_matlab
class TestMatlabLintMcpTool:
    """Integration tests for the matlab_lint MCP tool."""

    @pytest.mark.asyncio
    async def test_tool_returns_correct_keys(self):
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        assert "diagnostics" in result
        assert "summary" in result
        assert "has_issues" in result

    @pytest.mark.asyncio
    async def test_tool_summary_keys(self):
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        summary = result["summary"]
        assert "errors" in summary
        assert "warnings" in summary
        assert "info" in summary
        assert "total" in summary

    @pytest.mark.asyncio
    async def test_tool_diagnostic_keys(self):
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
        code = "x = 1 + 1;\ndisp(x);\n"
        result = await matlab_lint(code_or_file=code)

        assert result["summary"]["errors"] == 0
        assert result["has_issues"] == (result["summary"]["total"] > 0)

    @pytest.mark.asyncio
    async def test_tool_detects_unused_variable(self):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        result = await matlab_lint(code_or_file=code)

        assert result["has_issues"] is True
        ids = [d["id"] for d in result["diagnostics"]]
        assert any("NASGU" in i for i in ids), (
            f"Expected NASGU in diagnostic IDs, got: {ids}"
        )

    @pytest.mark.asyncio
    async def test_tool_severity_filter(self):
        code = "x = 1;\ny = 2;\nz = x + 1;\ndisp(z);\n"
        result = await matlab_lint(code_or_file=code, severity_filter="error")

        for diag in result["diagnostics"]:
            assert diag["severity"] == "error"

    @pytest.mark.asyncio
    async def test_tool_lint_file_path(self, tmp_path):
        matlab_file = tmp_path / "tool_test.m"
        matlab_file.write_text("a = 1;\nb = 2;\nc = a + 1;\ndisp(c);\n")

        result = await matlab_lint(code_or_file=str(matlab_file))

        assert "diagnostics" in result
        assert "summary" in result
        assert result["has_issues"] is True
