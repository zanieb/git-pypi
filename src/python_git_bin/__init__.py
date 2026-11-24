"""Run the Git installation bundled with this wheel."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

__all__ = ["GIT_DIR", "GIT_EXE", "GIT_EXEC_PATH", "git", "main"]

GIT_DIR = Path(__file__).parent / "git"
if sys.platform == "win32":
    GIT_EXE = GIT_DIR / "cmd" / "git.exe"
    # MinGit's toolchain directory varies by architecture and release.
    (GIT_EXEC_PATH,) = GIT_DIR.glob("*/libexec/git-core")
else:
    GIT_EXE = GIT_DIR / "bin" / "git"
    GIT_EXEC_PATH = GIT_DIR / "libexec" / "git-core"


def git(*args: str | os.PathLike[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """Run Git with the given arguments and subprocess options."""
    return subprocess.run([str(GIT_EXE), *args], **kwargs)


def main() -> None:
    """Run Git with the command-line arguments."""
    if sys.platform == "win32":
        sys.exit(git(*sys.argv[1:]).returncode)
    os.execv(GIT_EXE, [str(GIT_EXE), *sys.argv[1:]])
