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


@dataclass
class Region:
    hosts: list
    ring: list
    children: list = field(default_factory=list)
    obj: object = None

    @property
    def key(self):
        return frozenset(wall for wall, _ in self.hosts)

    @property
    def holes(self):
        return [child.ring for child in self.children]


def edges(ring):
    return zip(ring, ring[1:] + ring[:1])


def crosses(a, b):
    return any(outlines._intersects(u, v, x, y) for u, v in edges(a) for x, y in edges(b))


def area_at_origin(ring):
    return area([p-ring[0] for p in ring])


def _closed_components(walls):
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
    for i,p in enumerate(points):
        x,y = [floor(v/outlines.CLOSE) for v in p]
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for j in cells[x+dx,y+dy]:
                    if outlines._within(p,points[j],outlines.CLOSE):
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


def _regions(hosts, poly, inverse, level, walls):
    root = Region(hosts,poly)
    host_set = root.key
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
        parent = root
        for other in inner[:i]:
            if crosses(child.ring,other.ring):
                raise ValueError('Interior wall loops touch or cross. No floors were changed.')
            if inside(other.ring,child.ring[0]):
                parent = other
        parent.children.append(child)
    return root, inner


def plan_regions(hosts, poly, inverse, level, walls):
    return _regions(hosts,poly,inverse,level,walls)


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


def _assert_other_slabs_clear(context, known, plan, inverse, level):
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
        for node in plan:
            other = rings[0]
            # Shared corner/edge is not an overlap. A substantial part of the
            # other slab inside a new region (or vice versa) is not guessed.
            def strictly_in(shape,p):
                return inside(shape,p) and outlines.floor_divider.snap(shape,p)[0]>outlines.SHAPE_EPS
            if (outlines._same_ring(node.ring,other,outlines.CLOSE)
                or any(strictly_in(node.ring,p) for p in other)
                or any(strictly_in(other,p) and not any(inside(hole,p) for hole in rings[1:])
                       for p in node.ring)
                or any((b-a).cross(c-a)*(b-a).cross(d-a)<-outlines.SHAPE_EPS**2
                       and (d-c).cross(a-c)*(d-c).cross(b-c)<-outlines.SHAPE_EPS**2
                       for a,b in edges(node.ring) for c,d in edges(other))):
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
    if initial:
        hosts,poly,plan = initial
        _,top,_,_ = outlines._supported_mesh(root,multiring=True)
    else:
        hosts,_,top,_,_ = _read(root,scene)
        walls = [edge for obj in context.view_layer.objects if (edge:=outlines.wall_edge(obj))]
    root_matrix, inverse, level = outlines.floor_plane(root,top)
    if not initial:
        poly = outlines._new_outline(hosts,inverse,level)
    root_node,inner = plan if initial else _regions(hosts,poly,inverse,level,walls)
    root_node.obj = root
    planned = {node.key:node for node in inner}
    known = {root}
    for obj in context.scene.objects:
        if obj.get(ROOT)!=root:
            continue
        if obj.name not in context.view_layer.objects or not outlines.selected_floor(obj):
            raise ValueError('A floor in this room group is excluded or read-only. No floor was changed.')
        existing_hosts,_,_,_,_ = _read(obj,scene)
        key = frozenset(wall for wall,_ in existing_hosts)
        if key not in planned or planned[key].obj is not None:
            raise ValueError('An existing room no longer has a unique closed wall loop. No rooms were merged or deleted.')
        planned[key].obj = obj
        known.add(obj)
    new_nodes = [node for node in inner if node.obj is None]
    if new_nodes:
        _assert_other_slabs_clear(context,known,new_nodes,inverse,level)

    staged = []
    created = []
    applied = []
    data = []
    warnings = []
    def stage(node, inheritance):
        obj = node.obj or inheritance
        old_rings,t,b,idx = outlines._supported_mesh(obj,multiring=True)
        outer = outlines._physical_ring(node.hosts,node.ring,root_matrix,level,scene,warnings=warnings)
        holes = [outlines._physical_ring(child.hosts,child.ring,root_matrix,level,scene,interior=False,warnings=warnings)
                 for child in node.children]
        if any(crosses(outer,hole) or not all(inside(outer,p) for p in hole) for hole in holes):
            raise ValueError('A room threshold or wall face leaves its surrounding floor. No floors were changed.')
        if any(crosses(hole,sibling) or inside(sibling,hole[0]) or inside(hole,sibling[0])
               for i,hole in enumerate(holes) for sibling in holes[:i]):
            raise ValueError('Room boundaries overlap after accounting for wall faces. No floors were changed.')
        outer,*holes = _root_space_to_floor([outer,*holes],root_matrix,obj,top)
        mesh = None
        if node.obj is None or not outlines._same_ring(old_rings[0],outer) or not _match_holes(old_rings[1:],holes):
            mesh = outlines._build_mesh(obj,outer,t,b,idx,holes=holes)
            staged.append(mesh)
        data.append((node,obj,outer,holes,mesh))
        for child in node.children:
            stage(child,obj)

    try:
        stage(root_node,root)
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
    for _,old,_ in applied:
        if old.users==0:
            bpy.data.meshes.remove(old)
    from .finishes import refresh_floor_baseboards
    warnings.extend(warning for node,_,_,_,_ in data
                    for warning in refresh_floor_baseboards(context,node.obj))
    return bool(staged),list(dict.fromkeys(warnings)),len(created)
