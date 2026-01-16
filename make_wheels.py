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
  e.g., 2.47.1.20260118 for Git 2.47.1 built on 2026-01-18

Usage:
    uv run make_wheels.py --version 2.47.1 --platform win_amd64
    uv run make_wheels.py --version 2.47.1 --platform all
    uv run make_wheels.py --version 2.47.1 --platform linux_x86_64 --binary-dir ./build-output
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


def write_wheel(out_dir, *, name, version, tag, metadata, description, contents):
    """Write a complete wheel with metadata."""
    wheel_name = f"{name}-{version}-{tag}.whl"
    dist_info = f"{name}-{version}.dist-info"

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
            f"{dist_info}/entry_points.txt": make_message(
                [], "[console_scripts]\ngit = python_git_bin:main"
            ),
            f"{dist_info}/METADATA": make_message(
                [
                    ("Metadata-Version", "2.4"),
                    ("Name", name),
                    ("Version", version),
                    *metadata,
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
            # Find corresponding .sha256 file
            sha256_name = asset["name"] + ".sha256"
            sha256_url = None
            for sha_asset in release_info.get("assets", []):
                if sha_asset["name"] == sha256_name:
                    sha256_url = sha_asset["browser_download_url"]
                    break

            return {
                "url": asset["browser_download_url"],
                "name": asset["name"],
                "sha256_url": sha256_url,
            }

    raise ValueError(f"MinGit asset not found for platform: {platform}")


def download_with_checksum(url, sha256_url=None, expected_sha256=None):
    """Download a file and verify its checksum."""
    print(f"Downloading {url}...")

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "git-bin-wheel-builder")

    with urllib.request.urlopen(req) as response:
        data = response.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()

    # Get expected checksum
    if expected_sha256:
        expected = expected_sha256
    elif sha256_url:
        req = urllib.request.Request(sha256_url)
        req.add_header("User-Agent", "git-bin-wheel-builder")
        with urllib.request.urlopen(req) as response:
            # Format is usually "hash  filename" or just "hash"
            expected = response.read().decode().split()[0].lower()
    else:
        print(f"  SHA256: {actual_sha256} (no verification)")
        return data

    if actual_sha256.lower() != expected.lower():
        raise ValueError(f"SHA256 mismatch! Expected {expected}, got {actual_sha256}")

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


def write_git_wheel(out_dir, *, version, platform, archive_data=None, binary_dir=None):
    """
    Create a Git wheel for the specified platform.

    Either archive_data (for Windows MinGit) or binary_dir (for local builds) must be provided.
    """
    contents = {}
    python_platform = PLATFORM_TAGS[platform]

    # Create __init__.py
    contents["python_git_bin/__init__.py"] = b'''"""Git binary distribution package."""

import os
import subprocess
import sys
from pathlib import Path

__all__ = ['GIT_DIR', 'GIT_EXE', 'GIT_EXEC_PATH', 'main', 'run']

# Directory containing git installation
GIT_DIR = Path(__file__).parent / 'git'

# Path to git executable and exec path for helpers
if sys.platform == 'win32':
    GIT_EXE = GIT_DIR / 'cmd' / 'git.exe'
    GIT_EXEC_PATH = GIT_DIR / 'mingw64' / 'libexec' / 'git-core'
else:
    GIT_EXE = GIT_DIR / 'bin' / 'git'
    GIT_EXEC_PATH = GIT_DIR / 'libexec' / 'git-core'


def _get_env():
    """Get environment with GIT_EXEC_PATH set."""
    env = os.environ.copy()
    env['GIT_EXEC_PATH'] = str(GIT_EXEC_PATH)
    # Also set template dir for init/clone operations
    template_dir = GIT_DIR / 'share' / 'git-core' / 'templates'
    if template_dir.exists():
        env['GIT_TEMPLATE_DIR'] = str(template_dir)
    return env


def run(*args, **kwargs):
    """Run git with given arguments. Returns CompletedProcess."""
    cmd = [str(GIT_EXE)] + list(args)
    kwargs.setdefault('env', _get_env())
    return subprocess.run(cmd, **kwargs)


def main():
    """Run git with command line arguments."""
    env = _get_env()
    sys.exit(subprocess.call([str(GIT_EXE)] + sys.argv[1:], env=env))
'''

    # Create __main__.py for python -m python_git_bin support
    contents["python_git_bin/__main__.py"] = b'''"""Allow running as python -m python_git_bin."""
from python_git_bin import main
main()
'''

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

        for file_path in binary_path.rglob("*"):
            rel_path = file_path.relative_to(binary_path)
            zip_info = ZipInfo(f"python_git_bin/git/{rel_path}")

            if file_path.is_symlink():
                target = os.readlink(file_path)
                # Symlinks to 'git' are not needed - git dispatches internally via argv[0]
                if target == "git":
                    continue
                # For symlinks to other targets (like git-remote-https -> git-remote-http),
                # create a tiny Python shim instead of copying the whole binary. Python
                # shims are cross-platform and consistent with how pip generates entry points.
                shim_script = f"""#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
target = Path(__file__).parent / {target!r}
sys.exit(subprocess.call([str(target)] + sys.argv[1:]))
"""
                zip_info.external_attr = (0o0755) << 16
                contents[zip_info] = shim_script.encode("utf-8")
            elif file_path.is_file():
                # Determine file permissions
                # Executables in bin/ and libexec/ should always have execute permissions
                # even if source files lost them during tar extraction
                rel_str = str(rel_path)
                if rel_str.startswith("bin/") or rel_str.startswith("libexec/"):
                    # Executable: rwxr-xr-x
                    mode = stat.S_IFREG | 0o755
                else:
                    # Preserve original permissions
                    mode = file_path.stat().st_mode
                zip_info.external_attr = (mode & 0xFFFF) << 16
                contents[zip_info] = file_path.read_bytes()
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
    archive_data = download_with_checksum(asset["url"], sha256_url=asset.get("sha256_url"))

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
    # Build Windows x64 wheel (version: 2.47.1.<today>)
    uv run make_wheels.py --version 2.47.1 --platform win_amd64

    # Build with specific build date (version: 2.47.1.20260115)
    uv run make_wheels.py --version 2.47.1 --platform win_amd64 --build 20260115

    # Build from local binaries
    uv run make_wheels.py --version 2.47.1 --platform linux_x86_64 \\
        --binary-dir ./build/output/linux-x86_64

    # Build all platforms
    uv run make_wheels.py --version 2.47.1 --platform all
""",
    )
    parser.add_argument("--version", required=True, help="Git version to package (e.g., 2.47.1)")
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

            # Check for platform-specific subdirectory
            binary_dir = Path(args.binary_dir)
            platform_dir = binary_dir / platform
            if platform_dir.exists():
                binary_dir = platform_dir

            build_local_wheel(str(out_dir), wheel_version, platform, str(binary_dir))

    print(f"\nDone! Wheels written to {out_dir}")


if __name__ == "__main__":
    main()
