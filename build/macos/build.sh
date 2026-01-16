#!/usr/bin/env bash
#
# Build Git for macOS
#
# This script builds Git from source on macOS, creating a relocatable
# installation that can be packaged into a Python wheel.
#
# Usage:
#   ./build/macos/build.sh [GIT_VERSION] [ARCH]
#
# Examples:
#   ./build/macos/build.sh 2.47.1           # Build for current architecture
#   ./build/macos/build.sh 2.47.1 x86_64    # Cross-compile for Intel
#   ./build/macos/build.sh 2.47.1 arm64     # Cross-compile for Apple Silicon
#
# Prerequisites:
#   - Xcode Command Line Tools
#   - Optional: openssl, curl (via Homebrew for better HTTPS support)
#
# Output: build/output/macos_{arch}/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GIT_VERSION="${1:-2.47.1}"
HOST_ARCH="$(uname -m)"
ARCH="${2:-$HOST_ARCH}"  # Target architecture, defaults to host

# Validate architecture
if [[ "$ARCH" != "x86_64" && "$ARCH" != "arm64" ]]; then
    echo "Error: Unsupported architecture: $ARCH"
    echo "Supported: x86_64, arm64"
    exit 1
fi

CROSS_COMPILE=false
if [ "$ARCH" != "$HOST_ARCH" ]; then
    CROSS_COMPILE=true
    echo "Cross-compiling for $ARCH (host is $HOST_ARCH)"
fi

# Map to our platform names
PLATFORM="macos_$ARCH"

OUTPUT_DIR="$PROJECT_ROOT/build/output/$PLATFORM"
BUILD_DIR="$PROJECT_ROOT/build/tmp/git-$GIT_VERSION-$ARCH"
INSTALL_DIR="$BUILD_DIR/install"

echo "========================================"
echo "Building Git $GIT_VERSION for macOS $ARCH"
echo "========================================"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Check prerequisites
if ! xcode-select -p &>/dev/null; then
    echo "Error: Xcode Command Line Tools not installed"
    echo "Run: xcode-select --install"
    exit 1
fi

# Create directories
mkdir -p "$BUILD_DIR" "$OUTPUT_DIR"

# Download Git source if needed
GIT_TARBALL="$BUILD_DIR/git-$GIT_VERSION.tar.xz"
GIT_SRC="$BUILD_DIR/git-$GIT_VERSION"

if [ ! -f "$GIT_TARBALL" ]; then
    echo "Downloading Git $GIT_VERSION source..."
    curl -fSL "https://mirrors.edge.kernel.org/pub/software/scm/git/git-$GIT_VERSION.tar.xz" \
        -o "$GIT_TARBALL"
fi

if [ ! -d "$GIT_SRC" ]; then
    echo "Extracting source..."
    tar -xf "$GIT_TARBALL" -C "$BUILD_DIR"
fi

cd "$GIT_SRC"

# Set up build flags
# Use system OpenSSL/LibreSSL on macOS by default
# Target macOS versions following python-build-standalone conventions:
#   - x86_64: 10.15 (Catalina) - last Intel-only macOS
#   - arm64: 11.0 (Big Sur) - first Apple Silicon macOS

if [ "$ARCH" = "arm64" ]; then
    export MACOSX_DEPLOYMENT_TARGET=11.0
else
    export MACOSX_DEPLOYMENT_TARGET=10.15
fi

# Check for Homebrew OpenSSL (preferred for HTTPS)
# Skip Homebrew libraries when cross-compiling since they're single-arch
OPENSSL_PREFIX=""
CURL_PREFIX=""

if [ "$CROSS_COMPILE" = false ]; then
    if [ -d "/opt/homebrew/opt/openssl@3" ]; then
        OPENSSL_PREFIX="/opt/homebrew/opt/openssl@3"
    elif [ -d "/usr/local/opt/openssl@3" ]; then
        OPENSSL_PREFIX="/usr/local/opt/openssl@3"
    elif [ -d "/opt/homebrew/opt/openssl@1.1" ]; then
        OPENSSL_PREFIX="/opt/homebrew/opt/openssl@1.1"
    elif [ -d "/usr/local/opt/openssl@1.1" ]; then
        OPENSSL_PREFIX="/usr/local/opt/openssl@1.1"
    fi

    if [ -d "/opt/homebrew/opt/curl" ]; then
        CURL_PREFIX="/opt/homebrew/opt/curl"
    elif [ -d "/usr/local/opt/curl" ]; then
        CURL_PREFIX="/usr/local/opt/curl"
    fi
else
    echo "Cross-compiling: using system libraries only (no Homebrew)"
fi

EXTRA_CFLAGS="-arch $ARCH"
EXTRA_LDFLAGS="-arch $ARCH"
EXTRA_MAKE_FLAGS=""

# For cross-compilation, we need to override CC to always emit the target architecture
# Just passing CFLAGS isn't enough as git's Makefile autodetection can override them
CC_CMD="cc"
if [ "$CROSS_COMPILE" = true ]; then
    CC_CMD="cc -arch $ARCH"
    EXTRA_MAKE_FLAGS="$EXTRA_MAKE_FLAGS HOST_CPU=$ARCH"
fi

if [ -n "$OPENSSL_PREFIX" ]; then
    echo "Using OpenSSL from: $OPENSSL_PREFIX"
    EXTRA_CFLAGS="$EXTRA_CFLAGS -I$OPENSSL_PREFIX/include"
    EXTRA_LDFLAGS="$EXTRA_LDFLAGS -L$OPENSSL_PREFIX/lib"
fi

if [ -n "$CURL_PREFIX" ]; then
    echo "Using curl from: $CURL_PREFIX"
    EXTRA_CFLAGS="$EXTRA_CFLAGS -I$CURL_PREFIX/include"
    EXTRA_LDFLAGS="$EXTRA_LDFLAGS -L$CURL_PREFIX/lib"
    EXTRA_MAKE_FLAGS="$EXTRA_MAKE_FLAGS CURLDIR=$CURL_PREFIX"
fi

echo ""
echo "Building Git..."

# Clean any previous build (thorough clean for cross-compilation)
make clean 2>/dev/null || true
find . -name '*.o' -delete 2>/dev/null || true
find . -name '*.a' -delete 2>/dev/null || true

# Configure and build
# Key flags:
#   NO_GETTEXT=1 - Skip internationalization
#   NO_TCLTK=1 - Skip Tcl/Tk GUI
#   NO_PERL=1 - Skip Perl scripts for minimal install
#   NO_INSTALL_HARDLINKS=1 - Use copies instead of hardlinks for portability

make -j$(sysctl -n hw.ncpu) \
    CC="$CC_CMD" \
    prefix=/usr/local \
    gitexecdir=/usr/local/libexec/git-core \
    NO_GETTEXT=1 \
    NO_TCLTK=1 \
    NO_PERL=1 \
    NO_PYTHON=1 \
    NO_INSTALL_HARDLINKS=1 \
    CFLAGS="-O2 $EXTRA_CFLAGS" \
    LDFLAGS="$EXTRA_LDFLAGS" \
    $EXTRA_MAKE_FLAGS \
    all

echo ""
echo "Installing to staging directory..."

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

make \
    CC="$CC_CMD" \
    prefix=/usr/local \
    gitexecdir=/usr/local/libexec/git-core \
    NO_GETTEXT=1 \
    NO_TCLTK=1 \
    NO_PERL=1 \
    NO_PYTHON=1 \
    NO_INSTALL_HARDLINKS=1 \
    DESTDIR="$INSTALL_DIR" \
    install

# Reorganize for distribution
# We want a self-contained structure:
#   bin/git
#   libexec/git-core/
#   share/git-core/

echo ""
echo "Creating distribution layout..."

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/bin" "$OUTPUT_DIR/libexec"

cp "$INSTALL_DIR/usr/local/bin/git" "$OUTPUT_DIR/bin/"
cp -R "$INSTALL_DIR/usr/local/libexec/git-core" "$OUTPUT_DIR/libexec/"

# Copy templates if present
if [ -d "$INSTALL_DIR/usr/local/share/git-core" ]; then
    mkdir -p "$OUTPUT_DIR/share"
    cp -R "$INSTALL_DIR/usr/local/share/git-core" "$OUTPUT_DIR/share/"
fi

# Fix up library paths to be relocatable
# On macOS, we need to adjust rpath for any dynamic libraries
echo ""
echo "Checking library dependencies..."

# Show dependencies
otool -L "$OUTPUT_DIR/bin/git" || true

# For a fully portable binary, we'd need to bundle dependent dylibs
# and fix up paths with install_name_tool. For now, we rely on
# system libraries which are available on all targeted macOS versions
# (10.15+ for x86_64, 11.0+ for arm64)

# Verify the build
echo ""
echo "Testing build..."
# When cross-compiling to arm64 from x86_64, we can't run the binary
# When cross-compiling to x86_64 from arm64, Rosetta 2 can run it
if [ "$CROSS_COMPILE" = true ] && [ "$ARCH" = "arm64" ]; then
    echo "Cross-compiled for arm64 - skipping runtime test (use 'arch -arm64' or run on Apple Silicon)"
    file "$OUTPUT_DIR/bin/git"
else
    "$OUTPUT_DIR/bin/git" --version
fi

echo ""
echo "Build complete!"
echo ""
echo "Files in $OUTPUT_DIR:"
find "$OUTPUT_DIR" -type f | head -20
echo "..."
du -sh "$OUTPUT_DIR"

echo ""
echo "To create a wheel:"
echo "  uv run make_wheels.py --version $GIT_VERSION --platform $PLATFORM --binary-dir $OUTPUT_DIR"
