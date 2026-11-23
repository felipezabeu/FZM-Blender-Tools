"""Geometry math for FZM Tile Panels. Blender-independent for unit testing.

Units passed to generate_panel are inches. Vertices returned in meters.
X is panel width; Y is height/length measured along the panel surface.
Wall maps (X, Y, depth) -> (X, -depth, Z=Y).
Floor maps (X, Y, depth) -> (X, Y, Z=depth).
The origin is at the lower-left corner of the *back* surface.
"""
from __future__ import annotations

import math

INCH = 0.0254

PRESETS = {
    "3x6": (3.0, 6.0),
    "3x12": (3.0, 12.0),
    "4x12": (4.0, 12.0),
    "8x8": (8.0, 8.0),
    "12x12": (12.0, 12.0),
    "12x24": (12.0, 24.0),
    "12x36": (12.0, 36.0),
    "24x24": (24.0, 24.0),
    "24x48": (24.0, 48.0),
    "30x30": (30.0, 30.0),
    "30x60": (30.0, 60.0),
    "32x32": (32.0, 32.0),
    "36x36": (36.0, 36.0),
    "36x72": (36.0, 72.0),
    "48x48": (48.0, 48.0),
    "8x48": (8.0, 48.0),
    "9x48": (9.0, 48.0),
}


class TooManyTiles(ValueError):
    pass


def generate_panel(
    panel_width: float,
    panel_height: float,
    thickness: float = 0.5,
    tile_a: float = 12.0,
    tile_b: float = 24.0,
    orientation: str = "HORIZONTAL",
    pattern: str = "STACK",
    grout: float = 0.125,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    surface: str = "WALL",
    tile_relief: float = 0.035,
    material_count: int = 1,
    max_tiles: int = 12000,
) -> dict:
    """Build a single grouted panel + capped tile faces (seams are real geometry).

    `material_count` is count of tile materials; index 0 is grout,
    tile surfaces use indices [1..material_count]. Tile extents are clipped to panel.
    The geometry represents a visual finish, not a construction/quantity takeoff.
    """
    values = [panel_width, panel_height, thickness, tile_a, tile_b, grout, tile_relief]
    if not all(math.isfinite(v) for v in values + [offset_x, offset_y]):
        raise ValueError("Values must be finite")
    if panel_width <= 0 or panel_height <= 0 or thickness <= 0:
        raise ValueError("Panel width, height and thickness must be positive")
    if tile_a <= 0 or tile_b <= 0 or grout < 0:
        raise ValueError("Tile dimensions must be positive and grout nonnegative")
    if not 0 < tile_relief < thickness:
        raise ValueError("Tile relief must be greater than 0 and less than panel thickness")
    if material_count < 1:
        raise ValueError("At least one tile material is required")
    if orientation not in ("HORIZONTAL", "VERTICAL"):
        raise ValueError("Unknown orientation")
    if pattern not in ("STACK", "HALF", "THIRD"):
        raise ValueError("Unknown pattern")
    if surface not in ("WALL", "FLOOR"):
        raise ValueError("Unknown panel type")

    if orientation == "HORIZONTAL":
        tile_w, tile_h = max(tile_a, tile_b), min(tile_a, tile_b)
    else:
        tile_w, tile_h = min(tile_a, tile_b), max(tile_a, tile_b)
    pitch_x, pitch_y = tile_w + grout, tile_h + grout
    estimate = (math.ceil(panel_width / pitch_x) + 4) * (math.ceil(panel_height / pitch_y) + 4)
    if estimate > max_tiles:
        raise TooManyTiles(f"Panel would need too many tiles (~{estimate:,}); choose larger tiles or smaller panel")

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    uvs: list[list[tuple[float, float]]] = []
    material_indices: list[int] = []
    tile_bounds: list[tuple[float, float, float, float]] = []

    def pos(x: float, y: float, depth: float) -> tuple[float, float, float]:
        if surface == "WALL":
            return (x * INCH, -depth * INCH, y * INCH)
        return (x * INCH, y * INCH, depth * INCH)

    def quad(coords, mat=0, uv=((0, 0), (1, 0), (1, 1), (0, 1))):
        start = len(vertices)
        vertices.extend(pos(*p) for p in coords)
        faces.append((start, start + 1, start + 2, start + 3))
        uvs.append([tuple(v) for v in uv])
        material_indices.append(mat)

    dbase = thickness - tile_relief
    W, H = panel_width, panel_height
    # Solid panel shell, 0 at rear and (thickness - relief) at visible grout face.
    quad([(0, 0, dbase), (W, 0, dbase), (W, H, dbase), (0, H, dbase)])
    quad([(0, H, 0), (W, H, 0), (W, 0, 0), (0, 0, 0)])
    quad([(0, 0, 0), (W, 0, 0), (W, 0, dbase), (0, 0, dbase)])
    quad([(W, 0, 0), (W, H, 0), (W, H, dbase), (W, 0, dbase)])
    quad([(W, H, 0), (0, H, 0), (0, H, dbase), (W, H, dbase)])
    quad([(0, H, 0), (0, 0, 0), (0, 0, dbase), (0, H, dbase)])

    # Shift phase is bounded modulo tile pitch so extreme offsets stay fast.
    phase_x, phase_y = offset_x % pitch_x, offset_y % pitch_y
    row_min = math.floor(-phase_y / pitch_y) - 1
    row_max = math.ceil((H - phase_y) / pitch_y) + 1
    eps = 1e-7
    for row in range(row_min, row_max + 1):
        y0_full = phase_y + row * pitch_y
        y1_full = y0_full + tile_h
        y0 = max(0.0, y0_full)
        y1 = min(H, y1_full)
        if y1 - y0 <= eps:
            continue
        shift_frac = 0.0 if pattern == "STACK" else ((row % (2 if pattern == "HALF" else 3)) / (2 if pattern == "HALF" else 3))
        base_x = phase_x - shift_frac * pitch_x
        col_min = math.floor(-base_x / pitch_x) - 1
        col_max = math.ceil((W - base_x) / pitch_x) + 1
        for col in range(col_min, col_max + 1):
            x0_full = base_x + col * pitch_x
            x1_full = x0_full + tile_w
            x0 = max(0.0, x0_full)
            x1 = min(W, x1_full)
            if x1 - x0 <= eps:
                continue
            tile_bounds.append((x0, y0, x1, y1))
            m = 1 + ((row * 131 + col * 97) % material_count)
            uv = [
                ((x0 - x0_full) / tile_w, (y0 - y0_full) / tile_h),
                ((x1 - x0_full) / tile_w, (y0 - y0_full) / tile_h),
                ((x1 - x0_full) / tile_w, (y1 - y0_full) / tile_h),
                ((x0 - x0_full) / tile_w, (y1 - y0_full) / tile_h),
            ]
            # Visible surface with one real texture image per tile (same UV for each full piece).
            quad([(x0, y0, thickness), (x1, y0, thickness), (x1, y1, thickness), (x0, y1, thickness)], m, uv)
            # Tile sidewalls extend to grout plane, providing visual depth to joints.
            quad([(x0, y0, dbase), (x1, y0, dbase), (x1, y0, thickness), (x0, y0, thickness)], m)
            quad([(x1, y0, dbase), (x1, y1, dbase), (x1, y1, thickness), (x1, y0, thickness)], m)
            quad([(x1, y1, dbase), (x0, y1, dbase), (x0, y1, thickness), (x1, y1, thickness)], m)
            quad([(x0, y1, dbase), (x0, y0, dbase), (x0, y0, thickness), (x0, y1, thickness)], m)
            if len(tile_bounds) > max_tiles:
                raise TooManyTiles(f"Maximum {max_tiles:,} tile pieces exceeded")

    return {
        "vertices": vertices,
        "faces": faces,
        "uvs": uvs,
        "material_indices": material_indices,
        "tile_bounds": tile_bounds,
        "tile_count": len(tile_bounds),
        "tile_width": tile_w,
        "tile_height": tile_h,
        "panel_bbox_inches": (W, H, thickness),
    }