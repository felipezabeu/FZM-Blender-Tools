"""Match a floor's outline to physical wall faces, without a selected wall chain."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite

from mathutils import Vector

from .. import hb_types


EPS = 0.001
MATCH = 0.010  # Allow the same endpoint tolerance as Add Floor's wall-chain search.
LEVEL = 0.010
PARALLEL = 0.01  # Sine of a small angle; an actual crossing wall is not a match.


@dataclass(frozen=True)
class Edge:
    start: Vector
    direction: Vector
    inward: Vector
    length: float

    @property
    def end(self):
        return self.start + self.length * self.direction


@dataclass(frozen=True)
class Wall:
    obj: object
    start: Vector
    end: Vector
    offset: Vector


@dataclass(frozen=True)
class Face:
    wall: Wall
    origin: Vector
    direction: Vector
    inward: Vector

    def at(self, edge, distance, projection=0):
        """Point on the exact wall face at a floor-edge longitudinal distance."""
        start = self.origin + projection * self.inward
        t = (edge.start + distance * edge.direction - start).dot(edge.direction)
        return start + self.direction * (t / self.direction.dot(edge.direction))


@dataclass
class Run:
    edge: Edge
    face: Face
    left: float
    right: float


def floor_outline(floor):
    """Return the world-space CCW boundary of the original top surface.

    The floor divider changes this source contour; material changes and interior
    Floor Cutter modifiers do not create perimeter edges.
    """
    if not floor.data.vertices:
        raise ValueError('The selected floor has no geometry')
    top = max(v.co.z for v in floor.data.vertices)
    top_faces = [face for face in floor.data.polygons if
                 all(abs(floor.data.vertices[i].co.z - top) < 1e-5 for i in face.vertices)]
    edge_counts = Counter(tuple(sorted(edge)) for face in top_faces for edge in face.edge_keys)
    adjacency = defaultdict(list)
    for (a, b), count in edge_counts.items():
        if count == 1:
            adjacency[a].append(b)
            adjacency[b].append(a)
    if len(adjacency) < 3 or any(len(incident) != 2 for incident in adjacency.values()):
        raise ValueError('The selected floor needs a closed, flat top outline')
    # Use the largest ring as the outer perimeter, not any editable interior hole.
    unseen = set(adjacency)
    rings = []
    matrix = floor.matrix_world
    while unseen:
        start = min(unseen)
        order, previous, current = [], None, start
        while current in unseen:
            order.append(current)
            unseen.remove(current)
            next_point = next(i for i in adjacency[current] if i != previous)
            previous, current = current, next_point
        if current != start or len(order) < 3:
            raise ValueError('The selected floor needs a closed, flat top outline')
        coords = [matrix @ floor.data.vertices[i].co for i in order]
        # Subtract origin to keep the signed area robust for plans far from (0,0).
        origin = coords[0].to_2d()
        xy = [p.to_2d() - origin for p in coords]
        area = sum(a.cross(b) for a, b in zip(xy, xy[1:] + xy[:1]))
        rings.append((area, coords))
    area, coords = max(rings, key=lambda item: abs(item[0]))
    level = sum(p.z for p in coords) / len(coords)
    if abs(area) < EPS ** 2 or any(abs(p.z - level) > EPS for p in coords):
        raise ValueError('The selected floor needs a level, non-collapsed top outline')
    outline = [p.to_2d() for p in (coords if area > 0 else reversed(coords))]
    edges = []
    for a, b in zip(outline, outline[1:] + outline[:1]):
        delta = b - a
        if delta.length < EPS:
            raise ValueError('The selected floor outline contains a collapsed edge')
        direction = delta.normalized()
        edges.append(Edge(a, direction, Vector((-direction.y, direction.x)), delta.length))
    return edges, level


def physical_walls(context, level):
    for obj in context.view_layer.objects:
        if (not obj.get('IS_WALL_BP') or obj.type != 'MESH'
                or obj.get('IS_FAKE_WALL') or obj.get('WALL_TYPE') == 'Fake'):
            continue
        wall = hb_types.GeoNodeWall(obj)
        if not all(wall.has_input(s) for s in ('Length', 'Thickness', 'Height')):
            continue
        length, thickness, height = (wall.get_input(s) for s in ('Length', 'Thickness', 'Height'))
        if any(v is None or not isfinite(v) for v in (length, thickness, height)):
            continue
        matrix = obj.matrix_world
        base = matrix.translation
        end = matrix @ Vector((length, 0, 0))
        far = matrix @ Vector((0, thickness, 0))
        top = matrix @ Vector((0, 0, height))
        if (max(abs(p.z - level) for p in (base, end, far)) > LEVEL
                or top.z <= level + EPS
                or (end.to_2d() - base.to_2d()).length < EPS
                or (far.to_2d() - base.to_2d()).length < EPS):
            continue
        yield Wall(obj, base.to_2d(), end.to_2d(), far.to_2d() - base.to_2d())


def edge_runs(edge, walls):
    """Disjoint projected wall spans; prefer the closest face on overlap."""
    candidates = []
    for wall in walls:
        wall_direction = (wall.end - wall.start).normalized()
        if abs(edge.direction.cross(wall_direction)) > PARALLEL:
            continue
        if wall_direction.dot(edge.direction) < 0:
            wall_direction.negate()
        lo, hi = sorted(((wall.start - edge.start).dot(edge.direction),
                         (wall.end - edge.start).dot(edge.direction)))
        lo, hi = max(0., lo), min(edge.length, hi)
        if hi - lo < EPS:
            continue
        inward = Vector((-wall_direction.y, wall_direction.x))
        far = wall.start + wall.offset
        if wall.offset.dot(inward) > 0:
            outer, inner = wall.start, far
        else:
            outer, inner = far, wall.start
        face = Face(wall, inner, wall_direction, inward)
        # The floor edge can be on either wall datum, or inside a real wall
        # footprint (e.g. a floor split down the center of a partition).
        offsets = [(face.at(edge, t) - edge.start).dot(edge.inward) for t in (lo, hi)]
        width = (inner - outer).dot(inward) / edge.direction.dot(wall_direction)
        if min(offsets) < -MATCH or max(offsets) > width + MATCH:
            continue
        signed = sum(offsets) / 2
        priority = (max(0., -signed, signed - width),
                    min(abs(signed), abs(signed - width)), wall.obj.name)
        candidates.append((lo, hi, priority, face))
    if not candidates:
        return []
    # Resolve overlaps once instead of laying two boards on coincident walls.
    ends = sorted({x for lo, hi, _, _ in candidates for x in (lo, hi)})
    runs = []
    for lo, hi in zip(ends, ends[1:]):
        if hi - lo < 1e-6:
            continue
        middle = (lo + hi) * .5
        winner = min((c for c in candidates if c[0] <= middle <= c[1]),
                     key=lambda c: c[2], default=None)
        if winner is None:
            continue
        face = winner[3]
        if runs and runs[-1].face is face and lo - runs[-1].right < 1e-6:
            runs[-1].right = hi
        else:
            runs.append(Run(edge, face, lo, hi))
    return [run for run in runs if run.right - run.left >= EPS]


def intersection(a, direction, b, other_direction):
    divisor = direction.cross(other_direction)
    if abs(divisor) < 1e-5:
        return None
    return a + direction * ((b - a).cross(other_direction) / divisor)


def end_point(run, left, projection, adjacent_edge, adjacent_run):
    """Miter onto the next real wall, or clip to the untrimmed/divider edge."""
    edge, face = run.edge, run.face
    t = run.left if left else run.right
    here = face.at(edge, t, projection)
    if abs(t - (0 if left else edge.length)) > MATCH:
        return here
    if adjacent_run:
        other_t = adjacent_run.right if left else adjacent_run.left
        other = adjacent_run.face.at(adjacent_run.edge, other_t, projection)
        point = intersection(here, face.direction, other, adjacent_run.face.direction)
        if point is None and (here - other).length <= MATCH:
            return (here + other) * .5
    else:
        # A shallow virtual divider still clips the board to the selected side.
        # If the profile is too wide for that sliver, the loft is omitted below.
        point = intersection(here, face.direction, adjacent_edge.start, adjacent_edge.direction)
        return point if point is not None else here
    # An unstable acute miter between real walls must not create a long spike.
    max_extension = max(MATCH, face.wall.offset.length + projection)
    if adjacent_run:
        max_extension = max(max_extension, adjacent_run.face.wall.offset.length + projection)
    if point is None or (point - here).length > 4 * max_extension:
        return here
    return point


def board_sections(context, floor, profile, height, thickness, wall_spans, matched_walls):
    """Yield (matched wall, independent start/end loft rings in floor space)."""
    context.view_layer.update()
    edges, level = floor_outline(floor)
    walls = list(physical_walls(context, level))
    perimeter = [edge_runs(edge, walls) for edge in edges]
    matched_walls.update(run.face.wall.obj for runs in perimeter for run in runs)
    try:
        inverse = floor.matrix_world.inverted()
    except ValueError as error:
        raise ValueError('The floor transform cannot be inverted') from error

    for i, runs in enumerate(perimeter):
        previous, following = perimeter[i - 1], perimeter[(i + 1) % len(edges)]
        previous_edge, following_edge = edges[i - 1], edges[(i + 1) % len(edges)]
        previous_wall = previous[-1] if previous and previous_edge.length - previous[-1].right <= MATCH else None
        following_wall = following[0] if following and following[0].left <= MATCH else None
        for k, run in enumerate(runs):
            # Only corner-adjacent wall segments may miter or use the divider cap.
            ends = ((previous_edge, previous_wall) if k == 0 else (run.edge, None),
                    (following_edge, following_wall) if k == len(runs) - 1 else (run.edge, None))
            origin = end_point(run, True, 0, *ends[0])
            end = end_point(run, False, 0, *ends[1])
            direction = run.face.direction
            length = (end - origin).dot(direction)
            if length < EPS:
                continue
            for left, right in wall_spans(run.face.wall.obj, origin, end, run.face.inward, level, height):
                if right - left < EPS:
                    continue
                rings = [[], []]
                for up, out in profile:
                    distance = thickness * out
                    a = (end_point(run, True, distance, *ends[0]) if left <= 1e-6
                         else origin + left * direction + distance * run.face.inward)
                    b = (end_point(run, False, distance, *ends[1]) if right >= length - 1e-6
                         else origin + right * direction + distance * run.face.inward)
                    if (b - a).dot(direction) < EPS:
                        break
                    for ring, point in zip(rings, (a, b)):
                        ring.append(inverse @ Vector((*point, level + up * height)))
                if len(rings[0]) == len(profile):
                    yield run.face.wall.obj, rings
