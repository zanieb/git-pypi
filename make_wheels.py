# /// script
# requires-python = "~=3.9"
# dependencies = [
#   "wheel~=0.41.0",
# ]
# ///

"""
Build Git wheels for PyPI distribution.

This script packages Git binaries as Python wheels:
- Windows: Downloads official MinGit from Git for Windows releases
- macOS/Linux: Uses pre-built binaries from local build scripts

Wheel versions use format: <git-version>.<build-date>
  e.g., 2.56.1.20261124 for Git 2.56.1 built on 2026-11-24

Usage:
    uv run make_wheels.py --version 2.56.1 --platform win_amd64
    uv run make_wheels.py --version 2.56.1 --platform all
    uv run make_wheels.py --version 2.56.1 --platform linux_x86_64 --binary-dir ./build-output
"""

import argparse
import hashlib
import io
import json
import logging
import os
import re
import stat
import tarfile
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from wheel.wheelfile import WheelFile

# Git for Windows release info URL
GIT_FOR_WINDOWS_API_URL = "https://api.github.com/repos/git-for-windows/git/releases"

# Platform mapping: our platform names -> Python wheel platform tags
# macOS targets follow python-build-standalone conventions:
#   - x86_64: 10.15 (Catalina) - broader Intel Mac compatibility
#   - arm64: 11.0 (Big Sur) - minimum for Apple Silicon
PLATFORM_TAGS = {
    "win_amd64": "win_amd64",
    "win_arm64": "win_arm64",
    "win32": "win32",
    "macos_x86_64": "macosx_10_15_x86_64",
    "macos_arm64": "macosx_11_0_arm64",
    "linux_x86_64": "manylinux_2_17_x86_64.musllinux_1_1_x86_64",
    "linux_aarch64": "manylinux_2_17_aarch64.musllinux_1_1_aarch64",
}

# Windows MinGit asset patterns (architecture -> asset name pattern)
MINGIT_PATTERNS = {
    "win_amd64": r"MinGit-[\d.]+-64-bit\.zip$",
    "win_arm64": r"MinGit-[\d.]+-arm64\.zip$",
    "win32": r"MinGit-[\d.]+-32-bit\.zip$",
}

REQUIRED_DISTRIBUTION_LICENSE_FILES = (
    "LICENSE-APACHE",
    "LICENSE-MIT",
    "NOTICE",
    "licenses/GIT-LICENSE-GPL2",
    "licenses/REFTABLE-LICENSE-BSD",
    "licenses/SHA1DC-LICENSE-MIT",
)


def read_license_files():
    """Read the legal files included in distributions."""
    project_root = Path(__file__).parent
    required_license_files = {
        relative_path: (project_root / relative_path).read_bytes()
        for relative_path in REQUIRED_DISTRIBUTION_LICENSE_FILES
    }
    discovered_license_files = {
        path.relative_to(project_root).as_posix(): path.read_bytes()
        for path in sorted((project_root / "licenses").rglob("*"))
        if path.is_file()
    }
    return {**required_license_files, **discovered_license_files}


class ReproducibleWheelFile(WheelFile):
    """WheelFile that produces reproducible output."""

    def writestr(self, zinfo_or_arcname, data, *args, **kwargs):
        if isinstance(zinfo_or_arcname, ZipInfo):
            zinfo = zinfo_or_arcname
        else:
            assert isinstance(zinfo_or_arcname, str)
            zinfo = ZipInfo(zinfo_or_arcname)
            zinfo.file_size = len(data)
            zinfo.external_attr = 0o0644 << 16
            if zinfo_or_arcname.endswith(".dist-info/RECORD"):
                zinfo.external_attr = 0o0664 << 16

        zinfo.compress_type = ZIP_DEFLATED
        zinfo.date_time = (1980, 1, 1, 0, 0, 0)
        zinfo.create_system = 3
        super().writestr(zinfo, data, *args, **kwargs)


def make_message(headers, payload=None):
    """Create an email message for wheel metadata."""
    msg = EmailMessage()
    for name, value in headers:
        if isinstance(value, list):
            for value_part in value:
                msg[name] = value_part
        else:
            msg[name] = value
    if payload:
        msg.set_payload(payload)
    return msg


def write_wheel_file(filename, contents):
    """Write a wheel file with given contents."""
    with ReproducibleWheelFile(filename, "w") as wheel:
        for member_info, member_source in contents.items():
            wheel.writestr(member_info, bytes(member_source))
    return filename


def write_wheel(
    out_dir, *, name, version, tag, metadata, description, contents, license_files=None
):
    """Write a complete wheel with metadata."""
    wheel_name = f"{name}-{version}-{tag}.whl"
    dist_info = f"{name}-{version}.dist-info"
    license_files = license_files or {}

    # Expand compressed tags for WHEEL file
    pytag, abitag, platformtag = tag.split("-")
    expanded_tags = [
        "-".join((x, y, z))
        for z in platformtag.split(".")
        for y in abitag.split(".")
        for x in pytag.split(".")
    ]

    return write_wheel_file(
        os.path.join(out_dir, wheel_name),
        {
            **contents,
            **{
                f"{dist_info}/licenses/{license_path}": license_contents
                for license_path, license_contents in license_files.items()
            },
            f"{dist_info}/entry_points.txt": make_message(
                [], "[console_scripts]\ngit = python_git_bin:main"
            ),
            f"{dist_info}/METADATA": make_message(
                [
                    ("Metadata-Version", "2.4"),
                    ("Name", name),
                    ("Version", version),
                    *metadata,
                    ("License-File", list(license_files)),
                ],
                description,
            ),
            f"{dist_info}/WHEEL": make_message(
                [
                    ("Wheel-Version", "1.0"),
                    ("Generator", "git-bin make_wheels.py"),
                    ("Root-Is-Purelib", "false"),
                    ("Tag", expanded_tags),
                ]
            ),
        },
    )


def fetch_git_for_windows_release(version):
    """Fetch release info from Git for Windows GitHub releases."""
    # Try exact version tag first
    tag = f"v{version}.windows.1"
    url = f"{GIT_FOR_WINDOWS_API_URL}/tags/{tag}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "git-bin-wheel-builder")

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Git for Windows release not found for version {version}")
        raise


def find_mingit_asset(release_info, platform):
    """Find the MinGit asset URL and checksum for a platform."""
    pattern = MINGIT_PATTERNS.get(platform)
    if not pattern:
        raise ValueError(f"No MinGit pattern for platform: {platform}")

    regex = re.compile(pattern)

    for asset in release_info.get("assets", []):
        if regex.search(asset["name"]):
            return {
                "url": asset["browser_download_url"],
                "name": asset["name"],
                "sha256": parse_sha256_digest(asset.get("digest"), asset["name"]),
            }

    raise ValueError(f"MinGit asset not found for platform: {platform}")


def parse_sha256_digest(digest, asset_name):
    """Parse a GitHub release asset SHA256 digest."""
    if not digest:
        raise ValueError(f"Missing digest for release asset: {asset_name}")

    algorithm, separator, expected_sha256 = digest.partition(":")
    if separator != ":" or algorithm.lower() != "sha256":
        raise ValueError(f"Unsupported digest for release asset {asset_name}: {digest}")

    return validate_sha256(expected_sha256, asset_name)


def validate_sha256(expected_sha256, source):
    """Validate and normalize a SHA256 checksum."""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError(f"Invalid SHA256 checksum for {source}: {expected_sha256}")
    return expected_sha256.lower()


def download_with_checksum(url, expected_sha256):
    """Download a file and verify its checksum."""
    expected_sha256 = validate_sha256(expected_sha256, url)
    print(f"Downloading {url}...")

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "git-bin-wheel-builder")

    with urllib.request.urlopen(req) as response:
        data = response.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()

    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"SHA256 mismatch! Expected {expected_sha256}, got {actual_sha256}"
        )

    print(f"  SHA256: {actual_sha256} (verified)")
    return data


def iter_zip_contents(data):
    """Iterate over contents of a ZIP archive."""
    with ZipFile(io.BytesIO(data)) as zip_file:
        for entry in zip_file.infolist():
            if not entry.is_dir():
                yield entry.filename, entry.external_attr >> 16, zip_file.read(entry)


def iter_tar_contents(data):
    """Iterate over contents of a tar archive."""
    # Detect compression
    if data[:2] == b"\x1f\x8b":
        mode = "r:gz"
    elif data[:3] == b"BZh":
        mode = "r:bz2"
    elif data[:6] == b"\xfd7zXZ\x00":
        mode = "r:xz"
    else:
        mode = "r"

    with tarfile.open(fileobj=io.BytesIO(data), mode=mode) as tar:
        for entry in tar:
            if entry.isreg():
                file_obj = tar.extractfile(entry)
                assert file_obj is not None  # Always true for regular files
                yield entry.name, entry.mode | (1 << 15), file_obj.read()


def get_git_executable_name(platform):
    """Get the main git executable name for a platform."""
    if platform.startswith("win"):
        return "cmd/git.exe"
    else:
        return "bin/git"


def resolve_binary_dir(binary_dir, platform, *, require_platform_dir=False):
    """Resolve a direct artifact directory or a child of a shared platform directory."""
    binary_path = Path(binary_dir)
    platform_path = binary_path / platform
    if platform_path.is_dir():
        return platform_path

    has_platform_subdirs = any(
        (binary_path / candidate).is_dir()
        for candidate in PLATFORM_TAGS
        if not candidate.startswith("win")
    )
    if require_platform_dir or has_platform_subdirs:
        raise ValueError(f"Binary directory not found for {platform}: {platform_path}")

    return binary_path


def local_git_files(binary_path: Path) -> Iterator[tuple[ZipInfo, bytes]]:
    """Collect the Unix installation, replacing executable aliases with regular files."""
    for path in sorted(binary_path.rglob("*")):
        relative = path.relative_to(binary_path)
        if path.is_symlink():
            # Wheel installers do not recreate symlinks. Git dispatches built-ins
            # internally, but local transports invoke these dashed names directly.
            target = os.readlink(path)
            if target == "git":
                if path.name not in {"git-upload-pack", "git-receive-pack", "git-upload-archive"}:
                    continue
                command = '"${0%/*}/git" ' + path.name.removeprefix("git-")
            elif target == "git-remote-http":
                command = '"${0%/*}/git-remote-http"'
            else:
                raise ValueError(f"Unexpected Git symlink: {relative} -> {target}")
            data = f'#!/bin/sh\nexec {command} "$@"\n'.encode()
        elif path.is_file():
            data = path.read_bytes()
        else:
            continue

        info = ZipInfo(f"python_git_bin/git/{relative.as_posix()}")
        # pip requires the regular-file flag as well as the executable bit.
        if relative.parts[0] in {"bin", "libexec"}:
            mode = stat.S_IFREG | 0o755
        else:
            mode = path.stat().st_mode
        info.external_attr = (mode & 0xFFFF) << 16
        yield info, data


def write_git_wheel(out_dir, *, version, platform, archive_data=None, binary_dir=None):
    """
    Create a Git wheel for the specified platform.

    Either archive_data (for Windows MinGit) or binary_dir (for local builds) must be provided.
    """
    contents = {}
    python_platform = PLATFORM_TAGS[platform]

    package_dir = Path(__file__).parent / "src" / "python_git_bin"
    for filename in ("__init__.py", "__main__.py"):
        contents[f"python_git_bin/{filename}"] = (package_dir / filename).read_bytes()

    # Process archive contents
    if archive_data:
        # Windows MinGit ZIP
        for entry_name, entry_mode, entry_data in iter_zip_contents(archive_data):
            # MinGit extracts with files at root level
            zip_info = ZipInfo(f"python_git_bin/git/{entry_name}")
            # Preserve executable bit
            if entry_mode:
                zip_info.external_attr = (entry_mode & 0xFFFF) << 16
            elif entry_name.endswith(".exe"):
                zip_info.external_attr = 0o0755 << 16
            else:
                zip_info.external_attr = 0o0644 << 16
            contents[zip_info] = entry_data
    elif binary_dir:
        # Local build directory
        binary_path = Path(binary_dir)
        if not binary_path.exists():
            raise ValueError(f"Binary directory not found: {binary_dir}")

        git_executable = binary_path / get_git_executable_name(platform)
        if not git_executable.is_file():
            raise ValueError(f"Git executable not found for {platform}: {git_executable}")

        contents.update(local_git_files(binary_path))
    else:
        raise ValueError("Either archive_data or binary_dir must be provided")

    # Read description
    readme_path = Path(__file__).parent / "README.pypi.md"
    if readme_path.exists():
        description = readme_path.read_text()
    else:
        description = "Git distributed as a Python package."

    return write_wheel(
        out_dir,
        name="python_git_bin",
        version=version,
        tag=f"py3-none-{python_platform}",
        metadata=[
            ("Summary", "Git - fast, scalable, distributed revision control system"),
            ("Description-Content-Type", "text/markdown"),
            ("License-Expression", "GPL-2.0-only"),
            ("Classifier", "Development Status :: 5 - Production/Stable"),
            ("Classifier", "Intended Audience :: Developers"),
            ("Classifier", "Topic :: Software Development :: Version Control :: Git"),
            ("Classifier", "Programming Language :: C"),
            ("Classifier", "License :: OSI Approved :: GNU General Public License v2 (GPLv2)"),
            ("Project-URL", "Homepage, https://git-scm.com"),
            ("Project-URL", "Source Code, https://github.com/git/git"),
            ("Project-URL", "PyPI Project, https://github.com/zanieb/git-pypi"),
            ("Requires-Python", ">=3.8"),
        ],
        description=description,
        contents=contents,
        license_files=read_license_files(),
    )


def build_windows_wheel(out_dir, git_version, wheel_version, platform):
    """Build a wheel for Windows using official MinGit."""
    print(f"\nBuilding wheel for {platform}...")

    # Fetch release info (uses git version for GitHub API)
    release_info = fetch_git_for_windows_release(git_version)
    print(f"Found release: {release_info.get('tag_name')}")

    # Find MinGit asset
    asset = find_mingit_asset(release_info, platform)
    print(f"Asset: {asset['name']}")

    # Download and verify
    archive_data = download_with_checksum(asset["url"], asset["sha256"])

    # Create wheel (uses wheel version for package metadata)
    wheel_path = write_git_wheel(
        out_dir,
        version=wheel_version,
        platform=platform,
        archive_data=archive_data,
    )

    with open(wheel_path, "rb") as f:
        wheel_hash = hashlib.sha256(f.read()).hexdigest()
    print(f"Created: {wheel_path}")
    print(f"  SHA256: {wheel_hash}")

    return wheel_path


def build_local_wheel(out_dir, version, platform, binary_dir):
    """Build a wheel using locally built binaries."""
    print(f"\nBuilding wheel for {platform} from {binary_dir}...")

    wheel_path = write_git_wheel(
        out_dir,
        version=version,
        platform=platform,
        binary_dir=binary_dir,
    )

    with open(wheel_path, "rb") as f:
        wheel_hash = hashlib.sha256(f.read()).hexdigest()
    print(f"Created: {wheel_path}")
    print(f"  SHA256: {wheel_hash}")

    return wheel_path


def main():
    parser = argparse.ArgumentParser(
        description="Build Git wheels for PyPI distribution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Build Windows x64 wheel (version: 2.56.1.<today>)
    uv run make_wheels.py --version 2.56.1 --platform win_amd64

    # Build with specific build date (version: 2.56.1.20261124)
    uv run make_wheels.py --version 2.56.1 --platform win_amd64 --build 20261124

    # Build from local binaries
    uv run make_wheels.py --version 2.56.1 --platform linux_x86_64 \\
        --binary-dir ./build/output/linux_x86_64

    # Build all platforms
    uv run make_wheels.py --version 2.56.1 --platform all
""",
    )
    parser.add_argument("--version", required=True, help="Git version to package (e.g., 2.56.1)")
    platforms_list = ", ".join(PLATFORM_TAGS.keys())
    parser.add_argument(
        "--platform",
        action="append",
        default=[],
        help=f"Platform to build for. Options: {platforms_list}, all",
    )
    parser.add_argument(
        "--outdir", default="dist/", help="Output directory for wheels (default: dist/)"
    )
    parser.add_argument(
        "--binary-dir", help="Directory containing pre-built Git binaries (for macOS/Linux)"
    )
    parser.add_argument(
        "--build", help="Build date as YYYYMMDD (default: today). Fourth version component."
    )

    args = parser.parse_args()
    logging.getLogger("wheel").setLevel(logging.WARNING)

    # Determine platforms
    platforms = args.platform
    if not platforms:
        parser.error("At least one --platform is required")

    if "all" in platforms:
        platforms = list(PLATFORM_TAGS.keys())

    local_platforms = {
        platform
        for platform in platforms
        if platform in PLATFORM_TAGS and not platform.startswith("win")
    }

    # Create output directory
    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Effective version: <git-version>.<build-date>
    build_date = args.build or datetime.now(timezone.utc).strftime("%Y%m%d")
    wheel_version = args.version.replace("-", ".") + "." + build_date

    # Build wheels
    for platform in platforms:
        if platform not in PLATFORM_TAGS:
            print(f"Unknown platform: {platform}, skipping")
            continue

        if platform.startswith("win"):
            # Windows: download official MinGit
            build_windows_wheel(out_dir, args.version, wheel_version, platform)
        else:
            # macOS/Linux: use local binaries
            if not args.binary_dir:
                print(f"Skipping {platform}: --binary-dir required for non-Windows platforms")
                continue

            binary_dir = resolve_binary_dir(
                args.binary_dir,
                platform,
                require_platform_dir=len(local_platforms) > 1,
            )

            build_local_wheel(str(out_dir), wheel_version, platform, str(binary_dir))

    print(f"\nDone! Wheels written to {out_dir}")


if __name__ == "__main__":
    main()
