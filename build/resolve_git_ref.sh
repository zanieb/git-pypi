#!/bin/sh
#
# Resolve a Git source ref to an immutable commit.
#
# Usage:
#   ./build/resolve_git_ref.sh HEAD
#   ./build/resolve_git_ref.sh v2.47.1
#   ./build/resolve_git_ref.sh <full-commit-sha>
#
# Set GIT_SOURCE_REPOSITORY to resolve refs from a repository other than
# https://github.com/git/git.git.

set -eu

GIT_SOURCE_REF="${1:-}"
GIT_SOURCE_REPOSITORY="${GIT_SOURCE_REPOSITORY:-https://github.com/git/git.git}"

if [ -z "$GIT_SOURCE_REF" ]; then
    echo "Usage: $0 <git-source-ref>" >&2
    exit 2
fi

# A full commit SHA is already an immutable source identifier. This also lets
# callers pass commits that are reachable but not advertised as a named ref.
if printf '%s\n' "$GIT_SOURCE_REF" | grep -Eq '^[0-9a-fA-F]{40}$'; then
    printf '%s\n' "$GIT_SOURCE_REF" | tr '[:upper:]' '[:lower:]'
    exit 0
fi

refs="$(git ls-remote "$GIT_SOURCE_REPOSITORY" "$GIT_SOURCE_REF" "$GIT_SOURCE_REF^{}")"

# Prefer the peeled commit for annotated tags, then fall back to the first
# matching ref for branches, lightweight tags, and HEAD.
commit="$(printf '%s\n' "$refs" | awk '$2 ~ /\^\{\}$/ { print $1; exit }')"
if [ -z "$commit" ]; then
    commit="$(printf '%s\n' "$refs" | awk 'NR == 1 { print $1 }')"
fi

if [ -z "$commit" ]; then
    echo "Error: Could not resolve Git source ref '$GIT_SOURCE_REF' from $GIT_SOURCE_REPOSITORY" >&2
    echo "Use a branch, tag, HEAD, or full 40-character commit SHA." >&2
    exit 1
fi

printf '%s\n' "$commit"
