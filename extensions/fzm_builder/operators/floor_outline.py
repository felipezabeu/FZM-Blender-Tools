"""Rebuild one existing slab from its physical wall loop, without replacing its object."""

from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Vector

from .. import hb_types
from . import floor_divider

KIND = 'FZM_FLOOR_OUTLINE_KIND'
HOSTS = 'FZM_FLOOR_OUTLINE_HOSTS'
RIM = 'FZM_FLOOR_OUTLINE_LAST_RIM'
TRANSFORM = 'FZM_FLOOR_OUTLINE_LAST_MATRIX'
LINKED = 'LINKED'
DIVIDED = 'DIVIDED'
BOUNDS = 'BOUNDS'
CLOSE = .01             # Match Add Floor's existing loop tolerance.
EXACT = .00015         # Tight matching for legacy association, not nearest-room inference.
SHAPE_EPS = .00002
LEVEL_EPS = .002
INTERNAL_ATTRS = {'position', 'material_index', 'sharp_face'}


@dataclass
class WallEdge:
    obj: object
    start: Vector
    end: Vector
    level: float


def selected_floor(obj):
    return bool(obj and obj.type == 'MESH' and obj.get('IS_FLOOR_BP')
                and not (obj.library or obj.override_library))


def wall_edge(obj):
    if (not obj or obj.type != 'MESH' or not obj.get('IS_WALL_BP')
            or obj.get('IS_FAKE_WALL') or obj.get('WALL_TYPE') == 'Fake'):
        return None
    wall = hb_types.GeoNodeWall(obj)
    if not wall.has_input('Length'):
        return None
    length = wall.get_input('Length')
    if length is None or not isfinite(length) or length <= SHAPE_EPS:
        return None
    a = obj.matrix_world.translation
    b = obj.matrix_world @ Vector((length, 0., 0.))
    if not all(isfinite(v) for v in (*a, *b)) or abs(a.z-b.z) > LEVEL_EPS:
        return None
    if (b.xy-a.xy).length < SHAPE_EPS:
        return None
    return WallEdge(obj, a.xy, b.xy, a.z)


def floor_plane(floor, local_top):
    matrix = floor.matrix_world
    if (abs(matrix[2][0]) > SHAPE_EPS or abs(matrix[2][1]) > SHAPE_EPS
            or abs(matrix[0][2]) > SHAPE_EPS or abs(matrix[1][2]) > SHAPE_EPS):
        raise ValueError('Update Floor Outline requires a level floor.')
    try:
        inverse = matrix.inverted()
    except ValueError as error:
        raise ValueError('The floor transform cannot be inverted.') from error
    return matrix, inverse, (matrix @ Vector((0, 0, local_top))).z


def _matrix_dump(matrix):
    return [v for row in matrix for v in row]


def _ring_dump(poly):
    return [v for corner in poly for v in corner]


def _within(a, b, tolerance):
    return (a-b).length <= tolerance


def _same_ring(a, b, tolerance=SHAPE_EPS):
    if len(a) != len(b):
        return False
    for i, p in enumerate(b):
        if _within(a[0], p, tolerance):
            if any(all(_within(q, b[(i + step*j) % len(b)], tolerance)
                       for j, q in enumerate(a)) for step in (1, -1)):
                return True
    return False


def _store(floor, hosts, poly):
    floor[HOSTS] = {f'{i:04d}': {'wall': obj, 'reversed': rev}
                    for i, (obj, rev) in enumerate(hosts)}
    floor[RIM] = _ring_dump(poly)
    floor[TRANSFORM] = _matrix_dump(floor.matrix_world)
    floor[KIND] = LINKED


def remember_created_floor(floor, walls, *, bounds=False):
    # Classify bounding boxes but never turn the temporary Add Floor fallback
    # into a guessed closed room. Existing Add Floor geometry is untouched.
    if bounds:
        floor[KIND] = BOUNDS
        return
    try:
        poly, *_ = floor_divider.top_outline(floor.data)
    except ValueError:
        return
    if len(walls) >= 3:
        _store(floor, [(obj, False) for obj in walls], poly)


def mark_divided(*floors):
    for floor in floors:
        if selected_floor(floor):
            for key in (HOSTS, RIM, TRANSFORM):
                if key in floor:
                    del floor[key]
            floor[KIND] = DIVIDED


def _legacy_hosts(floor, poly, top, walls):
    """Associate only an exact closed wall bijection, regardless of selection/order."""
    matrix, _, level = floor_plane(floor, top)
    rim = [(matrix @ Vector((*p, top))).xy for p in poly]
    eligible = [w for w in walls if abs(w.level-level) <= LEVEL_EPS]
    hosts = []
    for a, b in zip(rim, rim[1:] + rim[:1]):
        matches = []
        for edge in eligible:
            for start, end, rev in ((edge.start, edge.end, False), (edge.end, edge.start, True)):
                if _within(start, a, EXACT) and _within(end, b, EXACT):
                    matches.append((edge.obj, rev))
        if len(matches) != 1:
            raise ValueError('No unique exact wall loop matches this older floor. Do not rebuild divided or ambiguous floors.')
        hosts.append(matches[0])
    if len({obj for obj, _ in hosts}) != len(hosts):
        raise ValueError('The older floor does not match a closed set of distinct walls.')
    return hosts


def legacy_before_wall_edit(context, moved_walls):
    """Capture exact legacy hosts before a native wall edit, without changing the floor."""
    floors = [o for o in context.scene.objects if selected_floor(o) and KIND not in o]
    if not floors:
        return []
    walls = [edge for o in context.scene.objects if (edge := wall_edge(o))]
    bindings = []
    for floor in floors:
        try:
            poly, top, _, _ = floor_divider.top_outline(floor.data)
            hosts = _legacy_hosts(floor, poly, top, walls)
        except (ValueError, TypeError, RuntimeError):
            continue
        if any(obj in moved_walls for obj, _ in hosts):
            bindings.append((floor, hosts, poly))
    return bindings


def save_legacy_bindings(bindings):
    for floor, hosts, poly in bindings:
        _store(floor, hosts, poly)


def _intersects(a, b, c, d):
    def side(p, q, v):
        return ((q-p).cross(v-p)) / (q-p).length
    def on_segment(p, q, v, s):
        pq = q-p
        t = (v-p).dot(pq.normalized())
        return abs(s) <= SHAPE_EPS and -SHAPE_EPS <= t <= pq.length+SHAPE_EPS
    aa, bb, cc, dd = side(a,b,c), side(a,b,d), side(c,d,a), side(c,d,b)
    return ((aa*bb < 0 and cc*dd < 0) or on_segment(a,b,c,aa) or on_segment(a,b,d,bb)
            or on_segment(c,d,a,cc) or on_segment(c,d,b,dd))


def _validate_ring(poly):
    if len(poly) < 3:
        raise ValueError('At least three walls must form a closed floor loop.')
    center = poly[0]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    if any((b-a).length <= SHAPE_EPS for a,b in edges):
        raise ValueError('The wall loop has a collapsed floor edge.')
    area = .5*sum((a-center).cross(b-center) for a,b in edges)
    if abs(area) < SHAPE_EPS:
        raise ValueError('The wall loop does not enclose an area.')
    for i, (a,b) in enumerate(edges):
        for j, (c,d) in enumerate(edges):
            if j <= i+1 or (i == 0 and j == len(edges)-1):
                continue
            if _intersects(a,b,c,d):
                raise ValueError('The wall loop crosses itself; the floor was not changed.')


def _new_outline(hosts, inverse, level):
    if len(hosts) < 3 or len({w for w,_ in hosts}) != len(hosts):
        raise ValueError('The saved floor perimeter needs at least three distinct walls.')
    edges = []
    for obj, rev in hosts:
        edge = wall_edge(obj)
        if edge is None:
            raise ValueError('A source wall is missing or no longer a compatible physical wall.')
        if edges and abs(edge.level-edges[0][2]) > LEVEL_EPS:
            raise ValueError('The source walls no longer have the same base level.')
        a,b = (edge.end,edge.start) if rev else (edge.start,edge.end)
        edges.append((a,b,edge.level))
    for (_,b,_), (c,_,_) in zip(edges, edges[1:] + edges[:1]):
        if not _within(b,c,CLOSE):
            raise ValueError('The source walls no longer form a closed perimeter; the floor was not changed.')
    poly = [(inverse @ Vector((*a,level))).xy for a,_,_ in edges]
    _validate_ring(poly)
    return poly


def _physical_ring(hosts, poly, matrix, level, scene, *, interior=True, warnings=None):
    from .floor_thresholds import physical_floor_ring
    ring = physical_floor_ring(
        [(obj,a,b) for (obj,_),a,b in zip(hosts,poly,poly[1:]+poly[:1])],
        matrix,level,scene,interior=interior,warnings=warnings)
    _validate_ring(ring)
    return ring


def _read_saved_host(floor, scene, current_poly):
    values = floor.get(RIM)
    if values is None or len(values) % 2 or len(values) < 6:
        raise ValueError('The saved floor outline cannot be verified.')
    saved_poly = [Vector(values[i:i+2]) for i in range(0,len(values),2)]
    if not _same_ring(current_poly,saved_poly):
        raise ValueError('This floor outline was edited manually. Its custom shape was not overwritten.')
    saved_matrix = floor.get(TRANSFORM, ())
    current_matrix = _matrix_dump(floor.matrix_world)
    if len(saved_matrix) != len(current_matrix) or any(abs(a-b)>SHAPE_EPS for a,b in zip(saved_matrix,current_matrix)):
        raise ValueError('This floor object was moved or transformed separately. Its saved placement was not overwritten.')
    hosts = [(item.get('wall'), bool(item.get('reversed')))
             for _,item in sorted(floor.get(HOSTS, {}).items())]
    if not hosts or any(not obj or obj.name not in scene.objects for obj,_ in hosts):
        raise ValueError('A saved source wall was removed from this scene; the floor was not changed.')
    return hosts


def _uv_layers(mesh):
    """Read planar/affine UVs. Reject hand-painted seams instead of erasing them."""
    result = []
    for layer in mesh.uv_layers:
        samples = [(mesh.vertices[lp.vertex_index].co.xy.copy(), layer.uv[lp.index].vector.copy())
                   for lp in mesh.loops]
        if len(samples) < 3:
            raise ValueError('The floor UV map cannot be verified.')
        a, u = samples[0]
        pair = next(((b,v) for b,v in samples if (b-a).length > SHAPE_EPS),None)
        if pair is None:
            raise ValueError('The floor UV mapping is degenerate.')
        b, v = pair
        ab = b-a
        third = next(((c,w) for c,w in samples if abs(ab.cross(c-a)) > SHAPE_EPS**2),None)
        if third is None:
            raise ValueError('The floor UV mapping is degenerate.')
        c,w = third
        ac = c-a
        determinant = ab.cross(ac)
        uvx = ((v-u)*ac.y - (w-u)*ab.y)/determinant
        uvy = ((w-u)*ab.x - (v-u)*ac.x)/determinant
        offset = u - uvx*a.x - uvy*a.y
        if not all(isfinite(x) for value in (uvx,uvy,offset) for x in value):
            raise ValueError('The floor UV map is not finite.')
        if any((uvx*p.x+uvy*p.y+offset-value).length > max(5e-5, 3e-7*value.length)
               for p,value in samples):
            raise ValueError('This floor has custom non-planar UVs. The outline was not changed.')
        result.append((layer.name,layer.active_render,layer.active_clone,uvx,uvy,offset))
    return result, mesh.uv_layers.active.name if mesh.uv_layers.active else None


def _supported_mesh(floor, *, multiring=False):
    mesh = floor.data
    if mesh.shape_keys or floor.vertex_groups:
        raise ValueError('This floor has custom vertex data; the outline was not changed.')
    if any(c.parent_type in {'VERTEX','VERTEX_3'} for c in floor.children):
        raise ValueError('This floor has a vertex-parented object. Its attachment was not changed.')
    existing_uvs = {layer.name for layer in mesh.uv_layers}
    attrs = {a.name for a in mesh.attributes if not a.is_internal}
    if attrs - existing_uvs - INTERNAL_ATTRS:
        raise ValueError('This floor has custom mesh attributes; the outline was not changed.')
    smooth = {p.use_smooth for p in mesh.polygons}
    if len(smooth) > 1 or mesh.has_custom_normals:
        raise ValueError('This floor has custom face normals; the outline was not changed.')
    return (floor_divider.top_rings if multiring else floor_divider.top_outline)(mesh)


def _build_mesh(floor, outline, top, base, index, *, holes=()):
    old = floor.data
    layers, active = _uv_layers(old)
    if holes:
        from .floor_regions import make_slab
    else:
        make_slab = floor_divider.make_slab
    new = make_slab(floor.name+' Outline',outline,top,base,old,index,
                    **({'holes':holes} if holes else {}))
    try:
        fresh_uv = new.uv_layers.get('UVMap')
        if fresh_uv is not None:
            new.uv_layers.remove(fresh_uv)
        if layers:
            for name,render,clone,uvx,uvy,offset in layers:
                uv = new.uv_layers.new(name=name,do_init=False)
                uv.active_render = render
                uv.active_clone = clone
                for lp in new.loops:
                    pt = new.vertices[lp.vertex_index].co
                    uv.uv[lp.index].vector = uvx*pt.x+uvy*pt.y+offset
            if active:
                new.uv_layers.active = new.uv_layers[active]
        if old.polygons[0].use_smooth:
            for face in new.polygons:
                face.use_smooth = True
        for key,value in old.items():
            new[key]=value
    except Exception:
        bpy.data.meshes.remove(new)
        raise
    return new


def _slots(floor):
    return [(i,slot.material) for i,slot in enumerate(floor.material_slots) if slot.link=='OBJECT']


def _set_mesh(floor, mesh, slots):
    floor.data = mesh
    for i, material in slots:
        floor.material_slots[i].link = 'OBJECT'
        floor.material_slots[i].material = material


def _replace_mesh(floor, outline, top, base, index):
    old, slots = floor.data, _slots(floor)
    new = _build_mesh(floor,outline,top,base,index)
    try:
        _set_mesh(floor,new,slots)
    except Exception:
        _set_mesh(floor,old,slots)
        bpy.data.meshes.remove(new)
        raise
    if old.users == 0:
        label = old.name
        bpy.data.meshes.remove(old)
        new.name = label
    return new


def update_floor_outline(context, floor):
    context.view_layer.update()
    from . import floor_regions
    mode = floor.get(KIND)
    if floor.get(floor_regions.ROOT) or floor_regions.HOLES in floor:
        return floor_regions.update_family(context,floor)
    if mode == DIVIDED:
        raise ValueError('This floor was divided. Update is disabled to preserve its divider.')
    if mode == BOUNDS:
        raise ValueError('This is an open-layout bounding-box floor, not a closed wall loop.')
    if mode not in (None,LINKED):
        raise ValueError('This floor has an unsupported layout source.')
    current,top,base,idx = _supported_mesh(floor)
    matrix,inverse,level = floor_plane(floor,top)
    walls = [edge for obj in context.view_layer.objects if (edge:=wall_edge(obj))]
    if mode == LINKED:
        hosts = _read_saved_host(floor,context.scene,current)
    else:
        hosts = _legacy_hosts(floor,current,top,walls)
    poly = _new_outline(hosts,inverse,level)
    plan = floor_regions.plan_regions(hosts,poly,matrix,inverse,level,walls)
    if plan[1]:
        return floor_regions.update_family(context,floor,initial=(hosts,poly,plan))
    warnings = []
    poly = _physical_ring(hosts,poly,matrix,level,context.scene,warnings=warnings)
    from .finishes import refresh_floor_baseboards
    if _same_ring(current,poly):
        _store(floor,hosts,current)
        warnings.extend(refresh_floor_baseboards(context,floor))
        return False,warnings,0
    _replace_mesh(floor,poly,top,base,idx)
    _store(floor,hosts,poly)

    warnings.extend(refresh_floor_baseboards(context,floor))
    return True,warnings,0


class FZM_OT_update_floor_outline(bpy.types.Operator):
    bl_idname='fzm_builder.update_floor_outline'
    bl_label='Update Floor Outline'
    bl_description='Update the active floor to match closed walls and separate any enclosed interior rooms'
    bl_options={'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode=='OBJECT' and selected_floor(context.active_object)

    def execute(self, context):
        floor = context.active_object
        try:
            changed,warnings,created = update_floor_outline(context,floor)
        except (ValueError,RuntimeError,TypeError,KeyError,AttributeError) as error:
            self.report({'WARNING'},str(error))
            return {'CANCELLED'}
        if warnings:
            self.report({'WARNING'},('Floor updated. ' if changed else '')+warnings[0])
        elif created:
            self.report({'INFO'},f'Found {created} enclosed room(s) and created separate floors. Set finishes and room paint separately.')
        elif changed:
            self.report({'INFO'},'Floor outline updated. Refresh Room Paint and Wall Tiles if used.')
        else:
            self.report({'INFO'},'Floor outline already matches its walls. Existing baseboards checked.')
        return {'FINISHED'}
