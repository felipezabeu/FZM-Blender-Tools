"""Geometry helpers for trim attached to an individual wall, not a floor."""
from math import isfinite, tan

from mathutils import Vector

from .. import hb_types
from . import baseboard_perimeter as perimeter


EPS = perimeter.EPS


def footprint(obj):
    """Builder's true four bottom corners, including its node-driven miters."""
    geo = hb_types.GeoNodeWall(obj)
    names = ('Length', 'Thickness', 'Left Angle', 'Right Angle')
    if not all(geo.has_input(key) for key in names):
        raise ValueError(f'{obj.name}: select a physical Builder wall.')
    length, depth, a, b = (geo.get_input(key) for key in names)
    if not all(v is not None and isfinite(v) for v in (length, depth, a, b)):
        raise ValueError(f'{obj.name}: invalid wall dimensions.')
    l, r = depth * tan(a), length + depth * tan(b)
    if min(length, r - l, abs(depth)) < EPS:
        raise ValueError(f'{obj.name}: the wall has a collapsed base.')
    points = tuple(obj.matrix_world @ Vector((x, y, 0)) for x, y in
                   ((0, 0), (length, 0), (r, depth), (l, depth)))
    level = points[0].z
    xy = tuple(p.xy for p in points)
    if any(abs(p.z - level) >= EPS for p in points):
        raise ValueError(f'{obj.name}: the wall base must be level.')
    if abs((xy[1]-xy[0]).cross(xy[3]-xy[0])) < EPS**2:
        raise ValueError(f'{obj.name}: the wall base has no area.')
    return xy, level


def obstacles(walls):
    for obj in walls:
        try:
            yield obj, footprint(obj)[0]
        except ValueError:
            continue


def normal(points, i):
    d = (points[(i+1) % 4] - points[i]).normalized()
    positive = (points[1]-points[0]).cross(points[3]-points[0]) > 0
    return Vector((d.y, -d.x)) if positive else Vector((-d.y, d.x))


def intervals(polygons, origin, end, *, inset=0.):
    """Clip a segment against convex footprints, returning world lengths."""
    length = (end-origin).length
    for points in polygons:
        lo, hi = 0., 1.
        for i, corner in enumerate(points):
            out = normal(points, i)
            a = (origin-corner).dot(out) + inset
            b = (end-corner).dot(out) + inset
            if a > 1e-7 and b > 1e-7:
                break
            if a > 1e-7:
                lo = max(lo, a/(a-b))
            elif b > 1e-7:
                hi = min(hi, a/(a-b))
        else:
            if (hi-lo)*length > EPS:
                yield lo*length, hi*length


def board_sections(context, obj, sides, returns, profile, height, thickness, spans):
    points, level = footprint(obj)
    inverse = obj.matrix_world.inverted()
    world_walls = list(perimeter.physical_walls(context, level))
    if not any(w.obj == obj for w in world_walls):
        raise ValueError(f'{obj.name}: select a physical Builder wall.')
    neighbors = [poly for _, poly in obstacles(w.obj for w in world_walls if w.obj != obj)]
    long_edges = () if not sides else (0,) if sides == 'SIDE_1' else (2,) if sides == 'SIDE_2' else (0, 2)
    runs = {}
    for i in long_edges:
        start, end = points[i], points[(i+1)%4]
        # Clip walls joined at a T anywhere along this face. A parallel wall
        # sharing the bare line should not block trim outside its footprint.
        outward = normal(points, i)
        offset = outward * (EPS * .1)
        runs[i] = [(a,b) for a,b in spans(start,end,outward,level,height,
                                        tuple(intervals(neighbors,start+offset,end+offset)))
                   if b-a >= EPS]

    def meets(edge, start):
        if not runs.get(edge):
            return False
        if start:
            return runs[edge][0][0] <= 1e-6
        return runs[edge][-1][1] >= (points[(edge+1)%4]-points[edge]).length - 1e-6

    def miter(i, at_start, projection):
        j = i if at_start else (i+1)%4
        other = (i-1)%4 if at_start else (i+1)%4
        point = points[j]
        outward = normal(points,i)
        here = point+projection*outward
        if not meets(other, not at_start):
            return here
        along = (points[(i+1)%4]-points[i]).normalized()
        adjacent = (points[(other+1)%4]-points[other]).normalized()
        match = perimeter.intersection(here,along,point+projection*normal(points,other),adjacent)
        if match is None or (match-here).length > 4*max(projection,EPS):
            return here
        return match

    if returns:
        for i in (1, 3):
            if not (meets(i-1, False) or meets((i+1)%4, True)):
                continue  # Don't leave an orphan cap next to a tiled/cut run.
            # Probe just beyond the cap: a butt joint along the exact same edge
            # is closed, even if no wall crosses into this wall's interior.
            offset = normal(points,i) * (EPS * .1)
            if any(intervals(neighbors,points[i]+offset,points[(i+1)%4]+offset)):
                continue
            runs[i] = [(0.,(points[(i+1)%4]-points[i]).length)]

    for i,ranges in runs.items():
        a,b = points[i], points[(i+1)%4]
        length = (b-a).length
        along = (b-a).normalized()
        outward = normal(points,i)
        for start,end in ranges:
            rings = [[], []]
            for up, out in profile:
                projection = out*thickness
                first = (miter(i,True,projection) if start <= 1e-6
                         else a+start*along+projection*outward)
                last = (miter(i,False,projection) if end >= length-1e-6
                        else a+end*along+projection*outward)
                if (last-first).dot(along) < EPS:
                    break
                for ring,p in zip(rings,(first,last)):
                    ring.append(inverse @ Vector((*p,level+up*height)))
            if len(rings[0]) == len(profile):
                yield rings
