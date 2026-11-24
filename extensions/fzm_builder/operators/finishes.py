"""Interactive controls for wall paint, doorway casing, and room baseboards."""

from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import bmesh
import bpy
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector
from mathutils.geometry import intersect_line_line_2d

from .. import hb_assets, hb_types, hb_utils, paint_palettes


CASING = 'FZM_DOOR_CASING'
BASEBOARD = 'FZM_ROOM_BASEBOARD'
CUT_TOLERANCE = 0.001
PALETTE_FOLDER = Path('Paletas', 'Benjamin Moore')
EXTENSION_PACKAGE = __package__.rsplit('.', 1)[0]

PROFILES = {
    # Coordinates are fractions of profile width and projection from the wall.
    'FLAT': ((0, 0), (1, 0), (1, 1), (0, 1)),
    'COLONIAL': ((0, 0), (1, 0), (1, 0.35), (0.86, 0.35), (0.75, 0.48),
                 (0.66, 0.7), (0.55, 0.88), (0.42, 1), (0.2, 1), (0, 0.68)),
    'STEP_BEVEL': ((0, 0), (1, 0), (1, 0.35), (0.78, 0.35), (0.78, 0.55),
                   (0.6, 0.55), (0.42, 1), (0, 1)),
}
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
        ('DEFAULT', 'Project Default', 'Update unpainted walls and future walls'),
        ('ALL', 'All Walls', 'Replace every wall color and set the project default'),
        ('SELECTED', 'Selected Walls', 'Paint selected walls individually'),
        ('RESET', 'Reset Selected', 'Return selected walls to the project default'),
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
        self.catalog = wall_paint_catalog()
        return context.window_manager.invoke_props_dialog(self)

    def check(self, context):
        return self.input_mode == 'PALETTE'

    def draw(self, context):
        self.layout.prop(self, 'scope')
        if self.scope == 'RESET':
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


def make_casing(context, door, profile, width, projection, material):
    cage = hb_types.GeoNodeCage(door)
    dimensions = [cage.get_input(name) for name in ('Dim X', 'Dim Z', 'Dim Y')]
    vertices, faces = casing_vertices(PROFILES[profile], *dimensions, width, projection)
    mesh = create_mesh('Door Casing', vertices, faces)
    casing = bpy.data.objects.new('Door Casing', mesh)
    context.collection.objects.link(casing)
    casing.parent = door
    casing.hide_select = True
    casing[CASING] = True
    casing['profile'] = profile
    casing['width'] = width
    casing['projection'] = projection
    if material:
        mesh.materials.append(material)

    # Offsets on independent shape keys keep the joins mitered as the opening changes.
    casing.shape_key_add(name='Basis')
    for index, (name, size) in enumerate(zip(('Dim X', 'Dim Z', 'Dim Y'), dimensions)):
        changed = dimensions.copy()
        changed[index] += 1
        coordinates, _ = casing_vertices(PROFILES[profile], *changed, width, projection)
        key = casing.shape_key_add(name=name)
        for point, coordinate in zip(key.data, coordinates):
            point.co = coordinate
        key.slider_min = -10
        key.slider_max = 10
        curve = key.driver_add('value')
        hb_utils.add_driver_variables(curve, [cage.var_input(name, 'dimension')])
        curve.driver.expression = f'dimension - {size!r}'
    return casing


class FZM_OT_door_casing(bpy.types.Operator):
    bl_idname = 'fzm_builder.door_casing'
    bl_label = 'Door Casing'
    bl_options = {'UNDO'}

    profile: bpy.props.EnumProperty(name='Profile', items=PROFILE_ITEMS)
    width: bpy.props.FloatProperty(name='Width', default=0.064, min=0.006, unit='LENGTH')
    projection: bpy.props.FloatProperty(name='Thickness', default=0.016, min=0.003, unit='LENGTH')
    remove: bpy.props.BoolProperty(name='Remove Casing')
    material: bpy.props.StringProperty(name='Material')

    @classmethod
    def poll(cls, context):
        door = door_from_object(context.object)
        return bool(door and hb_types.GeoNodeCage(door).has_modifier())

    def invoke(self, context, event):
        door = door_from_object(context.object)
        old = next((child for child in door.children if child.get(CASING)), None)
        if old:
            self.profile = old['profile']
            self.width = old['width']
            self.projection = old['projection']
            if old.data.materials:
                self.material = old.data.materials[0].name if old.data.materials[0] else ''
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, 'remove')
        if not self.remove:
            for name in ('profile', 'width', 'projection'):
                self.layout.prop(self, name)
            self.layout.prop_search(self, 'material', bpy.data, 'materials')

    def execute(self, context):
        door = door_from_object(context.object)
        previous = [obj for obj in door.children if obj.get(CASING)]
        if not self.remove:
            make_casing(context, door, self.profile, self.width, self.projection,
                        bpy.data.materials.get(self.material))
        for obj in previous:
            remove_finish(obj)
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


def wall_spans(obj, origin, end, level, height):
    direction = (end - origin).normalized()
    length = (end - origin).length
    gaps = []
    for child in obj.children:
        if not child.get('IS_ENTRY_DOOR_BP'):
            continue
        cage = hb_types.GeoNodeCage(child)
        z = child.matrix_world.translation.z
        if not cage.has_input('Dim X') or z > level + height or z + cage.get_input('Dim Z') <= level:
            continue
        start = child.matrix_world.translation.to_2d()
        finish = (child.matrix_world @ Vector((cage.get_input('Dim X'), 0, 0))).to_2d()
        start, finish = sorted(((start - origin).dot(direction), (finish - origin).dot(direction)))
        casing = next((part for part in child.children if part.get(CASING)), None)
        clear = casing['width'] if casing else 0
        gaps.append((max(0, start - clear), min(length, finish + clear)))
    cursor = 0.0
    for start, end in sorted(gaps):
        if end <= cursor:
            continue
        if start > cursor:
            yield cursor, start
        cursor = end
    if cursor < length:
        yield cursor, length


def baseboard_geometry(context, floor, walls, profile, height, thickness):
    edges, level = room_edges(walls)
    corners = inner_corners(edges, 0)
    if not floor_covers_room(context, floor, corners, edges, level):
        raise ValueError('Select a floor that covers the room at the wall level')
    sections = [
        (up, out, inner_corners(edges, thickness * out))
        for up, out in PROFILES[profile]
    ]
    vertices, faces = [], []
    inverse = floor.matrix_world.inverted()
    for i, (wall, _, _, normal) in enumerate(edges):
        j = (i + 1) % len(corners)
        start, end = corners[i], corners[j]
        direction = (end - start).normalized()
        length = (end - start).length
        for left, right in wall_spans(wall, start, end, level, height):
            if right - left < CUT_TOLERANCE:
                continue
            rings = [[], []]
            for up, out, rim in sections:
                offset = normal * (thickness * out)
                a = rim[i] if left == 0 else start + direction * left + offset
                b = rim[j] if right == length else start + direction * right + offset
                if (b - a).dot(direction) < CUT_TOLERANCE:
                    raise ValueError('A doorway leaves too little space for a mitered baseboard')
                for ring, point in zip(rings, (a, b)):
                    ring.append(inverse @ Vector((*point, level + up * height)))
            append_loft(vertices, faces, rings)
    if not faces:
        raise ValueError('The selected room has no space for baseboards')
    return vertices, faces


class FZM_OT_room_baseboards(bpy.types.Operator):
    bl_idname = 'fzm_builder.room_baseboards'
    bl_label = 'Room Baseboards'
    bl_options = {'UNDO'}

    profile: bpy.props.EnumProperty(name='Profile', items=PROFILE_ITEMS)
    height: bpy.props.FloatProperty(name='Height', default=0.1143, min=0.01, unit='LENGTH')
    thickness: bpy.props.FloatProperty(name='Thickness', default=0.016, min=0.002, unit='LENGTH')
    material: bpy.props.StringProperty(name='Material')
    remove: bpy.props.BoolProperty(name='Remove Baseboards')

    def invoke(self, context, event):
        floors = [obj for obj in context.selected_objects if obj.get('IS_FLOOR_BP')]
        if len(floors) == 1:
            old = next((part for part in floors[0].children if part.get(BASEBOARD)), None)
            if old:
                self.profile = old['profile']
                self.height = old['height']
                self.thickness = old['thickness']
                if old.data.materials:
                    self.material = old.data.materials[0].name if old.data.materials[0] else ''
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, 'remove')
        if not self.remove:
            self.layout.label(text='Select the room floor and perimeter walls.')
            for name in ('profile', 'height', 'thickness'):
                self.layout.prop(self, name)
            self.layout.prop_search(self, 'material', bpy.data, 'materials')

    def execute(self, context):
        floors = [obj for obj in context.selected_objects if obj.get('IS_FLOOR_BP')]
        if len(floors) != 1 or floors[0].type != 'MESH':
            self.report({'WARNING'}, 'Select exactly one floor')
            return {'CANCELLED'}
        floor = floors[0]
        previous = [obj for obj in floor.children if obj.get(BASEBOARD)]
        if not self.remove:
            walls = selected_walls(context)
            if not walls and previous:
                walls = {wall for wall in previous[0].get('walls', {}).values()
                         if wall and wall.name in context.scene.objects}
            try:
                vertices, faces = baseboard_geometry(
                    context, floor, walls,
                    self.profile, self.height, self.thickness,
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
                old_mesh = trim.data
                trim.data = mesh
                if old_mesh.users == 0:
                    bpy.data.meshes.remove(old_mesh)
            else:
                trim = bpy.data.objects.new('Room Baseboards', mesh)
                context.collection.objects.link(trim)
                trim.parent = floor
                trim[BASEBOARD] = True
            trim['profile'] = self.profile
            trim['height'] = self.height
            trim['thickness'] = self.thickness
            trim['walls'] = {str(i): wall for i, wall in enumerate(sorted(walls, key=lambda wall: wall.name))}
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
