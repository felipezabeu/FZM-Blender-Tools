"""Metric, staggered wood boards in a surface shader (no generated floor meshes)."""

import bpy

BOARD_WIDTH = .1524
BOARD_LENGTH = 1.2192
BOARD_DIMENSIONS = 'fzm_floor_wood_board_m'
WOOD_GROUP = 'fzm_metric_wood_board_group'
WOOD_GROUP_VERSION = 1


def _layout_group():
    for group in bpy.data.node_groups:
        if group.bl_idname == 'ShaderNodeTree' and group.get(WOOD_GROUP) == WOOD_GROUP_VERSION:
            return group
    g = bpy.data.node_groups.new('FZM Metric Wood Boards v1', 'ShaderNodeTree')
    g[WOOD_GROUP] = WOOD_GROUP_VERSION
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
    # Small, stable per-board grain phase; bypass with another layout active.
    grain_v = math('ADD', v, math('MULTIPLY', shifted_tone, .18, 1340, 925), 1520, 925)
    l.new(combine(u, grain_v, 1695, 925), dst.inputs['Grain UV'])
    dst.location = (1900, 650)
    return g


def attach_board_shader(material, pbr, uv, scale, grain_out, width, length, joint_color):
    """Use existing procedural grain with a per-board variation, seam and micro-bevel."""
    material[BOARD_DIMENSIONS] = (width, length)
    nodes, links = material.node_tree.nodes, material.node_tree.links
    layout = nodes.new('ShaderNodeGroup')
    layout.node_tree = _layout_group()
    layout.label = 'FZM staggered hardwood boards (metric)'
    layout.location = (-800, 50)
    uv.location = (-1040, 50)
    scale.location = (-570, 90)
    pbr.location = (430, 230)
    links.new(uv.outputs['UV'], layout.inputs['Metric UV'])
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
        if node.type == 'GROUP' and node.node_tree and node.node_tree.get(WOOD_GROUP) == WOOD_GROUP_VERSION:
            node.inputs['Board Joints'].default_value = 0.
