"""Tests for building wheels from local Git artifacts."""

import sys
from pathlib import Path

import pytest

import make_wheels


def test_missing_platform_artifact_does_not_build_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary_dir = tmp_path / "build" / "output"
    wrong_git = binary_dir / "linux_x86_64" / "bin" / "git"
    wrong_git.parent.mkdir(parents=True)
    wrong_git.write_bytes(b"x86_64 git")

    out_dir = tmp_path / "dist"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_wheels.py",
            "--version",
            "2.54.0",
            "--build",
            "20260603",
            "--platform",
            "linux_aarch64",
            "--binary-dir",
            str(binary_dir),
            "--outdir",
            str(out_dir),
        ],
    )

    with pytest.raises(ValueError, match="Binary directory not found for linux_aarch64"):
        make_wheels.main()

    assert not list(out_dir.glob("*.whl"))


def test_direct_platform_artifact_is_resolved(tmp_path: Path) -> None:
    binary_dir = tmp_path / "linux_aarch64"
    git = binary_dir / "bin" / "git"
    git.parent.mkdir(parents=True)
    git.write_bytes(b"aarch64 git")

    assert make_wheels.resolve_binary_dir(binary_dir, "linux_aarch64") == binary_dir


def test_shared_platform_artifact_is_resolved(tmp_path: Path) -> None:
    binary_dir = tmp_path / "build" / "output"
    platform_dir = binary_dir / "linux_aarch64"
    platform_dir.mkdir(parents=True)

    assert make_wheels.resolve_binary_dir(binary_dir, "linux_aarch64") == platform_dir


def test_multiple_platforms_require_platform_subdirectories(tmp_path: Path) -> None:
    binary_dir = tmp_path / "build" / "output"
    git = binary_dir / "bin" / "git"
    git.parent.mkdir(parents=True)
    git.write_bytes(b"unknown platform git")

    with pytest.raises(ValueError, match="Binary directory not found for linux_aarch64"):
        make_wheels.resolve_binary_dir(
            binary_dir,
            "linux_aarch64",
            require_platform_dir=True,
        )
