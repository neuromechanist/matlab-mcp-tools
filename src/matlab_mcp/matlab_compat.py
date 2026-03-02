"""MATLAB-Python compatibility detection and version mapping."""

import os
import platform
import sys
from pathlib import Path

# Compatibility mapping: MATLAB version -> (python_versions, matlabengine_version_prefix)
# Python versions listed from most recent to oldest (preferred first).
MATLAB_COMPAT: dict[str, tuple[list[str], str]] = {
    "R2024b": (["3.12", "3.11", "3.10", "3.9"], "24.2"),
    "R2024a": (["3.11", "3.10", "3.9"], "24.1"),
    "R2023b": (["3.11", "3.10", "3.9"], "23.2"),
    "R2023a": (["3.10", "3.9", "3.8"], "23.1"),
    "R2022b": (["3.10", "3.9", "3.8"], "9.13"),
}


def detect_matlab_installations() -> list[tuple[str, str]]:
    """Scan standard paths for MATLAB installations.

    Also checks the MATLAB_PATH environment variable.

    Returns:
        List of (path, version_string) tuples, e.g.
        [("/Applications/MATLAB_R2024b.app", "R2024b")]
    """
    found: list[tuple[str, str]] = []
    seen_paths: set[str] = set()

    def _add_if_valid(path: Path) -> None:
        resolved = str(path.resolve())
        if resolved in seen_paths:
            return
        if path.is_dir():
            version = _extract_version(path.name)
            if version:
                seen_paths.add(resolved)
                found.append((str(path), version))

    system = platform.system()

    if system == "Darwin":
        # Check /Applications
        for p in Path("/Applications").glob("MATLAB_*.app"):
            _add_if_valid(p)
        # Check any mounted volume's Applications directory
        volumes = Path("/Volumes")
        if volumes.is_dir():
            for vol in volumes.iterdir():
                apps = vol / "Applications"
                if apps.is_dir():
                    for p in apps.glob("MATLAB_*.app"):
                        _add_if_valid(p)
    elif system == "Linux":
        for p in Path("/usr/local/MATLAB").glob("R*"):
            _add_if_valid(p)

    # Check MATLAB_PATH env var regardless of platform
    env_path = os.environ.get("MATLAB_PATH", "").strip()
    if env_path:
        p = Path(env_path)
        _add_if_valid(p)

    return found


def _extract_version(name: str) -> str | None:
    """Extract MATLAB release string (e.g. 'R2024b') from a directory name.

    Args:
        name: Directory name such as 'MATLAB_R2024b.app' or 'R2024b'.

    Returns:
        Version string like 'R2024b', or None if not found.
    """
    import re

    match = re.search(r"(R\d{4}[ab])", name)
    return match.group(1) if match else None


def get_compatible_python_versions(matlab_version: str) -> list[str]:
    """Return compatible Python versions for a given MATLAB release.

    Args:
        matlab_version: MATLAB release string, e.g. 'R2024b'.

    Returns:
        List of compatible Python version strings (most recent first),
        or an empty list if the version is unknown.
    """
    entry = MATLAB_COMPAT.get(matlab_version)
    if entry is None:
        return []
    return entry[0]


def get_matlabengine_version(matlab_version: str) -> str | None:
    """Return the matlabengine pip version prefix for a MATLAB release.

    Args:
        matlab_version: MATLAB release string, e.g. 'R2024b'.

    Returns:
        Version prefix string like '24.2', or None for unknown versions.
    """
    entry = MATLAB_COMPAT.get(matlab_version)
    if entry is None:
        return None
    return entry[1]


def select_best_python(matlab_version: str) -> str | None:
    """Return the most recent Python version compatible with a MATLAB release.

    Args:
        matlab_version: MATLAB release string, e.g. 'R2024b'.

    Returns:
        Python version string like '3.12', or None if no mapping exists.
    """
    versions = get_compatible_python_versions(matlab_version)
    if not versions:
        return None
    # Versions are stored most-recent first; return the first one.
    return versions[0]


def validate_environment() -> dict:
    """Check current Python version against detected MATLAB installations.

    Returns:
        Status dictionary with keys:
        - current_python: running Python version string (e.g. '3.11')
        - matlab_installations: list of (path, version) tuples
        - compatible: bool - True if current Python is compatible with any found MATLAB
        - recommendations: list of recommendation strings
        - matlab_version: best-matched MATLAB version (or None)
        - matlabengine_pin: suggested pip version pin (or None)
    """
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    installations = detect_matlab_installations()
    recommendations: list[str] = []
    compatible = False
    matched_matlab: str | None = None
    engine_pin: str | None = None

    if not installations:
        recommendations.append(
            "No MATLAB installations detected. Set MATLAB_PATH env var to your "
            "MATLAB installation directory."
        )
        return {
            "current_python": current,
            "matlab_installations": [],
            "compatible": False,
            "recommendations": recommendations,
            "matlab_version": None,
            "matlabengine_pin": None,
        }

    for _path, version in installations:
        compat_versions = get_compatible_python_versions(version)
        if current in compat_versions:
            compatible = True
            matched_matlab = version
            prefix = get_matlabengine_version(version)
            engine_pin = f"matlabengine=={prefix}.*" if prefix else None
            break

    if not compatible:
        # Give actionable advice based on the first detected installation
        first_version = installations[0][1]
        best = select_best_python(first_version)
        compat = get_compatible_python_versions(first_version)
        prefix = get_matlabengine_version(first_version)

        if best:
            recommendations.append(
                f"Python {current} is NOT compatible with detected MATLAB "
                f"{first_version}. Compatible versions: {', '.join(compat)}."
            )
            recommendations.append(
                f"Recreate the virtual environment with: uv venv --python {best}"
            )
        if prefix:
            recommendations.append(
                f"Install the matching engine: uv pip install 'matlabengine=={prefix}.*'"
            )
    else:
        recommendations.append(
            f"Python {current} is compatible with MATLAB {matched_matlab}."
        )
        if engine_pin:
            recommendations.append(f"Recommended engine pin: {engine_pin}")

    return {
        "current_python": current,
        "matlab_installations": installations,
        "compatible": compatible,
        "recommendations": recommendations,
        "matlab_version": matched_matlab,
        "matlabengine_pin": engine_pin,
    }
