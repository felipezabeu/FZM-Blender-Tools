"""Project the actual foot of each Wall Tiles face onto a trim run."""
from collections import defaultdict

from . import shower_area as sh


LEVEL_EPS = .00025  # metres; not the board height or a construction clearance
FACE_EPS = 2 * sh.PLANAR
CORNER_EPS = 2 * sh.SEPARATION + sh.PLANAR


def panels_by_wall(context):
    """Read only managed tile faces, not their controller's other children."""
    panels = defaultdict(list)
    for panel in context.scene.objects:
        if panel.type == 'MESH' and panel.get(sh.PART) and panel.parent and panel.parent.get(sh.AREA):
            wall = panel.get('fzm_shower_wall')
            if wall:
                panels[wall].append(panel)
    return panels


def floor_gaps(panels, origin, direction, inward, length, level):
    """Yield intervals where tile on this wall face touches the floor.

    Tile meshes already include the evaluated wall holes, miters and both Wall
    Divider bounds. Intersect the polygons with the floor rather than using
    the panel's overall extent (which may bridge an opening or a raised tile
    segment). For a solid lining, use the flush backing face; for an old
    visual sheet, account for its historical render separation.
    """
    for panel in panels:
        matrix = panel.matrix_world
        normal_matrix = matrix.to_3x3().inverted_safe().transposed()
        # Use the backing of a solid lining, since trim sits on the same wall
        # face. The legacy visual sheet has no separate backing.
        is_solid = bool(panel.get(sh.LINING_THICKNESS, 0.))
        wanted_normal = -1 if is_solid else 1
        plane_offset = 0. if is_solid else sh.SEPARATION
        points = []
        for vertex in panel.data.vertices:
            world = matrix @ vertex.co
            delta = world.xy - origin
            points.append((delta.dot(direction), delta.dot(inward), world.z))
        for face in panel.data.polygons:
            normal = (normal_matrix @ face.normal).normalized()
            if wanted_normal * normal.xy.dot(inward) < .95:
                continue
            vertices = [points[i] for i in face.vertices]
            if any(abs(p[1] - plane_offset) > FACE_EPS for p in vertices):
                continue
            lower = min(p[2] for p in vertices)
            upper = max(p[2] for p in vertices)
            if lower > level + LEVEL_EPS or upper <= level + LEVEL_EPS:
                continue
            z = max(level, lower)  # Snap a microscopic z mismatch, not a raised finish.
            crossings = [p[0] for p in vertices if abs(p[2] - z) <= 1e-6]
            for a, b in zip(vertices, vertices[1:] + vertices[:1]):
                if min(a[2], b[2]) < z < max(a[2], b[2]):
                    fraction = (z - a[2]) / (b[2] - a[2])
                    crossings.append(a[0] + fraction * (b[0] - a[0]))
            if len(crossings) < 2:
                continue
            lo, hi = min(crossings), max(crossings)
            if hi <= 0. or lo >= length or hi - lo <= 1e-6:
                continue
            # The offset tile's miter does not line up exactly with the bare
            # wall miter. Do not leave a millimetre-wide board at that corner.
            lo = 0. if lo <= CORNER_EPS else lo
            hi = length if length - hi <= CORNER_EPS else hi
            yield lo, hi
