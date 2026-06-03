"""Tests for wheel construction."""

import io
import sys
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

import pytest

import make_wheels

PROJECT_ROOT = Path(__file__).parent.parent
VERSION = "2.54.0.20260603"
REQUIRED_LICENSE_FILES = [
    "LICENSE-APACHE",
    "LICENSE-MIT",
    "NOTICE",
    "licenses/GIT-LICENSE-GPL2",
    "licenses/REFTABLE-LICENSE-BSD",
    "licenses/SHA1DC-LICENSE-MIT",
]


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


def expected_license_files() -> list[str]:
    """Return required and additionally discovered legal payloads."""
    discovered = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in sorted((PROJECT_ROOT / "licenses").rglob("*"))
        if path.is_file()
    ]
    return REQUIRED_LICENSE_FILES + [
        relative_path for relative_path in discovered if relative_path not in REQUIRED_LICENSE_FILES
    ]


def assert_wheel_includes_license_files(wheel_path: Path) -> None:
    """Assert a wheel includes and declares every legal payload."""
    dist_info = f"python_git_bin-{VERSION}.dist-info"
    license_root = f"{dist_info}/licenses/"
    expected = expected_license_files()

    with ZipFile(wheel_path) as wheel:
        included = {
            name.removeprefix(license_root)
            for name in wheel.namelist()
            if name.startswith(license_root)
        }
        assert included == set(expected)

        for relative_path in expected:
            assert (
                wheel.read(f"{license_root}{relative_path}")
                == (PROJECT_ROOT / relative_path).read_bytes()
            )

        metadata = BytesParser().parsebytes(wheel.read(f"{dist_info}/METADATA"))
        assert metadata.get_all("License-File") == expected


@pytest.mark.parametrize("platform", ["linux_x86_64", "macos_arm64"])
def test_local_wheel_includes_license_files(tmp_path: Path, platform: str) -> None:
    """Linux and macOS wheels include every legal payload."""
    binary_dir = tmp_path / "git"
    (binary_dir / "bin").mkdir(parents=True)
    (binary_dir / "bin" / "git").write_bytes(b"git")

    wheel_path = make_wheels.write_git_wheel(
        tmp_path,
        version=VERSION,
        platform=platform,
        binary_dir=binary_dir,
    )

    assert_wheel_includes_license_files(wheel_path)


def test_archive_wheel_includes_license_files(tmp_path: Path) -> None:
    """Archive-based wheels include every legal payload."""
    archive_data = io.BytesIO()
    with ZipFile(archive_data, "w") as archive:
        archive.writestr("cmd/git.exe", b"git")

    wheel_path = make_wheels.write_git_wheel(
        tmp_path,
        version=VERSION,
        platform="win_amd64",
        archive_data=archive_data.getvalue(),
    )

    assert_wheel_includes_license_files(wheel_path)


@pytest.mark.parametrize(
    ("platform", "helper_dir"),
    [
        ("win_amd64", "mingw64"),
        ("win_arm64", "clangarm64"),
        ("win32", "mingw32"),
    ],
)
def test_windows_wrapper_uses_platform_helper_directory(
    tmp_path: Path, platform: str, helper_dir: str
) -> None:
    """The generated GIT_EXEC_PATH points to helpers included by that MinGit build."""
    archive_data = io.BytesIO()
    helper_member = f"{helper_dir}/libexec/git-core/git-help.exe"
    with ZipFile(archive_data, "w") as mingit:
        mingit.writestr("cmd/git.exe", b"")
        mingit.writestr(helper_member, b"")

    wheel_path = make_wheels.write_git_wheel(
        tmp_path,
        version="1.0.0",
        platform=platform,
        archive_data=archive_data.getvalue(),
    )

    with ZipFile(wheel_path) as wheel:
        init_module = wheel.read("python_git_bin/__init__.py").decode()
        assert f"python_git_bin/git/{helper_member}" in wheel.namelist()

    assert f"GIT_EXEC_PATH = GIT_DIR / '{helper_dir}' / 'libexec' / 'git-core'" in init_module
