import io
import os
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class ReleaseCase:
    tag: str
    artifact_version: str
    succeeds: bool


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            ReleaseCase(tag="v0.1.0", artifact_version="0.1.0", succeeds=True),
            id="release",
        ),
        pytest.param(
            ReleaseCase(tag="v0.1.0rc1", artifact_version="0.1.0rc1", succeeds=True),
            id="prerelease",
        ),
        pytest.param(
            ReleaseCase(tag="v0.1.0", artifact_version="0.2.0", succeeds=False),
            id="mismatch",
        ),
        pytest.param(
            ReleaseCase(tag="v0.0.0", artifact_version="0.0.0", succeeds=False),
            id="fallback",
        ),
        pytest.param(
            ReleaseCase(
                tag="v0.1.0.dev1", artifact_version="0.1.0.dev1", succeeds=False
            ),
            id="dev",
        ),
        pytest.param(
            ReleaseCase(tag="0.1.0", artifact_version="0.1.0", succeeds=False),
            id="missing-prefix",
        ),
    ],
)
def test_release_version_gate(case: ReleaseCase, tmp_path: Path) -> None:
    metadata = f"Name: example\nVersion: {case.artifact_version}\n".encode()
    with zipfile.ZipFile(tmp_path / "example.whl", "w") as wheel:
        wheel.writestr("example.dist-info/METADATA", metadata)
    with tarfile.open(tmp_path / "example.tar.gz", "w:gz") as sdist:
        member = tarfile.TarInfo("example/PKG-INFO")
        member.size = len(metadata)
        sdist.addfile(member, io.BytesIO(metadata))
    script = Path(__file__).resolve().parents[1] / "scripts/check-release.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        env={**os.environ, "RELEASE_TAG": case.tag, "DIST_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (result.returncode == 0) == case.succeeds, result.stderr
