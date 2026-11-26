"""Build a backed tile lining from the sampled and clipped room-side face."""
from collections import defaultdict
from math import floor, hypot


_WELD = 1e-6


def build_shell(vertices, faces, uv, direction, inward, thickness, phase, length,
                back_start_shift, back_end_shift):
    """Return a closed shell and per-corner metric UVs.

    Adjacent sampled wall triangles must share mesh vertices before we join their
    boundary to the backing. Duplicating each triangle as a separate solid would
    leave internal caps at grout courses and at evaluated door/niche openings.
    At a shared room corner we move the backing endpoint along the wall to its
    own miter, so the two layers meet continuously through the lining depth.
    """
    cells = defaultdict(list)
    front, coords, remap = [], [], []
    for point, (u, z) in zip(vertices, uv):
        key = floor(u / _WELD), floor(z / _WELD)
        match = None
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for idx in cells.get((key[0]+i, key[1]+j), ()):
                    a, b = coords[idx]
                    if max(abs(a-u), abs(b-z)) <= _WELD:
                        match = idx
                        break
                if match is not None:
                    break
            if match is not None:
                break
        if match is None:
            match = len(front)
            cells[key].append(match)
            front.append(point)
            coords.append((u, z))
        remap.append(match)
    if not front:
        return [], [], []

    front_faces = []
    incidence = defaultdict(list)
    for face in faces:
        welded = list(dict.fromkeys(remap[i] for i in face))
        if len(welded) < 3:
            continue
        front_faces.append(tuple(welded))
        for a, b in zip(welded, welded[1:] + welded[:1]):
            incidence[tuple(sorted((a,b)))].append((a,b))

    back = []
    for (x,y,z), (u,_) in zip(front,coords):
        station = u-phase
        shift = (back_start_shift if abs(station) <= 2*_WELD else
                 back_end_shift if abs(station-length) <= 2*_WELD else 0.)
        back.append((x-thickness*inward.x+shift*direction.x,
                     y-thickness*inward.y+shift*direction.y,z))
    n = len(front)
    polygons = front_faces + [tuple(i+n for i in reversed(face)) for face in front_faces]
    per_face_uvs = [tuple(coords[i % n] for i in face) for face in polygons]
    for edge in incidence.values():
        if len(edge) != 1:
            continue
        a,b = edge[0]
        polygons.append((b,a,a+n,b+n))
        au, av = coords[a]
        bu, bv = coords[b]
        size = hypot(bu-au,bv-av)
        # Continue the metric UVs around the lip at the same texel density.
        out_u, out_v = thickness*(av-bv)/size, thickness*(bu-au)/size
        per_face_uvs.append(((bu,bv),(au,av),(au+out_u,av+out_v),(bu+out_u,bv+out_v)))
    return front + back, polygons, per_face_uvs
