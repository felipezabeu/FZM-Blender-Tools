"""Split a generated floor at a drawn chord without adding a wall."""
from collections import Counter, defaultdict
from math import isfinite

import bmesh
import bpy
import gpu
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from mathutils.geometry import intersect_line_plane


EPS = 1e-5
SNAP_METRES = .08


def top_rings(mesh):
    """Extract the closed boundary rings of the unmodified floor slab."""
    if not mesh.vertices or not mesh.polygons:
        raise ValueError("The floor has no geometry.")
    top = max(v.co.z for v in mesh.vertices)
    base = min(v.co.z for v in mesh.vertices)
    if top - base <= EPS or any(
        min(abs(v.co.z - top), abs(v.co.z - base)) > EPS for v in mesh.vertices
    ):
        raise ValueError("Use a flat, two-level floor slab.")
    top_faces = [p for p in mesh.polygons if all(
        abs(mesh.vertices[i].co.z - top) <= EPS for i in p.vertices
    )]
    if not top_faces or len({p.material_index for p in mesh.polygons}) > 1:
        raise ValueError("Use a floor slab with a single face material.")
    edge_count = Counter(tuple(sorted(pair)) for p in top_faces for pair in p.edge_keys)
    adj = defaultdict(list)
    for (a, b), count in edge_count.items():
        if count == 1:
            adj[a].append(b)
            adj[b].append(a)
    if not adj or any(len(neighbors) != 2 for neighbors in adj.values()):
        raise ValueError("The floor perimeter is not a simple closed boundary.")
    rings = []
    unseen = set(adj)
    while unseen:
        first = min(unseen)
        ring = [first]
        prev, cur = first, adj[first][0]
        unseen.remove(first)
        while cur != first and cur in unseen:
            ring.append(cur)
            unseen.remove(cur)
            nxt = next(i for i in adj[cur] if i != prev)
            prev, cur = cur, nxt
        if cur != first or len(ring) < 3:
            raise ValueError("The floor perimeter is not a simple closed boundary.")
        rings.append([mesh.vertices[i].co.to_2d() for i in ring])
    rings.sort(key=lambda ring: abs(area([p-ring[0] for p in ring])), reverse=True)
    return rings, top, base, top_faces[0].material_index


def top_outline(mesh):
    rings, top, base, index = top_rings(mesh)
    if len(rings) != 1:
        raise ValueError("This tool requires one floor outline without built-in holes. Floor Cutter modifiers are supported.")
    return rings[0], top, base, index


def cross(a, b):
    return a.x * b.y - a.y * b.x


def area(poly):
    return sum(cross(a, b) for a, b in zip(poly, poly[1:] + poly[:1])) / 2


def snap(poly, point):
    options = []
    for i, a in enumerate(poly):
        edge = poly[(i + 1) % len(poly)] - a
        if edge.length <= EPS:
            continue
        t = min(1., max(0., (point - a).dot(edge) / edge.length_squared))
        if t * edge.length <= EPS:
            t = 0.
        if (1. - t) * edge.length <= EPS:
            t = 1.
        p = a + edge * t
        options.append(((p - point).length, i, t, p))
    return min(options, key=lambda item: item[0])


def inside(poly, p):
    return sum((a.y > p.y) != (b.y > p.y) and
               p.x < a.x + (b.x-a.x)*(p.y-a.y)/(b.y-a.y)
               for a, b in zip(poly, poly[1:] + poly[:1])) % 2


def split_ring(poly, first, second, snap_limit=SNAP_METRES):
    picks = [snap(poly, p) for p in (first, second)]
    if max(item[0] for item in picks) > snap_limit:
        raise ValueError("Both ends must reach the selected floor boundary.")
    a, b = (item[3] for item in picks)
    delta = b - a
    length = delta.length
    if length <= EPS or not inside(poly, (a + b) / 2):
        raise ValueError("Draw the divider through the interior of the floor.")
    unit = delta / length
    for p, q in zip(poly, poly[1:] + poly[:1]):
        dp, dq = cross(unit, p-a), cross(unit, q-a)
        tp, tq = (p-a).dot(unit), (q-a).dot(unit)
        if abs(dp) <= EPS and abs(dq) <= EPS:
            if min(max(tp, tq), length) - max(min(tp, tq), 0.) > EPS:
                raise ValueError("The divider cannot follow an existing edge.")
        elif dp*dq < 0 or min(abs(dp), abs(dq)) <= EPS:
            if abs(dp-dq) <= EPS:
                continue
            t = tp + (tq-tp)*dp/(dp-dq)
            if EPS < t < length-EPS:
                raise ValueError("The divider crosses another edge of this floor.")
    expanded, indices = [], {}
    for i, point in enumerate(poly):
        expanded.append(point)
        for j, (_, edge, t, p) in enumerate(picks):
            if (i == edge and t == 0.) or (i == (edge + 1) % len(poly) and t == 1.):
                indices[j] = len(expanded) - 1
        for j, (_, edge, t, p) in sorted(enumerate(picks), key=lambda item: item[1][2]):
            if i == edge and 0 < t < 1:
                indices[j] = len(expanded)
                expanded.append(p)
    i, j = sorted(indices.values())
    regions = expanded[i:j+1], expanded[j:] + expanded[:i+1]
    if any(len(r) < 3 or abs(area(r)) <= EPS for r in regions):
        raise ValueError("The divider must leave two usable floor regions.")
    return regions


def make_slab(name, poly, top, base, source, material_index):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    try:
        upper = [bm.verts.new((*p, top)) for p in poly]
        lower = [bm.verts.new((*p, base)) for p in poly]
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            bm.faces.new((upper[i], lower[i], lower[j], upper[j]))
        for ring in (upper, lower):
            edges = [bm.edges.get((v, ring[(i+1) % len(ring)])) for i, v in enumerate(ring)]
            filled = bmesh.ops.triangle_fill(bm, edges=edges, use_beauty=True)
            if not any(isinstance(g, bmesh.types.BMFace) for g in filled['geom']):
                raise ValueError("Could not triangulate the floor region.")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        uv = bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            f.material_index = material_index
            for loop in f.loops:
                loop[uv].uv = tuple(loop.vert.co.xy)
        bm.to_mesh(mesh)
        for mat in source.materials:
            mesh.materials.append(mat)
        mesh.update()
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    finally:
        bm.free()


def divide_floor(floor, first, second):
    from .floor_regions import ROOT, HOLES
    if floor.get(ROOT) or HOLES in floor:
        raise ValueError("This floor tracks enclosed rooms. Change the room walls and use Update Floor Outline.")
    if not floor.users_collection:
        raise ValueError("The floor needs to belong to a collection.")
    if floor.data.shape_keys or floor.vertex_groups or any(m.type != 'BOOLEAN' for m in floor.modifiers):
        raise ValueError("Use an original floor slab with no mesh customizations other than Floor Cutters.")
    poly, top, base, mat_idx = top_outline(floor.data)
    regions = split_ring(poly, first, second)
    old_mesh = floor.data
    meshes = []
    new_floor = None
    try:
        for region in regions:
            meshes.append(make_slab(floor.name + " Region", region, top, base, old_mesh, mat_idx))
        new_floor = floor.copy()
        new_floor.name = floor.name + " Region"
        overrides = [(i, slot.material) for i, slot in enumerate(floor.material_slots) if slot.link == 'OBJECT']
        new_floor.data = meshes[1]
        for col in floor.users_collection:
            col.objects.link(new_floor)
        floor.data = meshes[0]
        for obj in (floor, new_floor):
            for i, mat in overrides:
                obj.material_slots[i].link = 'OBJECT'
                obj.material_slots[i].material = mat
    except Exception:
        floor.data = old_mesh
        if new_floor is not None:
            bpy.data.objects.remove(new_floor, do_unlink=True)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        raise
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    from .floor_outline import mark_divided
    mark_divided(floor, new_floor)
    return new_floor


class FZM_OT_floor_divider(bpy.types.Operator):
    bl_idname = "fzm_builder.floor_divider"
    bl_label = "Divide Floor"
    bl_description = "Draw between two edges of the active floor to create separate floor pieces without a wall"
    bl_options = {'UNDO'}

    first: bpy.props.FloatVectorProperty(size=2, subtype='XYZ', options={'HIDDEN'})
    second: bpy.props.FloatVectorProperty(size=2, subtype='XYZ', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH' and bool(obj.get('IS_FLOOR_BP'))

    def execute(self, context):
        if not all(isfinite(v) for v in (*self.first, *self.second)):
            self.report({'WARNING'}, "The divider endpoints must be finite.")
            return {'CANCELLED'}
        try:
            result = divide_floor(context.active_object, Vector(self.first), Vector(self.second))
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        context.active_object.select_set(False)
        result.select_set(True)
        context.view_layer.objects.active = result
        return {'FINISHED'}

    def invoke(self, context, event):
        if not context.area or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not region:
            return {'CANCELLED'}
        self.floor = context.active_object
        try:
            self.outline, self.z, _, _ = top_outline(self.floor.data)
            self.inverse = self.floor.matrix_world.inverted()
        except ValueError as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        self.region = region
        self.area = context.area
        self.rv3d = context.space_data.region_3d
        self.start = self.cursor = None
        self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(self.preview, (), 'WINDOW', 'POST_VIEW')
        self.area.header_text_set("Divide Floor: click a floor edge, then another edge | Esc: cancel")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def preview(self):
        if bpy.context.area != self.area or bpy.context.region != self.region or self.start is None or self.cursor is None:
            return
        coords = [self.floor.matrix_world @ Vector((*p, self.z + .002)) for p in (self.start, self.cursor)]
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        shader.bind()
        shader.uniform_float("color", (0.05, .8, 1., 1.))
        batch_for_shader(shader, 'LINES', {"pos": coords}).draw(shader)

    def cancel(self, context):
        if getattr(self, 'draw_handle', None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle, 'WINDOW')
            self.draw_handle = None
        self.area.header_text_set(None)
        self.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        if event.type not in {'LEFTMOUSE', 'MOUSEMOVE'}:
            return {'RUNNING_MODAL'}
        coords = (event.mouse_x - self.region.x, event.mouse_y - self.region.y)
        if not (0 <= coords[0] < self.region.width and 0 <= coords[1] < self.region.height):
            return {'RUNNING_MODAL'}
        origin = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, coords)
        direction = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, coords)
        p, q = self.inverse @ origin, self.inverse @ (origin + direction)
        hit = intersect_line_plane(p, q, Vector((0, 0, self.z)), Vector((0, 0, 1)))
        if hit is None:
            return {'RUNNING_MODAL'}
        distance, _, _, nearest = snap(self.outline, hit.xy)
        self.cursor = nearest if distance <= SNAP_METRES else hit.xy
        self.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if distance > SNAP_METRES:
                self.report({'WARNING'}, "Click near an edge of the selected floor.")
            elif self.start is None:
                self.start = nearest
            else:
                if context.active_object != self.floor:
                    self.cancel(context)
                    return {'CANCELLED'}
                try:
                    split_ring(self.outline, self.start, nearest)
                except ValueError as error:
                    self.report({'WARNING'}, str(error))
                    return {'RUNNING_MODAL'}
                self.first, self.second = self.start, nearest
                self.cancel(context)
                return self.execute(context)
        return {'RUNNING_MODAL'}
