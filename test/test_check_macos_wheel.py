"""Tests for macOS wheel dependency verification."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zipfile import ZipFile

CHECKER_PATH = Path(__file__).parents[1] / "scripts" / "check_macos_wheel.py"
CHECKER_SPEC = spec_from_file_location("check_macos_wheel", CHECKER_PATH)
assert CHECKER_SPEC is not None
assert CHECKER_SPEC.loader is not None
CHECKER = module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)

check_wheel = CHECKER.check_wheel
is_macho_magic = CHECKER.is_macho_magic
is_system_dependency = CHECKER.is_system_dependency
parse_otool_dependencies = CHECKER.parse_otool_dependencies

MACHO_CONTENTS = b"\xcf\xfa\xed\xfe" + b"\0" * 16


def write_wheel(path: Path, contents: dict[str, bytes]) -> None:
    """Write a minimal wheel-like ZIP archive for dependency checker tests."""
    with ZipFile(path, "w") as wheel:
        for name, data in contents.items():
            wheel.writestr(name, data)


def test_is_macho_magic() -> None:
    assert is_macho_magic(MACHO_CONTENTS[:4])
    assert not is_macho_magic(b"#!/u")


def test_parse_otool_dependencies() -> None:
    output = (
        "binary:\n"
        "\t/usr/lib/libz.1.dylib "
        "(compatibility version 1.0.0, current version 1.2.12)\n"
        "\t/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation "
        "(compatibility version 150.0.0, current version 3502.1.255)\n"
    )
    assert parse_otool_dependencies(output) == [
        "/usr/lib/libz.1.dylib",
        "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
    ]


def test_is_system_dependency() -> None:
    assert is_system_dependency("/usr/lib/libcurl.4.dylib")
    assert is_system_dependency("/System/Library/Frameworks/CoreServices.framework/CoreServices")
    assert not is_system_dependency("/usr/local/opt/curl/lib/libcurl.4.dylib")
    assert not is_system_dependency("@rpath/libcurl.4.dylib")


def test_check_wheel_accepts_system_dependencies(tmp_path: Path) -> None:
    wheel_path = tmp_path / "system.whl"
    write_wheel(wheel_path, {"python_git_bin/git/bin/git": MACHO_CONTENTS})

    checked, errors = check_wheel(
        wheel_path,
        dependency_reader=lambda _: ["/usr/lib/libSystem.B.dylib"],
    )

    assert checked == 1
    assert errors == []


def test_check_wheel_rejects_non_system_dependencies(tmp_path: Path) -> None:
    wheel_path = tmp_path / "homebrew.whl"
    member = "python_git_bin/git/libexec/git-core/git-remote-https"
    write_wheel(wheel_path, {member: MACHO_CONTENTS})

    checked, errors = check_wheel(
        wheel_path,
        dependency_reader=lambda _: ["/usr/local/opt/curl/lib/libcurl.4.dylib"],
    )

    assert checked == 1
    assert errors == [
        "non-system dependency '/usr/local/opt/curl/lib/libcurl.4.dylib' used by: "
        f"{member}"
    ]


def test_check_wheel_reads_identical_binaries_once(tmp_path: Path) -> None:
    wheel_path = tmp_path / "duplicates.whl"
    write_wheel(
        wheel_path,
        {
            "python_git_bin/git/bin/git": MACHO_CONTENTS,
            "python_git_bin/git/libexec/git-core/git": MACHO_CONTENTS,
        },
    )
    calls = 0

    def dependency_reader(_: Path) -> list[str]:
        nonlocal calls
        calls += 1
        return ["/usr/lib/libSystem.B.dylib"]

    checked, errors = check_wheel(wheel_path, dependency_reader=dependency_reader)

    assert checked == 2
    assert calls == 1
    assert errors == []


def test_check_wheel_requires_macho_files(tmp_path: Path) -> None:
    wheel_path = tmp_path / "empty.whl"
    write_wheel(wheel_path, {"python_git_bin/__init__.py": b""})

    checked, errors = check_wheel(wheel_path)

    assert checked == 0
    assert errors == ["no Mach-O files found"]
