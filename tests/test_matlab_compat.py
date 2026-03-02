"""Tests for MATLAB-Python compatibility detection module."""

import os
import platform
import re
import sys
from pathlib import Path

import pytest

from matlab_mcp.matlab_compat import (
    MATLAB_COMPAT,
    _extract_version,
    detect_matlab_installations,
    get_compatible_python_versions,
    get_matlabengine_version,
    select_best_python,
    validate_environment,
)

# ---------------------------------------------------------------------------
# Compatibility table tests (pure logic, always run)
# ---------------------------------------------------------------------------


class TestCompatTable:
    """Tests for the static compatibility mapping."""

    def test_all_known_versions_present(self):
        expected = {
            "R2025b",
            "R2025a",
            "R2024b",
            "R2024a",
            "R2023b",
            "R2023a",
            "R2022b",
        }
        assert set(MATLAB_COMPAT.keys()) == expected

    def test_each_entry_has_python_list_and_prefix(self):
        for version, (py_versions, prefix) in MATLAB_COMPAT.items():
            assert isinstance(py_versions, list), f"{version}: py_versions must be list"
            assert len(py_versions) > 0, f"{version}: py_versions must be non-empty"
            assert isinstance(prefix, str), f"{version}: prefix must be str"
            assert prefix, f"{version}: prefix must be non-empty"

    def test_python_versions_are_valid_strings(self):
        for version, (py_versions, _) in MATLAB_COMPAT.items():
            for pv in py_versions:
                parts = pv.split(".")
                assert len(parts) == 2, f"{version}: bad version string {pv!r}"
                major, minor = parts
                assert major.isdigit() and minor.isdigit()

    def test_versions_sorted_most_recent_first(self):
        for version, (py_versions, _) in MATLAB_COMPAT.items():
            minor_versions = [int(v.split(".")[1]) for v in py_versions]
            assert minor_versions == sorted(minor_versions, reverse=True), (
                f"{version}: Python versions should be sorted most recent first"
            )

    def test_r2023a_engine_uses_old_versioning(self):
        """R2023a and R2022b use 9.x versioning, not calendar-based."""
        assert MATLAB_COMPAT["R2023a"][1] == "9.14"
        assert MATLAB_COMPAT["R2022b"][1] == "9.13"

    def test_r2024_and_later_use_calendar_versioning(self):
        """R2024a+ use YY.N versioning scheme."""
        for version in ["R2025b", "R2025a", "R2024b", "R2024a", "R2023b"]:
            prefix = MATLAB_COMPAT[version][1]
            assert re.match(r"\d{2}\.\d", prefix), (
                f"{version}: expected calendar-based version, got {prefix}"
            )


# ---------------------------------------------------------------------------
# get_compatible_python_versions
# ---------------------------------------------------------------------------


class TestGetCompatiblePythonVersions:
    def test_r2025b(self):
        versions = get_compatible_python_versions("R2025b")
        assert "3.12" in versions
        assert "3.9" in versions

    def test_r2024b(self):
        versions = get_compatible_python_versions("R2024b")
        assert "3.12" in versions
        assert "3.9" in versions
        assert versions.index("3.12") < versions.index("3.9")

    def test_r2024a(self):
        versions = get_compatible_python_versions("R2024a")
        assert "3.11" in versions
        assert "3.9" in versions
        assert "3.12" not in versions

    def test_r2023a(self):
        versions = get_compatible_python_versions("R2023a")
        assert "3.10" in versions
        assert "3.8" in versions

    def test_r2022b(self):
        versions = get_compatible_python_versions("R2022b")
        assert "3.10" in versions
        assert "3.8" in versions

    def test_unknown_version_returns_empty(self):
        assert get_compatible_python_versions("R2099z") == []

    def test_empty_string_returns_empty(self):
        assert get_compatible_python_versions("") == []


# ---------------------------------------------------------------------------
# get_matlabengine_version
# ---------------------------------------------------------------------------


class TestGetMatlabengineVersion:
    def test_r2025b(self):
        assert get_matlabengine_version("R2025b") == "25.2"

    def test_r2025a(self):
        assert get_matlabengine_version("R2025a") == "25.1"

    def test_r2024b(self):
        assert get_matlabengine_version("R2024b") == "24.2"

    def test_r2024a(self):
        assert get_matlabengine_version("R2024a") == "24.1"

    def test_r2023b(self):
        assert get_matlabengine_version("R2023b") == "23.2"

    def test_r2023a(self):
        assert get_matlabengine_version("R2023a") == "9.14"

    def test_r2022b(self):
        assert get_matlabengine_version("R2022b") == "9.13"

    def test_unknown_version_returns_none(self):
        assert get_matlabengine_version("R2099z") is None


# ---------------------------------------------------------------------------
# select_best_python
# ---------------------------------------------------------------------------


class TestSelectBestPython:
    def test_r2025b_returns_highest(self):
        assert select_best_python("R2025b") == "3.12"

    def test_r2024b_returns_highest(self):
        assert select_best_python("R2024b") == "3.12"

    def test_r2024a_returns_highest(self):
        assert select_best_python("R2024a") == "3.11"

    def test_r2023a_returns_highest(self):
        assert select_best_python("R2023a") == "3.10"

    def test_r2022b_returns_highest(self):
        assert select_best_python("R2022b") == "3.10"

    def test_unknown_version_returns_none(self):
        assert select_best_python("R2099z") is None


# ---------------------------------------------------------------------------
# _extract_version (internal helper)
# ---------------------------------------------------------------------------


class TestExtractVersion:
    def test_app_bundle_name(self):
        assert _extract_version("MATLAB_R2024b.app") == "R2024b"

    def test_linux_dir_name(self):
        assert _extract_version("R2023a") == "R2023a"

    def test_no_match(self):
        assert _extract_version("SomeOtherDir") is None

    def test_embedded_version(self):
        assert _extract_version("matlab-R2022b-toolbox") == "R2022b"

    def test_r2025b(self):
        assert _extract_version("MATLAB_R2025b.app") == "R2025b"


# ---------------------------------------------------------------------------
# detect_matlab_installations
# ---------------------------------------------------------------------------


class TestDetectMatlabInstallations:
    """Test MATLAB detection on the actual system."""

    def test_returns_list(self):
        result = detect_matlab_installations()
        assert isinstance(result, list)

    def test_each_entry_is_path_version_tuple(self):
        result = detect_matlab_installations()
        for path, version in result:
            assert isinstance(path, str)
            assert Path(path).is_dir(), f"Detected path must exist: {path}"
            assert version.startswith("R"), f"Version must start with R: {version}"

    def test_versions_are_known_or_plausible(self):
        result = detect_matlab_installations()
        for _, version in result:
            assert re.match(r"R\d{4}[ab]", version), (
                f"Unexpected version format: {version}"
            )

    @pytest.mark.skipif(
        platform.system() != "Darwin", reason="macOS-specific detection path"
    )
    def test_macos_detects_s1_volume(self):
        """On the developer machine, R2024b is on /Volumes/S1."""
        result = detect_matlab_installations()
        versions = [v for _, v in result]
        if Path("/Volumes/S1/Applications/MATLAB_R2024b.app").is_dir():
            assert any("R2024b" in v for v in versions)

    def test_env_var_path_is_detected(self, tmp_path):
        """MATLAB_PATH env var pointing to a valid dir with version in name is found."""
        fake_matlab = tmp_path / "MATLAB_R2024b.app"
        fake_matlab.mkdir()
        old_val = os.environ.get("MATLAB_PATH")
        try:
            os.environ["MATLAB_PATH"] = str(fake_matlab)
            result = detect_matlab_installations()
        finally:
            if old_val is None:
                os.environ.pop("MATLAB_PATH", None)
            else:
                os.environ["MATLAB_PATH"] = old_val
        paths = [p for p, _ in result]
        versions = [v for _, v in result]
        assert str(fake_matlab) in paths
        assert "R2024b" in versions

    def test_invalid_env_var_path_ignored(self, tmp_path):
        """Nonexistent MATLAB_PATH is silently ignored."""
        fake_path = str(tmp_path / "nonexistent_MATLAB_R2024b.app")
        old_val = os.environ.get("MATLAB_PATH")
        try:
            os.environ["MATLAB_PATH"] = fake_path
            result = detect_matlab_installations()
        finally:
            if old_val is None:
                os.environ.pop("MATLAB_PATH", None)
            else:
                os.environ["MATLAB_PATH"] = old_val
        assert all(p != fake_path for p, _ in result)


# ---------------------------------------------------------------------------
# validate_environment
# ---------------------------------------------------------------------------


class TestValidateEnvironment:
    def test_returns_dict_with_required_keys(self):
        result = validate_environment()
        required = {
            "current_python",
            "matlab_installations",
            "compatible",
            "recommendations",
            "matlab_version",
            "matlabengine_pin",
        }
        assert required.issubset(result.keys())

    def test_current_python_matches_runtime(self):
        result = validate_environment()
        expected = f"{sys.version_info.major}.{sys.version_info.minor}"
        assert result["current_python"] == expected

    def test_compatible_is_bool(self):
        result = validate_environment()
        assert isinstance(result["compatible"], bool)

    def test_recommendations_is_list_of_strings(self):
        result = validate_environment()
        assert isinstance(result["recommendations"], list)
        for rec in result["recommendations"]:
            assert isinstance(rec, str)

    def test_no_matlab_found_gives_recommendation(self):
        """When MATLAB_PATH points nowhere and no system MATLAB, get recommendation."""
        old_val = os.environ.get("MATLAB_PATH")
        try:
            os.environ.pop("MATLAB_PATH", None)
            result = validate_environment()
        finally:
            if old_val is not None:
                os.environ["MATLAB_PATH"] = old_val
        # Either MATLAB is found on the system (compatible or not) or we get recommendations
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) > 0

    @pytest.mark.skipif(
        not any(
            Path(p).is_dir()
            for p in [
                "/Volumes/S1/Applications/MATLAB_R2024b.app",
                "/Applications/MATLAB_R2024b.app",
            ]
        ),
        reason="R2024b not installed",
    )
    def test_with_real_matlab_r2024b(self):
        """On systems with R2024b, validate_environment returns correct info."""
        result = validate_environment()
        # Current Python 3.11 is compatible with R2024b
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        r2024b_compat = get_compatible_python_versions("R2024b")
        if current in r2024b_compat:
            assert result["compatible"] is True
            assert result["matlabengine_pin"] is not None
