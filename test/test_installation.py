"""Tests for git binary installation verification."""

import os
from pathlib import Path
from typing import Callable


class TestGitBinary:
    """Tests for the git binary itself."""

    def test_binary_exists(self, git_bin: Path) -> None:
        """Test that the git binary exists."""
        assert git_bin.exists(), f"Git binary not found: {git_bin}"

    def test_binary_is_executable(self, git_bin: Path) -> None:
        """Test that the git binary is executable."""
        assert os.access(git_bin, os.X_OK), f"Git binary is not executable: {git_bin}"

    def test_binary_returns_version(self, git_run: Callable) -> None:
        """Test that the git binary returns a version string."""
        result = git_run("--version")
        assert result.returncode == 0, f"git --version failed: {result.stderr}"
        assert "git version" in result.stdout, f"Unexpected version output: {result.stdout}"
