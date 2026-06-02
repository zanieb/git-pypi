#!/bin/sh
#
# Fetch an immutable Git source commit into a new directory.
#
# Usage:
#   ./build/fetch_git_source.sh <full-commit-sha> <destination>
#
# Set GIT_SOURCE_REPOSITORY to fetch from a repository other than
# https://github.com/git/git.git.

set -eu

GIT_COMMIT="${1:-}"
DESTINATION="${2:-}"
GIT_SOURCE_REPOSITORY="${GIT_SOURCE_REPOSITORY:-https://github.com/git/git.git}"

if [ -z "$GIT_COMMIT" ] || [ -z "$DESTINATION" ]; then
    echo "Usage: $0 <full-commit-sha> <destination>" >&2
    exit 2
fi

if ! printf '%s\n' "$GIT_COMMIT" | grep -Eq '^[0-9a-fA-F]{40}$'; then
    echo "Error: Git source commit must be a full 40-character SHA: $GIT_COMMIT" >&2
    exit 1
fi

if [ -e "$DESTINATION" ]; then
    echo "Error: Git source destination already exists: $DESTINATION" >&2
    exit 1
fi

echo "Fetching Git source commit $GIT_COMMIT from $GIT_SOURCE_REPOSITORY..."
git init --quiet "$DESTINATION"
git -C "$DESTINATION" remote add origin "$GIT_SOURCE_REPOSITORY"

# Fetch tags and commit history so Git's GIT-VERSION-GEN can describe
# development builds. Blob filtering keeps the transfer focused on the source
# tree that is actually checked out when the server supports partial clone.
git -C "$DESTINATION" fetch --quiet --filter=blob:none --tags origin "$GIT_COMMIT"
git -C "$DESTINATION" checkout --quiet --detach FETCH_HEAD

actual_commit="$(git -C "$DESTINATION" rev-parse HEAD)"
if [ "$actual_commit" != "$GIT_COMMIT" ]; then
    echo "Error: Fetched Git source commit $actual_commit, expected $GIT_COMMIT" >&2
    exit 1
fi

echo "Checked out Git source commit $actual_commit."
