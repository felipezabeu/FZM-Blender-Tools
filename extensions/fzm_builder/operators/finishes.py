"""Interactive controls for wall paint, doorway casing, and room baseboards."""

from math import isfinite
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import bmesh
import bpy
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector
from mathutils.geometry import intersect_line_line_2d

from .. import hb_assets, hb_types, hb_utils, paint_palettes
from . import baseboard_perimeter, door_units, room_paint, shower_trim, trim_profiles, wall_baseboard


CASING = 'FZM_DOOR_CASING'
BASEBOARD = 'FZM_ROOM_BASEBOARD'
WALL_BASEBOARD = 'FZM_WALL_BASEBOARD'
CUT_TOLERANCE = 0.001
PALETTE_FOLDER = Path('Paletas', 'Benjamin Moore')
EXTENSION_PACKAGE = __package__.rsplit('.', 1)[0]

PROFILE_ITEMS = [
    ('FLAT', 'Flat', 'Straight rectangular profile'),
    ('COLONIAL', 'Colonial', 'Rounded decorative profile'),
    ('STEP_BEVEL', 'Step Bevel', 'Stepped profile with a beveled face'),
]


def selected_walls(context):
    return {wall for obj in context.selected_objects if (wall := hb_utils.get_wall_bp(obj))}


def parse_hex(value):
    value = value.strip().removeprefix('#')
    if not re.fullmatch('[0-9a-fA-F]{6}', value):
        raise ValueError('Enter a six-digit HEX color, such as #E6DED4')
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def paint_material(srgb, swatch=None):
    channels = tuple(round(value * 255) for value in srgb)
    label = '#' + ''.join(f'{value:02X}' for value in channels)
    linear = tuple(value / 12.92 if value <= 0.04045
                   else ((value + 0.055) / 1.055) ** 2.4
                   for value in (channel / 255 for channel in channels))
    color_name = label
    if swatch:
        color_name = ' '.join(filter(None, (swatch.code, swatch.name)))
    mat = bpy.data.materials.new(f'FZM Paint {color_name}')
    if swatch:
        mat['fzm_paint_code'] = swatch.code
        mat['fzm_paint_name'] = swatch.name
        mat['fzm_paint_palette'] = swatch.palette
        mat['fzm_paint_srgb'] = tuple(srgb)
    mat.use_nodes = True
    mat.diffuse_color = (*linear, 1)
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = mat.diffuse_color
    shader.inputs['Roughness'].default_value = 0.65
    return mat


def imported_palettes_path(create=False):
    return Path(bpy.utils.extension_path_user(
        EXTENSION_PACKAGE, path='paint_palettes', create=create,
    ))


def wall_paint_catalog():
    shared = hb_assets.get_all_subfolder_paths(str(PALETTE_FOLDER))
    return paint_palettes.load_catalog([*shared, imported_palettes_path()])


class FZM_OT_import_paint_palette(bpy.types.Operator, ImportHelper):
    bl_idname = 'fzm_builder.import_paint_palette'
    bl_label = 'Import Paint Palette'
    bl_description = 'Import an Adobe Swatch Exchange (.ase) file into this Blender profile'
    filename_ext = '.ase'

    filter_glob: bpy.props.StringProperty(default='*.ase', options={'HIDDEN'})

    def execute(self, context):
        source = Path(self.filepath)
        staged = None
        try:
            if source.suffix.lower() != '.ase':
                raise ValueError('Select an .ase palette')
            data = paint_palettes.read_ase_bytes(source)
            entries = paint_palettes.parse_ase(data, source.stem)
            destination = imported_palettes_path(create=True) / source.name
            with NamedTemporaryFile(dir=destination.parent, delete=False) as file:
                staged = Path(file.name)
                file.write(data)
            staged.replace(destination)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f'Could not import palette: {error}')
            return {'CANCELLED'}
        finally:
            if staged and staged.exists():
                staged.unlink(missing_ok=True)
        self.report({'INFO'}, f'Imported {len(entries)} swatches from {source.name}')
        return {'FINISHED'}


def search_paint_collections(operator, context, edit_text):
    catalog = getattr(operator, 'catalog', None)
    if catalog is None:
        return []
    return [name for name in catalog.collections(operator.paint_code)
            if edit_text.casefold() in name.casefold()]


class FZM_OT_wall_paint(bpy.types.Operator):
    bl_idname = 'fzm_builder.wall_paint'
    bl_label = 'Wall Paint'
    bl_options = {'UNDO'}

    scope: bpy.props.EnumProperty(name='Apply To', items=[
        ('DEFAULT', 'Project Default', 'Update base project and future wall colors without removing room-specific paint'),
        ('ALL', 'All Walls', 'Replace every wall color, clear room-specific paint, and set the project default'),
        ('SELECTED', 'Selected Walls', 'Paint entire selected walls, replacing room-specific paint on those walls'),
        ('RESET', 'Reset Selected', 'Return whole selected walls to the project default'),
        ('ROOM', 'Selected Room Floor', 'Paint only the physical wall faces and portions facing one selected floor'),
        ('RESET_ROOM', 'Reset Room Paint', 'Remove only the room paint associated with one selected floor'),
    ])
    input_mode: bpy.props.EnumProperty(name='Input', items=[
        ('HEX', 'HEX', 'Six-digit sRGB color'),
        ('RGB', 'RGB', 'sRGB color picker'),
        ('PALETTE', 'Palette', 'Look up an imported or shared palette by code or name'),
    ])
    hex_color: bpy.props.StringProperty(name='HEX', default='#E6DED4')
    paint_code: bpy.props.StringProperty(
        name='Code or Name', description='Example: OC-65 or Chantilly Lace',
    )
    paint_collection: bpy.props.StringProperty(
        name='Palette File',
        description='Select the source collection if a code appears in multiple palettes',
        search=search_paint_collections,
    )
    rgb_color: bpy.props.FloatVectorProperty(
        name='RGB', size=3, min=0, max=1, subtype='COLOR_GAMMA',
        default=(0.902, 0.871, 0.831),
    )

    def invoke(self, context, event):
        active = context.active_object
        if (not self.properties.is_property_set('scope') and active and active.get('IS_FLOOR_BP')):
            self.scope = 'ROOM'
        self.catalog = wall_paint_catalog()
        return context.window_manager.invoke_props_dialog(self)

    def check(self, context):
        return self.input_mode == 'PALETTE'

    def draw(self, context):
        self.layout.prop(self, 'scope')
        if self.scope in {'ROOM', 'RESET_ROOM'}:
            self.layout.label(text='Select one floor. Only its room-facing wall spans are affected.')
            if self.scope == 'ROOM':
                self.layout.label(text='Use Material Preview or Rendered to see room colors.')
        if self.scope in {'RESET', 'RESET_ROOM'}:
            return

        self.layout.prop(self, 'input_mode', expand=True)
        if self.input_mode != 'PALETTE':
            self.layout.prop(self, 'hex_color' if self.input_mode == 'HEX' else 'rgb_color')
            return

        self.layout.prop(self, 'paint_code')
        if self.paint_collection or len(self.catalog.collections(self.paint_code)) > 1:
            self.layout.prop(self, 'paint_collection')
        if self.paint_code.strip():
            try:
                swatch = self.find_swatch(self.catalog)
                name = ' '.join(filter(None, (swatch.code, swatch.name)))
                self.layout.label(text=name, icon='COLOR')
            except ValueError as error:
                self.layout.label(text=str(error), icon='INFO')

    def find_swatch(self, catalog):
        if not catalog.names:
            raise ValueError('Import an ASE file or add it to Paletas/Benjamin Moore')
        if not self.paint_code.strip():
            raise ValueError('Enter a paint code or name')
        swatch = catalog.lookup(self.paint_code, self.paint_collection)
        if not swatch:
            message = 'Swatch not found in the loaded palettes'
            if self.paint_collection:
                message = 'Swatch not found in that palette file'
            if catalog.skipped:
                message += f' ({len(catalog.skipped)} unreadable)'
            raise ValueError(message)
        return swatch

    def execute(self, context):
        room_scope = self.scope in {'ROOM', 'RESET_ROOM'}
        if room_scope:
            floors = [obj for obj in context.selected_objects
                      if obj.type == 'MESH' and obj.get('IS_FLOOR_BP')]
            if len(floors) != 1:
                self.report({'WARNING'}, 'Select exactly one room floor')
                return {'CANCELLED'}
            floor = floors[0]
            if self.scope == 'RESET_ROOM':
                try:
                    count = room_paint.apply_room(context, floor)
                except (ValueError, RuntimeError) as error:
                    self.report({'WARNING'}, str(error))
                    return {'CANCELLED'}
                self.report({'INFO'}, f'Reset paint on {count} room-facing wall sides')
                return {'FINISHED'}
        selected_only = self.scope in {'SELECTED', 'RESET'}
        targets = selected_walls(context) if selected_only else [
            obj for obj in context.scene.objects if obj.get('IS_WALL_BP')
        ]
        wall_type = hb_types.GeoNodeWall
        targets = [obj for obj in targets if wall_type.material_inputs(obj)]
        if selected_only and not targets:
            self.report({'WARNING'}, 'Select at least one editable wall')
            return {'CANCELLED'}
        if self.scope == 'RESET' and not context.scene.home_builder.wall_material:
            self.report({'WARNING'}, 'Set a project default wall material first')
            return {'CANCELLED'}

        if self.scope == 'RESET':
            material = context.scene.home_builder.wall_material
        else:
            try:
                swatch = None
                if self.input_mode == 'PALETTE':
                    swatch = self.find_swatch(wall_paint_catalog())
                    color = swatch.rgb
                else:
                    color = parse_hex(self.hex_color) if self.input_mode == 'HEX' else self.rgb_color
            except ValueError as error:
                self.report({'ERROR'}, str(error))
                return {'CANCELLED'}
            material = paint_material(color, swatch)

        if room_scope:
            try:
                count = room_paint.apply_room(context, floor, material)
            except (ValueError, RuntimeError) as error:
                if material.users == 0:
                    bpy.data.materials.remove(material)
                self.report({'WARNING'}, str(error))
                return {'CANCELLED'}
            self.report({'INFO'}, f'Painted {count} room-facing wall sides')
            return {'FINISHED'}
        if self.scope in {'ALL', 'SELECTED', 'RESET'}:
            room_paint.clear_walls(targets)
        if self.scope in {'DEFAULT', 'ALL'}:
            context.scene.home_builder.wall_material = material
        if self.scope != 'DEFAULT':
            for obj in targets:
                if self.scope == 'SELECTED':
                    obj[wall_type.PAINT_OVERRIDE] = True
                elif wall_type.PAINT_OVERRIDE in obj:
                    del obj[wall_type.PAINT_OVERRIDE]
                wall_type.apply_material(obj, material)
        return {'FINISHED'}


def append_loft(vertices, faces, rings):
    """Connect corresponding profile points along a path and cap both ends."""
    start = len(vertices)
    size = len(rings[0])
    for ring in rings:
        vertices.extend(ring)
    faces.append(tuple(reversed(range(start, start + size))))
    for ring in range(len(rings) - 1):
        offset = start + ring * size
        for i in range(size):
            next_i = (i + 1) % size
            faces.append((offset + i, offset + next_i,
                          offset + size + next_i, offset + size + i))
    end = start + (len(rings) - 1) * size
    faces.append(tuple(range(end, end + size)))


def create_mesh(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
    return mesh


def remove_finish(obj):
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def door_from_object(obj):
    while obj and not obj.get('IS_ENTRY_DOOR_BP'):
        obj = obj.parent
    return obj


def casing_vertices(profile, width, height, depth, trim_width, projection):
    vertices, faces = [], []
    for side in (-1, 1):
        outline = [[] for _ in range(4)]
        for across, out in profile:
            offset = across * trim_width
            y = (0 if side < 0 else depth) + side * (out * projection - 0.001)
            for ring, point in zip(outline, [
                (-offset, y, 0), (-offset, y, height + offset),
                (width + offset, y, height + offset), (width + offset, y, 0),
            ]):
                ring.append(point)
        append_loft(vertices, faces, outline)
    return vertices, faces


def _cage_dimensions(door):
    cage = hb_types.GeoNodeCage(door)
    names=('Dim X','Dim Z','Dim Y')
    if not cage.has_modifier() or any(not cage.has_input(name) for name in names):
        raise ValueError(f'{door.name} does not have a supported opening.')
    dims = tuple(cage.get_input(name) for name in names)
    if not all(isfinite(value) and value > 0 for value in dims):
        raise ValueError(f'{door.name} does not have finite, positive opening dimensions.')
    return cage,dims


def make_casing(context, door, profile, width, projection, material):
    cage,dimensions = _cage_dimensions(door)
    cross_section=trim_profiles.CASING_PROFILES[profile]
    vertices, faces = casing_vertices(cross_section, *dimensions, width, projection)
    mesh = create_mesh('Door Casing', vertices, faces)
    casing = bpy.data.objects.new('Door Casing', mesh)
    try:
        (door.users_collection[0] if door.users_collection else context.collection).objects.link(casing)
        casing.parent = door
        casing[CASING] = True
        door_units.protect_part(casing)
        casing['profile'] = profile
        casing['fzm_casing_profile_revision'] = trim_profiles.REVISION if profile != 'FLAT' else 1
        casing['width'] = width
        casing['projection'] = projection
        if material:
            mesh.materials.append(material)

        # Offsets on independent shape keys keep the joins mitered as each
        # individual opening changes, even after applying one profile in bulk.
        casing.shape_key_add(name='Basis')
        for index, (name, size) in enumerate(zip(('Dim X', 'Dim Z', 'Dim Y'), dimensions)):
            changed = list(dimensions)
            changed[index] += 1
            coordinates, _ = casing_vertices(cross_section, *changed, width, projection)
            key = casing.shape_key_add(name=name)
            for point, coordinate in zip(key.data, coordinates):
                point.co = coordinate
            key.slider_min = -10
            key.slider_max = 10
            curve = key.driver_add('value')
            hb_utils.add_driver_variables(curve, [cage.var_input(name, 'dimension')])
            curve.driver.expression = f'dimension - {size!r}'
    except Exception:
        remove_finish(casing)
        raise
    return casing


def casing_targets(context, scope):
    if scope == 'SCENE':
        # No recursive lookups or assumptions about other scenes / the project.
        candidates=(o for o in context.scene.objects if o.get('IS_ENTRY_DOOR_BP'))
    else:
        candidates=context.selected_objects or (context.object,)
    result=set()
    for obj in candidates:
        door=door_from_object(obj)
        if door and door.library is None and door.override_library is None and door.name in context.scene.objects:
            result.add(door)
    return sorted(result,key=lambda o:o.name)


class FZM_OT_door_casing(bpy.types.Operator):
    bl_idname = 'fzm_builder.door_casing'
    bl_label = 'Door Casing'
    bl_description = 'Apply one casing profile to selected Builder doors or all doors in this scene'
    bl_options = {'UNDO'}

    scope: bpy.props.EnumProperty(name='Apply To',items=(
        ('SELECTED','Selected Doors','Apply the same profile to selected openings only'),
        ('SCENE','All Doors in This Scene','Apply to all local Builder openings in this scene, not other room scenes')))
    profile: bpy.props.EnumProperty(name='Profile', items=PROFILE_ITEMS)
    width: bpy.props.FloatProperty(name='Width', default=0.064, min=0.006, unit='LENGTH')
    projection: bpy.props.FloatProperty(name='Thickness', default=0.016, min=0.003, unit='LENGTH')
    remove: bpy.props.BoolProperty(name='Remove Casing')
    material: bpy.props.StringProperty(name='Material')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and bool(casing_targets(context,'SELECTED') or
                                                casing_targets(context,'SCENE'))

    def invoke(self, context, event):
        selected=casing_targets(context,'SELECTED')
        door=door_from_object(context.object)
        if door not in selected:
            door=selected[0] if selected else None
        old = next((child for child in door.children if child.get(CASING)), None) if door else None
        self.remove = False
        self.scope = 'SELECTED'
        self.profile,self.width,self.projection,self.material='FLAT',.064,.016,''
        if old:
            self.profile = old['profile']
            self.width = old['width']
            self.projection = old['projection']
            if old.data.materials:
                self.material = old.data.materials[0].name if old.data.materials[0] else ''
        return context.window_manager.invoke_props_dialog(self,width=385)

    def draw(self, context):
        layout=self.layout
        layout.prop(self,'scope')
        count = len(casing_targets(context,self.scope))
        if count:
            layout.label(text=f'{count} opening(s) in scope')
        else:
            layout.label(text='Select one or more door openings or change scope.',icon='INFO')
        layout.prop(self,'remove')
        if not self.remove:
            for name in ('profile', 'width', 'projection'):
                layout.prop(self, name)
            layout.prop_search(self, 'material', bpy.data, 'materials')

    def execute(self, context):
        doors=casing_targets(context,self.scope)
        if not doors:
            self.report({'WARNING'},'Select one or more local Builder doors.')
            return {'CANCELLED'}
        if not self.remove and not all(isfinite(v) and v > 0. for v in (self.width,self.projection)):
            self.report({'WARNING'},'Use a finite positive casing width and thickness.')
            return {'CANCELLED'}
        previous = [obj for door in doors for obj in door.children if obj.get(CASING)]
        drafts=[]
        try:
            if not self.remove:
                for door in doors:
                    _cage_dimensions(door)
                material=bpy.data.materials.get(self.material)
                for door in doors:
                    drafts.append(make_casing(context,door,self.profile,self.width,self.projection,material))
        except (RuntimeError,ValueError,KeyError) as exc:
            for obj in drafts:
                remove_finish(obj)
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        for obj in previous:
            # User-created children are not part of the managed casing.
            for child in list(obj.children):
                pose=child.matrix_world.copy()
                child.parent=None
                child.matrix_world=pose
            remove_finish(obj)
        refresh_opening_baseboards(context, doors, self.report)
        self.report({'INFO'},f'Casing {"removed" if self.remove else "applied"} on {len(doors)} door opening(s).')
        return {'FINISHED'}


def validate_loop(points):
    pairs = list(zip(points, points[1:] + points[:1]))
    if any((end - start).length < CUT_TOLERANCE for start, end in pairs):
        raise ValueError('The room boundary has a short or collapsed edge')
    for i, (start, end) in enumerate(pairs):
        for j in range(i + 2, len(pairs)):
            if i == 0 and j == len(pairs) - 1:
                continue
            if intersect_line_line_2d(start, end, *pairs[j]) is not None:
                raise ValueError('The room boundary crosses itself')


def room_edges(walls):
    """Resolve one explicitly selected, non-branching perimeter in either direction."""
    points, edges = [], {}
    adjacency = []

    def vertex(point):
        for index, existing in enumerate(points):
            if (point - existing).length < CUT_TOLERANCE:
                return index
        points.append(point)
        adjacency.append([])
        return len(points) - 1

    for obj in sorted(walls, key=lambda obj: obj.name):
        wall = hb_types.GeoNodeWall(obj)
        if not wall.has_input('Length') or not wall.has_input('Thickness'):
            raise ValueError('Every selected wall must be parametric')
        matrix = obj.matrix_world
        start = matrix.translation
        end = matrix @ Vector((wall.get_input('Length'), 0, 0))
        face = matrix @ Vector((0, wall.get_input('Thickness'), 0))
        a, b = vertex(start), vertex(end)
        if a == b or (a, b) in edges or (b, a) in edges:
            raise ValueError('The selected walls contain a duplicate or zero-length edge')
        edges[a, b] = obj, face - start
        adjacency[a].append(b)
        adjacency[b].append(a)
    if len(points) < 3 or any(len(neighbors) != 2 for neighbors in adjacency):
        raise ValueError('Select walls that form one closed, unbranched room')
    level = points[0].z
    if any(abs(point.z - level) > CUT_TOLERANCE for point in points):
        raise ValueError('Select walls on the same level')

    order = [0]
    previous, current = 0, adjacency[0][0]
    while current != 0:
        order.append(current)
        neighbor = next(neighbor for neighbor in adjacency[current] if neighbor != previous)
        previous, current = current, neighbor
    if len(order) != len(points):
        raise ValueError('Select only one closed room')
    polygon = [points[index].to_2d() for index in order]
    validate_loop(polygon)
    area = sum(a.cross(b) for a, b in zip(polygon, polygon[1:] + polygon[:1]))
    if abs(area) < CUT_TOLERANCE ** 2:
        raise ValueError('The selected room has no usable area')
    if area < 0:
        order.reverse()

    result = []
    for a, b in zip(order, order[1:] + order[:1]):
        obj, face = edges.get((a, b)) or edges[b, a]
        start, end = points[a].to_2d(), points[b].to_2d()
        direction = (end - start).normalized()
        inward = Vector((-direction.y, direction.x))
        offset = inward * max(0, face.to_2d().dot(inward))
        result.append((obj, start + offset, end + offset, inward))
    return result, level


def inner_corners(edges, projection):
    corners = []
    for index, (_, start, end, normal) in enumerate(edges):
        _, previous_start, previous_end, previous_normal = edges[index - 1]
        a = previous_end + projection * previous_normal
        b = start + projection * normal
        first, second = previous_end - previous_start, end - start
        turn = first.normalized().cross(second.normalized())
        if abs(turn) < 1e-5:
            if (a - b).length > CUT_TOLERANCE or first.dot(second) <= 0:
                raise ValueError('Adjacent wall faces cannot be joined cleanly')
            corners.append((a + b) / 2)
        else:
            corners.append(a + first * ((b - a).cross(second) / first.cross(second)))
    validate_loop(corners)
    for i, (_, start, end, _) in enumerate(edges):
        if (corners[(i + 1) % len(corners)] - corners[i]).dot(end - start) <= 0:
            raise ValueError('The trim is too thick for this room boundary')
    return corners


def floor_covers_room(context, floor, corners, edges, level):
    depsgraph = context.evaluated_depsgraph_get()
    inverse = floor.matrix_world.inverted()
    direction = inverse.to_3x3() @ Vector((0, 0, -1))
    for index, (_, _, _, inward) in enumerate(edges):
        a, b = corners[index], corners[(index + 1) % len(corners)]
        for fraction in (0.1, 0.5, 0.9):
            point = a.lerp(b, fraction) + 0.004 * inward
            hit, location, *_ = floor.ray_cast(
                inverse @ Vector((*point, level + 0.05)), direction, depsgraph=depsgraph,
            )
            if not hit or abs((floor.matrix_world @ location).z - level) > 0.01:
                return False
    return True


def _casing_interval(casing, depsgraph, origin, direction, inward, level, height):
    """Project evaluated casing edges overlapping the actual trim/wall face.

    Casing may have shape-key drivers, object transforms, or different extents
    on its two faces. Test the side and board height in world space; dimensions
    metadata is neither a geometric bound nor authoritative after editing.
    """
    obj = casing.evaluated_get(depsgraph)
    mesh = obj.data
    if obj.type != 'MESH' or not mesh.edges:
        return None
    coords = []
    for vertex in mesh.vertices:
        point = obj.matrix_world @ vertex.co
        delta = point.to_2d() - origin
        coords.append((delta.dot(direction), delta.dot(inward), point.z))
    minimum, maximum = float('inf'), -float('inf')
    for edge in mesh.edges:
        a, b = (coords[i] for i in edge.vertices)
        lo, hi = 0., 1.
        # Built-in casings recess their backing by 1 mm. Allow that backing
        # and a small tolerance; do not consider the opposite-face casing.
        for av, bv in ((a[1] + 2 * CUT_TOLERANCE, b[1] + 2 * CUT_TOLERANCE),
                       (a[2] - level + CUT_TOLERANCE, b[2] - level + CUT_TOLERANCE),
                       (level + height - a[2], level + height - b[2])):
            if av < 0 and bv < 0:
                lo, hi = 1., 0.
                break
            if av < 0:
                lo = max(lo, -av / (bv - av))
            elif bv < 0:
                hi = min(hi, av / (av - bv))
        if lo <= hi:
            x0, x1 = sorted(a[0] + t * (b[0] - a[0]) for t in (lo, hi))
            minimum, maximum = min(minimum, x0), max(maximum, x1)
    return (minimum, maximum) if minimum < maximum else None


def _wall_doors(wall):
    # The actual cutter also identifies a door after imports/reparenting.
    # Retain child lookup for legacy saved openings, but never windows.
    doors = set(wall.children)
    doors.update(mod.object for mod in wall.modifiers
                 if mod.type == 'BOOLEAN' and mod.operation == 'DIFFERENCE' and mod.object)
    return (door for door in sorted(doors, key=lambda obj: obj.name)
            if door.get('IS_ENTRY_DOOR_BP') and not door.get('IS_WINDOW_BP'))


def wall_spans(obj, origin, end, inward, level, height, depsgraph, tile_panels=(), extra_gaps=()):
    direction = (end - origin).normalized()
    length = (end - origin).length
    gaps = list(extra_gaps)
    gaps.extend(shower_trim.floor_gaps(tile_panels, origin, direction, inward, length, level))
    for door in _wall_doors(obj):
        cage = hb_types.GeoNodeCage(door)
        if not all(cage.has_input(name) for name in ('Dim X', 'Dim Y', 'Dim Z')):
            continue
        width, depth, opening_height = (cage.get_input(name) for name in ('Dim X', 'Dim Y', 'Dim Z'))
        if not all(v is not None and isfinite(v) for v in (width, depth, opening_height)):
            continue
        if abs(width) < CUT_TOLERANCE or abs(opening_height) < CUT_TOLERANCE:
            continue
        matrix = door.evaluated_get(depsgraph).matrix_world
        # Use the opening edges on this face of the wall, not the swing leaf
        # or a global XY bounding box that also spans the other face.
        y = min((0., depth), key=lambda y:
                abs(((matrix @ Vector((0, y, 0))).to_2d() - origin).dot(inward)))
        a = matrix @ Vector((0, y, 0))
        b = matrix @ Vector((width, y, 0))
        bottom = min(a.z, b.z)
        high = (matrix.to_3x3() @ Vector((0, 0, opening_height))).z
        top = max(a.z, b.z) + max(high, 0.)
        bottom += min(high, 0.)
        if bottom >= level + height or top <= level:
            continue
        start, finish = sorted(((a.to_2d() - origin).dot(direction),
                                (b.to_2d() - origin).dot(direction)))
        for casing in door.children:
            if casing.get(CASING):
                bounds = _casing_interval(casing, depsgraph, origin, direction, inward, level, height)
                if bounds:
                    start, finish = min(start, bounds[0]), max(finish, bounds[1])
        start, finish = max(0., start), min(length, finish)
        if finish - start > CUT_TOLERANCE:
            gaps.append((start, finish))
    cursor = 0.0
    for start, end in sorted(gaps):
        if end <= cursor:
            continue
        if start > cursor:
            yield cursor, start
        cursor = end
    if cursor < length:
        yield cursor, length


def baseboard_geometry(context, floor, walls, profile, height, thickness, *, allow_empty=False, revision=trim_profiles.REVISION):
    depsgraph = context.evaluated_depsgraph_get()
    edges, level = room_edges(walls)
    corners = inner_corners(edges, 0)
    if not floor_covers_room(context, floor, corners, edges, level):
        raise ValueError('Select a floor that covers the room at the wall level')
    sections = [
        (up, out, inner_corners(edges, thickness * out))
        for up, out in trim_profiles.baseboard(profile, revision)
    ]
    vertices, faces = [], []
    inverse = floor.matrix_world.inverted()
    tiled = shower_trim.panels_by_wall(context)
    for i, (wall, _, _, normal) in enumerate(edges):
        j = (i + 1) % len(corners)
        start, end = corners[i], corners[j]
        direction = (end - start).normalized()
        length = (end - start).length
        for left, right in wall_spans(wall, start, end, normal, level, height, depsgraph, tiled.get(wall, ())):
            if right - left < CUT_TOLERANCE:
                continue
            rings = [[], []]
            for up, out, rim in sections:
                offset = normal * (thickness * out)
                a = rim[i] if left == 0 else start + direction * left + offset
                b = rim[j] if right == length else start + direction * right + offset
                if (b - a).dot(direction) < CUT_TOLERANCE:
                    break  # Opening consumed this miter; leave other boards intact.
                for ring, point in zip(rings, (a, b)):
                    ring.append(inverse @ Vector((*point, level + up * height)))
            if len(rings[0]) == len(sections):
                append_loft(vertices, faces, rings)
    if not faces and not allow_empty:
        raise ValueError('The selected room has no space for baseboards')
    return vertices, faces


def automatic_baseboard_geometry(context, floor, profile, height, thickness, *, allow_empty=False, revision=trim_profiles.REVISION):
    vertices, faces, walls = [], [], set()
    depsgraph = context.evaluated_depsgraph_get()
    tiled = shower_trim.panels_by_wall(context)

    obstacles_by_level = {}

    def spans(obj, origin, end, inward, level, height):
        if level not in obstacles_by_level:
            obstacles_by_level[level] = tuple(wall_baseboard.obstacles(
                w.obj for w in baseboard_perimeter.physical_walls(context, level)))
        # A T that doesn't close a room still physically interrupts the
        # perimeter trim. Ignore coincident faces and corner contacts.
        probe = inward * (CUT_TOLERANCE * .1)
        gaps = wall_baseboard.intervals(
            (poly for wall, poly in obstacles_by_level[level] if wall != obj),
            origin + probe, end + probe, inset=CUT_TOLERANCE * .15,
        )
        return wall_spans(obj, origin, end, inward, level, height, depsgraph, tiled.get(obj, ()), gaps)

    for _, rings in baseboard_perimeter.board_sections(
        context, floor, trim_profiles.baseboard(profile, revision), height, thickness, spans, walls,
    ):
        append_loft(vertices, faces, rings)
    if not walls:
        raise ValueError('No physical walls match the selected floor perimeter at this level')
    if not faces and not allow_empty:
        raise ValueError('The selected room has no space for baseboards')
    return vertices, faces, walls


def _wall_refs(trim, scene):
    return {wall for wall in trim.get('walls', {}).values()
            if wall and wall.name in scene.objects}


def _save_wall_refs(trim, walls):
    trim['walls'] = {str(i): wall for i, wall in enumerate(sorted(walls, key=lambda wall: wall.name))}


def _replace_baseboard_mesh(trim, mesh):
    old_mesh = trim.data
    trim.data = mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)


def _replace_baseboard_preserving_materials(trim, mesh):
    old_slots = [(slot.link, slot.material) for slot in trim.material_slots]
    for material in trim.data.materials:
        mesh.materials.append(material)
    _replace_baseboard_mesh(trim, mesh)
    for slot, (link, material) in zip(trim.material_slots, old_slots):
        if link == 'OBJECT':
            slot.link = link
            slot.material = material


def _same_baseboard_geometry(before, after, tolerance=1e-5):
    """Avoid replacing an already aligned mesh or its per-face data."""
    return (len(before.vertices)==len(after.vertices)
            and len(before.polygons)==len(after.polygons)
            and all((a.co-b.co).length<=tolerance for a,b in zip(before.vertices,after.vertices))
            and all(tuple(a.vertices)==tuple(b.vertices)
                    for a,b in zip(before.polygons,after.polygons)))


def wall_baseboard_geometry(context, wall, side, returns, profile, height, thickness,
                            *, allow_empty=False, tiled=None, revision=trim_profiles.REVISION):
    depsgraph = context.evaluated_depsgraph_get()
    if tiled is None:
        tiled = shower_trim.panels_by_wall(context).get(wall, ())

    def spans(origin, end, inward, level, board_height, gaps):
        return wall_spans(wall, origin, end, inward, level, board_height,
                          depsgraph, tiled, gaps)

    vertices, faces = [], []
    for rings in wall_baseboard.board_sections(
        context, wall, side, returns, trim_profiles.baseboard(profile, revision), height, thickness, spans,
    ):
        append_loft(vertices, faces, rings)
    if not faces and not allow_empty:
        raise ValueError(f'{wall.name}: no space on that face. Choose the other side or check the tile.')
    return vertices, faces


def wall_trim_children(wall):
    return [child for child in wall.children if child.get(WALL_BASEBOARD)
            and child.type == 'MESH' and not (child.library or child.override_library)]


def refresh_attached_baseboards(context, walls=None):
    targets = list(walls) if walls is not None else list(context.scene.objects)
    attached = [trim for wall in targets if wall.get('IS_WALL_BP') for trim in wall_trim_children(wall)]
    if not attached:
        return []
    context.view_layer.update()
    tiled = shower_trim.panels_by_wall(context)
    failures = []
    for trim in attached:
        wall = trim.parent
        try:
            v, f = wall_baseboard_geometry(
                context, wall, *(trim[key] for key in ('side', 'returns', 'profile', 'height', 'thickness')),
                allow_empty=True, tiled=tiled.get(wall, ()),
                revision=trim.get('fzm_baseboard_profile_revision', 1),
            )
            mesh = create_mesh('Wall Baseboards', v, f)
            if _same_baseboard_geometry(trim.data, mesh):
                bpy.data.meshes.remove(mesh)
            else:
                _replace_baseboard_preserving_materials(trim, mesh)
        except (KeyError, RuntimeError, ValueError) as error:
            failures.append(f'{trim.name}: {error}')
    return failures


def refresh_wall_baseboards(context, walls):
    """Refresh only existing trims attached to a changed Builder wall.

    Called inside the committing operator so the wall finish or door and its trim
    share one undo step. Saved manual trims keep their wall list and profile.
    """
    walls = {wall for wall in walls if wall and wall.get('IS_WALL_BP')}
    if not walls:
        return []
    affected = [(trim, refs) for trim in context.scene.objects
                if trim.get(BASEBOARD) and trim.type == 'MESH' and trim.library is None
                and trim.override_library is None and trim.parent and trim.parent.get('IS_FLOOR_BP')
                and (refs := _wall_refs(trim, context.scene)) & walls]
    return _refresh_existing_baseboards(context, affected) + refresh_attached_baseboards(context, walls)


def refresh_floor_baseboards(context, floor):
    """Update only existing trim on the floor whose outline was refreshed."""
    affected = [(child, _wall_refs(child, context.scene)) for child in floor.children
                if child.get(BASEBOARD) and child.type == 'MESH'
                and not (child.library or child.override_library)]
    return _refresh_existing_baseboards(context, affected)


def _refresh_existing_baseboards(context, affected):
    if not affected:
        return []
    context.view_layer.update()
    failures = []
    for trim, refs in affected:
        try:
            profile, height, thickness = (trim[key] for key in ('profile', 'height', 'thickness'))
            mode = trim.get('wall_source') or ('SELECTED' if refs else 'AUTO')
            revision = trim.get('fzm_baseboard_profile_revision', 1)
            if mode == 'AUTO':
                v, f, refs = automatic_baseboard_geometry(context, trim.parent, profile,
                                                          height, thickness, allow_empty=True, revision=revision)
            else:
                v, f = baseboard_geometry(context, trim.parent, refs, profile,
                                          height, thickness, allow_empty=True, revision=revision)
            mesh = create_mesh('Room Baseboards', v, f)
            if _same_baseboard_geometry(trim.data,mesh):
                bpy.data.meshes.remove(mesh)
            else:
                _replace_baseboard_preserving_materials(trim,mesh)
            if refs!=_wall_refs(trim,context.scene):
                _save_wall_refs(trim,refs)
        except (KeyError, RuntimeError, ValueError) as error:
            failures.append(f'{trim.name}: {error}')
    return failures


def opening_host_walls(context, doors):
    doors = {door for door in doors if door and door.get('IS_ENTRY_DOOR_BP')}
    if not doors:
        return set()
    walls = {hb_utils.get_wall_bp(door.parent) for door in doors if door.parent}
    walls.update(o for o in context.scene.objects if o.get('IS_WALL_BP') and any(
        m.type == 'BOOLEAN' and m.operation == 'DIFFERENCE' and m.object in doors
        for m in o.modifiers
    ))
    return walls


def refresh_opening_baseboards(context, doors, report):
    for failure in refresh_wall_baseboards(context, opening_host_walls(context, doors)):
        report({'WARNING'}, f'Could not refresh baseboards: {failure}')


class FZM_OT_room_baseboards(bpy.types.Operator):
    bl_idname = 'fzm_builder.room_baseboards'
    bl_label = 'Add Baseboards'
    bl_description = 'Add baseboards along a floor or to individual wall faces'
    bl_options = {'UNDO'}

    wall_source: bpy.props.EnumProperty(name='Walls', items=[
        ('AUTO', 'Automatic', 'Find physical walls bordering the selected floor'),
        ('SELECTED', 'Selected Perimeter', 'Use manually selected walls that form a closed room'),
        ('WALL_FACES', 'Selected Walls', 'Trim individual wall faces; no closed room or floor required'),
    ], default='AUTO')

    profile: bpy.props.EnumProperty(name='Profile', items=PROFILE_ITEMS)
    height: bpy.props.FloatProperty(name='Height', default=0.1143, min=0.01, unit='LENGTH')
    thickness: bpy.props.FloatProperty(name='Thickness', default=0.016, min=0.002, unit='LENGTH')
    material: bpy.props.StringProperty(name='Material')
    remove: bpy.props.BoolProperty(name='Remove Baseboards')
    side: bpy.props.EnumProperty(name='Wall Side', items=[
        ('SIDE_1', 'Side 1 (Right)', 'Right when looking along the wall from its drawn start to its end'),
        ('SIDE_2', 'Side 2 (Left)', 'Left when looking along the wall from its drawn start to its end'),
        ('BOTH', 'Both Sides', 'Trim both long faces independently'),
    ])
    returns: bpy.props.BoolProperty(name='Wrap Free Ends', default=True,
        description='Continue the baseboard across the thickness at exposed ends, not into joined walls')

    def invoke(self, context, event):
        floors = [obj for obj in context.selected_objects if obj.get('IS_FLOOR_BP')]
        walls = sorted(selected_walls(context), key=lambda wall: wall.name)
        if not self.properties.is_property_set('wall_source'):
            self.wall_source = 'WALL_FACES' if walls and not floors else 'AUTO'
        old = None
        if self.wall_source == 'WALL_FACES' and len(walls) == 1:
            old = next(iter(wall_trim_children(walls[0])), None)
            if old:
                self.side = old['side']
                self.returns = old['returns']
        elif len(floors) == 1:
            old = next((part for part in floors[0].children if part.get(BASEBOARD)), None)
        if old:
            self.profile = old['profile']
            self.height = old['height']
            self.thickness = old['thickness']
            if old.material_slots:
                self.material = old.material_slots[0].material.name if old.material_slots[0].material else ''
        return context.window_manager.invoke_props_dialog(self, width=390)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'wall_source')
        if self.wall_source == 'AUTO':
            layout.label(text='Select one floor. Only physical wall edges receive trim.')
        elif self.wall_source == 'SELECTED':
            layout.label(text='Select the floor and its closed perimeter walls.')
        else:
            layout.label(text='Select walls only. A closed room is not required.')
        layout.prop(self, 'remove')
        if not self.remove:
            if self.wall_source == 'WALL_FACES':
                layout.prop(self, 'side')
                layout.prop(self, 'returns')
            for name in ('profile', 'height', 'thickness'):
                layout.prop(self, name)
            layout.prop_search(self, 'material', bpy.data, 'materials')

    def execute_wall_faces(self, context, walls):
        if not walls or any(not room_paint.editable_wall(wall) for wall in walls):
            self.report({'WARNING'}, 'Select one or more local Builder walls.')
            return {'CANCELLED'}
        walls = sorted(walls, key=lambda wall: wall.name)
        if self.remove:
            for wall in walls:
                for trim in wall_trim_children(wall):
                    remove_finish(trim)
            return {'FINISHED'}
        context.view_layer.update()
        tiled = shower_trim.panels_by_wall(context)
        try:
            planned = [(wall, wall_baseboard_geometry(
                context, wall, self.side, self.returns, self.profile, self.height,
                self.thickness, allow_empty=True, tiled=tiled.get(wall, ())))
                for wall in walls]
        except (ValueError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        if not any(faces for _, (_, faces) in planned):
            self.report({'WARNING'}, 'No space on the chosen face. Try the other side or check the tile.')
            return {'CANCELLED'}
        material = bpy.data.materials.get(self.material)
        for wall, (vertices, faces) in planned:
            previous = wall_trim_children(wall)
            mesh = create_mesh('Wall Baseboards', vertices, faces)
            if material:
                mesh.materials.append(material)
            if previous:
                trim = previous.pop(0)
                _replace_baseboard_mesh(trim, mesh)
            else:
                trim = bpy.data.objects.new('Wall Baseboards', mesh)
                context.collection.objects.link(trim)
                trim.parent = wall
                trim[WALL_BASEBOARD] = True
            for key in ('side', 'returns', 'profile', 'height', 'thickness'):
                trim[key] = getattr(self, key)
            trim['fzm_baseboard_profile_revision'] = trim_profiles.REVISION
            for obj in previous:
                remove_finish(obj)
        return {'FINISHED'}

    def execute(self, context):
        floors = [obj for obj in context.selected_objects if obj.get('IS_FLOOR_BP')]
        walls = selected_walls(context)
        if self.wall_source == 'WALL_FACES' or (walls and not floors and
                                               not self.properties.is_property_set('wall_source')):
            return self.execute_wall_faces(context, walls)
        if len(floors) != 1 or floors[0].type != 'MESH':
            self.report({'WARNING'}, 'Select exactly one floor')
            return {'CANCELLED'}
        floor = floors[0]
        previous = [obj for obj in floor.children if obj.get(BASEBOARD)]
        if not self.remove:
            walls = selected_walls(context)
            wall_source = self.wall_source
            if walls and not self.properties.is_property_set('wall_source'):
                wall_source = 'SELECTED'  # Preserve older callers passing selected walls.
            try:
                if wall_source == 'AUTO':
                    vertices, faces, walls = automatic_baseboard_geometry(
                        context, floor, self.profile, self.height, self.thickness,
                    )
                else:
                    if not walls and previous:
                        walls = _wall_refs(previous[0], context.scene)
                    vertices, faces = baseboard_geometry(
                        context, floor, walls, self.profile, self.height, self.thickness,
                    )
            except ValueError as error:
                self.report({'WARNING'}, str(error))
                return {'CANCELLED'}
            mesh = create_mesh('Room Baseboards', vertices, faces)
            material = bpy.data.materials.get(self.material)
            if material:
                mesh.materials.append(material)
            trim = previous.pop(0) if previous else None
            if trim:
                _replace_baseboard_mesh(trim, mesh)
            else:
                trim = bpy.data.objects.new('Room Baseboards', mesh)
                context.collection.objects.link(trim)
                trim.parent = floor
                trim[BASEBOARD] = True
            trim['profile'] = self.profile
            trim['fzm_baseboard_profile_revision'] = trim_profiles.REVISION
            trim['height'] = self.height
            trim['thickness'] = self.thickness
            trim['wall_source'] = wall_source
            _save_wall_refs(trim, walls)
        for obj in previous:
            remove_finish(obj)
        return {'FINISHED'}


CLASSES = (
    FZM_OT_import_paint_palette,
    FZM_OT_wall_paint,
    FZM_OT_door_casing,
    FZM_OT_room_baseboards,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
