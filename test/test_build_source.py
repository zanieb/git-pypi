"""Tests for selecting and fetching Git source revisions."""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
RESOLVE_GIT_REF = PROJECT_ROOT / "build" / "resolve_git_ref.sh"
FETCH_GIT_SOURCE = PROJECT_ROOT / "build" / "fetch_git_source.sh"

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="Source build helpers are only used for macOS and Linux builds",
)


def run_git(repo: Path, *args: str) -> str:
    """Run the system Git against a repository and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_script(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a build helper script."""
    return subprocess.run(
        [str(script), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def source_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a source repository with an annotated tag and a later commit."""
    repo = tmp_path / "source"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")

    source_file = repo / "source.txt"
    source_file.write_text("tagged\n")
    run_git(repo, "add", "source.txt")
    run_git(repo, "commit", "-m", "Tagged commit")
    tagged_commit = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "tag", "-a", "v1.0.0", "-m", "Version 1.0.0")

    source_file.write_text("head\n")
    run_git(repo, "commit", "-am", "Head commit")
    head_commit = run_git(repo, "rev-parse", "HEAD")

    return repo, tagged_commit, head_commit


def source_env(repo: Path) -> dict[str, str]:
    """Return an environment that points build helpers at a local repository."""
    env = os.environ.copy()
    env["GIT_SOURCE_REPOSITORY"] = repo.as_uri()
    return env


def test_resolve_git_ref_head(source_repo: tuple[Path, str, str]) -> None:
    """HEAD resolves to the remote repository's current commit."""
    repo, _, head_commit = source_repo

    result = run_script(RESOLVE_GIT_REF, "HEAD", env=source_env(repo))

    assert result.stdout.strip() == head_commit


def test_resolve_git_ref_annotated_tag(source_repo: tuple[Path, str, str]) -> None:
    """Annotated tags resolve to their peeled commit instead of the tag object."""
    repo, tagged_commit, _ = source_repo

    result = run_script(RESOLVE_GIT_REF, "v1.0.0", env=source_env(repo))

    assert result.stdout.strip() == tagged_commit


def test_resolve_git_ref_full_commit(source_repo: tuple[Path, str, str]) -> None:
    """Full commit SHAs are normalized without requiring an advertised ref."""
    repo, _, head_commit = source_repo

    result = run_script(RESOLVE_GIT_REF, head_commit.upper(), env=source_env(repo))

    assert result.stdout.strip() == head_commit


def test_fetch_git_source_commit(source_repo: tuple[Path, str, str], tmp_path: Path) -> None:
    """Fetching a commit checks out its tree with tags and history available."""
    repo, _, head_commit = source_repo
    destination = tmp_path / "checkout"

    run_script(FETCH_GIT_SOURCE, head_commit, str(destination), env=source_env(repo))

    assert run_git(destination, "rev-parse", "HEAD") == head_commit
    assert (destination / "source.txt").read_text() == "head\n"
    assert run_git(destination, "describe", "--tags", "--match", "v[0-9]*").startswith(
        "v1.0.0-1-g"
    )
