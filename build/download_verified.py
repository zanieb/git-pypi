# /// script
# requires-python = "==3.12.*"
# dependencies = []
# ///

"""Download a pinned source archive and verify its SHA-256 checksum."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

SOURCES_PATH = Path(__file__).with_name("sources.json")


def reject_duplicate_keys(pairs):
    """Build a JSON object while rejecting duplicate keys."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate key in source catalog: {key}")
        result[key] = value
    return result


def load_source(source_name: str, sources_path: Path) -> tuple[str, str]:
    """Load and validate a source URL and checksum from the catalog."""
    with sources_path.open() as sources_file:
        sources = json.load(sources_file, object_pairs_hook=reject_duplicate_keys)

    if not isinstance(sources, dict) or source_name not in sources:
        raise ValueError(f"Missing source catalog entry: {source_name}")

    source = sources[source_name]
    if not isinstance(source, dict) or set(source) != {"url", "sha256"}:
        raise ValueError(f"Invalid source catalog entry: {source_name}")

    url = source["url"]
    expected_sha256 = source["sha256"]
    if not isinstance(url, str) or not isinstance(expected_sha256, str):
        raise ValueError(f"Invalid source catalog entry: {source_name}")

    url_name = Path(unquote(urlparse(url).path)).name
    if url_name != source_name:
        raise ValueError(f"Source URL filename does not match {source_name}: {url_name}")

    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError(f"Invalid SHA256 checksum for {source_name}: {expected_sha256}")

    return url, expected_sha256.lower()


def sha256_file(path: Path) -> str:
    """Calculate the SHA-256 checksum for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, source_name: str, expected_sha256: str) -> None:
    """Verify a downloaded or cached source archive."""
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"SHA256 mismatch for {source_name}: expected {expected_sha256}, got {actual_sha256}"
        )


def download_verified(
    source_name: str, destination: Path, sources_path: Path = SOURCES_PATH
) -> None:
    """Download a source archive if needed, then verify it."""
    url, expected_sha256 = load_source(source_name, sources_path)

    if not destination.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = Path(f"{destination}.part")
        try:
            print(f"Downloading {url}...")
            request = urllib.request.Request(url, headers={"User-Agent": "git-pypi-builder"})
            with urllib.request.urlopen(request) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            verify_file(partial, source_name, expected_sha256)
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)

    verify_file(destination, source_name, expected_sha256)
    print(f"Verified SHA256 for {source_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_name")
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sources", type=Path, default=SOURCES_PATH)
    args = parser.parse_args()

    try:
        download_verified(args.source_name, args.destination, args.sources)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
