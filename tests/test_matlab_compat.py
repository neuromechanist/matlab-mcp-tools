"""Tests for MATLAB-Python compatibility detection module."""

import os
import platform
import sys
from pathlib import Path
from unittest.mock import patch

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
        expected = {"R2024b", "R2024a", "R2023b", "R2023a", "R2022b"}
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


# ---------------------------------------------------------------------------
# get_compatible_python_versions
# ---------------------------------------------------------------------------


class TestGetCompatiblePythonVersions:
    def test_r2024b(self):
        versions = get_compatible_python_versions("R2024b")
        assert "3.12" in versions
        assert "3.9" in versions
        # Most recent first
        assert versions.index("3.12") < versions.index("3.9")

    def test_r2024a(self):
        versions = get_compatible_python_versions("R2024a")
        assert "3.11" in versions
        assert "3.9" in versions
        assert "3.12" not in versions

    def test_r2023b(self):
        versions = get_compatible_python_versions("R2023b")
        assert "3.11" in versions
        assert "3.8" not in versions

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
    def test_r2024b(self):
        assert get_matlabengine_version("R2024b") == "24.2"

    def test_r2024a(self):
        assert get_matlabengine_version("R2024a") == "24.1"

    def test_r2023b(self):
        assert get_matlabengine_version("R2023b") == "23.2"

    def test_r2023a(self):
        assert get_matlabengine_version("R2023a") == "23.1"

    def test_r2022b(self):
        assert get_matlabengine_version("R2022b") == "9.13"

    def test_unknown_version_returns_none(self):
        assert get_matlabengine_version("R2099z") is None


# ---------------------------------------------------------------------------
# select_best_python
# ---------------------------------------------------------------------------


class TestSelectBestPython:
    def test_r2024b_returns_highest(self):
        best = select_best_python("R2024b")
        assert best == "3.12"

    def test_r2024a_returns_highest(self):
        best = select_best_python("R2024a")
        assert best == "3.11"

    def test_r2023b_returns_highest(self):
        best = select_best_python("R2023b")
        assert best == "3.11"

    def test_r2023a_returns_highest(self):
        best = select_best_python("R2023a")
        assert best == "3.10"

    def test_r2022b_returns_highest(self):
        best = select_best_python("R2022b")
        assert best == "3.10"

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
        import re

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
        paths = [p for p, _ in result]
        versions = [v for _, v in result]
        # If MATLAB is installed on /Volumes/S1, it should be found
        if Path("/Volumes/S1/Applications/MATLAB_R2024b.app").is_dir():
            assert any("R2024b" in v for v in versions)
            assert any("S1" in p or "R2024b" in p for p in paths)

    def test_env_var_path_is_detected(self, tmp_path):
        """MATLAB_PATH env var pointing to a valid dir with version in name is found."""
        fake_matlab = tmp_path / "MATLAB_R2024b.app"
        fake_matlab.mkdir()
        with patch.dict(os.environ, {"MATLAB_PATH": str(fake_matlab)}):
            result = detect_matlab_installations()
        paths = [p for p, _ in result]
        versions = [v for _, v in result]
        assert str(fake_matlab) in paths
        assert "R2024b" in versions

    def test_missing_env_var_does_not_crash(self):
        env = {k: v for k, v in os.environ.items() if k != "MATLAB_PATH"}
        with patch.dict(os.environ, env, clear=True):
            result = detect_matlab_installations()
        assert isinstance(result, list)

    def test_invalid_env_var_path_ignored(self, tmp_path):
        """Nonexistent MATLAB_PATH is silently ignored."""
        fake_path = str(tmp_path / "nonexistent_MATLAB_R2024b.app")
        with patch.dict(os.environ, {"MATLAB_PATH": fake_path}):
            result = detect_matlab_installations()
        assert all(p != fake_path for p, _ in result)

    def test_duplicate_paths_deduplicated(self, tmp_path):
        """Same path via env var and filesystem scan is only listed once."""
        fake_matlab = tmp_path / "MATLAB_R2023b.app"
        fake_matlab.mkdir()
        with patch.dict(os.environ, {"MATLAB_PATH": str(fake_matlab)}):
            result = detect_matlab_installations()
        paths = [p for p, _ in result]
        assert paths.count(str(fake_matlab.resolve())) <= 1


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

    def test_no_matlab_found_scenario(self, tmp_path):
        """When no MATLAB is installed and MATLAB_PATH is unset, compatible=False."""
        env = {k: v for k, v in os.environ.items() if k != "MATLAB_PATH"}

        # Patch detect_matlab_installations to return empty list
        with patch(
            "matlab_mcp.matlab_compat.detect_matlab_installations", return_value=[]
        ), patch.dict(os.environ, env, clear=True):
            result = validate_environment()

        assert result["compatible"] is False
        assert result["matlab_installations"] == []
        assert result["matlab_version"] is None
        assert result["matlabengine_pin"] is None
        assert len(result["recommendations"]) > 0

    def test_incompatible_python_gives_recommendation(self):
        """When running Python is not in the compat list, recommendations guide user."""
        fake_installs = [("/fake/MATLAB_R2024b.app", "R2024b")]

        # Override compatible versions to exclude current Python
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        # R2024b supports 3.9-3.12; if we pretend only 3.8 is supported it's incompatible
        fake_compat = {"R2024b": (["3.8"], "24.2")}

        with patch(
            "matlab_mcp.matlab_compat.detect_matlab_installations",
            return_value=fake_installs,
        ), patch("matlab_mcp.matlab_compat.MATLAB_COMPAT", fake_compat):
            result = validate_environment()

        # Current python (3.10+) should not be in ["3.8"]
        if current not in ["3.8"]:
            assert result["compatible"] is False
            assert any("NOT compatible" in rec for rec in result["recommendations"])

    def test_compatible_python_no_warning(self):
        """When Python matches, compatible=True and matlabengine_pin is set."""
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        fake_installs = [("/fake/MATLAB_R2024b.app", "R2024b")]
        fake_compat = {"R2024b": ([current], "24.2")}

        with patch(
            "matlab_mcp.matlab_compat.detect_matlab_installations",
            return_value=fake_installs,
        ), patch("matlab_mcp.matlab_compat.MATLAB_COMPAT", fake_compat):
            result = validate_environment()

        assert result["compatible"] is True
        assert result["matlab_version"] == "R2024b"
        assert result["matlabengine_pin"] == "matlabengine==24.2.*"

    def test_unknown_matlab_version_not_compatible(self):
        """Unknown MATLAB version yields compatible=False with no compat versions."""
        fake_installs = [("/fake/MATLAB_R2099z.app", "R2099z")]

        with patch(
            "matlab_mcp.matlab_compat.detect_matlab_installations",
            return_value=fake_installs,
        ):
            result = validate_environment()

        assert result["compatible"] is False
        assert result["matlab_version"] is None
