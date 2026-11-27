"""Compile the shared tile layout into a Blender material; no tiles as objects."""
from dataclasses import dataclass
from math import isfinite, sqrt

import bpy

from ..tile_core import tile_pitch
from .floor_wood import hide_board_pattern
from .tile_catalog import PORCELAIN_TAG, apply_directional_porcelain


PATTERNS = (('STACK', "Stack", "Straight aligned joints"),
            ('HALF', "Brick 50%", "Half-pitch staggered joints"),
            ('THIRD', "Brick 33%", "One-third-pitch staggered joints"))
FLOOR_PATTERNS = (('NONE', "No Tile Layout", "Keep the region's base finish"), *PATTERNS)
SHAPES = (('RECTANGLE', 'Rectangle', 'Use the selected rectangular layout'),
          ('SQUARE', 'Square', 'Equal square mosaic tiles'),
          ('HEX', 'Hexagonal', 'Regular hexagons, measured across flats'),
          ('PENNY', 'Penny Round', 'Round tiles, measured by diameter'))
MOSAIC_SIZE = {'SQUARE': .0508, 'HEX': .0508, 'PENNY': .0254}
def reset_mosaic_size(operator, context):
    if operator.tile_shape in MOSAIC_SIZE:
        operator.mosaic_size = MOSAIC_SIZE[operator.tile_shape]


TILE_GROUP_VERSION = 2
TILE_MATERIAL = "FZM_TILE_SURFACE"
TILE_BASE = "FZM_TILE_BASE_MATERIAL"


@dataclass(frozen=True)
class TileSpec:
    pattern: str = 'STACK'
    width: float = .6096
    height: float = .3048
    grout: float = .003
    angle: float = 0.
    offset_u: float = 0.
    offset_v: float = 0.
    color: tuple = (.24, .23, .21, 1.)
    shape: str = 'RECTANGLE'


def validate(spec):
    if spec.shape not in {row[0] for row in SHAPES}:
        raise ValueError("Unsupported tile shape.")
    if spec.shape != 'RECTANGLE' and abs(spec.height - spec.width) > 1e-8:
        raise ValueError("Mosaic shapes need equal tile dimensions.")
    pattern = spec.pattern if spec.shape == 'RECTANGLE' else 'STACK'
    pitch_u, pitch_v, cycle = tile_pitch(spec.width, spec.height, spec.grout, pattern)
    if spec.shape in {'HEX', 'PENNY'}:
        pitch_v = pitch_u * sqrt(3)
    if min(spec.width, spec.height) < .009999 or max(spec.width, spec.height) > 10.:
        raise ValueError("Tile width and length must be between 10 mm and 10 m.")
    if spec.grout > min(spec.width, spec.height) * .5:
        raise ValueError("Grout cannot exceed half the small tile dimension.")
    if not all(isfinite(v) for v in (spec.angle, spec.offset_u, spec.offset_v, *spec.color)):
        raise ValueError("Tile settings must be finite.")
    if len(spec.color) != 4 or any(not 0. <= v <= 1. for v in spec.color):
        raise ValueError("Invalid grout color.")
    return pitch_u, pitch_v, cycle


def _node_group(shape='RECTANGLE'):
    name = ("FZM Metric Tile Layout v2" if shape in {'RECTANGLE', 'SQUARE'}
            else f"FZM Metric Mosaic {shape} v2")
    group = bpy.data.node_groups.get(name)
    if group and group.get('fzm_metric_tile_group') == TILE_GROUP_VERSION:
        return group
    group = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    group['fzm_metric_tile_group'] = TILE_GROUP_VERSION
    inputs = (('Surface UV (m)', 'NodeSocketVector'), ('Tile Width', 'NodeSocketFloat'),
              ('Tile Height', 'NodeSocketFloat'), ('Pitch U', 'NodeSocketFloat'),
              ('Pitch V', 'NodeSocketFloat'), ('Cycle', 'NodeSocketFloat'),
              ('Angle', 'NodeSocketFloat'), ('Phase U', 'NodeSocketFloat'),
              ('Phase V', 'NodeSocketFloat'))
    outputs = (('Grout', 'NodeSocketFloat'), ('Tile UV', 'NodeSocketVector'),
               ('Tile Column', 'NodeSocketFloat'), ('Tile Row', 'NodeSocketFloat'))
    for direction, items in (('INPUT', inputs), ('OUTPUT', outputs)):
        for label, typ in items:
            group.interface.new_socket(name=label, in_out=direction, socket_type=typ)
    nodes = group.nodes
    links = group.links
    src = nodes.new('NodeGroupInput')
    dst = nodes.new('NodeGroupOutput')
    rotate = nodes.new('ShaderNodeVectorRotate')
    rotate.rotation_type = 'AXIS_ANGLE'
    rotate.inputs['Axis'].default_value = (0., 0., 1.)
    rotate.invert = True
    links.new(src.outputs['Surface UV (m)'], rotate.inputs['Vector'])
    links.new(src.outputs['Angle'], rotate.inputs['Angle'])
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(rotate.outputs['Vector'], split.inputs[0])

    def run(op, a, b=None):
        node = nodes.new('ShaderNodeMath')
        node.operation = op
        for value, socket in zip((a, b), node.inputs[:2]):
            if value is None:
                break
            if isinstance(value, bpy.types.NodeSocket):
                links.new(value, socket)
            else:
                socket.default_value = value
        return node.outputs[0]

    u = run('SUBTRACT', split.outputs['X'], src.outputs['Phase U'])
    v = run('SUBTRACT', split.outputs['Y'], src.outputs['Phase V'])
    if shape in {'HEX', 'PENNY'}:
        px, py = src.outputs['Pitch U'], src.outputs['Pitch V']

        def centered(value, pitch):
            half = run('MULTIPLY', pitch, .5)
            return run('SUBTRACT', run('FLOORED_MODULO', run('ADD', value, half), pitch), half)

        a = centered(u, px), centered(v, py)
        b = centered(run('SUBTRACT', u, run('MULTIPLY', px, .5)), px), centered(
                     run('SUBTRACT', v, run('MULTIPLY', py, .5)), py)
        def squared(pair):
            x, y = pair
            return run('ADD', run('MULTIPLY', x, x), run('MULTIPLY', y, y))
        da, db = squared(a), squared(b)
        use_b = run('LESS_THAN', db, da)
        def pick(i):
            return run('ADD', a[i], run('MULTIPLY', use_b, run('SUBTRACT', b[i], a[i])))
        x, y = pick(0), pick(1)
        half_width = run('MULTIPLY', src.outputs['Tile Width'], .5)
        if shape == 'HEX':
            ax, ay = run('ABSOLUTE', x), run('ABSOLUTE', y)
            radius = run('MAXIMUM', ax, run('MULTIPLY', run('ADD', ax, run('MULTIPLY', ay, sqrt(3))), .5))
            inside = run('LESS_THAN', radius, half_width)
            image_height = run('MULTIPLY', src.outputs['Tile Width'], 2 / sqrt(3))
        else:
            inside = run('LESS_THAN', run('MINIMUM', da, db), run('MULTIPLY', half_width, half_width))
            image_height = src.outputs['Tile Width']
        links.new(run('SUBTRACT', 1., inside), dst.inputs['Grout'])
        combine = nodes.new('ShaderNodeCombineXYZ')
        links.new(run('ADD', .5, run('DIVIDE', x, src.outputs['Tile Width'])), combine.inputs['X'])
        links.new(run('ADD', .5, run('DIVIDE', y, image_height)), combine.inputs['Y'])
        links.new(combine.outputs[0], dst.inputs['Tile UV'])
        # Circle/hex centres alternate across two half-shifted sub-lattices.
        # Recover the centre from the chosen local offset and round onto
        # half-pitch indices so the random seed is stable over the whole tile.
        for coord, local, pitch, label in ((u, x, px, 'Tile Column'),
                                           (v, y, py, 'Tile Row')):
            center_id = run('ROUND', run('DIVIDE', run('MULTIPLY', run('SUBTRACT', coord, local), 2.), pitch))
            links.new(center_id, dst.inputs[label])
        return group

    row = run('FLOOR', run('DIVIDE', v, src.outputs['Pitch V']))
    shift = run('DIVIDE', run('FLOORED_MODULO', row, src.outputs['Cycle']), src.outputs['Cycle'])
    u = run('ADD', u, run('MULTIPLY', shift, src.outputs['Pitch U']))
    s = run('FLOORED_MODULO', u, src.outputs['Pitch U'])
    t = run('FLOORED_MODULO', v, src.outputs['Pitch V'])
    # At exactly tile_width or tile_height the shared layout is grout.
    grout_x = run('SUBTRACT', 1., run('LESS_THAN', s, src.outputs['Tile Width']))
    grout_y = run('SUBTRACT', 1., run('LESS_THAN', t, src.outputs['Tile Height']))
    links.new(run('MAXIMUM', grout_x, grout_y), dst.inputs['Grout'])
    combine = nodes.new('ShaderNodeCombineXYZ')
    links.new(run('DIVIDE', s, src.outputs['Tile Width']), combine.inputs['X'])
    links.new(run('DIVIDE', t, src.outputs['Tile Height']), combine.inputs['Y'])
    links.new(combine.outputs[0], dst.inputs['Tile UV'])
    links.new(run('FLOOR', run('DIVIDE', u, src.outputs['Pitch U'])), dst.inputs['Tile Column'])
    links.new(row, dst.inputs['Tile Row'])
    return group


def _surface(material):
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output
                   and n.target == 'ALL'), None)
    if output is None:
        output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'
                       and n.is_active_output), None)
    if output is None:
        output = nodes.new('ShaderNodeOutputMaterial')
    if not output.inputs['Surface'].is_linked:
        base = nodes.new('ShaderNodeBsdfPrincipled')
        base.inputs['Base Color'].default_value = material.diffuse_color
        links.new(base.outputs['BSDF'], output.inputs['Surface'])
    return output


def base_material(material):
    if material is not None and material.get(TILE_MATERIAL):
        return material.get(TILE_BASE)
    return material


def tile_material(source, settings, *, one_image_per_tile=False):
    """Maintain original finish shader/scale; only blend grout on the surface."""
    pitch_u, pitch_v, cycle = validate(settings)
    source = base_material(source)
    mat = source.copy() if source is not None else bpy.data.materials.new('FZM Neutral Tile')
    try:
        if source is None:
            # Unfinished slabs get a neutral tile color, not a replacement catalog entry.
            mat.diffuse_color = (.58, .55, .49, 1.)
            mat.use_nodes = True
            bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            bsdf.inputs['Base Color'].default_value = mat.diffuse_color
            bsdf.inputs['Roughness'].default_value = .35
        elif not source.use_nodes:
            mat.use_nodes = True
            bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if bsdf is not None:
                bsdf.inputs['Base Color'].default_value = source.diffuse_color
                bsdf.inputs['Roughness'].default_value = source.roughness
                bsdf.inputs['Metallic'].default_value = source.metallic
        mat.name = (source.name if source else "FZM Neutral Tile") + " | Tile Joint"
        hide_board_pattern(mat)
        mat[TILE_MATERIAL] = True
        if source is not None:
            mat[TILE_BASE] = source
        output = _surface(mat)
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        base_input = output.inputs['Surface'].links[0].from_socket
        uv = nodes.new('ShaderNodeUVMap')
        uv.uv_map = 'UVMap'
        uv.location = (-440, -440)
        layout = nodes.new('ShaderNodeGroup')
        layout.node_tree = _node_group(settings.shape)
        layout.label = 'FZM metric tile joints'
        layout.location = (-220, -440)
        links.new(uv.outputs["UV"], layout.inputs['Surface UV (m)'])
        for key, value in {
            'Tile Width': settings.width, 'Tile Height': settings.height,
            'Pitch U': pitch_u, 'Pitch V': pitch_v, 'Cycle': cycle,
            'Angle': settings.angle, 'Phase U': settings.offset_u % pitch_u,
            'Phase V': settings.offset_v % pitch_v,
        }.items():
            layout.inputs[key].default_value = value
        grout = nodes.new('ShaderNodeBsdfPrincipled')
        grout.label = 'FZM grout appearance'
        grout.location = (0, -440)
        grout.inputs['Base Color'].default_value = settings.color
        grout.inputs['Roughness'].default_value = .83
        # A different grout roughness does not change the original tile
        # material's normal or supplier texture mapping.
        mix = nodes.new('ShaderNodeMixShader')
        mix.label = 'FZM tile joints over existing finish'
        mix.location = (output.location.x - 170, output.location.y)
        links.new(layout.outputs['Grout'], mix.inputs[0])
        links.new(base_input, mix.inputs[1])
        links.new(grout.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs['Surface'])
        if source is not None and source.get(PORCELAIN_TAG):
            apply_directional_porcelain(mat, layout)
        elif one_image_per_tile:
            for image in (node for node in nodes if node.type == 'TEX_IMAGE'):
                links.new(layout.outputs['Tile UV'], image.inputs['Vector'])
                image.extension = 'EXTEND'
        return mat
    except Exception:
        bpy.data.materials.remove(mat)
        raise


def dispose_if_unused(material):
    if (material is not None and material.users == 0
            and material.get(TILE_MATERIAL) and not material.use_fake_user):
        bpy.data.materials.remove(material)
