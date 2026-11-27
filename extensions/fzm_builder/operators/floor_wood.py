"""Metric wood-board layouts in a surface shader (no generated floor meshes)."""

from math import pi, remainder, tau

import bpy

BOARD_WIDTH = .1524
BOARD_LENGTH = 1.2192
BOARD_DIMENSIONS = 'fzm_floor_wood_board_m'
BOARD_ANGLE = 'fzm_floor_wood_angle'
BOARD_HERRINGBONE = 'fzm_floor_wood_herringbone'
WOOD_GROUP = 'fzm_metric_wood_board_group'
WOOD_GROUP_VERSION = 1
HERRINGBONE_GROUP_VERSION = 2


def _layout_group(herringbone=False):
    version = HERRINGBONE_GROUP_VERSION if herringbone else WOOD_GROUP_VERSION
    for group in bpy.data.node_groups:
        if group.bl_idname == 'ShaderNodeTree' and group.get(WOOD_GROUP) == version:
            return group
    name = 'FZM Metric Herringbone v2' if herringbone else 'FZM Metric Wood Boards v1'
    g = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    g[WOOD_GROUP] = version
    for name, kind, direction in (
        ('Metric UV', 'NodeSocketVector', 'INPUT'),
        ('Board Width', 'NodeSocketFloat', 'INPUT'),
        ('Board Length', 'NodeSocketFloat', 'INPUT'),
        ('Board Joints', 'NodeSocketFloat', 'INPUT'),
        ('Grain UV', 'NodeSocketVector', 'OUTPUT'),
        ('Board Tone', 'NodeSocketFloat', 'OUTPUT'),
        ('Seam', 'NodeSocketFloat', 'OUTPUT'),
        ('Bevel', 'NodeSocketFloat', 'OUTPUT'),
    ):
        g.interface.new_socket(name=name, in_out=direction, socket_type=kind)
    n, l = g.nodes, g.links
    src = n.new('NodeGroupInput')
    src.location = (-950, 180)
    dst = n.new('NodeGroupOutput')
    dst.location = (1140, 150)
    split = n.new('ShaderNodeSeparateXYZ')
    split.location = (-750, 230)
    l.new(src.outputs['Metric UV'], split.inputs[0])
    u, v = split.outputs['X'], split.outputs['Y']
    width, length, enabled = (src.outputs[key] for key in ('Board Width', 'Board Length', 'Board Joints'))

    def wire(socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            l.new(value, socket)
        else:
            socket.default_value = value

    def math(op, a, b, x, y, label=''):
        node = n.new('ShaderNodeMath')
        node.operation = op
        node.label = label
        node.location = (x, y)
        wire(node.inputs[0], a)
        if b is not None:
            wire(node.inputs[1], b)
        return node.outputs[0]

    def combine(a, b, x, y):
        node = n.new('ShaderNodeCombineXYZ')
        node.location = (x, y)
        wire(node.inputs['X'], a)
        wire(node.inputs['Y'], b)
        return node.outputs[0]

    def map_range(value, a, b, c, d, x, y, label='', smooth=False):
        node = n.new('ShaderNodeMapRange')
        node.location = (x, y)
        node.label = label
        node.clamp = True
        if smooth:
            node.interpolation_type = 'SMOOTHSTEP'
        for name, source in zip(('Value', 'From Min', 'From Max', 'To Min', 'To Max'), (value, a, b, c, d)):
            wire(node.inputs[name], source)
        return node.outputs[0]

    if herringbone:
        # Exact tiling for L >= W, including nonintegral L/W. Each lattice
        # cell contains two planks in a right-angle joint, repeated by
        # (W, W) and (L, -L). Horizontal base: [0,L]×[0,W];
        # vertical base: [L,L+W]×[W-L,W]. The d=x-y projections give a
        # single candidate from each family. If the horizontal candidate
        # misses the sample, the vertical one covers it.
        def op(kind, a, b=None, label=''):
            index = len(n) - 3
            loc = (-550. + 180. * (index % 10), 570. - 270. * (index // 10))
            return math(kind, a, b, *loc, label)

        diag = op('SUBTRACT', u, v)
        cycle = op('MULTIPLY', length, 2.)
        m0 = op('FLOOR', op('DIVIDE', op('ADD', diag, width), cycle), label='Horizontal strip')
        p0 = op('MULTIPLY', m0, length)
        y0 = op('ADD', v, p0)
        n0 = op('FLOOR', op('DIVIDE', y0, width), label='Horizontal board')
        b0 = op('MULTIPLY', n0, width)
        s0 = op('SUBTRACT', op('SUBTRACT', u, p0), b0)
        t0 = op('SUBTRACT', y0, b0)
        horizontal = op('MULTIPLY', op('LESS_THAN', s0, length),
                        op('SUBTRACT', 1., op('LESS_THAN', s0, 0.)))

        m1 = op('FLOOR', op('DIVIDE', op('SUBTRACT', op('ADD', diag, width), length), cycle),
                label='Vertical strip')
        p1 = op('MULTIPLY', op('ADD', m1, 1.), length)
        x1 = op('SUBTRACT', u, p1)
        n1 = op('FLOOR', op('DIVIDE', x1, width), label='Vertical board')
        b1 = op('MULTIPLY', n1, width)
        s1 = op('SUBTRACT', op('ADD', v, p1), op('ADD', b1, width))
        t1 = op('SUBTRACT', x1, b1)

        def pick(a, b):
            return op('ADD', b, op('MULTIPLY', horizontal, op('SUBTRACT', a, b)))

        s, t = pick(s0, s1), pick(t0, t1)
        d_end = op('MINIMUM', s, op('SUBTRACT', length, s), label='Distance to end joint (m)')
        d_long = op('MINIMUM', t, op('SUBTRACT', width, t), label='Distance to long joint (m)')
        dist = op('MINIMUM', d_end, d_long)
        # Local (s,t) keeps the grain parallel to the long edge on both
        # orientations; the orientation bit separates the two board IDs.
        col, row = pick(n0, n1), op('ADD', op('MULTIPLY', pick(m0, m1), 2.), horizontal)
        grain_u, grain_v = s, t
    else:
        # Nominal dimensions are seam-centre pitches. The fractional 38.2% row
        # shift avoids a repeated brick bond; adjacent rows cannot align end joints.
        row_coord = math('DIVIDE', v, width, -575, 200)
        row = math('FLOOR', row_coord, None, -390, 190, 'Row index')
        advance = math('MULTIPLY', row, .381966, -210, 390)
        phase = math('FRACT', advance, None, -30, 420)
        col_coord = math('ADD', math('DIVIDE', u, length, -390, 420), phase, 150, 420)
        col = math('FLOOR', col_coord, None, 335, 450, 'Board index')
        s = math('FRACT', col_coord, None, 335, 225)
        t = math('FRACT', row_coord, None, -210, -80)
        d_end = math('MULTIPLY', math('MINIMUM', s, math('SUBTRACT', 1, s, 505, 115), 665, 260),
                     length, 835, 285, 'Distance to end joint (m)')
        d_long = math('MULTIPLY', math('MINIMUM', t, math('SUBTRACT', 1, t, -30, -185), 150, -85),
                      width, 335, -75, 'Distance to long joint (m)')
        dist = math('MINIMUM', d_end, d_long, 1015, 285)
        grain_u, grain_v = u, v

    seam = map_range(dist, .00045, .00115, 1., 0., 1210, 180, 'Fine dark joint', smooth=True)
    bevel = map_range(dist, 0., .0017, 0., 1., 1210, -95, 'Micro-bevel', smooth=True)
    l.new(math('MULTIPLY', seam, enabled, 1410, 180), dst.inputs['Seam'])
    l.new(math('MULTIPLY', bevel, enabled, 1410, -95), dst.inputs['Bevel'])

    random = n.new('ShaderNodeTexWhiteNoise')
    random.location = (790, 610)
    l.new(combine(col, row, 580, 630), random.inputs['Vector'])
    shifted_tone = math('MULTIPLY', math('SUBTRACT', random.outputs['Value'], .5, 980, 645),
                        enabled, 1160, 645)
    tone = math('ADD', 1., math('MULTIPLY', shifted_tone, .28, 1340, 655), 1520, 655)
    l.new(tone, dst.inputs['Board Tone'])
    # Small, stable per-board grain phase. With explicit tile joints active,
    # fall back to continuous grain rather than leave wood joints showing.
    if herringbone:
        def masked_grain(continuous, board, x, y):
            return math('ADD', continuous,
                        math('MULTIPLY', enabled, math('SUBTRACT', board, continuous, x, y), x+180, y),
                        x+360, y)

        # A 45° offset is built into the herringbone placement; undo that
        # offset for continuous grain so Board Angle still has its usual meaning.
        continuous = n.new('ShaderNodeVectorRotate')
        continuous.rotation_type = 'AXIS_ANGLE'
        continuous.location = (120, 1140)
        continuous.inputs['Axis'].default_value = (0., 0., 1.)
        continuous.inputs['Angle'].default_value = -pi / 4
        l.new(src.outputs['Metric UV'], continuous.inputs['Vector'])
        continuous_split = n.new('ShaderNodeSeparateXYZ')
        continuous_split.location = (350, 1140)
        l.new(continuous.outputs['Vector'], continuous_split.inputs[0])
        grain_u = masked_grain(continuous_split.outputs['X'], grain_u, 650, 1050)
        grain_v = masked_grain(continuous_split.outputs['Y'], grain_v, 650, 925)
    grain_v = math('ADD', grain_v, math('MULTIPLY', shifted_tone, .18, 1260, 1180), 1520, 925)
    l.new(combine(grain_u, grain_v, 1695, 925), dst.inputs['Grain UV'])
    dst.location = (1900, 650)
    return g


def attach_board_shader(material, pbr, uv, scale, grain_out, width, length, joint_color,
                        *, angle=0., herringbone=False):
    """Use existing procedural grain with a per-board variation, seam and micro-bevel."""
    material[BOARD_DIMENSIONS] = (width, length)
    material[BOARD_ANGLE] = angle
    material[BOARD_HERRINGBONE] = herringbone
    nodes, links = material.node_tree.nodes, material.node_tree.links
    layout = nodes.new('ShaderNodeGroup')
    layout.node_tree = _layout_group(herringbone)
    layout.label = 'FZM herringbone hardwood' if herringbone else 'FZM staggered hardwood boards'
    layout.location = (-800, 50)
    uv.location = (-1040, 50)
    scale.location = (-570, 90)
    pbr.location = (430, 230)
    # Inverse-map coordinates so a positive entered angle rotates the
    # visible finish counterclockwise from the floor's existing UV axes.
    # At 0°, herringbone's spine follows U, with planks at ±45° to it.
    coord = uv.outputs['UV']
    layout_angle = remainder(remainder(angle, tau) - (pi / 4 if herringbone else 0.), tau)
    if layout_angle:
        uv.location.x -= 215
        rotate = nodes.new('ShaderNodeVectorRotate')
        rotate.label = 'Wood finish direction (no geometry change)'
        rotate.rotation_type = 'AXIS_ANGLE'
        rotate.invert = True
        rotate.inputs['Axis'].default_value = (0., 0., 1.)
        rotate.inputs['Angle'].default_value = layout_angle
        rotate.location = (-1040, 50)
        links.new(coord, rotate.inputs['Vector'])
        coord = rotate.outputs['Vector']
    links.new(coord, layout.inputs['Metric UV'])
    layout.inputs['Board Width'].default_value = width
    layout.inputs['Board Length'].default_value = length
    layout.inputs['Board Joints'].default_value = 1.
    links.new(layout.outputs['Grain UV'], scale.inputs[0])
    tone = nodes.new('ShaderNodeMixRGB')
    tone.blend_type = 'MULTIPLY'
    tone.label = 'Slight variation from board to board'
    tone.location = (-10, 200)
    tone.inputs[0].default_value = 1.
    links.new(grain_out, tone.inputs[1])
    links.new(layout.outputs['Board Tone'], tone.inputs[2])
    seams = nodes.new('ShaderNodeMixRGB')
    seams.label = 'Fine wood seams'
    seams.location = (190, 200)
    seams.inputs[2].default_value = joint_color
    links.new(layout.outputs['Seam'], seams.inputs[0])
    links.new(tone.outputs[0], seams.inputs[1])
    links.new(seams.outputs[0], pbr.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.label = 'Micro-bevel, not a geometry cut'
    bump.location = (195, -80)
    bump.inputs['Strength'].default_value = .38
    bump.inputs['Distance'].default_value = .0006
    links.new(layout.outputs['Bevel'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], pbr.inputs['Normal'])


def hide_board_pattern(material):
    """Let explicit tile joints take precedence on their copy of the base finish."""
    if BOARD_DIMENSIONS not in material:
        return
    for node in material.node_tree.nodes:
        if node.type == 'GROUP' and node.node_tree and node.node_tree.get(WOOD_GROUP) in (WOOD_GROUP_VERSION, HERRINGBONE_GROUP_VERSION):
            node.inputs['Board Joints'].default_value = 0.
