"""Read RGB swatches from local Adobe Swatch Exchange palettes."""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from pathlib import Path
import re
import struct


MAX_PALETTE_SIZE = 8 * 1024 * 1024
CODE = r'(?:[A-Z]+[ -]?)?[0-9]+(?:-[0-9]+)*[A-Z]?'
SWATCH_LABEL = re.compile(rf'^({CODE})\s+(.+)$', re.IGNORECASE)
DASHES = str.maketrans('‐‑‒–—−', '------')


@dataclass(frozen=True)
class Swatch:
    code: str
    name: str
    rgb: tuple[float, float, float]
    palette: str


def normalize_code(value):
    value = value.strip().translate(DASHES).upper()
    return re.sub(r'^([A-Z]+)[ -](?=[0-9])', r'\1', value)


def name_key(value):
    return ' '.join(value.casefold().split())


def parse_ase(data, palette):
    if len(data) < 12 or len(data) > MAX_PALETTE_SIZE:
        raise ValueError('Invalid ASE file size')
    signature, major, _, count = struct.unpack_from('>4sHHI', data)
    if signature != b'ASEF' or major != 1 or count > (len(data) - 12) // 6:
        raise ValueError('Invalid or unsupported ASE format')

    entries = []
    offset = 12
    for _ in range(count):
        if offset + 6 > len(data):
            raise ValueError('Incomplete ASE block')
        kind, size = struct.unpack_from('>HI', data, offset)
        start = offset + 6
        offset = start + size
        if offset > len(data):
            raise ValueError('Incomplete ASE block')
        if kind != 1:
            continue

        if size < 8:
            raise ValueError('Incomplete ASE color block')
        name_size = struct.unpack_from('>H', data, start)[0] * 2
        name_end = start + 2 + name_size
        if name_size == 0 or name_end + 4 > offset:
            raise ValueError('Invalid ASE swatch name')
        if data[name_end:name_end + 4] != b'RGB ':
            continue
        if name_end + 18 != offset:
            raise ValueError('Invalid ASE RGB block')
        rgb = struct.unpack_from('>3f', data, name_end + 4)
        if not all(isfinite(value) and 0 <= value <= 1 for value in rgb):
            raise ValueError('Invalid ASE RGB channels')

        label = data[start + 2:name_end].decode('utf-16-be').rstrip('\0').strip()
        match = SWATCH_LABEL.fullmatch(label.translate(DASHES))
        code, name = match.groups() if match else ('', label)
        if name:
            entries.append(Swatch(code.upper(), name.strip(), rgb, palette))

    if offset != len(data):
        raise ValueError('Unexpected data after ASE blocks')
    if not entries:
        raise ValueError('Palette contains no supported RGB swatches')
    return tuple(entries)


def read_ase_bytes(path):
    with path.open('rb') as file:
        return file.read(MAX_PALETTE_SIZE + 1)


@lru_cache(maxsize=64)
def _read_palette(path, modified, size):
    # Both stat fields participate in the cache key so synced edits are picked up.
    return parse_ase(read_ase_bytes(path), path.stem)


class Catalog:
    def __init__(self, entries, skipped=()):
        self.codes = {}
        self.names = {}
        self.skipped = tuple(skipped)
        for swatch in entries:
            if swatch.code:
                self.codes.setdefault(normalize_code(swatch.code), []).append(swatch)
            self.names.setdefault(name_key(swatch.name), []).append(swatch)

    def matches(self, value):
        return self.codes.get(normalize_code(value)) or self.names.get(name_key(value), ())

    def collections(self, value):
        return sorted({swatch.palette for swatch in self.matches(value)}, key=str.casefold)

    def lookup(self, value, palette=''):
        matches = self.matches(value)
        if palette:
            matches = [swatch for swatch in matches if name_key(swatch.palette) == name_key(palette)]
        if not matches:
            return None
        first = matches[0]
        # Multiple collections sometimes contain the same swatch. Compare at the
        # same 8-bit precision used by Wall Paint while keeping distinct codes.
        colors = {(normalize_code(swatch.code), tuple(round(c * 255) for c in swatch.rgb))
                  for swatch in matches}
        if len(colors) > 1:
            raise ValueError('Multiple swatches match. Select a palette file or use the exact code.')
        return first


def load_catalog(directories):
    entries = []
    skipped = []
    seen = set()
    for directory in directories:
        try:
            paths = sorted((path for path in Path(directory).iterdir()
                            if path.suffix.lower() == '.ase'), key=lambda path: path.name.casefold())
        except FileNotFoundError:
            continue
        except OSError:
            skipped.append(Path(directory).name)
            continue
        for path in paths:
            try:
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                stat = path.stat()
                entries.extend(_read_palette(resolved, stat.st_mtime_ns, stat.st_size))
            except (OSError, ValueError):
                skipped.append(path.name)
    return Catalog(entries, skipped)
