"""Subdivide a wall-backed floor into non-overlapping, persistent floor objects."""
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

import bpy
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

from . import floor_outline as outlines
from .floor_divider import area, inside

ROOT = 'FZM_FLOOR_REGION_ROOT'
HOLES = 'FZM_FLOOR_REGION_HOLES'
ENVELOPE = 'FZM_FLOOR_REGION_ENVELOPE'
SPAN_X = 'FZM_FLOOR_REGION_HOST_SPANS_X'
DATUM = 'FZM_FLOOR_REGION_DATUM'


@dataclass
class Region:
    hosts: list
    ring: list
    children: list = field(default_factory=list)
    obj: object = None
    spans: list = field(default_factory=list)
    source: object = None

    @property
    def key(self):
        return frozenset(wall for wall, _ in self.hosts)

    @property
    def identity(self):
        return _identity(self.hosts, partial=bool(self.spans))

    @property
    def holes(self):
        return [child.ring for child in self.children]



def _wall_interval(wall, a, b, matrix, z):
    inv = wall.matrix_world.inverted()
    return tuple((inv @ matrix @ Vector((*p,z))).x for p in (a,b))


def _records(prop):
    return {key: dict(row.items()) for key,row in prop.items()}


def plan_wall_division_bindings(context, head, cut_x):
    """Preflight floor metadata against a proposed structural wall division."""
    if not (0. < cut_x):
        raise ValueError('The wall division point must be inside the wall.')
    result = []
    for floor in context.scene.objects:
        if not floor.get('IS_FLOOR_BP'):
            continue
        fields = {key: _records(floor[key]) for key in (outlines.HOSTS,ENVELOPE,SPAN_X) if key in floor}
        if not any(row.get('wall') == head for key in (outlines.HOSTS,ENVELOPE)
                   for row in fields.get(key,{}).values()):
            continue
        if not outlines.selected_floor(floor) or floor.mode!='OBJECT':
            raise ValueError(f'{floor.name}: finish editing the associated floor before dividing this wall.')
        spans,hosts = fields.get(SPAN_X),fields.get(outlines.HOSTS,{})
        if floor.get(ENVELOPE) and spans is None:
            raise ValueError(f'{floor.name}: update its room outline before dividing a bound wall.')
        if spans is not None and (set(spans)!=set(hosts) or any(
                'start' not in row or 'end' not in row for row in spans.values())):
            raise ValueError(f'{floor.name}: a saved wall span could not be verified.')
        result.append((floor,fields,cut_x))
    # Existing pre-link floors can be associated only when their actual
    # closed wall match is exact; do not bind an unrelated/manual floor.
    legacy = outlines.legacy_before_wall_edit(context,{head})
    return result, legacy


def apply_wall_division_bindings(plan, head, tail):
    """Apply preflighted references; restore with restore_wall_division_bindings()."""
    recorded, legacy = plan
    for floor,fields,cut in recorded:
        for field in (outlines.HOSTS,ENVELOPE):
            if field not in fields:
                continue
            old_spans = fields.get(SPAN_X) if field==outlines.HOSTS else None
            updated, new_spans = {}, {}
            def append(row, interval=None):
                name=f'{len(updated):04d}'
                updated[name] = row.copy()
                if interval is not None:
                    new_spans[name] = {'start':interval[0],'end':interval[1]}
            for key,row in sorted(fields[field].items()):
                span = old_spans[key] if old_spans is not None else None
                if row.get('wall') != head:
                    append(row,(span['start'],span['end']) if span is not None else None)
                    continue
                second = dict(row,wall=tail)
                if span is None:
                    for part in ((second,row) if row.get('reversed') else (row,second)):
                        append(part)
                    continue
                a,b = span['start'],span['end']
                lo, hi = sorted((a,b))
                # These values were recorded in each wall's own model
                # space and need rebasing to the newly moved tail origin.
                if hi <= cut + outlines.SHAPE_EPS:
                    append(row,(a,b))
                elif lo >= cut - outlines.SHAPE_EPS:
                    append(second,(a-cut,b-cut))
                elif a > b:
                    append(second,(a-cut,0.))
                    append(row,(cut,b))
                else:
                    append(row,(a,cut))
                    append(second,(0.,b-cut))
            floor[field] = updated
            if old_spans is not None:
                floor[SPAN_X] = new_spans
    for floor,hosts,poly in legacy:
        expanded = []
        for wall,rev in hosts:
            if wall==head:
                expanded.extend(((tail,True),(head,True)) if rev else ((head,False),(tail,False)))
            else:
                expanded.append((wall,rev))
        outlines._store(floor,expanded,poly)


def restore_wall_division_bindings(plan):
    recorded, legacy = plan
    for floor,fields,_ in recorded:
        for field,values in fields.items():
            floor[field] = values
    for floor,_,_ in legacy:
        for key in (outlines.HOSTS,outlines.KIND,outlines.RIM,outlines.TRANSFORM):
            if key in floor:
                del floor[key]


def edges(ring):
    return zip(ring, ring[1:] + ring[:1])


def crosses(a, b):
    return any(outlines._intersects(u, v, x, y) for u, v in edges(a) for x, y in edges(b))


def area_at_origin(ring):
    return area([p-ring[0] for p in ring])


def _closed_components(walls, *, physical_contacts=False):
    """Endpoint graph; ignore loose chains and don't guess junctions or wall crossings."""
    if not walls:
        return
    points = [p for w in walls for p in (w.start,w.end)]
    representatives = list(range(len(points)))

    def find(i):
        while representatives[i] != i:
            representatives[i] = representatives[representatives[i]]
            i = representatives[i]
        return i

    cells = defaultdict(list)
    from math import floor
    reach = .6 if physical_contacts else outlines.CLOSE

    def joined(i,j):
        if i//2 == j//2 or not outlines._within(points[i],points[j],reach):
            return False
        if outlines._within(points[i],points[j],outlines.CLOSE):
            return True
        first,second = walls[i//2],walls[j//2]
        return outlines._touched_joint(
            (first.obj,points[i^1],points[i],first.level),
            (second.obj,points[j],points[j^1],second.level),
        ) is not None

    for i,p in enumerate(points):
        x,y = [floor(v/reach) for v in p]
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for j in cells[x+dx,y+dy]:
                    if joined(i,j):
                        representatives[find(i)] = find(j)
        cells[x,y].append(i)

    endpoints = [(find(i),find(i+1)) for i in range(0,len(points),2)]
    links = defaultdict(list)
    for i,(a,b) in enumerate(endpoints):
        links[a].append((i,False,b))
        links[b].append((i,True,a))

    pending = deque(node for node,incident in links.items() if len(incident)<2)
    while pending:  # A loose spur attached to a room must not erase its cycle.
        node = pending.popleft()
        if node not in links:
            continue
        for i,_,other in links.pop(node):
            if other in links:
                links[other] = [row for row in links[other] if row[0]!=i]
                if len(links[other])<2:
                    pending.append(other)

    remaining = set(links)
    for start in sorted(links):
        if start not in remaining:
            continue
        seen = {start}
        stack = [start]
        while stack:
            point = stack.pop()
            for _,_,other in links[point]:
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        remaining.difference_update(seen)
        if len(seen) < 3 or any(len(links[node]) != 2 for node in seen):
            continue
        current, prior = start, -1
        cycle = []
        for _ in seen:
            i,reversed_edge,other = next(r for r in links[current] if r[0] != prior)
            cycle.append((walls[i].obj,reversed_edge))
            prior,current = i,other
        if current == start and len({w for w,_ in cycle}) == len(cycle):
            yield cycle


def _identity(hosts, *, partial=False):
    if not partial:
        return frozenset(wall for wall,_ in hosts)
    cycle = tuple(hosts)
    start = min(range(len(cycle)), key=lambda i:
                tuple((w.name, r) for w,r in cycle[i:] + cycle[:i]))
    return cycle[start:] + cycle[:start]


def _regions(hosts, poly, matrix, inverse, level, walls, preferred=None, preferred_floor=None):
    from .floor_partition_graph import connected_rooms
    faces = connected_rooms(hosts,poly,matrix,inverse,level,walls)
    if faces:
        roots = [Region([(w,r) for w,r,_,_ in spans], [a for _,_,a,_ in spans],
                        spans=spans) for spans in faces]
        roots.sort(key=lambda node: (-abs(area_at_origin(node.ring)),
                                    tuple(sorted(w.name for w in node.key))))
        if preferred is not None:
            root = next((node for node in roots if node.identity == preferred),None)
            if root is None:
                subset = _refined_rooms(preferred_floor,roots)
                if not subset:
                    raise ValueError('The existing primary room no longer has its original set of walls. No rooms were merged or deleted.')
                root = subset[0]
                for candidate in subset:
                    candidate.source = preferred_floor
            roots.remove(root)
            roots.insert(0,root)
    else:
        if preferred is not None:
            raise ValueError('An existing wall partition is no longer closed. No rooms were merged or deleted.')
        roots = [Region(hosts,poly)]
    host_set = set().union(*(r.key for r in roots))
    inner = []
    low = tuple(min(p[i] for p in poly) for i in (0,1))
    high = tuple(max(p[i] for p in poly) for i in (0,1))
    for cycle in _closed_components([w for w in walls if w.obj not in host_set
                                      and abs(w.level-level) <= outlines.LEVEL_EPS]):
        loc = [inverse @ Vector((*(w.matrix_world.translation.xy),level)) for w,_ in cycle]
        if any(min(p[i] for p in loc)>high[i]+outlines.CLOSE or
               max(p[i] for p in loc)<low[i]-outlines.CLOSE for i in (0,1)):
            continue
        # Skip exterior detached rooms before imposing geometry constraints here.
        if all(not inside(poly,p.xy) for p in loc):
            if not crosses(poly,[p.xy for p in loc]):
                continue
        ring = outlines._new_outline(cycle,inverse,level)
        if crosses(poly,ring) or not all(inside(poly,p) for p in ring):
            if any(inside(poly,p) for p in ring) or crosses(poly,ring):
                raise ValueError('A separate wall loop touches or crosses this floor boundary. No floors were changed.')
            continue
        inner.append(Region(cycle,ring))
    inner.sort(key=lambda node: (-abs(area_at_origin(node.ring)),
                                tuple(sorted(w.name for w in node.key))))
    for i, child in enumerate(inner):
        parents = [node for node in roots if inside(node.ring,child.ring[0])
                   and not crosses(node.ring,child.ring)]
        if len(parents)!=1:
            raise ValueError('An interior room touches or crosses a connected partition. No floors were changed.')
        parent = parents[0]
        for other in inner[:i]:
            if crosses(child.ring,other.ring):
                raise ValueError('Interior wall loops touch or cross. No floors were changed.')
            if inside(other.ring,child.ring[0]):
                parent = other
        parent.children.append(child)
    return roots[0], roots[1:]+inner, roots[1:]


def plan_regions(hosts, poly, matrix, inverse, level, walls):
    return _regions(hosts,poly,matrix,inverse,level,walls)


def make_slab(name, poly, top, base, source, index, *, holes):
    """Triangulate both caps with identical hole edges and close all side faces."""
    points, boundary_edges = [], []
    for ring in (poly,*holes):
        n = len(points)
        points.extend(p-poly[0] for p in ring)
        boundary_edges.extend((n+i,n+(i+1)%len(ring)) for i in range(len(ring)))
    xy, _, caps, vertex_origins, _, _ = delaunay_2d_cdt(
        points,boundary_edges,[],0,outlines.SHAPE_EPS/5)
    if len(points)!=len(xy) or any(len(orig)!=1 for orig in vertex_origins):
        raise ValueError('A floor boundary contains edges too close to triangulate safely.')
    original_to_mesh = {orig[0]:i for i,orig in enumerate(vertex_origins)}
    boundary = {tuple(sorted((original_to_mesh[a],original_to_mesh[b]))) for a,b in boundary_edges}
    coords = [v+poly[0] for v in xy]
    cap = []
    for a,b,c in caps:
        center = (coords[a]+coords[b]+coords[c])/3
        if inside(poly,center) and not any(inside(hole,center) for hole in holes):
            orient = (xy[b]-xy[a]).cross(xy[c]-xy[a])
            cap.append((a,b,c) if orient>0 else (a,c,b))
    hits = Counter(tuple(sorted((a,b))) for face in cap for a,b in edges(list(face)))
    if {side for side,n in hits.items() if n==1} != boundary or any(n not in (1,2) for n in hits.values()):
        raise ValueError('The floor triangulation did not preserve all room boundaries.')
    expected = abs(area_at_origin(poly))-sum(abs(area_at_origin(r)) for r in holes)
    actual = sum(abs((xy[b]-xy[a]).cross(xy[c]-xy[a]))/2 for a,b,c in cap)
    if expected<=outlines.SHAPE_EPS or abs(expected-actual)>max(1e-6,expected*1e-5):
        raise ValueError('The floor triangulation did not preserve the net area.')
    n = len(coords)
    verts = [(*p,z) for z in (top,base) for p in coords]
    # CCW upper triangles point out; orient every wall opposite its upper face.
    shell = [(b,a,a+n,b+n) for face in cap for a,b in edges(list(face))
             if tuple(sorted((a,b))) in boundary]
    mesh = bpy.data.meshes.new(name)
    try:
        mesh.from_pydata(verts,[],cap+[(c+n,b+n,a+n) for a,b,c in cap]+shell)
        for mat in source.materials:
            mesh.materials.append(mat)
        for face in mesh.polygons:
            face.material_index = index
        if mesh.validate():
            raise ValueError('The generated floor mesh needed repairs.')
        mesh.update()
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise


def _match_holes(have, wanted):
    return len(have)==len(wanted) and all(
        any(outlines._same_ring(ring,other) for other in wanted) for ring in have)


def _read(floor, scene):
    rings,top,base,index = outlines._supported_mesh(floor,multiring=True)
    hosts = outlines._read_saved_host(floor,scene,rings[0])
    saved = floor.get(HOLES,{}).values()
    holes = [[Vector(values[i:i+2]) for i in range(0,len(values),2)] for values in saved]
    if not _match_holes(rings[1:],holes):
        raise ValueError('A saved room floor was edited manually. No floors were overwritten.')
    return hosts,rings,top,base,index


def _overlap_area(a, b):
    """Measure overlap, including coincident edges and containment."""
    ra, rb = a[0], b[0]
    for i in range(2):
        if (min(max(p[i] for p in ra),max(p[i] for p in rb))
                - max(min(p[i] for p in ra),min(p[i] for p in rb))) <= outlines.SHAPE_EPS:
            return 0.
    points, constraints = [], []
    origin = ra[0]
    for ring in (*a,*b):
        offset = len(points)
        points.extend(v-origin for v in ring)
        constraints.extend((offset+i,offset+(i+1) % len(ring)) for i in range(len(ring)))
    xy, _, triangles, _, _, _ = delaunay_2d_cdt(
        points,constraints,[],0,outlines.SHAPE_EPS/5)
    def filled(rings,p):
        return inside(rings[0],p) and not any(inside(h,p) for h in rings[1:])
    overlap = 0.
    for i,j,k in triangles:
        p,q,r = xy[i],xy[j],xy[k]
        center = (p+q+r)/3 + origin
        if filled(a,center) and filled(b,center):
            overlap += abs((q-p).cross(r-p))/2
    return overlap


def _positive_overlap(a,b):
    return _overlap_area(a,b) > outlines.SHAPE_EPS


def _refined_rooms(existing, possible):
    saved = existing.get(DATUM,())
    if len(saved)<6 or len(saved)%2:
        return []
    old = [Vector(saved[i:i+2]) for i in range(0,len(saved),2)]
    old_area = abs(area_at_origin(old))
    tolerance = max(outlines.SHAPE_EPS,old_area*1e-5)
    found = []
    for candidate in possible:
        if not candidate.spans:
            continue
        size = abs(area_at_origin(candidate.ring))
        overlap = _overlap_area([old],[candidate.ring])
        if overlap>tolerance and abs(overlap-size)<=tolerance:
            found.append((size,candidate))
    # Movement, removal, merges, and unclear assignments do not destroy the
    # finishes of existing rooms. Only a geometric refinement is inherited.
    if not found or abs(sum(size for size,_ in found)-old_area)>tolerance:
        return []
    return [node for size,node in sorted(found,key=lambda row:-row[0])]


def _adopt_independent_rooms(context, known, plan, inverse, level):
    """Reuse exact legacy/Add Floor room slabs instead of duplicating them."""
    candidates = {node.key:node for node in plan if node.obj is None and not node.spans}
    if not candidates:
        return
    for obj in sorted(context.view_layer.objects,key=lambda item:item.name):
        if (obj in known or not outlines.selected_floor(obj) or obj.mode != 'OBJECT'
                or any(key in obj for key in (ROOT, HOLES, ENVELOPE))
                or obj.get(outlines.KIND) not in (None, outlines.LINKED)):
            continue
        try:
            poly,top,_,_ = outlines._supported_mesh(obj)
            matrix,_,other_level = outlines.floor_plane(obj,top)
            if abs(other_level-level)>outlines.LEVEL_EPS:
                continue
            if obj.get(outlines.KIND) == outlines.LINKED:
                hosts = outlines._read_saved_host(obj,context.scene,poly)
            else:
                walls = [edge for o in context.view_layer.objects if (edge:=outlines.wall_edge(o))]
                hosts = outlines._legacy_hosts(obj,poly,top,walls)
            node = candidates.get(frozenset(wall for wall,_ in hosts))
            if node is None or node.obj is not None:
                continue
            existing = [(inverse @ matrix @ Vector((*p,top))).xy for p in poly]
            source = outlines._new_outline(hosts,inverse,level)
            expected = outlines._physical_ring(hosts,source,inverse.inverted(),level,context.scene)
            if not outlines._same_ring(source,node.ring,outlines.CLOSE) or not (
                    outlines._same_ring(existing,node.ring,outlines.CLOSE)
                    or outlines._same_ring(existing,expected,outlines.CLOSE)):
                continue
        except (ValueError, TypeError, RuntimeError):
            continue
        node.obj = obj
        known.add(obj)


def _assert_other_slabs_clear(context, known, proposed, inverse, level):
    """Never lay down a second floor over an already covered independent region."""
    for obj in context.view_layer.objects:
        if not outlines.selected_floor(obj) or obj in known:
            continue
        try:
            rings,top,_,_ = outlines.floor_divider.top_rings(obj.data)
            matrix,_,other_level = outlines.floor_plane(obj,top)
        except (ValueError,TypeError,RuntimeError):
            continue
        if abs(other_level-level)>outlines.LEVEL_EPS:
            continue
        rings = [[(inverse @ matrix @ Vector((*p,top))).xy for p in ring] for ring in rings]
        if any(_positive_overlap(shape,rings) for shape in proposed):
            raise ValueError(f'{obj.name} already covers part of an enclosed room. No overlapping floor was created.')


def _root_space_to_floor(rings, root_matrix, obj, top):
    inverse = obj.matrix_world.inverted()
    matrix = inverse @ root_matrix
    return [[(matrix @ Vector((*p,top))).xy for p in ring] for ring in rings]


def update_family(context, selected, *, initial=None):
    """Preflight every region, then commit the family together under one Blender undo."""
    root = selected.get(ROOT) or selected
    if not outlines.selected_floor(root) or root.name not in context.view_layer.objects:
        raise ValueError('The original surrounding floor is missing. No floor was changed.')
    if root.mode != 'OBJECT':
        raise ValueError('Finish editing the surrounding floor first.')
    scene = context.scene
    envelope = root.get(ENVELOPE)
    partitioned = bool(envelope)
    if initial:
        hosts,poly,plan = initial
        _,top,_,_ = outlines._supported_mesh(root,multiring=True)
    else:
        root_faces,_,top,_,_ = _read(root,scene)
        hosts = ([(item.get('wall'),bool(item.get('reversed')))
                  for _,item in sorted(envelope.items())] if partitioned else root_faces)
        if any(not wall or wall.name not in scene.objects for wall,_ in hosts):
            raise ValueError('A source wall of the original floor was removed. No floors were changed.')
        walls = [edge for obj in context.view_layer.objects if (edge:=outlines.wall_edge(obj))]
    root_matrix, inverse, level = outlines.floor_plane(root,top)
    if not initial:
        poly = outlines._new_outline(hosts,inverse,level)
    root_node,inner,peers = plan if initial else _regions(
        hosts,poly,root_matrix,inverse,level,walls,
        preferred=_identity(root_faces,partial=True) if partitioned else None,
        preferred_floor=root if partitioned else None)
    root_node.obj = root
    planned = {node.identity:node for node in inner}
    if len(planned)!=len(inner):
        raise ValueError('The walls do not uniquely identify separate rooms. No floors were changed.')
    known = {root}
    missing = []
    for obj in context.scene.objects:
        if obj.get(ROOT)!=root:
            continue
        if obj.name not in context.view_layer.objects or not outlines.selected_floor(obj):
            raise ValueError('A floor in this room group is excluded or read-only. No floor was changed.')
        existing_hosts,_,_,_,_ = _read(obj,scene)
        key = _identity(existing_hosts,partial=bool(obj.get(ENVELOPE)))
        if key not in planned:
            missing.append(obj)
        elif planned[key].obj is not None or (planned[key].source and planned[key].source!=obj):
            raise ValueError('An existing room no longer has a unique closed wall loop. No rooms were merged or deleted.')
        else:
            planned[key].obj = obj
            known.add(obj)
    for obj in missing:
        subset = _refined_rooms(obj,[n for n in peers if n.obj is None and n.source is None])
        if not subset:
            raise ValueError('An existing room no longer has a unique closed wall loop. No rooms were merged or deleted.')
        subset[0].obj = obj
        for node in subset:
            node.source = obj
        known.add(obj)
    _adopt_independent_rooms(context,known,inner,inverse,level)

    staged = []
    created = []
    applied = []
    data = []
    warnings = []
    proposed = []
    all_rings = []
    def stage(node, inheritance):
        obj = node.obj or node.source or inheritance
        old_rings,t,b,idx = outlines._supported_mesh(obj,multiring=True)
        if node.spans:
            from .floor_thresholds import physical_floor_ring
            outer = physical_floor_ring(
                [(wall,a,b) for wall,_,a,b in node.spans],root_matrix,level,scene,
                warnings=warnings,partial=True)
            outlines._validate_ring(outer)
        else:
            outer = outlines._physical_ring(node.hosts,node.ring,root_matrix,level,scene,warnings=warnings)
        holes = [outlines._physical_ring(child.hosts,child.ring,root_matrix,level,scene,interior=False,warnings=warnings)
                 for child in node.children]
        if any(crosses(outer,hole) or not all(inside(outer,p) for p in hole) for hole in holes):
            raise ValueError('A room threshold or wall face leaves its surrounding floor. No floors were changed.')
        if any(crosses(hole,sibling) or inside(sibling,hole[0]) or inside(hole,sibling[0])
               for i,hole in enumerate(holes) for sibling in holes[:i]):
            raise ValueError('Room boundaries overlap after accounting for wall faces. No floors were changed.')
        datum_rings = [outer,*holes]
        all_rings.append(datum_rings)
        outer,*holes = _root_space_to_floor(datum_rings,root_matrix,obj,top)
        mesh = None
        if node.obj is None or not outlines._same_ring(old_rings[0],outer) or not _match_holes(old_rings[1:],holes):
            mesh = outlines._build_mesh(obj,outer,t,b,idx,holes=holes)
            staged.append(mesh)
            proposed.append(datum_rings)
        data.append((node,obj,outer,holes,mesh))
        for child in node.children:
            stage(child,obj)

    try:
        stage(root_node,root)
        for peer in peers:
            stage(peer,root)
        if proposed:
            _assert_other_slabs_clear(context,known,proposed,inverse,level)
            for i,shape in enumerate(all_rings):
                if any(_positive_overlap(shape,other) for other in all_rings[:i]):
                    raise ValueError('The proposed physical room floors overlap. No floors were changed.')
        for node,source,outer,holes,mesh in data:
            if node.obj is not None or mesh is None:
                continue
            obj = source.copy()
            created.append(obj)
            obj.name = 'Floor – Interior Room'
            outlines._set_mesh(obj,mesh,outlines._slots(source))
            for collection in source.users_collection:
                collection.objects.link(obj)
            if not obj.users_collection:
                raise ValueError('The surrounding floor must be in a collection.')
            node.obj = obj
        context.view_layer.update()
        for node,source,outer,holes,mesh in data:
            obj = node.obj
            if mesh is None or obj in created:
                continue
            old,slots = obj.data,outlines._slots(obj)
            applied.append((obj,old,slots))
            outlines._set_mesh(obj,mesh,slots)
    except Exception:
        for obj,old,slots in reversed(applied):
            outlines._set_mesh(obj,old,slots)
        for obj in reversed(created):
            bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in staged:
            if mesh.users==0:
                bpy.data.meshes.remove(mesh)
        raise

    for node,source,outer,holes,mesh in data:
        obj = node.obj
        outlines._store(obj,node.hosts,outer)
        obj[HOLES] = {f'{i:04d}':outlines._ring_dump(ring) for i,ring in enumerate(holes)}
        if obj!=root:
            obj[ROOT] = root
        if node.spans:
            obj[ENVELOPE] = {f'{i:04d}':{'wall':wall,'reversed':rev}
                             for i,(wall,rev) in enumerate(hosts)}
            spans = [_wall_interval(wall,a,b,root_matrix,top) for wall,_,a,b in node.spans]
            obj[SPAN_X] = {f'{i:04d}':{'start':a,'end':b} for i,(a,b) in enumerate(spans)}
            obj[DATUM] = outlines._ring_dump(node.ring)
        else:
            for key in (ENVELOPE,SPAN_X,DATUM):
                if key in obj:
                    del obj[key]
    for _,old,_ in applied:
        if old.users==0:
            bpy.data.meshes.remove(old)
    from .finishes import refresh_floor_baseboards
    warnings.extend(warning for node,_,_,_,_ in data
                    for warning in refresh_floor_baseboards(context,node.obj))
    return bool(staged),list(dict.fromkeys(warnings)),len(created)
