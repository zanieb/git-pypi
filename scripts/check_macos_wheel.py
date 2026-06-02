"""Verify that Mach-O files in macOS wheels link only system libraries."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

MACHO_MAGICS = {
    b"\xca\xfe\xba\xbe",  # Fat binary, big-endian
    b"\xbe\xba\xfe\xca",  # Fat binary, little-endian
    b"\xca\xfe\xba\xbf",  # Fat 64-bit binary, big-endian
    b"\xbf\xba\xfe\xca",  # Fat 64-bit binary, little-endian
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit, big-endian
    b"\xce\xfa\xed\xfe",  # Mach-O 32-bit, little-endian
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit, big-endian
    b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit, little-endian
}
SYSTEM_LIBRARY_PREFIXES = ("/usr/lib/", "/System/Library/")
DEPENDENCY_LINE = re.compile(r"^\s+(.+?) \(compatibility version ")

DependencyReader = Callable[[Path], list[str]]


def is_macho_magic(magic: bytes) -> bool:
    """Return whether the first four bytes identify a Mach-O binary."""
    return magic in MACHO_MAGICS


def parse_otool_dependencies(output: str) -> list[str]:
    """Parse dependency paths from `otool -L` output."""
    dependencies = []
    for line in output.splitlines():
        match = DEPENDENCY_LINE.match(line)
        if match:
            dependencies.append(match.group(1))
    return dependencies


def read_dependencies(binary_path: Path) -> list[str]:
    """Read dynamic library dependencies from a Mach-O binary."""
    try:
        result = subprocess.run(
            ["otool", "-L", str(binary_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("otool is required to inspect macOS wheels") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"otool failed with exit code {result.returncode}: {message}")

    return parse_otool_dependencies(result.stdout)


def is_system_dependency(dependency: str) -> bool:
    """Return whether a dependency is provided by the macOS system."""
    return dependency.startswith(SYSTEM_LIBRARY_PREFIXES)


def check_wheel(
    wheel_path: Path,
    dependency_reader: DependencyReader = read_dependencies,
) -> tuple[int, list[str]]:
    """Check one wheel and return the number of Mach-O files and any errors."""
    checked = 0
    errors = []
    dependency_cache: dict[bytes, list[str]] = {}
    non_system_users: dict[str, list[str]] = {}

    with ZipFile(wheel_path) as wheel, TemporaryDirectory(prefix="check-macos-wheel-") as temp_dir:
        for index, member in enumerate(wheel.infolist()):
            if member.is_dir():
                continue

            with wheel.open(member) as member_file:
                magic = member_file.read(4)
                if not is_macho_magic(magic):
                    continue
                contents = magic + member_file.read()

            checked += 1
            digest = hashlib.sha256(contents).digest()
            if digest in dependency_cache:
                dependencies = dependency_cache[digest]
            else:
                binary_path = Path(temp_dir) / str(index)
                binary_path.write_bytes(contents)
                try:
                    dependencies = dependency_reader(binary_path)
                except RuntimeError as exc:
                    errors.append(f"{member.filename}: {exc}")
                    continue
                dependency_cache[digest] = dependencies

            for dependency in dependencies:
                if not is_system_dependency(dependency):
                    non_system_users.setdefault(dependency, []).append(member.filename)

    if checked == 0:
        errors.append("no Mach-O files found")

    for dependency, members in sorted(non_system_users.items()):
        member_list = ", ".join(sorted(members))
        errors.append(f"non-system dependency {dependency!r} used by: {member_list}")

    return checked, errors


def main(argv: Sequence[str] | None = None) -> int:
    """Check macOS wheels from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", nargs="+", type=Path, help="macOS wheel files to inspect")
    args = parser.parse_args(argv)

    failed = False
    for wheel_path in args.wheels:
        try:
            checked, errors = check_wheel(wheel_path)
        except (BadZipFile, OSError) as exc:
            checked, errors = 0, [str(exc)]

        if errors:
            failed = True
            print(f"{wheel_path}: FAILED", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        else:
            print(f"{wheel_path}: checked {checked} Mach-O files")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
