"""Tests for source archive download verification."""

import hashlib
import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

DOWNLOADER_PATH = Path(__file__).parents[1] / "build" / "download_verified.py"
DOWNLOADER_SPEC = spec_from_file_location("download_verified", DOWNLOADER_PATH)
assert DOWNLOADER_SPEC is not None
assert DOWNLOADER_SPEC.loader is not None
DOWNLOADER = module_from_spec(DOWNLOADER_SPEC)
DOWNLOADER_SPEC.loader.exec_module(DOWNLOADER)

download_verified = DOWNLOADER.download_verified
load_source = DOWNLOADER.load_source


def write_sources(path: Path, sources: dict) -> None:
    path.write_text(json.dumps(sources))


def source_entry(source: Path, checksum: str) -> dict:
    return {"url": source.as_uri(), "sha256": checksum}


def test_download_verified_accepts_matching_archive(tmp_path: Path) -> None:
    source = tmp_path / "source.tar.xz"
    source.write_bytes(b"verified archive")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    sources = tmp_path / "sources.json"
    destination = tmp_path / "downloads" / source.name
    write_sources(sources, {source.name: source_entry(source, checksum.upper())})

    download_verified(source.name, destination, sources)

    assert destination.read_bytes() == source.read_bytes()


def test_download_verified_rejects_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.tar.xz"
    source.write_bytes(b"tampered archive")
    sources = tmp_path / "sources.json"
    destination = tmp_path / "downloads" / source.name
    write_sources(sources, {source.name: source_entry(source, "a" * 64)})

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        download_verified(source.name, destination, sources)

    assert not destination.exists()
    assert not Path(f"{destination}.part").exists()


def test_download_verified_accepts_matching_cached_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "archive.tar.xz"
    destination.write_bytes(b"verified archive")
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    sources = tmp_path / "sources.json"
    write_sources(
        sources,
        {
            destination.name: {
                "url": "https://example.invalid/archive.tar.xz",
                "sha256": checksum,
            }
        },
    )
    monkeypatch.setattr(
        DOWNLOADER.urllib.request,
        "urlopen",
        lambda request: pytest.fail(f"Unexpected download: {request.full_url}"),
    )

    download_verified(destination.name, destination, sources)


def test_download_verified_rejects_corrupt_cached_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "archive.tar.xz"
    destination.write_bytes(b"tampered archive")
    sources = tmp_path / "sources.json"
    write_sources(
        sources,
        {
            destination.name: {
                "url": "https://example.invalid/archive.tar.xz",
                "sha256": "a" * 64,
            }
        },
    )
    monkeypatch.setattr(
        DOWNLOADER.urllib.request,
        "urlopen",
        lambda request: pytest.fail(f"Unexpected download: {request.full_url}"),
    )

    with pytest.raises(ValueError, match="SHA256 mismatch"):
        download_verified(destination.name, destination, sources)


def test_download_verified_rejects_unknown_archive_before_download(tmp_path: Path) -> None:
    sources = tmp_path / "sources.json"
    destination = tmp_path / "downloads" / "unknown.tar.xz"
    write_sources(sources, {})

    with pytest.raises(ValueError, match="Missing source catalog entry"):
        download_verified("unknown.tar.xz", destination, sources)

    assert not destination.exists()


def test_load_source_rejects_duplicate_source_entries(tmp_path: Path) -> None:
    sources = tmp_path / "sources.json"
    sources.write_text(
        '{"source.tar.xz": {"url": "https://example.com/source.tar.xz", '
        '"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, '
        '"source.tar.xz": {"url": "https://example.com/source.tar.xz", '
        '"sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}'
    )

    with pytest.raises(ValueError, match="Duplicate key"):
        load_source("source.tar.xz", sources)


@pytest.mark.parametrize("checksum", ["short", "z" * 64])
def test_load_source_rejects_invalid_checksum(tmp_path: Path, checksum: str) -> None:
    source = tmp_path / "archive.tar.xz"
    sources = tmp_path / "sources.json"
    write_sources(sources, {source.name: source_entry(source, checksum)})

    with pytest.raises(ValueError, match="Invalid SHA256 checksum"):
        load_source(source.name, sources)


def test_load_source_rejects_filename_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "different.tar.xz"
    sources = tmp_path / "sources.json"
    write_sources(sources, {"archive.tar.xz": source_entry(source, "a" * 64)})

    with pytest.raises(ValueError, match="Source URL filename does not match"):
        load_source("archive.tar.xz", sources)
