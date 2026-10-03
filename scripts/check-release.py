"""Reject fallback/dev builds or artifacts inconsistent with the release tag."""

import email
import os
import tarfile
import zipfile
from pathlib import Path

from packaging.version import Version


def main() -> None:
    tag = os.environ["RELEASE_TAG"]
    if not tag.startswith("v"):
        raise ValueError("Release tags must start with v")
    expected = Version(tag[1:])
    if expected == Version("0.0.0") or expected.is_devrelease:
        raise ValueError("Fallback and development versions cannot be published")
    dist = Path(os.environ.get("DIST_DIR", "dist"))
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Expected exactly one wheel and one sdist")
    with zipfile.ZipFile(wheels[0]) as wheel:
        metadata = next(
            name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
        )
        wheel_version = email.message_from_bytes(wheel.read(metadata))["Version"]
    with tarfile.open(sdists[0]) as sdist:
        metadata = next(
            member
            for member in sdist.getmembers()
            if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
        )
        stream = sdist.extractfile(metadata)
        if stream is None:
            raise ValueError("Missing sdist metadata")
        sdist_version = email.message_from_bytes(stream.read())["Version"]
    if Version(wheel_version) != expected or Version(sdist_version) != expected:
        raise ValueError("Distribution versions do not match the release tag")


if __name__ == "__main__":
    main()
