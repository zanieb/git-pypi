"""Tests for git commands via git_bin."""

from pathlib import Path
from typing import Callable

import pytest


class TestGitInit:
    """Tests for git init command."""

    def test_git_init(self, tmp_path: Path, git_run: Callable) -> None:
        """Test git init creates .git directory."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        result = git_run("init", cwd=repo_path)
        assert result.returncode == 0, f"git init failed: {result.stderr}"
        assert (repo_path / ".git").is_dir(), ".git directory not created"


class TestGitConfig:
    """Tests for git config command."""

    def test_git_config_set_and_get(self, tmp_path: Path, git_run: Callable) -> None:
        """Test git config can set and retrieve values."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        git_run("init", cwd=repo_path)

        # Set config values
        result = git_run("config", "user.email", "test@example.com", cwd=repo_path)
        assert result.returncode == 0, f"git config user.email failed: {result.stderr}"

        result = git_run("config", "user.name", "Test User", cwd=repo_path)
        assert result.returncode == 0, f"git config user.name failed: {result.stderr}"

        # Verify config values
        result = git_run("config", "user.email", cwd=repo_path)
        assert result.stdout.strip() == "test@example.com"

        result = git_run("config", "user.name", cwd=repo_path)
        assert result.stdout.strip() == "Test User"


class TestGitAdd:
    """Tests for git add command."""

    def test_git_add(self, git_repo: Path, git_run: Callable) -> None:
        """Test git add stages a file."""
        test_file = git_repo / "test.txt"
        test_file.write_text("Hello, World!\n")

        result = git_run("add", "test.txt", cwd=git_repo)
        assert result.returncode == 0, f"git add failed: {result.stderr}"

    def test_git_add_file_staged(self, git_repo: Path, git_run: Callable) -> None:
        """Test git add correctly stages file (visible in status)."""
        test_file = git_repo / "test.txt"
        test_file.write_text("Hello, World!\n")

        git_run("add", "test.txt", cwd=git_repo)

        result = git_run("status", cwd=git_repo)
        assert "new file" in result.stdout and "test.txt" in result.stdout, "File not staged"


class TestGitCommit:
    """Tests for git commit command."""

    def test_git_commit(self, git_repo: Path, git_run: Callable) -> None:
        """Test git commit creates a commit."""
        test_file = git_repo / "test.txt"
        test_file.write_text("Hello, World!\n")

        git_run("add", "test.txt", cwd=git_repo)
        result = git_run("commit", "-m", "Initial commit", cwd=git_repo)
        assert result.returncode == 0, f"git commit failed: {result.stderr}"

    def test_git_commit_in_log(self, git_repo: Path, git_run: Callable) -> None:
        """Test git commit appears in log."""
        test_file = git_repo / "test.txt"
        test_file.write_text("Hello, World!\n")

        git_run("add", "test.txt", cwd=git_repo)
        git_run("commit", "-m", "Initial commit", cwd=git_repo)

        result = git_run("log", "--oneline", cwd=git_repo)
        assert "Initial commit" in result.stdout, "Commit not found in log"


class TestGitLog:
    """Tests for git log command."""

    def test_git_log(self, git_repo_with_commit: Path, git_run: Callable) -> None:
        """Test git log shows commits."""
        result = git_run("log", "--oneline", cwd=git_repo_with_commit)
        assert result.returncode == 0, f"git log failed: {result.stderr}"
        assert "Initial commit" in result.stdout, "Commit not found in log"

    def test_git_log_format(self, git_repo_with_commit: Path, git_run: Callable) -> None:
        """Test git log with custom format."""
        result = git_run("log", "--format=%H %s", cwd=git_repo_with_commit)
        assert result.returncode == 0, f"git log --format failed: {result.stderr}"
        assert "Initial commit" in result.stdout, "Commit not found in formatted log"


class TestGitBranch:
    """Tests for git branch and checkout commands."""

    def test_git_checkout_create_branch(
        self, git_repo_with_commit: Path, git_run: Callable
    ) -> None:
        """Test git checkout -b creates a new branch."""
        result = git_run("checkout", "-b", "feature", cwd=git_repo_with_commit)
        assert result.returncode == 0, f"git checkout -b failed: {result.stderr}"

    def test_git_branch_lists_branches(self, git_repo_with_commit: Path, git_run: Callable) -> None:
        """Test git branch lists created branches."""
        git_run("checkout", "-b", "feature", cwd=git_repo_with_commit)

        result = git_run("branch", cwd=git_repo_with_commit)
        assert result.returncode == 0, f"git branch failed: {result.stderr}"
        assert "feature" in result.stdout, "Feature branch not found"

    def test_git_checkout_switch_branch(
        self, git_repo_with_commit: Path, git_run: Callable
    ) -> None:
        """Test git checkout can switch between branches."""
        git_run("checkout", "-b", "feature", cwd=git_repo_with_commit)

        # Try to switch back to master or main
        result = git_run("checkout", "master", cwd=git_repo_with_commit)
        if result.returncode != 0:
            result = git_run("checkout", "main", cwd=git_repo_with_commit)

        assert result.returncode == 0, f"git checkout (switch branch) failed: {result.stderr}"


class TestGitDiff:
    """Tests for git diff command."""

    def test_git_diff(self, git_repo_with_commit: Path, git_run: Callable) -> None:
        """Test git diff shows changes."""
        test_file = git_repo_with_commit / "test.txt"
        with open(test_file, "a") as f:
            f.write("More content\n")

        result = git_run("diff", cwd=git_repo_with_commit)
        assert result.returncode == 0, f"git diff failed: {result.stderr}"
        assert "+More content" in result.stdout, "Changes not shown in diff"


class TestGitStatus:
    """Tests for git status command."""

    def test_git_status(self, git_repo: Path, git_run: Callable) -> None:
        """Test git status shows staged files."""
        test_file = git_repo / "test.txt"
        test_file.write_text("Hello, World!\n")

        git_run("add", "test.txt", cwd=git_repo)

        result = git_run("status", cwd=git_repo)
        assert result.returncode == 0, f"git status failed: {result.stderr}"
        assert "new file" in result.stdout and "test.txt" in result.stdout, "File not staged"


class TestGitVersion:
    """Tests for git --version command."""

    def test_git_version(self, git_run: Callable) -> None:
        """Test git --version returns version string."""
        result = git_run("--version")
        assert result.returncode == 0, f"git --version failed: {result.stderr}"
        assert "git version" in result.stdout, f"Unexpected version output: {result.stdout}"


@pytest.mark.network
class TestGitClone:
    """Tests for git clone command (requires network)."""

    def test_git_clone_https(self, tmp_path: Path, git_run: Callable) -> None:
        """Test git clone via HTTPS."""
        clone_dir = tmp_path / "clone-test"

        result = git_run(
            "clone",
            "--depth",
            "1",
            "https://github.com/git/git.git",
            str(clone_dir),
            cwd=tmp_path,
        )
        assert result.returncode == 0, f"git clone failed: {result.stderr}"
        assert (clone_dir / "README.md").exists(), "README.md not found after clone"
