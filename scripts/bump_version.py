#!/usr/bin/env python3
"""Version bumping script for matlab-mcp-tools.

This script manages semantic versioning with support for:
- major.minor.patch version bumping
- Pre-release labels (alpha, beta, rc, dev) in PEP 440 format
- Incrementing prerelease number (dev0 -> dev1, a0 -> a1)
- Changing prerelease label without version bump
- Automatic git tagging and GitHub release creation

PEP 440 Version Format:
    - dev:   0.2.0.dev0, 0.2.0.dev1, ...  (development pre-release)
    - alpha: 0.2.0a0, 0.2.0a1, ...        (alpha pre-release)
    - beta:  0.2.0b0, 0.2.0b1, ...        (beta pre-release)
    - rc:    0.2.0rc0, 0.2.0rc1, ...      (release candidate)
    - stable: 0.2.0                        (final release)

Usage:
    python scripts/bump_version.py [major|minor|patch] [--prerelease alpha|beta|rc|dev|stable]
    python scripts/bump_version.py --prerelease dev    # Increment prerelease: dev0 -> dev1
    python scripts/bump_version.py --prerelease alpha  # Change label: dev0 -> a0
    python scripts/bump_version.py --current           # Show current version

Examples:
    python scripts/bump_version.py patch                      # 0.2.0a0 -> 0.2.1a0
    python scripts/bump_version.py minor --prerelease beta    # 0.2.0a0 -> 0.3.0b0
    python scripts/bump_version.py major --prerelease stable  # 0.2.0a0 -> 1.0.0
    python scripts/bump_version.py --prerelease alpha         # 0.2.0.dev0 -> 0.2.0a0
    python scripts/bump_version.py --prerelease dev           # 0.2.0.dev0 -> 0.2.0.dev1
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Project-specific configuration
PACKAGE_NAME = "matlab_mcp"
VERSION_LOCATIONS = [
    # (file_relative_path, regex_pattern, replacement_template)
    (
        "src/matlab_mcp/__init__.py",
        r'__version__\s*=\s*"[^"]+"',
        '__version__ = "{version}"',
    ),
    ("pyproject.toml", r'version\s*=\s*"[^"]+"', 'version = "{version}"'),
]


class VersionBumper:
    """Handle version bumping and Git operations."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.init_file = project_root / "src" / PACKAGE_NAME / "__init__.py"
        self.pyproject_file = project_root / "pyproject.toml"

    # PEP 440 prerelease prefix mapping (without number)
    PRERELEASE_PREFIXES = {
        "dev": ".dev",
        "alpha": "a",
        "beta": "b",
        "rc": "rc",
        "stable": "",
    }

    # Reverse mapping for parsing (pattern -> label)
    PRERELEASE_PATTERNS = {
        r"\.dev(\d+)": "dev",
        r"a(\d+)": "alpha",
        r"b(\d+)": "beta",
        r"rc(\d+)": "rc",
    }

    def get_current_version(self) -> tuple:
        """Read the current version from __init__.py.

        Returns:
            Tuple of (major, minor, patch, prerelease_label, prerelease_num)
            For stable versions, prerelease_label is "stable" and prerelease_num is 0.
        """
        content = self.init_file.read_text()

        version_match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
        if not version_match:
            raise ValueError(f"Could not find __version__ in {self.init_file}")

        version_str = version_match.group(1)

        match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:[-.]?(.+))?", version_str)
        if not match:
            raise ValueError(f"Invalid version format: {version_str}")

        major, minor, patch, suffix = match.groups()

        prerelease = "stable"
        prerelease_num = 0

        if suffix:
            for pattern, label in self.PRERELEASE_PATTERNS.items():
                suffix_match = re.match(pattern, suffix)
                if suffix_match:
                    prerelease = label
                    prerelease_num = (
                        int(suffix_match.group(1)) if suffix_match.group(1) else 0
                    )
                    break
            else:
                suffix_lower = suffix.lower()
                num_match = re.match(r"([a-z]+)(\d*)", suffix_lower)
                if num_match:
                    label_part = num_match.group(1)
                    num_part = num_match.group(2)
                    if label_part in self.PRERELEASE_PREFIXES:
                        prerelease = label_part
                        prerelease_num = int(num_part) if num_part else 0
                    elif label_part in ["a", "b"]:
                        prerelease = "alpha" if label_part == "a" else "beta"
                        prerelease_num = int(num_part) if num_part else 0

        return int(major), int(minor), int(patch), prerelease, prerelease_num

    def format_version(
        self,
        major: int,
        minor: int,
        patch: int,
        prerelease: str,
        prerelease_num: int = 0,
    ) -> str:
        """Format version tuple into PEP 440 compliant version string."""
        version = f"{major}.{minor}.{patch}"
        prefix = self.PRERELEASE_PREFIXES.get(prerelease, "")
        if prefix:
            return f"{version}{prefix}{prerelease_num}"
        return version

    def bump_version(self, bump_type: str | None, new_prerelease: str = None) -> tuple:
        """Bump version and return (old_version, new_version).

        Logic:
        - If bump_type is specified, bump the version number
        - If new_prerelease is specified:
          - If same as current prerelease and no bump_type: increment prerelease_num
          - If different from current prerelease: change label and reset num to 0
          - If bump_type is specified: reset prerelease_num to 0
        """
        major, minor, patch, prerelease, prerelease_num = self.get_current_version()
        old_version = self.format_version(
            major, minor, patch, prerelease, prerelease_num
        )

        new_prerelease_num = prerelease_num

        version_bumped = False
        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
            version_bumped = True
        elif bump_type == "minor":
            minor += 1
            patch = 0
            version_bumped = True
        elif bump_type == "patch":
            patch += 1
            version_bumped = True
        elif bump_type is not None:
            raise ValueError(f"Invalid bump type: {bump_type}")

        if new_prerelease is not None:
            if new_prerelease == prerelease and not version_bumped:
                new_prerelease_num = prerelease_num + 1
            else:
                new_prerelease_num = 0
            prerelease = new_prerelease
        elif version_bumped:
            new_prerelease_num = 0

        new_version = self.format_version(
            major, minor, patch, prerelease, new_prerelease_num
        )

        self._write_version(new_version)

        return old_version, new_version

    def _write_version(self, version: str):
        """Write new version to all version locations."""
        for rel_path, pattern, template in VERSION_LOCATIONS:
            file_path = self.project_root / rel_path
            if not file_path.exists():
                print(f"  Warning: {rel_path} not found, skipping")
                continue

            content = file_path.read_text()
            replacement = template.format(version=version)

            # For pyproject.toml, only replace the first occurrence (in [project])
            if rel_path == "pyproject.toml":
                updated = re.sub(pattern, replacement, content, count=1)
            else:
                updated = re.sub(pattern, replacement, content)

            file_path.write_text(updated)
            print(f"  Updated {rel_path}")

    def git_commit_and_tag(self, version: str):
        """Commit version bump and create Git tag."""
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print("Not in a Git repository. Skipping Git operations.")
            return False

        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=self.project_root,
            capture_output=True,
            text=True,
        )

        version_files = {loc[0] for loc in VERSION_LOCATIONS}
        uncommitted_files = [
            f for f in result.stdout.strip().split("\n") if f and f not in version_files
        ]

        if uncommitted_files:
            print(
                f"Warning: Uncommitted changes detected in: {', '.join(uncommitted_files)}"
            )
            response = input("Continue with version bump? (y/N): ")
            if response.lower() != "y":
                print("Aborted.")
                return False

        # Stage version files
        files_to_stage = [loc[0] for loc in VERSION_LOCATIONS]
        subprocess.run(
            ["git", "add"] + files_to_stage, cwd=self.project_root, check=True
        )

        # Commit
        commit_message = f"Bump version to {version}"
        subprocess.run(
            ["git", "commit", "-m", commit_message], cwd=self.project_root, check=True
        )
        print(f"Committed: {commit_message}")

        # Create tag
        tag_name = f"v{version}"
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Release {version}"],
            cwd=self.project_root,
            check=True,
        )
        print(f"Created tag: {tag_name}")

        return True

    def create_github_release(self, version: str, notes: str = None):
        """Create GitHub release using gh CLI."""
        result = subprocess.run(["gh", "--version"], capture_output=True, text=True)

        if result.returncode != 0:
            print(
                "GitHub CLI (gh) not found. Install it to create releases automatically."
            )
            return False

        tag_name = f"v{version}"

        if not notes:
            result = subprocess.run(
                ["git", "log", "--oneline", "--no-decorate", "-10"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
            )
            recent_commits = result.stdout.strip()
            notes = f"## Recent Changes\n{recent_commits}\n\nFor full changelog, see commit history."

        release_cmd = [
            "gh",
            "release",
            "create",
            tag_name,
            "--title",
            f"Release {version}",
            "--notes",
            notes,
        ]

        # Check if prerelease
        if any(
            label in version.lower()
            for label in ["alpha", "beta", "rc", "dev", "a", "b"]
        ):
            release_cmd.append("--prerelease")
            print("  (Marking as pre-release)")

        print(f"\nCreating GitHub release for {tag_name}...")
        result = subprocess.run(
            release_cmd, cwd=self.project_root, capture_output=True, text=True
        )

        if result.returncode == 0:
            print(f"Created GitHub release: {tag_name}")
            if result.stdout.strip():
                print(f"  URL: {result.stdout.strip()}")
            return True
        else:
            print(f"Failed to create GitHub release: {result.stderr}")
            return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bump matlab-mcp-tools version and create Git tag/release",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "bump_type",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="Type of version bump",
    )

    parser.add_argument(
        "--prerelease",
        choices=["alpha", "beta", "rc", "dev", "stable"],
        help="Set pre-release label (dev for develop, omit for stable)",
    )

    parser.add_argument(
        "--current", action="store_true", help="Show current version and exit"
    )

    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip Git operations (commit, tag, release)",
    )

    parser.add_argument(
        "--create-release",
        action="store_true",
        help="Create GitHub release after tagging (skips interactive prompt)",
    )

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    bumper = VersionBumper(project_root)

    if args.current:
        major, minor, patch, prerelease, prerelease_num = bumper.get_current_version()
        version = bumper.format_version(major, minor, patch, prerelease, prerelease_num)
        print(f"Current version: {version}")
        if prerelease != "stable":
            print(
                f"  Components: {major}.{minor}.{patch} ({prerelease} #{prerelease_num})"
            )
        return 0

    if not args.bump_type and not args.prerelease:
        parser.print_help()
        return 1

    try:
        old_version, new_version = bumper.bump_version(args.bump_type, args.prerelease)
        print(f"\nVersion bumped: {old_version} -> {new_version}\n")

        if not args.no_git:
            if bumper.git_commit_and_tag(new_version):
                print("\nNext steps:")
                print(f"  1. Review: git show v{new_version}")
                print(f"  2. Push tag: git push origin v{new_version}")
                print("  3. Push branch and create PR")

                if args.create_release:
                    bumper.create_github_release(new_version)
                else:
                    response = input("\nCreate GitHub release now? (y/N): ")
                    if response.lower() == "y":
                        bumper.create_github_release(new_version)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
