"""Sync/check the MIT tile geometry core needed by both standalone ZIPs."""
from argparse import ArgumentParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TILE = ROOT / "extensions" / "fzm_tile_panels"
BUILDER = ROOT / "extensions" / "fzm_builder"
FILES = (
    (TILE / "tile_geometry.py", BUILDER / "tile_core.py"),
    (TILE / "LICENSE.txt", BUILDER / "tile_core_LICENSE.txt"),
)


def work(check):
    for source, dest in FILES:
        body = source.read_bytes()
        if check:
            if not dest.exists() or dest.read_bytes() != body:
                raise SystemExit(f"{dest.name} is stale; run scripts/sync_tile_core.py")
        else:
            dest.write_bytes(body)


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    work(parser.parse_args().check)
