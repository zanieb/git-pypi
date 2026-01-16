"""Pytest configuration and shared fixtures for git-bin tests."""

import subprocess
from pathlib import Path
from typing import Callable

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options."""
    parser.addoption(
        "--git-bin",
        action="store",
        required=True,
        help="Path to the git binary to test",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Configure custom markers."""
    config.addinivalue_line("markers", "network: tests requiring network access")


@pytest.fixture(scope="session")
def git_bin(request: pytest.FixtureRequest) -> Path:
    """Get the git binary path from command-line option."""
    git_path = Path(request.config.getoption("--git-bin")).resolve()
    if not git_path.exists():
        pytest.fail(f"Git binary not found: {git_path}")
    return git_path


@pytest.fixture
def git_run(git_bin: Path, tmp_path: Path) -> Callable[..., subprocess.CompletedProcess]:
    """Create a helper function to run the git binary.

    Returns a function that takes git arguments and returns CompletedProcess.
    The default working directory is tmp_path.
    """

    def _run(
        *args: str, cwd: Path | None = None, check: bool = False
    ) -> subprocess.CompletedProcess:
        """Run a git command.

        Args:
            *args: Git command arguments (e.g., "init", "add", "test.txt")
            cwd: Working directory (defaults to tmp_path)
            check: If True, raise CalledProcessError on non-zero exit

        Returns:
            CompletedProcess with stdout, stderr, and returncode
        """
        cmd = [str(git_bin), *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or tmp_path,
            check=check,
        )

    return _run


@pytest.fixture
def git_repo(tmp_path: Path, git_run: Callable) -> Path:
    """Initialize a git repository with user config.

    Returns the path to the repo directory.
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Initialize repo
    result = git_run("init", cwd=repo_path)
    if result.returncode != 0:
        pytest.fail(f"Failed to init repo: {result.stderr}")

    # Configure user
    git_run("config", "user.email", "test@example.com", cwd=repo_path)
    git_run("config", "user.name", "Test User", cwd=repo_path)

    return repo_path


@pytest.fixture
def git_repo_with_commit(git_repo: Path, git_run: Callable) -> Path:
    """Create a git repository with an initial commit.

    Returns the path to the repo directory.
    """
    test_file = git_repo / "test.txt"
    test_file.write_text("Hello, World!\n")

    git_run("add", "test.txt", cwd=git_repo)
    result = git_run("commit", "-m", "Initial commit", cwd=git_repo)
    if result.returncode != 0:
        pytest.fail(f"Failed to create initial commit: {result.stderr}")

    return git_repo
