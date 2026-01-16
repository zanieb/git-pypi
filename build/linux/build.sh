#!/usr/bin/env bash
#
# Build static Git binaries for Linux using Docker
#
# Usage:
#   ./build/linux/build.sh [GIT_VERSION] [ARCH]
#
# Examples:
#   ./build/linux/build.sh 2.47.1              # Build for current architecture
#   ./build/linux/build.sh 2.47.1 x86_64       # Build for x86_64
#   ./build/linux/build.sh 2.47.1 aarch64      # Build for ARM64
#
# Output: build/output/linux_{arch}/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

GIT_VERSION="${1:-2.47.1}"
ARCH="${2:-$(uname -m)}"

# Normalize architecture names
case "$ARCH" in
    x86_64|amd64)
        ARCH="x86_64"
        DOCKER_PLATFORM="linux/amd64"
        ;;
    aarch64|arm64)
        ARCH="aarch64"
        DOCKER_PLATFORM="linux/arm64"
        ;;
    *)
        echo "Unsupported architecture: $ARCH"
        echo "Supported: x86_64, aarch64"
        exit 1
        ;;
esac

OUTPUT_DIR="$PROJECT_ROOT/build/output/linux_${ARCH}"
IMAGE_NAME="git-builder-linux-${ARCH}"

echo "========================================"
echo "Building Git $GIT_VERSION for Linux $ARCH"
echo "========================================"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Check if docker buildx is available for cross-platform builds
if docker buildx version &>/dev/null; then
    DOCKER_BUILD="docker buildx build --load"
else
    DOCKER_BUILD="docker build"
    if [ "$ARCH" != "$(uname -m)" ] && [ "$ARCH" != "amd64" -o "$(uname -m)" != "x86_64" ]; then
        echo "Warning: docker buildx not available, cross-platform build may not work"
    fi
fi

# Build the Docker image
echo "Building Docker image..."
$DOCKER_BUILD \
    --platform "$DOCKER_PLATFORM" \
    --build-arg GIT_VERSION="$GIT_VERSION" \
    -t "$IMAGE_NAME" \
    -f "$SCRIPT_DIR/Dockerfile" \
    "$PROJECT_ROOT"

# Run the container to extract files
echo ""
echo "Extracting built files..."
docker run --rm \
    --platform "$DOCKER_PLATFORM" \
    -v "$OUTPUT_DIR:/output" \
    "$IMAGE_NAME"

# Verify
echo ""
echo "Build complete!"
echo "Files in $OUTPUT_DIR:"
ls -la "$OUTPUT_DIR"

# Show git version
if [ -x "$OUTPUT_DIR/bin/git" ]; then
    echo ""
    echo "Git version:"
    # Can't run directly if cross-compiled, but can at least check it exists
    file "$OUTPUT_DIR/bin/git"
fi

echo ""
echo "To create a wheel:"
echo "  uv run make_wheels.py --version $GIT_VERSION --platform linux_$ARCH --binary-dir $OUTPUT_DIR"
