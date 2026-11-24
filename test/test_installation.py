"""Tests for git binary installation verification."""

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Callable

import pytest


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


@pytest.mark.usefixtures("isolated_git_env")
def test_installed_entry_points(
    git_bin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from python_git_bin import GIT_EXE, GIT_EXEC_PATH, git

    assert GIT_EXE.samefile(git_bin)
    assert GIT_EXEC_PATH.is_dir()
    launcher = Path(sysconfig.get_path("scripts")) / ("git.exe" if os.name == "nt" else "git")
    for command in ([str(git_bin)], [str(launcher)], [sys.executable, "-m", "python_git_bin"]):
        output = subprocess.check_output([*command, "--exec-path"], cwd=tmp_path, text=True)
        assert Path(output.strip()).samefile(GIT_EXEC_PATH)

    template = tmp_path / "custom templates"
    template.mkdir()
    (template / "marker").touch()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(template))
    git("init", cwd=tmp_path, check=True)
    assert (tmp_path / ".git" / "marker").is_file()


@pytest.mark.usefixtures("isolated_git_env")
@pytest.mark.skipif(os.name == "nt", reason="MinGit supplies its own transport executables")
def test_local_transports(git_repo_with_commit: Path, git_run: Callable, tmp_path: Path) -> None:
    clone = tmp_path / "local clone"
    remote = tmp_path / "bare remote"
    git_run("clone", git_repo_with_commit.as_uri(), str(clone), check=True)
    assert (clone / ".git" / "info" / "exclude").is_file()
    git_run("init", "--bare", str(remote), check=True)
    git_run("push", str(remote), "HEAD:refs/heads/main", cwd=clone, check=True)
    archive = tmp_path / "archive.tar"
    git_run("archive", f"--remote={remote}", "-o", str(archive), "main", check=True)
    assert archive.stat().st_size > 0
