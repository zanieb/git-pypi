# git-bin

Git distributed as a Python package.

This package provides [Git](https://git-scm.com), the fast, scalable, distributed revision control system, as a Python wheel. Similar to [ziglang](https://pypi.org/project/ziglang/), this allows you to install and use Git without system-level installation.

## Installation

```bash
pip install git-bin
```

## Usage

After installation, Git is available as a command-line tool:

```bash
# Use via the entry point
git --version
git clone https://github.com/user/repo.git
git status

# Or use programmatically
python -m python_git_bin --version
```

### Programmatic Usage

```python
import subprocess
from python_git_bin import GIT_EXE

# Run git commands
result = subprocess.run([str(GIT_EXE), 'status'], capture_output=True, text=True)
print(result.stdout)
```

## Supported Platforms

| Platform | Architecture | Notes |
|----------|--------------|-------|
| Windows | x64, ARM64, x86 | Official MinGit from Git for Windows |
| macOS | Intel, Apple Silicon | Built from source |
| Linux | x64, ARM64 | Static musl build with HTTPS support |

## Features

- Full Git functionality including HTTPS clone support
- No system dependencies on Linux (static build)
- Works in virtual environments and CI/CD pipelines
- Compatible with Python 3.8+

## Use Cases

- **CI/CD Pipelines**: Install Git as a project dependency
- **Containerized Environments**: Add Git without modifying base images
- **Virtual Environments**: Isolate Git version per project
- **Cross-platform Scripts**: Ensure consistent Git availability

## License

Git is licensed under [GPL-2.0](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html).

## Links

- [Git Homepage](https://git-scm.com)
- [Git Source Code](https://github.com/git/git)
- [git-bin Source](https://github.com/zanieb/git-pypi)
