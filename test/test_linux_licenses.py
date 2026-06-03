"""Tests for Linux static dependency license documentation."""

import hashlib
from pathlib import Path
from typing import TypedDict

PROJECT_ROOT = Path(__file__).parent.parent


class LinuxDependency(TypedDict):
    """Legal and build metadata for a statically linked Linux dependency."""

    version: str
    pin: str
    usage: list[str]
    license: str
    license_sha256: str
    license_name: str
    source: str


LINUX_DEPENDENCIES: dict[str, LinuxDependency] = {
    "curl": {
        "version": "8.20.0",
        "pin": "ARG CURL_VERSION=8.20.0",
        "usage": ['curl -fsSL "https://curl.se/download/curl-${CURL_VERSION}.tar.xz"'],
        "license": "licenses/CURL-LICENSE-CURL",
        "license_sha256": "82f2f4427d6545ee5aaac4f0b80428da6cc8ba41c2cf5da3a03680ec327b9681",
        "license_name": "curl License",
        "source": "https://curl.se/download/curl-8.20.0.tar.xz",
    },
    "OpenSSL": {
        "version": "3.1.8 (Alpine 3.19 package 3.1.8-r1)",
        "pin": "ARG OPENSSL_PACKAGE_VERSION=3.1.8-r1",
        "usage": [
            "openssl-dev=${OPENSSL_PACKAGE_VERSION}",
            "openssl-libs-static=${OPENSSL_PACKAGE_VERSION}",
        ],
        "license": "licenses/OPENSSL-LICENSE-APACHE2",
        "license_sha256": "7d5450cb2d142651b8afa315b5f238efc805dad827d91ba367d8516bc9d49e7a",
        "license_name": "Apache License 2.0",
        "source": (
            "https://github.com/openssl/openssl/releases/download/"
            "openssl-3.1.8/openssl-3.1.8.tar.gz"
        ),
    },
    "zlib": {
        "version": "1.3.1 (Alpine 3.19 package 1.3.1-r0)",
        "pin": "ARG ZLIB_PACKAGE_VERSION=1.3.1-r0",
        "usage": [
            "zlib-dev=${ZLIB_PACKAGE_VERSION}",
            "zlib-static=${ZLIB_PACKAGE_VERSION}",
        ],
        "license": "licenses/ZLIB-LICENSE-ZLIB",
        "license_sha256": "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243",
        "license_name": "zlib License",
        "source": "https://zlib.net/fossils/zlib-1.3.1.tar.gz",
    },
}


def test_linux_static_dependency_licenses_are_documented() -> None:
    """Pinned Linux static dependencies have corresponding notices and license texts."""
    dockerfile = (PROJECT_ROOT / "build" / "linux" / "Dockerfile").read_text()
    notice = (PROJECT_ROOT / "NOTICE").read_text()

    assert "ARG ALPINE_VERSION=3.19" in dockerfile

    for name, dependency in LINUX_DEPENDENCIES.items():
        license_contents = (PROJECT_ROOT / dependency["license"]).read_bytes()

        assert dependency["pin"] in dockerfile
        assert all(usage in dockerfile for usage in dependency["usage"])
        assert f"{name}\n{'-' * 80}" in notice
        assert f"Version: {dependency['version']}" in notice
        assert f"License: {dependency['license_name']}" in notice
        assert f"Source: {dependency['source']}" in notice
        assert f"License file: {dependency['license']}" in notice
        assert hashlib.sha256(license_contents).hexdigest() == dependency["license_sha256"]
