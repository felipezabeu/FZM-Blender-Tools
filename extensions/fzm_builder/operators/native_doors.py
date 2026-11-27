"""Native FZM door assemblies. The existing cage remains the wall cutter.

A saved geometry-node modifier supplies the visible assembly. Its size sockets
are driven by the cage, so the opening and model stay in sync without handlers.
"""
import math

import bpy

from .. import hb_types
from ..units import inch
from . import shaker_door_profiles as shaker, six_panel_doors
from . import trim_paint


TYPE_KEY = "FZM_NATIVE_DOOR_TYPE"
VISUAL_KEY = "FZM_NATIVE_DOOR_VISUAL"
STYLE = "Leaf Style"
OPEN = "Open Amount"
RIGHT = "Right Hand"
STYLE_FLAT = 'FLAT'
STYLE_SHAKER = 'SHAKER'  # Existing one-panel ID, kept for .blend compatibility.
STYLE_SHAKER_2 = 'SHAKER_2'
STYLE_SHAKER_5 = 'SHAKER_5'
STYLE_MIRROR = 'MIRROR'
STYLE_SIX_PANEL = 'SIX_PANEL'
STYLES = (
    (STYLE_FLAT, "Flat White", "Smooth white door leaf", 0),
    (STYLE_SHAKER, "Shaker 1 Panel", "White framed leaf with one recessed panel", 1),
    (STYLE_SHAKER_2, "Shaker 2 Panel", "White framed leaf with two stacked recessed panels", 4),
    (STYLE_SHAKER_5, "Shaker 5 Panel", "White framed leaf with five stacked recessed panels", 5),
    (STYLE_SIX_PANEL, "White Six Panel", "Two columns of three molded panels; one column per bifold half", 2),
)
BYPASS_STYLES = (*STYLES, (STYLE_MIRROR, "Mirrored", "Mirror front with a slim aluminum frame", 3))
# These are stored as per-modifier float values, not enum order.
# Never renumber the four values first shipped in 5.1.5.
STYLE_VALUES = {STYLE_FLAT: 0, STYLE_SHAKER: 1, STYLE_MIRROR: 2, STYLE_SIX_PANEL: 3,
                STYLE_SHAKER_2: 4, STYLE_SHAKER_5: 5}
NEW_PANEL_STYLES = {STYLE_SHAKER_2, STYLE_SHAKER_5}
GEOMETRY_VERSION = 4
BIFOLD_SHAKER_STYLES = {STYLE_SHAKER, STYLE_SHAKER_2}
DOOR_TYPES = (
    ('BYPASS', "Sliding Closet (Bypass)", "Two leaves on parallel tracks"),
    ('BIFOLD', "Bifold", "Two hinged leaves fold as a pair"),
    ('POCKET', "Pocket", "One leaf slides into the adjacent wall"),
)
NAMES = {key: label for key, label, _ in DOOR_TYPES}
PRESETS = {
    'BYPASS': ((60, 80), (48, 80), (72, 80)),
    'BIFOLD': ((36, 80), (30, 80), (24, 80)),
    'POCKET': ((32, 80), (30, 80), (36, 80)),
}
MIN_WIDTH = {
    'BYPASS': .55,
    'BIFOLD': .45,
    'POCKET': .40,
}
MIN_HEIGHT = .65
EPS = 1e-5

MAT_SPECS = {
    'white': ("White paint", (.82, .81, .78), 0, .33),
    'inset': ("White inset", (.74, .73, .71), 0, .40),
    'mirror': ("Mirror", (.84, .88, .90), 1, .035),
    'metal': ("Satin aluminum", (.56, .58, .61), .82, .31),
    'hardware': ("Satin nickel", (.38, .40, .43), .86, .28),
}


def cage_for(obj):
    from .door_units import cage_for as unit_cage
    return unit_cage(obj)


def visual_for(cage):
    return next((o for o in cage.children if o.get(VISUAL_KEY)), None)


def material(key):
    name, rgb, metal, roughness = MAT_SPECS[key]
    name = "FZM Door | " + name
    mat = bpy.data.materials.get(name)
    if mat is not None and mat.get('fzm_native_door_material') == key:
        return mat
    mat = bpy.data.materials.new(name)
    mat["fzm_native_door_material"] = key
    mat.use_nodes = True
    mat.diffuse_color = (*rgb, 1)
    mat.metallic = metal
    mat.roughness = roughness
    bsdf = next(node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*rgb, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Roughness'].default_value = roughness
    if key == 'mirror':
        # A mirror in a dark scene requires a lit environment to reflect.
        bsdf.inputs['Coat Weight'].default_value = .5
    return mat


class Assembly:
    def __init__(self, group):
        self.group = group
        self.nodes = group.nodes
        self.links = group.links
        self.inputs = self.nodes.new('NodeGroupInput')
        self.output = self.nodes.new('NodeGroupOutput')
        self.cache = {}
        self.materials = {}

    def wire(self, value, dest):
        if isinstance(value, bpy.types.NodeSocket):
            self.links.new(value, dest)
        else:
            dest.default_value = value

    def calc(self, op, a, b=None):
        key = (op, a, b)
        if key not in self.cache:
            node = self.nodes.new('ShaderNodeMath')
            node.operation = op
            self.wire(a, node.inputs[0])
            if b is not None:
                self.wire(b, node.inputs[1])
            self.cache[key] = node.outputs[0]
        return self.cache[key]

    def add(self, a, b):
        return self.calc('ADD', a, b)

    def sub(self, a, b):
        return self.calc('SUBTRACT', a, b)

    def mul(self, a, b):
        return self.calc('MULTIPLY', a, b)

    def vector(self, xyz):
        if all(isinstance(v, (int, float)) for v in xyz):
            return xyz
        node = self.nodes.new('ShaderNodeCombineXYZ')
        for value, socket in zip(xyz, node.inputs):
            self.wire(value, socket)
        return node.outputs[0]

    def join(self, *pieces):
        node = self.nodes.new('GeometryNodeJoinGeometry')
        for part in pieces:
            self.wire(part, node.inputs['Geometry'])
        return node.outputs['Geometry']

    def transform(self, geometry, center=(0, 0, 0), angle=0, scale=(1, 1, 1)):
        node = self.nodes.new('GeometryNodeTransform')
        self.wire(geometry, node.inputs['Geometry'])
        self.wire(self.vector(center), node.inputs['Translation'])
        self.wire(self.vector((0, 0, angle)), node.inputs['Rotation'])
        self.wire(self.vector(scale), node.inputs['Scale'])
        return node.outputs['Geometry']

    def box(self, size, xyz, mat_key):
        cube = self.nodes.new('GeometryNodeMeshCube')
        self.wire(self.vector(size), cube.inputs['Size'])
        skin = self.nodes.new('GeometryNodeSetMaterial')
        self.wire(cube.outputs['Mesh'], skin.inputs['Geometry'])
        if mat_key not in self.materials:
            self.materials[mat_key] = material(mat_key)
        skin.inputs['Material'].default_value = self.materials[mat_key]
        return self.transform(skin.outputs['Geometry'], xyz)

    def select(self, condition, a, b):
        node = self.nodes.new('GeometryNodeSwitch')
        node.input_type = 'GEOMETRY'
        self.wire(condition, node.inputs['Switch'])
        self.wire(a, node.inputs['False'])
        self.wire(b, node.inputs['True'])
        return node.outputs[0]

    def leaf(self, width, height, *, thickness, mirrored_capable=False,
             pull=None, pull_side=-1, six_variant=None, shaker_variant=None,
             shaker_insert_material=None, shaker_insert_thickness=None):
        """Build the leaf centered on its local X/Y/Z for rotation."""
        flat = self.box((width, thickness, height), (0, 0, 0), 'white')
        rail = self.calc('MINIMUM', self.mul(width, .22), .064)
        x = self.mul(self.sub(width, rail), .5)
        z = self.mul(self.sub(height, rail), .5)
        center_width = self.sub(width, self.mul(rail, 2))
        center_height = self.sub(height, self.mul(rail, 2))
        frame_parts = (
            self.box((rail, thickness, height), (self.mul(x, -1), 0, 0), 'white'),
            self.box((rail, thickness, height), (x, 0, 0), 'white'),
            self.box((center_width, thickness, rail), (0, 0, z), 'white'),
            self.box((center_width, thickness, rail), (0, 0, self.mul(z, -1)), 'white'),
        )
        frame = self.join(*frame_parts,
            self.box((center_width, thickness * .55, center_height), (0, 0, 0), 'inset'),
        )

        def stacked_shaker(fractions):
            # Use narrower horizontal rails on narrow bifold leaves and keep
            # both the recess depth and thickness independent of leaf width.
            rail_h = self.calc('MINIMUM', .055, self.mul(width, .20))
            panel_height = self.sub(center_height, self.mul(rail_h, len(fractions) - 1))
            top = self.mul(center_height, .5)
            parts = list(frame_parts)
            for i, fraction in enumerate(fractions):
                panel_h = self.mul(panel_height, fraction)
                parts.append(self.box((center_width, thickness * .55, panel_h),
                    (0, 0, self.sub(top, self.mul(panel_h, .5))), 'inset'))
                top = self.sub(top, panel_h)
                if i < len(fractions) - 1:
                    parts.append(self.box((center_width, thickness, rail_h),
                        (0, 0, self.sub(top, self.mul(rail_h, .5))), 'white'))
                    top = self.sub(top, rail_h)
            return self.join(*parts)

        def carved(profile, insert=None, section=None):
            if insert is None:
                insert = material('inset')
            return shaker.build_leaf(self, width, height, thickness, profile, flat, insert,
                                     insert_thickness=section)

        if shaker_variant == 'BIFOLD':
            frame = carved(shaker.BIFOLD_ONE)
        elif shaker_variant == 'HINGED':
            frame = carved(shaker.HINGED_ONE)

        style = self.inputs.outputs[STYLE]
        leaf = self.select(self.calc('GREATER_THAN', style, .5), flat, frame)
        if six_variant:
            six_panel = six_panel_doors.build_leaf(self,width,height,thickness,six_variant,material('inset'))
        else:
            # Smaller widths retain two genuinely separate columns; mullion width
            # scales down while the door thickness stays constant.
            mullion = self.calc('MINIMUM', .044, self.mul(center_width, .19))
            panel_w = self.mul(self.sub(center_width, mullion), .5)
            panel_x = self.mul(self.add(panel_w, mullion), .5)
            rail_h = .043
            open_h = self.sub(center_height, 2 * rail_h)
            short_h, mid_h, lower_h = (self.mul(open_h, n) for n in (.20, .40, .40))
            top = self.mul(center_height, .5)
            first_rail = self.sub(self.sub(top, short_h), rail_h * .5)
            second_rail = self.sub(self.sub(first_rail, mid_h), rail_h)
            six_parts = [
                self.box((rail, thickness, height), (self.mul(x, -1), 0, 0), 'white'),
                self.box((rail, thickness, height), (x, 0, 0), 'white'),
                self.box((center_width, thickness, rail), (0, 0, z), 'white'),
                self.box((center_width, thickness, rail), (0, 0, self.mul(z, -1)), 'white'),
                self.box((mullion, thickness, center_height), (0, 0, 0), 'white'),
            ]
            panel_rows = (
                (short_h, self.sub(top, self.mul(short_h, .5))),
                (mid_h, self.sub(first_rail, self.add(rail_h * .5, self.mul(mid_h, .5)))),
                (lower_h, self.sub(second_rail, self.add(rail_h * .5, self.mul(lower_h, .5)))),
            )
            for rail_z in (first_rail, second_rail):
                for col in (-1, 1):
                    six_parts.append(self.box((panel_w, thickness, rail_h), (self.mul(panel_x, col), 0, rail_z), 'white'))
            for row_h, row_z in panel_rows:
                for col in (-1, 1):
                    six_parts.append(self.box((panel_w, thickness * .58, row_h), (self.mul(panel_x, col), 0, row_z), 'inset'))
            six_panel = self.join(*six_parts)
        if mirrored_capable:
            m_rail = .022
            m_x = self.mul(self.sub(width, m_rail), .5)
            m_z = self.mul(self.sub(height, m_rail), .5)
            m_w = self.sub(width, m_rail * 2)
            m_h = self.sub(height, m_rail * 2)
            mirror = self.join(
                self.box((m_rail, thickness, height), (self.mul(m_x, -1), 0, 0), 'metal'),
                self.box((m_rail, thickness, height), (m_x, 0, 0), 'metal'),
                self.box((m_w, thickness, m_rail), (0, 0, m_z), 'metal'),
                self.box((m_w, thickness, m_rail), (0, 0, self.mul(m_z, -1)), 'metal'),
                self.box((m_w, thickness * .64, m_h), (0, thickness * .12, 0), 'mirror'),
            )
            leaf = self.select(self.calc('GREATER_THAN', style, 1.5), leaf, mirror)
        leaf = self.select(self.calc('GREATER_THAN', style, 2.5), leaf, six_panel)
        if shaker_variant == 'BIFOLD':
            two = carved(shaker.BIFOLD_TWO)
        elif shaker_variant == 'HINGED':
            two = carved(shaker.HINGED_TWO)
        else:
            two = stacked_shaker((.58, .42))
        five = (carved(shaker.HINGED_FIVE, shaker_insert_material, shaker_insert_thickness)
                if shaker_variant == 'HINGED' else stacked_shaker((.20,) * 5))
        leaf = self.select(self.calc('GREATER_THAN', style, 3.5), leaf, two)
        leaf = self.select(self.calc('GREATER_THAN', style, 4.5), leaf, five)
        return self.add_pull(leaf, width, height, thickness, pull, pull_side) if pull else leaf

    def add_pull(self, leaf, width, height, thickness, pull, side):
        px = self.mul(self.sub(width, .11), .5 * side)
        pull_depth = .006 if pull == 'flush' else .02
        pull_h = .10 if pull == 'flush' else .065
        # Keep pulls below center without crossing the bottom of short leaves.
        pull_z = self.mul(height, -.06)
        return self.join(leaf, self.box((.024, pull_depth, pull_h),
            (px, thickness / 2 + pull_depth / 2, pull_z), 'hardware'))


def build_group(kind, version=None):
    if version is None:
        version = GEOMETRY_VERSION if kind == 'BIFOLD' else 3
    group_name = f"FZM Native Door v{version} | " + kind
    group = bpy.data.node_groups.get(group_name)
    if (group is not None and group.get('fzm_native_door_group') == kind
            and group.get('fzm_native_door_geometry_version') == version):
        return group
    group = bpy.data.node_groups.new(group_name, "GeometryNodeTree")
    group["fzm_native_door_group"] = kind
    group["fzm_native_door_geometry_version"] = version
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry').hide_in_modifier = True
    defaults = {
        'Width': (1., .15, 6.),
        'Depth': (.1143, .015, 2.),
        'Height': (2.032, .3, 5.),
        STYLE: (0., 0., 5.),
        OPEN: (0., 0., 1.),
        RIGHT: (0., 0., 1.),
    }
    for label, (default, min_value, max_value) in defaults.items():
        socket = group.interface.new_socket(name=label, in_out='INPUT', socket_type='NodeSocketFloat')
        socket.default_value = default
        socket.min_value = min_value
        socket.max_value = max_value
        socket.hide_in_modifier = True
    a = Assembly(group)
    w, d, h = (a.inputs.outputs[name] for name in ('Width', 'Depth', 'Height'))
    center_w = a.mul(w, .5)
    center_d = a.mul(d, .5)
    open_amt = a.inputs.outputs[OPEN]
    # All visible members stay within the rough height. A clearance separates
    # the bottom of the leaves from the finished opening.
    leaf_height = a.sub(h, .056)
    center_z = a.add(.014, a.mul(leaf_height, .5))
    track_z = a.sub(h, .016)

    if kind == 'BYPASS':
        leaf_w = a.add(a.mul(w, .5), .017)
        half = a.mul(leaf_w, .5)
        left = a.add(.007, half)
        right = a.sub(a.sub(w, .007), half)
        travel = a.sub(right, left)
        # Two rails remain parallel, even when the fronts overlap completely.
        rear, front = a.sub(center_d, .028), a.add(center_d, .028)
        rear_leaf = a.leaf(leaf_w, leaf_height, thickness=.024, mirrored_capable=True,
                           pull='flush', pull_side=-1,six_variant='FULL' if version>=3 else None)
        front_leaf = a.leaf(leaf_w, leaf_height, thickness=.024, mirrored_capable=True,
                            pull='flush', pull_side=1,six_variant='FULL' if version>=3 else None)
        g = a.join(
            a.transform(rear_leaf, (left, rear, center_z)),
            a.transform(front_leaf, (a.sub(right, a.mul(travel, open_amt)), front, center_z)),
            a.box((w, .017, .030), (center_w, rear, track_z), 'metal'),
            a.box((w, .017, .030), (center_w, front, track_z), 'metal'),
            a.box((w, .016, .008), (center_w, rear, .004), 'metal'),
            a.box((w, .016, .008), (center_w, front, .004), 'metal'),
        )
    elif kind == 'BIFOLD':
        leaf_w = a.mul(a.sub(w, .022), .5)
        pivot = .009
        angle = a.mul(open_amt, math.radians(77))
        cos_a, sin_a = a.calc('COSINE', angle), a.calc('SINE', angle)
        px, py = a.mul(leaf_w, cos_a), a.mul(leaf_w, sin_a)
        # Two fold-linked centers: each remains half a leaf from the hinge;
        # the wandering end slides along the upper track, not through it.
        hinge_x = a.add(pivot, a.add(px, .004))
        hinge_y = a.add(center_d, py)
        half_px, half_py = a.mul(px, .5), a.mul(py, .5)
        variant = 'BIFOLD' if version >= 4 else None
        leaf_a = a.leaf(leaf_w, leaf_height, thickness=.031, shaker_variant=variant,
                       six_variant='HALF_LEFT' if version >= 3 else None)
        leaf_b = a.leaf(leaf_w, leaf_height, thickness=.031, pull='normal', pull_side=-1,
                        shaker_variant=variant, six_variant='HALF_RIGHT' if version >= 3 else None)
        g = a.join(
            a.transform(leaf_a, (a.add(pivot, half_px), a.add(center_d, half_py), center_z), angle),
            a.transform(leaf_b, (a.add(hinge_x, half_px), a.sub(hinge_y, half_py), center_z), a.mul(angle, -1)),
            a.box((.018, .012, .05), (hinge_x, hinge_y, .55), 'hardware'),
            a.box((.018, .012, .05), (hinge_x, hinge_y, a.sub(h, .43)), 'hardware'),
            a.box((w, .035, .030), (center_w, center_d, track_z), 'metal'),
        )
    else:
        leaf_w = a.sub(w, .018)
        travel = a.sub(leaf_w, .065)
        x = a.sub(center_w, a.mul(travel, open_amt))
        leaf = a.leaf(leaf_w, leaf_height, thickness=.035, pull='flush', pull_side=1,six_variant='FULL' if version>=3 else None)
        g = a.join(
            a.transform(leaf, (x, center_d, center_z)),
            a.box((a.sub(a.mul(w, 2), .018), .030, .030), (.009, center_d, track_z), 'metal'),
            a.box((.011, .054, a.sub(h, .03)), (a.sub(w, .0055), center_d, a.mul(a.sub(h, .03), .5)), 'white'),
            a.box((.014, .051, .014), (.009, center_d, .007), 'hardware'),
        )
    if kind != 'BYPASS':
        mirror = a.transform(g, (w, 0, 0), scale=(-1, 1, 1))
        g = a.select(a.calc('GREATER_THAN', a.inputs.outputs[RIGHT], .5), g, mirror)
    a.wire(g, a.output.inputs["Geometry"])
    group.is_modifier = True
    return group


def create_visual(cage, kind, style, opening, right):
    group = build_group(kind)
    obj = bpy.data.objects.new(NAMES[kind] + " - Door Assembly", bpy.data.meshes.new("FZM door input"))
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = cage.obj
    obj[VISUAL_KEY] = True
    obj['MENU_ID'] = "HOME_BUILDER_MT_door_commands"
    mod = obj.modifiers.new("FZM Door Assembly", 'NODES')
    mod.node_group = group
    obj.home_builder.mod_name = mod.name
    visual = hb_types.GeoNodeObject(obj)
    for name, cage_input in (('Width', 'Dim X'), ('Depth', 'Dim Y'), ('Height', 'Dim Z')):
        visual.driver_input(name, 'size', [cage.var_input(cage_input, 'size')])
    cage.obj[TYPE_KEY] = kind
    set_options(obj, style, opening, right)
    return obj


def get_options(obj):
    visual = hb_types.GeoNodeObject(obj)
    style_id = int(round(visual.get_input(STYLE)))
    style = next((key for key, n in STYLE_VALUES.items() if n == style_id), STYLE_FLAT)
    return style, visual.get_input(OPEN), bool(visual.get_input(RIGHT))


def set_options(obj, style, opening, right):
    # Old saved node groups stay attached until that door is deliberately edited.
    # Viewport pose toggles never rebuild appearance.
    kind = obj.parent[TYPE_KEY]
    minimum = (4 if kind == 'BIFOLD' and style in BIFOLD_SHAKER_STYLES else
               3 if style == STYLE_SIX_PANEL else 2 if style in NEW_PANEL_STYLES else 1)
    mod = obj.modifiers[obj.home_builder.mod_name]
    old = mod.node_group
    if old.get('fzm_native_door_geometry_version', 1) < minimum:
        new = build_group(kind, minimum)
        for name in ('Width', 'Depth', 'Height', STYLE, OPEN, RIGHT):
            socket = old.interface.items_tree.get(name)
            if not socket or socket.identifier != new.interface.items_tree[name].identifier:
                raise ValueError("Cannot update this door's size driver sockets.")
        mod.node_group = new
    # Modifier sockets, not group defaults: two doors can share the group and
    # still have independently edited styles and poses.
    visual = hb_types.GeoNodeObject(obj)
    visual.set_input(STYLE, float(STYLE_VALUES[style]))
    visual.set_input(OPEN, min(1., max(0., opening)))
    visual.set_input(RIGHT, 1. if right else 0.)
    trim_paint.sync(obj)
    obj.update_tag()


def default_size(kind, number=0):
    width, height = PRESETS[kind][number]
    return inch(width), inch(height)


def size_error(cage, kind, right, width, height, offset=None):
    if not (math.isfinite(width) and math.isfinite(height)):
        return "Door dimensions must be finite."
    if width < MIN_WIDTH[kind] - EPS or height < MIN_HEIGHT - EPS:
        return "This opening is too small for the chosen door assembly."
    wall = cage.parent
    if wall is None or not wall.get('IS_WALL_BP'):
        return "Place the door on a parametric wall."
    params = hb_types.GeoNodeWall(wall)
    if not params.has_modifier():
        return "Place the door on a parametric wall."
    length = params.get_input('Length')
    wall_height = params.get_input('Height')
    x = cage.location.x if offset is None else offset
    if x < -EPS or x + width > length + EPS or cage.location.z + height > wall_height + EPS:
        return "The opening exceeds the selected wall."
    left, end = x, x + width
    if kind == 'POCKET':
        # Nominal visual envelope, not a manufacturer frame requirement.
        if abs(params.get_input('Thickness')) < .082:
            return "The wall is too thin for this visual pocket assembly."
        if right:
            end += width - .018
        else:
            left -= width - .018
        if left < -EPS or end > length + EPS:
            return "Leave one door width of clear wall on the pocket side."
    for obj in wall.children:
        if obj == cage or not (obj.get('IS_ENTRY_DOOR_BP') or obj.get('IS_WINDOW_BP')):
            continue
        other = hb_types.GeoNodeCage(obj)
        if not other.has_modifier():
            continue
        ow = other.get_input('Dim X')
        oleft, oend = obj.location.x, obj.location.x + ow
        if obj.get(TYPE_KEY) == 'POCKET' and (part := visual_for(obj)):
            _, _, other_right = get_options(part)
            if other_right:
                oend += ow - .018
            else:
                oleft -= ow - .018
        # A high window may coexist above the assembly, not across its track.
        z1, z2 = cage.location.z, cage.location.z + height
        oz1, oz2 = obj.location.z, obj.location.z + other.get_input('Dim Z')
        x_overlap = min(end, oend) - max(left, oleft)
        z_overlap = min(z2, oz2) - max(z1, oz1)
        if x_overlap > EPS and z_overlap > EPS:
            return "This door or its pocket overlaps another opening."
    return None
