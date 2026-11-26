"""Editable visualization fixtures attached to verified Shower Area walls."""
from dataclasses import asdict, dataclass
from math import isfinite

import bpy
from mathutils import Vector

from . import shower_area as sh
from .tile_shader import TileSpec, base_material, dispose_if_unused, tile_material
from .wall_boolean import wall_difference

FIXTURE = 'FZM_SHOWER_FIXTURE'
FIXTURE_OPTIONS = 'FZM_SHOWER_FIXTURE_OPTIONS'
VISUAL = 'FZM_SHOWER_FIXTURE_FINISH'
CUTTER = 'FZM_SHOWER_FIXTURE_CUTTER'
AREA = 'fzm_shower_fixture_area'
MARGIN = .015
CLEARANCE = .003
SKIN = .0008
# Vertex order uses positive local u (along shower path), v (into shower), z (up).
BOX = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
       (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5))


@dataclass(frozen=True)
class FixtureSpec:
    kind: str
    offset: float
    bottom: float
    width: float
    height: float
    depth: float
    anchor: str = 'WALL'
    override: bool = False
    color: tuple = (.40, .43, .45, 1.)
    filepath: str = ''
    full_width: bool = False
    niche_style: str = 'TILE'
    orientation: str = 'VERTICAL'


# Published outer-product dimensions only, not measured rough-opening data.
# https://bessofloor.com/products/marble-shower-niche-k (Mayroom K, SKU 10230).
MARBLE_K_OUTER = (.0254 * 13.875, .0254 * 21.875)
MARBLE_K_ESTIMATED_BORDER = .024
MARBLE_K_ESTIMATED_DEPTH = .075


def marble_outer(orientation):
    return MARBLE_K_OUTER if orientation == 'VERTICAL' else MARBLE_K_OUTER[::-1]


@dataclass
class Host:
    wall: object
    area: object
    panel: object
    a: Vector  # tile face start, including miter
    d: Vector  # wall path
    n: Vector  # inward into shower
    level: float
    length: float
    lining_left: float
    lining_right: float
    lining_bottom: float
    lining_top: float
    thickness: float
    adjacent: dict
    lining_planes: list

    def world(self, p):
        x, y, z = p
        xy = self.a + self.d*x + self.n*y
        return Vector((xy.x, xy.y, self.level+z))

    def coords(self, world):
        xy = world.xy-self.a
        return Vector((xy.dot(self.d), xy.dot(self.n), world.z-self.level))


def fixture_from(obj):
    if obj and obj.get(VISUAL):
        obj = obj.parent
    return obj if obj and obj.get(FIXTURE) else None


def fixtures_for_area(context, area):
    return [o for o in context.scene.objects if o.get(FIXTURE) and o.get(AREA) == area]


def _find_host(context, active, *, update=True):
    existing = fixture_from(active)
    if existing:
        area, wall = existing.get(AREA), existing.parent
        if not area or not wall or area.name not in context.scene.objects:
            raise ValueError("The Shower Area host is missing. Remove this fixture.")
    elif active and active.get(sh.PART) and sh.controller_for(active):
        area, wall = active.parent, active.get('fzm_shower_wall')
    elif active and active.get('IS_WALL_BP'):
        wall = active
        area = next((o for o in context.scene.objects if o.get(sh.AREA)
                    and wall in o.get(sh.SOURCE, {}).values()), None)
        if not area:
            raise ValueError("Tile this wall using Shower Area first.")
    else:
        raise ValueError("Select a Shower Area tile face, linked wall, or existing fixture.")
    if update:
        context.view_layer.update()
    walls = sh.FZM_OT_shower_area.targets(context, area)
    if wall not in walls or wall.library or wall.override_library or (existing and existing.library):
        raise ValueError("Use an editable local Builder wall that is part of this Shower Area.")
    # Use rigid, upright wall transforms; scaling can defeat the shell guarantee.
    axes = [col.to_3d() for col in wall.matrix_world.to_3x3().col]
    if (any(abs(v.length-1.) > sh.PLANAR for v in axes)
            or any(abs(axes[i].dot(axes[j])) > sh.PLANAR for i, j in ((0, 1), (0, 2), (1, 2)))):
        raise ValueError("Use an unscaled Builder wall; change wall size with Builder wall dimensions.")
    path, level = sh._ordered_path(walls, walls)
    lines, corners = sh._finish_lines(path)
    i = next(i for i, line in enumerate(lines) if line[0][0] == wall)
    row, _, _, d, n = lines[i]
    panel = next((o for o in area.children if o.get(sh.PART) and o.get('fzm_shower_wall') == wall), None)
    if not panel or not panel.data.materials or not panel.data.materials[0]:
        raise ValueError("Refresh the Shower Area before adding a fixture.")
    length = (corners[i+1]-corners[i]).dot(d)
    lining_left, lining_right = sh.wall_span(lines[i], corners[i], corners[i+1])
    if any(abs(saved-actual) > sh.PLANAR for saved, actual in (
            (panel['fzm_shower_length_m'], length),
            (panel.get(sh.SPAN_START, 0.), lining_left),
            (panel.get(sh.SPAN_END, length), lining_right))):
        raise ValueError("Refresh Shower Area after changing the walls, then edit the fixture.")
    # Thickness must be orthogonal to the wall path on unscaled supported walls.
    thickness = abs(row[3].dot(n))
    if thickness <= (2*MARGIN) or abs(row[3].dot(d)) > sh.PLANAR:
        raise ValueError("This wall is too thin or not perpendicular to its wall thickness.")
    adjacent = {}
    if i and lining_left <= sh.PLANAR:
        adjacent['START'] = lines[i-1][4]
    if i+1 < len(lines) and length-lining_right <= sh.PLANAR:
        adjacent['END'] = lines[i+1][4]
    opt = area[sh.OPTIONS]
    bottom = opt['bottom']
    return Host(wall, area, panel, corners[i], d, n, level, length, lining_left, lining_right,
                bottom, min(bottom+opt['heights'][i], row[4]), thickness, adjacent,
                [(line[1]+line[4]*sh.SEPARATION,line[4]) for j,line in enumerate(lines) if i != j]), existing


def _bounds(host, obj, depsgraph):
    item = obj.evaluated_get(depsgraph)
    local = [host.coords(item.matrix_world @ Vector(v)) for v in item.bound_box]
    return [tuple(fn(v[k] for v in local) for k in range(3)) for fn in (min, max)]


def _bounds_intersect(low, high, other):
    lo, hi = other
    return all(high[k] > lo[k]-CLEARANCE and low[k] < hi[k]+CLEARANCE for k in range(3))


def _validate_geometry(context, host, spec, existing):
    if not all(isfinite(v) for v in (spec.offset, spec.bottom, spec.width, spec.height, spec.depth)):
        raise ValueError("All fixture dimensions must be finite.")
    if min(spec.width, spec.height, spec.depth) < .025 or min(spec.offset, spec.bottom) < 0:
        raise ValueError("Use positive dimensions (minimum 25 mm) and nonnegative offsets.")
    left = spec.offset
    right = left + spec.width
    top = spec.bottom + spec.height
    dep_left, dep_right = left, right
    if spec.kind == 'NICHE':
        if spec.depth > host.thickness - MARGIN:
            raise ValueError(f"Niche must leave at least 15 mm of wall behind it; "
                             f"max depth on this wall is {(host.thickness-MARGIN)*1000:.0f} mm.")
        if (left < host.lining_left+MARGIN or right > host.lining_right-MARGIN or spec.bottom < host.lining_bottom+MARGIN
                or top > host.lining_top-MARGIN):
            raise ValueError("Keep the recess fully inside this tiled wall, at least 15 mm from every edge.")
        outer_x = outer_z = 0.
        if spec.niche_style == 'MARBLE_K':
            outer_w, outer_h = marble_outer(spec.orientation)
            outer_x, outer_z = (outer_w-spec.width)*.5, (outer_h-spec.height)*.5
            if min(outer_x,outer_z)<.005:
                raise ValueError("Estimated cutout must fit within the published prefab outline "
                                 "with at least 5 mm of border on each side.")
            if (left-outer_x < host.lining_left+MARGIN or right+outer_x > host.lining_right-MARGIN
                    or spec.bottom-outer_z < host.lining_bottom+MARGIN or top+outer_z > host.lining_top-MARGIN):
                raise ValueError("The selected prefab outline must fit fully inside the tiled wall.")
        bounds = ((left-outer_x,-spec.depth-sh.SEPARATION,spec.bottom-outer_z),
                  (right+outer_x,.02,top+outer_z))
    elif spec.kind == 'BENCH':
        if top > host.lining_top-MARGIN:
            raise ValueError("Bench seat must fit below the top of the tiled wall.")
        if spec.full_width:
            left, right = host.lining_left, host.lining_right
            dep_left, dep_right = left, right
        elif spec.anchor != 'WALL':
            if spec.anchor not in host.adjacent:
                raise ValueError("There is no adjoining shower wall at that end. Choose another anchor.")
            if spec.anchor == 'START':
                left, right = host.lining_left, host.lining_left+spec.width
            else:
                left, right = host.lining_right-spec.width, host.lining_right
            dep_left, dep_right = left, right
        touched = (host.adjacent if spec.full_width else
                   {spec.anchor:host.adjacent[spec.anchor]} if spec.anchor in host.adjacent else {})
        if any(abs(host.n.dot(adjacent)) > .003 for adjacent in touched.values()):
            raise ValueError("A rectangular corner bench needs a square corner. Try a partial width away from the end.")
        if (min(left, right, dep_left, dep_right) < host.lining_left-sh.PLANAR
                or max(left, right, dep_left, dep_right) > host.lining_right+sh.PLANAR
                or min(right-left, dep_right-dep_left) < .025):
            raise ValueError("Bench does not fit inside the supported corner or wall span.")
        footprint = (host.world((left,0.,0.)).xy, host.world((right,0.,0.)).xy,
                     host.world((dep_left,spec.depth,0.)).xy, host.world((dep_right,spec.depth,0.)).xy)
        if any((point-origin).dot(n) < -sh.PLANAR for origin,n in host.lining_planes for point in footprint):
            raise ValueError("Bench would cross a connected shower wall. Reduce depth or width.")
        bounds = ((min(left,dep_left),-SKIN,spec.bottom), (max(right,dep_right),spec.depth,top))
    else:
        raise ValueError("Unknown Shower Area fixture.")
    depsgraph = context.evaluated_depsgraph_get()
    check_walls = [host.wall]
    if spec.kind == 'BENCH':
        touched = (host.adjacent if spec.full_width else
                   {spec.anchor:host.adjacent[spec.anchor]} if spec.anchor in host.adjacent else {})
        if touched:
            walls = sh.FZM_OT_shower_area.targets(context, host.area)
            path, _ = sh._ordered_path(walls, walls)
            ordered = [row[0] for row, _, _ in path]
            for end in touched:
                check_walls.append(ordered[ordered.index(host.wall) + (-1 if end == 'START' else 1)])
    for wall in check_walls:
        for mod in wall.modifiers:
            if mod.type != 'BOOLEAN' or not mod.show_viewport:
                continue
            if not mod.object:
                if mod.operand_type == 'COLLECTION':
                    raise ValueError("Collection-based cuts are not supported on this fixture's wall.")
                continue
            cutter = mod.object
            if existing and cutter.parent == existing and cutter.get(CUTTER):
                continue
            if _bounds_intersect(*bounds, _bounds(host, cutter, depsgraph)):
                raise ValueError(f"Fixture overlaps or is too close to an existing cut on {wall.name}.")
    for root in fixtures_for_area(context, host.area):
        if root == existing:
            continue
        item = next((o for o in root.children if o.get(VISUAL)), None)
        if item and _bounds_intersect(*bounds, _bounds(host, item, depsgraph)):
            raise ValueError("Fixture overlaps or is too close to another shower fixture.")
    return left, right, dep_left, dep_right, top


def _mesh(context, host, name, verts, faces, root, material=None, override=None, uvs=None,
          accent_face=None, cutter=False, marble=None):
    mesh = bpy.data.meshes.new(name)
    item = None
    try:
        transform = host.wall.matrix_world.inverted()
        # Local frame's handedness depends on whether the shower path is CW.
        if host.d.cross(host.n) < 0:
            faces = [tuple(reversed(face)) for face in faces]
            if uvs:
                uvs = [tuple(reversed(uv)) for uv in uvs]
        mesh.from_pydata([transform @ host.world(p) for p in verts],[],faces)
        mesh.update()
        if material:
            mesh.materials.append(material)
            if marble:
                mesh.materials.append(marble)
                for face in mesh.polygons:
                    face.material_index=1
            if override:
                mesh.materials.append(override)
                mesh.polygons[accent_face].material_index=len(mesh.materials)-1
            layer = mesh.uv_layers.new(name='UVMap')
            for face, face_uv in zip(mesh.polygons, uvs):
                for loop, uv in zip(face.loop_indices, face_uv):
                    layer.data[loop].uv = uv
        item = bpy.data.objects.new(name, mesh)
        collection = host.area.users_collection[0] if host.area.users_collection else context.collection
        collection.objects.link(item)
        item.parent = root
        item[CUTTER if cutter else VISUAL] = True
        item.lock_location = item.lock_rotation = item.lock_scale = (True, True, True)
        if cutter:
            item['IS_CUTTING_OBJ'] = True
            item['IS_WALL_CUTTER'] = True
            item.display_type = 'WIRE'
            item.hide_render = True
            item.hide_select = True
            item.hide_set(True)
        return item
    except Exception:
        if item:
            bpy.data.objects.remove(item, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        raise


def _box(x, X, y, Y, z, Z, lx=None, rx=None):
    lx = x if lx is None else lx
    rx = X if rx is None else rx
    return ((x,y,z),(X,y,z),(rx,Y,z),(lx,Y,z),
            (x,y,Z),(X,y,Z),(rx,Y,Z),(lx,Y,Z))


def _marble_finish():
    """Procedural visual approximation, deliberately not a supplier texture."""
    mat = bpy.data.materials.new('Shower Prefab | White Marble (illustrative)')
    mat['fzm_shower_prefab_material'] = True
    mat.diffuse_color = (.84,.83,.80,1.)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    b = next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    b.inputs['Roughness'].default_value = .34
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    wave = nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'DIAGONAL'
    wave.inputs['Scale'].default_value = 6.2
    wave.inputs['Distortion'].default_value = 13.
    wave.inputs['Detail'].default_value = 4.
    wave.inputs['Detail Scale'].default_value = .72
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (.43,.45,.47,1.)
    ramp.color_ramp.elements[0].position = .025
    ramp.color_ramp.elements[1].color = (.89,.88,.85,1.)
    ramp.color_ramp.elements[1].position = .17
    links.new(uv.outputs['UV'],wave.inputs['Vector'])
    links.new(wave.outputs['Fac'],ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'],b.inputs['Base Color'])
    return mat


def _prefab_ring(verts, faces, spec, shape):
    left, right, _, _, top = shape
    z = spec.bottom
    outer_w,outer_h = marble_outer(spec.orientation)
    x_border,z_border = (outer_w-spec.width)*.5, (outer_h-spec.height)*.5
    # Front trim is set a few millimeters proud of lining and centered on the recess.
    front=.004
    corners=((left+SKIN,z+SKIN),(right-SKIN,z+SKIN),(right-SKIN,top-SKIN),(left+SKIN,top-SKIN),
             (left-x_border,z-z_border),(right+x_border,z-z_border),
             (right+x_border,top+z_border),(left-x_border,top+z_border))
    count=len(verts)
    verts.extend((x, front, z) for x,z in corners)
    for i in range(4):
        j=(i+1)%4
        faces.append(tuple(count+v for v in (j+4,i+4,i,j)))
    # Bridge frontmost inner edge to the recessed interior.
    for i,(u,v) in enumerate(((3,2),(2,6),(6,7),(7,3))):
        j=(i+1)%4
        faces.append((count+j,count+i,u,v))



def _visual(context, host, spec, shape, root):
    left, right, dep_left, dep_right, top = shape
    material = host.panel.data.materials[0]
    phase = host.panel['fzm_shower_phase_m']
    override = None
    override_base = None
    marble = None
    accent_name = 'Niche Back' if spec.kind == 'NICHE' else 'Bench Seat'
    if spec.override:
        previous = next((m for o in root.children if o.get(VISUAL) for m in list(o.data.materials)[1:]
                         if m and not m.get('fzm_shower_prefab_material')), None)
        override_base = sh._base_finish(accent_name, spec.color, spec.filepath, base_material(previous))
    try:
        if override_base:
            override = tile_material(override_base, TileSpec(**dict(host.area[sh.OPTIONS]['tile'])),
                                     one_image_per_tile=bool(spec.filepath))
        if spec.kind == 'NICHE':
            # Open toward positive depth (room); actual wall is cut behind this thin finish.
            verts = _box(left+SKIN, right-SKIN, -spec.depth-sh.SEPARATION+SKIN, 0.,
                         spec.bottom+SKIN, top-SKIN)
            faces = [tuple(reversed(BOX[i])) for i in (0,1,2,4,5)]
            accent = 2
            if spec.niche_style == 'MARBLE_K':
                marble = _marble_finish()
                verts=list(verts)
                _prefab_ring(verts,faces,spec,shape)
        else:
            verts = _box(left, right, -SKIN, spec.depth, spec.bottom, top, dep_left, dep_right)
            faces = BOX
            accent = 1
        def uv(point, index):
            x,y,z = point
            if index in (0,1):
                return phase+x, z-y  # fold across front/sill/seat
            if (spec.kind == 'NICHE' and index in (3,4)) or (spec.kind == 'BENCH' and index in (4,5)):
                return phase+x+y*(1 if index in (3,4) else -1), z
            return phase+x, z
        uvs = [tuple(uv(verts[v], i) for v in face) for i,face in enumerate(faces)]
        item = _mesh(context, host, 'Shower Niche Finish' if spec.kind == 'NICHE' else 'Shower Bench Finish',
                     verts, faces, root, material, override, uvs, accent, marble=marble)
        item['fzm_shower_fixture_tile_phase'] = phase
        return item
    except Exception:
        dispose_if_unused(override)
        if marble and not marble.users:
            bpy.data.materials.remove(marble)
        if override_base and not override_base.users:
            bpy.data.materials.remove(override_base)
        raise


def _check_recess(context, host, spec, shape):
    """Verify actual evaluated blind-depth cut and solid opposite face, not just its box."""
    context.view_layer.update()
    dg = context.evaluated_depsgraph_get()
    wall = host.wall.evaluated_get(dg)
    world_to_local = wall.matrix_world.inverted()
    d = (world_to_local.to_3x3() @ Vector((*host.n, 0.))).normalized()
    left, right, _, _, top = shape
    for u in (.18,.5,.82):
        for v in (.18,.5,.82):
            x = left+(right-left)*u
            z = spec.bottom+(top-spec.bottom)*v
            for start, normal, expected in ((.035,-d,-spec.depth-sh.SEPARATION),
                   (-host.thickness-.035,d,-host.thickness-sh.SEPARATION)):
                hit, local, _, _ = wall.ray_cast(world_to_local@host.world((x,start,z)),normal)
                if not hit or abs(host.coords(wall.matrix_world @ local).y-expected) > .001:
                    raise ValueError("Could not verify a clean blind recess; the wall was left unchanged.")


def _remove_mesh(item):
    data = item.data
    materials = list(data.materials)
    for child in list(item.children):
        pose = child.matrix_world.copy()
        child.parent = None
        child.matrix_world = pose
    bpy.data.objects.remove(item, do_unlink=True)
    if not data.users:
        bpy.data.meshes.remove(data)
    for material in materials:
        source = base_material(material)
        dispose_if_unused(material)
        if material == source and material and material.get('fzm_shower_prefab_material') and not material.users:
            bpy.data.materials.remove(material)
            continue
        if source and source != material and not source.users and source.get('fzm_shower_texture_source') is not None:
            bpy.data.materials.remove(source)


def _managed(root):
    return [o for o in root.children if o.get(CUTTER) or o.get(VISUAL)]


def _modifier(wall, root):
    return next((m for m in wall.modifiers if m.type == 'BOOLEAN' and m.object
                 and m.object.parent == root and m.object.get(CUTTER)), None)


def create_or_update(context, active, spec):
    host, root = _find_host(context, active)
    if root and root[FIXTURE] != spec.kind:
        raise ValueError("Use the button matching the selected Niche or Bench to edit it.")
    shape = _validate_geometry(context,host,spec,root)
    old = _managed(root) if root else []
    mod = _modifier(host.wall,root) if root else None
    previous_cutter = mod.object if mod else None
    existing = root is not None
    if root is None:
        root = bpy.data.objects.new('Shower Niche' if spec.kind == 'NICHE' else 'Shower Bench', None)
        collection = host.area.users_collection[0] if host.area.users_collection else context.collection
        collection.objects.link(root)
        root.parent = host.wall
        root.empty_display_size = .0005
        root.lock_location = root.lock_rotation = root.lock_scale = (True, True, True)
        root[FIXTURE], root[AREA] = spec.kind, host.area
    drafts = []
    try:
        drafts.append(_visual(context, host, spec, shape, root))
        if spec.kind == 'NICHE':
            left, right, _, _, top = shape
            box = _box(left,right,-spec.depth-sh.SEPARATION,
                       .025,spec.bottom,top)
            cutter = _mesh(context,host,'Shower Niche Cutter',box,BOX,root,cutter=True)
            drafts.append(cutter)
            if mod:
                mod.object=cutter
            else:
                mod=wall_difference(host.wall,cutter,'Shower Niche Recess')
            _check_recess(context,host,spec,shape)
            sh.rebuild_panels(context,host.area)
        root[FIXTURE_OPTIONS] = asdict(spec)
    except Exception:
        if mod and spec.kind == 'NICHE':
            if previous_cutter:
                mod.object=previous_cutter
            else:
                host.wall.modifiers.remove(mod)
        for item in drafts:
            _remove_mesh(item)
        if not existing:
            bpy.data.objects.remove(root,do_unlink=True)
        raise
    for item in old:
        _remove_mesh(item)
    return drafts[0]


def remove_fixture(context, root, refresh=True):
    wall, area = root.parent, root.get(AREA)
    mod = _modifier(wall,root) if wall else None
    if mod:
        enabled = mod.show_viewport
        mod.show_viewport=False
        try:
            if refresh and area and area.name in context.scene.objects:
                sh.rebuild_panels(context,area)
        except Exception:
            mod.show_viewport=enabled
            raise
        wall.modifiers.remove(mod)
    for item in _managed(root):
        _remove_mesh(item)
    for child in list(root.children):
        pose = child.matrix_world.copy()
        child.parent=None
        child.matrix_world=pose
    bpy.data.objects.remove(root,do_unlink=True)


def sync_fixture_finish(context, area, panels, spec):
    """Rebase wall finishes/phase and keep separately assigned accent finishes."""
    by_wall = {p['fzm_shower_wall']:p for p in panels}
    changes = []
    try:
        for root in fixtures_for_area(context,area):
            panel = by_wall.get(root.parent)
            if not panel:
                continue
            for item in (o for o in root.children if o.get(VISUAL)):
                options = root[FIXTURE_OPTIONS]
                index = None
                new_accent = None
                if options.get('override'):
                    index = len(item.data.materials)-1
                    source = base_material(item.data.materials[index])
                    if index>0 and source:
                        new_accent = tile_material(source,spec,one_image_per_tile=bool(options.get('filepath')))
                changes.append((item,panel,index,new_accent))
    except Exception:
        for _,_,_,accent in changes:
            dispose_if_unused(accent)
        raise
    for item,panel,index,accent in changes:
        previous = item.data.materials[0]
        item.data.materials[0] = panel.data.materials[0]
        dispose_if_unused(previous)
        if accent:
            previous = item.data.materials[index]
            item.data.materials[index] = accent
            dispose_if_unused(previous)
        phase = panel['fzm_shower_phase_m']
        delta = phase-item.get('fzm_shower_fixture_tile_phase',phase)
        if abs(delta)>sh.EPS:
            for loop in item.data.uv_layers['UVMap'].data:
                loop.uv.x += delta
        item['fzm_shower_fixture_tile_phase'] = phase


class FZM_OT_shower_fixture(bpy.types.Operator):
    bl_idname = 'fzm_builder.shower_fixture'
    bl_label = 'Shower Niche or Bench'
    bl_description = 'Place or edit a visualization fixture on a tiled Shower Area wall'
    bl_options = {'UNDO'}

    kind: bpy.props.EnumProperty(items=(('NICHE','Niche','Recess in a Shower Area wall'),
                                         ('BENCH','Bench','Bench against the wall or in a corner')))
    offset: bpy.props.FloatProperty(name='Distance From Start of Tile Face', unit='LENGTH', default=.35, min=0.,
        description='Distance along the untrimmed wall path, including any hidden section before a divider')
    bottom: bpy.props.FloatProperty(name='Height Above Wall Base', unit='LENGTH', default=1.05, min=0.)
    width: bpy.props.FloatProperty(name='Width', unit='LENGTH', default=.55, min=.025, max=8.)
    height: bpy.props.FloatProperty(name='Height', unit='LENGTH', default=.31, min=.025, max=4.)
    depth: bpy.props.FloatProperty(name='Depth', unit='LENGTH', default=.09, min=.025, max=2.)
    anchor: bpy.props.EnumProperty(name='Bench Placement', items=(
        ('WALL','Along Wall','Set a distance from the tile face start'),
        ('START','Start Corner','Anchor to the adjoining wall at the start (smaller tile phase)'),
        ('END','End Corner','Anchor to the adjoining wall at the end (larger tile phase)')))
    full_width: bpy.props.BoolProperty(name='Use Full Available Wall Width')
    niche_style: bpy.props.EnumProperty(name='Niche Model', items=(
        ('TILE','Custom Tile','Use adjustable rough opening dimensions and wall tile finish'),
        ('MARBLE_K','Marble Prefab | Mayroom K','Visualization based on published outer size for Besso SKU 10230')))
    orientation: bpy.props.EnumProperty(name='Visual Orientation', items=(
        ('VERTICAL','Vertical','Tall visualization'),
        ('HORIZONTAL','Horizontal','Wide visualization (not a supplier installation recommendation)')))
    override: bpy.props.BoolProperty(name='Custom Back / Seat Finish')
    color: bpy.props.FloatVectorProperty(name='Accent Color', size=4, subtype='COLOR',
        default=(.40,.43,.45,1.), min=0., max=1.)
    filepath: bpy.props.StringProperty(name='Accent Tile-Face Photo (optional)', subtype='FILE_PATH')
    remove: bpy.props.BoolProperty(name='Remove This Fixture')

    @classmethod
    def poll(cls,context):
        active = context.active_object
        return context.mode == 'OBJECT' and active is not None and bool(
            fixture_from(active) or active.get(sh.PART) or active.get('IS_WALL_BP'))

    def invoke(self,context,event):
        active = context.active_object
        target = fixture_from(active)
        self.remove = False
        try:
            host, _ = _find_host(context, active)
            if target:
                if target[FIXTURE] != self.kind:
                    raise ValueError("Use the matching Niche or Bench button for this fixture.")
                stored = target[FIXTURE_OPTIONS]
                for key, default in (('niche_style', 'TILE'), ('orientation', 'VERTICAL')):
                    setattr(self,key,stored.get(key,default))
                # Load the saved editable estimated cutout after model and orientation.
                for key, value in stored.items():
                    if key not in ('kind','niche_style','orientation'):
                        setattr(self, key, value)
            elif self.kind == 'NICHE':
                self.niche_style, self.orientation, self.override, self.filepath = 'TILE','VERTICAL',False,''
                self.width = min(.55, host.lining_right-host.lining_left-.05)
                self.offset = (host.lining_left+host.lining_right-self.width)*.5
                self.height = min(.31, host.lining_top-host.lining_bottom-.07)
                self.bottom = max(host.lining_bottom+.02, min(1.05, host.lining_top-self.height-.025))
                self.depth = min(.09, host.thickness-.018)
            else:
                self.override,self.filepath,self.full_width,self.anchor = False,'',False,'WALL'
                self.width = min(.72, host.lining_right-host.lining_left)
                self.offset = (host.lining_left+host.lining_right-self.width)*.5
                self.height, self.depth, self.bottom = .4572,.40,0.
        except ValueError as err:
            if not target or target[FIXTURE] != self.kind or (target.get(AREA) and target.parent):
                self.report({'WARNING'},str(err))
                return {'CANCELLED'}
        self._prefab_key = self.niche_style,self.orientation
        return context.window_manager.invoke_props_dialog(self,width=440)

    def check(self,context):
        key = self.niche_style,self.orientation
        if self.kind == 'NICHE' and key != getattr(self,'_prefab_key',None):
            self._prefab_key = key
            if self.niche_style == 'MARBLE_K':
                w, h = marble_outer(self.orientation)
                border = 2.*MARBLE_K_ESTIMATED_BORDER
                self.width, self.height, self.depth = w-border,h-border,MARBLE_K_ESTIMATED_DEPTH
        return True

    def draw(self,context):
        layout = self.layout
        target = fixture_from(context.active_object)
        if target:
            layout.prop(self,'remove')
        if self.remove:
            return
        try:
            host, _ = _find_host(context,context.active_object,update=False)
            layout.label(text=f'Host Wall: {host.wall.name}')
            if host.lining_left > sh.PLANAR:
                layout.label(text='Offsets include the hidden wall before the divider.', icon='INFO')
        except ValueError as err:
            layout.label(text=str(err),icon='ERROR')
        if self.kind == 'BENCH':
            layout.prop(self,'full_width')
            if not self.full_width:
                layout.prop(self,'anchor')
        else:
            layout.prop(self,'niche_style')
            if self.niche_style == 'MARBLE_K':
                layout.prop(self,'orientation')
                w,h=marble_outer(self.orientation)
                layout.label(text=f"Published outline: {w/.0254:.3f} × {h/.0254:.3f} in")
                layout.label(text='Cutout and depth are estimates. Verify with your supplier.',icon='INFO')
        if self.kind == 'NICHE' or (not self.full_width and self.anchor == 'WALL'):
            layout.prop(self,'offset')
        layout.prop(self,'bottom')
        is_prefab = self.kind == 'NICHE' and self.niche_style == 'MARBLE_K'
        for key in ('width','height','depth'):
            if key == 'width' and self.kind == 'BENCH' and self.full_width:
                continue
            layout.prop(self,key,text=f"Estimated Cutout {key.title()}" if is_prefab else key.title())
        layout.prop(self,'override',text='Custom Niche Back' if self.kind == 'NICHE' else 'Custom Bench Seat')
        if self.override:
            layout.prop(self,'color')
            layout.prop(self,'filepath')
        layout.label(text='Visualization only; not a construction detail.',icon='INFO')

    def execute(self,context):
        try:
            active = context.active_object
            target = fixture_from(active)
            if self.remove:
                if not target or target[FIXTURE] != self.kind:
                    raise ValueError("Select the fixture you want to remove.")
                remove_fixture(context,target)
                return {'FINISHED'}
            values = dict(bottom=self.bottom, width=self.width, height=self.height, depth=self.depth)
            defaults = {}
            if self.kind == 'BENCH':
                defaults = {'bottom':0., 'width':.72, 'height':.4572, 'depth':.40}
            elif self.niche_style == 'MARBLE_K':
                w, h = marble_outer(self.orientation)
                border = 2.*MARBLE_K_ESTIMATED_BORDER
                defaults = {'width':w-border, 'height':h-border, 'depth':MARBLE_K_ESTIMATED_DEPTH}
            for key, value in defaults.items():
                if not self.properties.is_property_set(key):
                    values[key] = value
            item = create_or_update(context,active,FixtureSpec(self.kind,self.offset,**values,
                anchor=self.anchor,override=self.override,color=tuple(self.color),filepath=self.filepath,
                full_width=self.full_width,niche_style=self.niche_style,orientation=self.orientation))
            for obj in context.selected_objects:
                obj.select_set(False)
            item.select_set(True)
            context.view_layer.objects.active = item
        except (ValueError, RuntimeError, OSError, KeyError) as err:
            self.report({'WARNING'},str(err))
            return {'CANCELLED'}
        return {'FINISHED'}
