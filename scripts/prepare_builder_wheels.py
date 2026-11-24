#!/usr/bin/env python3
"""Restore Home Builder's pinned Pillow wheels from PyPI before packaging."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import tomllib
from urllib.parse import urlparse
from urllib.request import urlopen


PYPI_METADATA = "https://pypi.org/pypi/Pillow/12.1.1/json"
WHEEL_HASHES = {
    'pillow-12.1.1-cp311-cp311-win_amd64.whl': 'fbfa2a7c10cc2623f412753cddf391c7f971c52ca40a3f65dc5039b2939e8563',
    'pillow-12.1.1-cp311-cp311-win_arm64.whl': 'b81b5e3511211631b3f672a595e3221252c90af017e399056d0faabb9538aa80',
    'pillow-12.1.1-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl': '597bd9c8419bc7c6af5604e55847789b69123bbe25d65cc6ad3012b4f3c98d8b',
    'pillow-12.1.1-cp311-cp311-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl': '7e7976bf1910a8116b523b9f9f58bf410f3e8aa330cd9a2bb2953f9266ab49af',
    'pillow-12.1.1-cp311-cp311-macosx_11_0_arm64.whl': '365b10bb9417dd4498c0e3b128018c4a624dc11c7b97d8cc54effe3b096f4c38',
    'pillow-12.1.1-cp311-cp311-macosx_10_10_x86_64.whl': 'e879bb6cd5c73848ef3b2b48b8af9ff08c5b71ecda8048b7dd22d8a33f60be32',
    'pillow-12.1.1-cp313-cp313-win_amd64.whl': '344cf1e3dab3be4b1fa08e449323d98a2a3f819ad20f4b22e77a0ede31f0faa1',
    'pillow-12.1.1-cp313-cp313-win_arm64.whl': '5c0dd1636633e7e6a0afe7bf6a51a14992b7f8e60de5789018ebbdfae55b040a',
    'pillow-12.1.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl': '47b94983da0c642de92ced1702c5b6c292a84bd3a8e1d1702ff923f183594717',
    'pillow-12.1.1-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl': '5a8eb7ed8d4198bccbd07058416eeec51686b498e784eda166395a23eb99138e',
    'pillow-12.1.1-cp313-cp313-macosx_11_0_arm64.whl': '8b7e5304e34942bf62e15184219a7b5ad4ff7f3bb5cca4d984f37df1a0e1aee2',
    'pillow-12.1.1-cp313-cp313-macosx_10_13_x86_64.whl': '6c6db3b84c87d48d0088943bf33440e0c42370b99b1c2a7989216f7b42eede60',
}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def prepare(source):
    manifest = tomllib.loads((source / "blender_manifest.toml").read_text(encoding="utf-8"))
    wheel_paths = manifest["wheels"]
    for entry in wheel_paths:
        relative = Path(entry)
        if relative.parent != Path("wheels") or relative.name not in WHEEL_HASHES:
            raise ValueError(f"No pinned Pillow artifact for {entry}")

    missing = [
        source / entry
        for entry in wheel_paths
        if not (source / entry).is_file()
        or sha256(source / entry) != WHEEL_HASHES[Path(entry).name]
    ]
    if not missing:
        return

    with urlopen(PYPI_METADATA, timeout=30) as response:
        files = {item["filename"]: item for item in json.load(response)["urls"]}
    for target in missing:
        item = files[target.name]
        expected = WHEEL_HASHES[target.name]
        url = urlparse(item["url"])
        if item["digests"]["sha256"] != expected or (
            url.scheme, url.hostname
        ) != ("https", "files.pythonhosted.org"):
            raise ValueError(f"Unexpected PyPI metadata for {target.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as staging:
            partial = Path(staging) / target.name
            with urlopen(url.geturl(), timeout=60) as response, partial.open("wb") as output:
                while chunk := response.read(256 * 1024):
                    output.write(chunk)
            if sha256(partial) != expected:
                raise ValueError(f"SHA-256 mismatch for {target.name}")
            partial.replace(target)
        print(f"Verified {target.name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "extensions" / "fzm_builder",
    )
    prepare(parser.parse_args().source_dir)
