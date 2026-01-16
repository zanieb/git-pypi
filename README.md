# git-pypi

Python wheels for Git.

## Overview

This project builds and packages Git binaries for distribution via PyPI. The resulting `git-bin` package allows users to install Git as a Python dependency.

## Building Wheels

macOS and Linux wheels are built from source.

### Prerequisites

- [uv](https://github.com/astral-sh/uv)
- Docker (for Linux builds)
- Xcode Command Line Tools (for macOS builds)

### Windows

Windows wheels download official MinGit builds from [Git for Windows](https://github.com/git-for-windows/git/releases).

```bash
uv run make_wheels.py --version 2.47.1 --platform win_amd64
uv run make_wheels.py --version 2.47.1 --platform win_arm64
uv run make_wheels.py --version 2.47.1 --platform win32
```

### Linux

Linux builds are performed in Docker using Alpine Linux and are **fully statically linked** against musl libc. This means Linux wheels have zero runtime dependencies and will run on any Linux distribution (glibc or musl based).

The static build includes:
- OpenSSL (for HTTPS support)
- curl (for HTTP/HTTPS transport)
- zlib (for compression)

```bash
./build/linux/build.sh 2.47.1 x86_64
./build/linux/build.sh 2.47.1 aarch64
uv run make_wheels.py --version 2.47.1 --platform linux_x86_64 --binary-dir build/output/linux_x86_64
uv run make_wheels.py --version 2.47.1 --platform linux_aarch64 --binary-dir build/output/linux_aarch64
```

### macOS

macOS builds are **dynamically linked against system libraries only**. This ensures portability across macOS versions without bundling any third-party libraries. The build targets:
- macOS 10.15+ (Catalina) for Intel
- macOS 11.0+ (Big Sur) for Apple Silicon

System libraries used:
- `/usr/lib/libcurl.4.dylib` - HTTP/HTTPS transport
- `/usr/lib/libz.1.dylib` - compression
- `/usr/lib/libiconv.2.dylib` - character encoding
- `/usr/lib/libexpat.1.dylib` - XML parsing
- `/usr/lib/libSystem.B.dylib` - system calls
- `/System/Library/Frameworks/CoreFoundation.framework` - Core Foundation
- `/System/Library/Frameworks/CoreServices.framework` - Core Services

The CI build verifies that no non-system libraries (e.g., Homebrew) are linked. If the build accidentally links against non-system libraries, CI will fail.

```bash
./build/macos/build.sh 2.47.1
uv run make_wheels.py --version 2.47.1 --platform macos_arm64 --binary-dir build/output/macos_arm64
uv run make_wheels.py --version 2.47.1 --platform macos_x86_64 --binary-dir build/output/macos_x86_64
```

## Supported Platforms

- Windows x64, ARM64, x86
- macOS Intel and Apple Silicon
- Linux x64 and ARM64

## License

The build tooling is licensed under either of

- Apache License, Version 2.0, ([LICENSE-APACHE](LICENSE-APACHE) or
  <https://www.apache.org/licenses/LICENSE-2.0>)
- MIT license ([LICENSE-MIT](LICENSE-MIT) or <https://opensource.org/licenses/MIT>)

at your option.

Unless you explicitly state otherwise, any contribution intentionally submitted for inclusion in this project by you, as defined in the Apache-2.0 license, shall be dually licensed as above, without any additional terms or conditions.

The distributed Git binaries are licensed under [GPL-2.0](https://opensource.org/licenses/GPL-2.0) and include third-party components with their own licenses. See [NOTICE](NOTICE) for details and [licenses/](licenses/) for the full license texts.

## Acknowledgments

This project is inspired by [ziglang](https://github.com/ziglang/zig-pypi), which distributes the Zig compiler as Python wheels.
