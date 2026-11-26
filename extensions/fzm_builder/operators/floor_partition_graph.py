"""Bounded planar faces of one saved footprint and its physical partitions."""
from collections import defaultdict, deque
from math import atan2

from mathutils import Vector

from .floor_divider import inside
from .floor_outline import CLOSE, LEVEL_EPS, SHAPE_EPS, _validate_ring
from .floor_thresholds import _wall_data


def _area(ring):
    origin = ring[0]
    return sum((a-origin).cross(b-origin) for a, b in zip(ring, ring[1:]+ring[:1]))*.5


def _walk(points, edges, perimeter_count):
    adjacency = defaultdict(set)
    for u, v in edges:
        adjacency[u].add(v)
        adjacency[v].add(u)

    # Discard components unattached to the envelope. Their detached room
    # detection and nesting are handled separately.
    connected = {i for pair, label in edges.items() if label[0] < perimeter_count for i in pair}
    pending = list(connected)
    while pending:
        for other in adjacency[pending.pop()] - connected:
            connected.add(other)
            pending.append(other)

    # Bridges do not bound any room. Prune tails first, then distinguish a
    # connector with a loop at its end from the cycle's own edges.
    todo = deque(i for i in connected if len(adjacency[i]) < 2)
    while todo:
        i = todo.popleft()
        for other in adjacency[i].copy():
            adjacency[i].remove(other)
            adjacency[other].remove(i)
            if len(adjacency[other]) == 1:
                todo.append(other)
    keep = set(connected)
    for source in connected:
        if not adjacency[source]:
            keep.discard(source)
    if not keep:
        return []

    entered, low, bridges = {}, {}, set()
    start = min(keep)
    entered[start] = low[start] = 0
    stack = [(start, None, iter(adjacency[start]))]
    while stack:
        current, previous, neighbors = stack[-1]
        other = next(neighbors, None)
        if other is None:
            stack.pop()
            if previous is not None:
                low[previous] = min(low[previous], low[current])
                if low[current] > entered[previous]:
                    bridges.add(tuple(sorted((previous, current))))
        elif other != previous and other in entered:
            low[current] = min(low[current], entered[other])
        elif other != previous:
            entered[other] = low[other] = len(entered)
            stack.append((other, current, iter(adjacency[other])))
    for a, b in bridges:
        adjacency[a].remove(b)
        adjacency[b].remove(a)
    # A detached loop reached only by a dangling connector is still a
    # detached room after that connector is removed.
    envelope_start = next(i for pair,label in edges.items()
                          if label[0] < perimeter_count for i in pair)
    keep = {envelope_start}
    pending = [envelope_start]
    while pending:
        for other in adjacency[pending.pop()] - keep:
            keep.add(other)
            pending.append(other)

    # Walking the predecessor of the reverse half-edge in angular order
    # keeps each bounded face on the left, producing CCW datum rings.
    def direction(i,j):
        delta = points[j]-points[i]
        return atan2(delta.y,delta.x)
    order = {i: sorted(adjacency[i],key=lambda j:direction(i,j)) for i in keep}
    seen, faces = set(), []
    for a in sorted(order):
        for b in order[a]:
            if (a, b) in seen:
                continue
            start = u, v = a, b
            face = []
            while (u, v) not in seen:
                seen.add((u, v))
                face.append((u, v))
                nexts = order[v]
                u, v = v, nexts[(nexts.index(u)-1) % len(nexts)]
            if (u, v) != start:
                raise ValueError('The wall intersections do not form a consistent floor plan.')
            ring = [points[u] for u, v in face]
            if len(ring) >= 3 and _area(ring) > SHAPE_EPS:
                try:
                    _validate_ring(ring)
                except ValueError as err:
                    raise ValueError('A connected room boundary touches itself. No floor was changed.') from err
                faces.append(face)
    return faces


def connected_rooms(hosts, poly, matrix, inverse, level, walls):
    """Yield partial wall edges, keyed by the supplied room's physical envelope.

    Endpoints snap only within the placement tolerance or along their own
    wall datum to a wall that physically touches them. A free-standing wall
    or loose stub never subdivides the floor.
    """
    outer = [(matrix @ Vector((*point, 0.))).xy for point in poly]
    objects = [obj for obj, _ in hosts]
    perimeter_count = len(objects)
    eligible = [edge for edge in walls if edge.obj not in objects and abs(edge.level-level) <= LEVEL_EPS]
    if not eligible:
        return []
    lines = [(a,b) for a,b in zip(outer,outer[1:]+outer[:1])]
    low = [min(p[axis] for p in outer) for axis in (0, 1)]
    high = [max(p[axis] for p in outer) for axis in (0, 1)]
    for edge in sorted(eligible, key=lambda row: row.obj.name):
        if any(max(edge.start[axis],edge.end[axis]) < low[axis]-CLOSE
               or min(edge.start[axis],edge.end[axis]) > high[axis]+CLOSE for axis in (0,1)):
            continue
        lines.append((edge.start, edge.end))
        objects.append(edge.obj)

    tolerance = SHAPE_EPS * 4
    parameters = [[(0., a), (1., b)] for a,b in lines]
    geometry = [_wall_data(obj) for obj in objects]

    def parameter(p, a, b):
        d = b-a
        return (p-a).dot(d)/d.length_squared

    def touches_wall(point, host_i, position, target_axis):
        datum = geometry[host_i]
        if not datum:
            return False
        unit = target_axis.normalized()
        signed = (point-position).cross(unit)
        side = datum[2].cross(unit)
        return min(0.,side)-CLOSE <= signed <= max(0.,side)+CLOSE

    # Move a terminal point onto the exact intersection of the two wall
    # datums when it was snapped to the host's actual offset face.
    for i in range(perimeter_count,len(lines)):
        a,b = lines[i]
        d = b-a
        for index, point in enumerate((a,b)):
            matches = []
            for j,(c,e) in enumerate(lines):
                if j == i:
                    continue
                v = e-c
                angle = d.cross(v)
                if abs(angle) < .1*d.length*v.length:
                    continue
                t = (c-a).cross(v)/angle
                p = a + d*t
                u = parameter(p,c,e)
                if -tolerance/v.length <= u <= 1.+tolerance/v.length:
                    distance = (p-point).length
                    if distance <= CLOSE or (distance <= .6 and touches_wall(point,j,p,v)):
                        matches.append((distance, p))
            if matches:
                best = min(matches,key=lambda q:q[0])
                if best[0] > tolerance:
                    parameters[i][index] = (float(index), best[1])

    # After offset end contacts have been normalized, explicitly node each
    # proper crossing, T intersection and shared endpoint.
    lines = [(points[0][1],points[1][1]) for points in parameters]
    for i,(a,b) in enumerate(lines):
        d = b-a
        if d.length < tolerance:
            continue
        for j,(c,e) in enumerate(lines[:i]):
            v = e-c
            if v.length < tolerance:
                continue
            cross = d.cross(v)
            if abs(cross) <= tolerance*max(d.length,v.length):
                if abs((c-a).cross(d.normalized())) > tolerance:
                    continue
                for p in (c,e):
                    t = parameter(p,a,b)
                    if 0. < t < 1.:
                        parameters[i].append((t,p))
                for p in (a,b):
                    u = parameter(p,c,e)
                    if 0. < u < 1.:
                        parameters[j].append((u,p))
                continue
            t = (c-a).cross(v)/cross
            u = (c-a).cross(d)/cross
            if (-tolerance/d.length <= t <= 1.+tolerance/d.length
                and -tolerance/v.length <= u <= 1.+tolerance/v.length):
                p = a+d*t
                if 0.<t<1.:
                    parameters[i].append((t,p))
                if 0.<u<1.:
                    parameters[j].append((u,p))

    points, grid = [], defaultdict(list)
    from math import floor
    def vertex(p):
        x,y = (floor(v/tolerance) for v in p)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for index in grid[x+dx,y+dy]:
                    if (points[index]-p).length <= tolerance:
                        return index
        n = len(points)
        points.append(p)
        grid[x,y].append(n)
        return n

    edges = {}
    for i,row in enumerate(parameters):
        row.sort(key=lambda item:item[0])
        for (_,a),(_,b) in zip(row,row[1:]):
            if (b-a).length <= tolerance:
                continue
            if i >= perimeter_count and not inside(outer, (a+b)*.5):
                continue
            u,v = vertex(a),vertex(b)
            key = tuple(sorted((u,v)))
            if key in edges:
                if edges[key][0] < perimeter_count:
                    continue  # Non-room wall coincides with a source rim.
                raise ValueError('Overlapping interior walls make floor room boundaries ambiguous.')
            edges[key] = (i,u,v)

    faces = _walk(points,edges,perimeter_count)
    if len(faces) < 2:
        return []
    area = sum(_area([points[u] for u,v in face]) for face in faces)
    if abs(area-abs(_area(outer))) > max(1e-5, abs(area)*2e-5):
        raise ValueError('The identified rooms do not cover the original floor exactly.')
    results = []
    for face in faces:
        result = []
        for u,v in face:
            i,original_u,original_v = edges[tuple(sorted((u,v)))]
            wall = objects[i]
            reverse = (v == original_u) != (i<perimeter_count and hosts[i][1])
            a,b = [(inverse @ Vector((*points[k], level))).xy for k in (u,v)]
            result.append((wall,reverse,a,b))
        # Ignore a collinear T node from a dangling wall on the same host;
        # it neither changes the boundary nor its identity.
        combined = []
        for entry in result:
            if combined and combined[-1][:2] == entry[:2]:
                w,r,a,_ = combined[-1]
                combined[-1] = (w,r,a,entry[3])
            else:
                combined.append(entry)
        if len(combined)>1 and combined[-1][:2]==combined[0][:2]:
            w,r,a,_ = combined.pop()
            combined[0] = (w,r,a,combined[0][3])
        results.append(combined)
    return results
