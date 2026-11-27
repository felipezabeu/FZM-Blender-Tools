"""Packaged Floor Finish smoke; set FZM_WOOD_RENDER_DIR for an optional Eevee seam comparison."""
from dataclasses import asdict
from importlib import import_module
from math import cos, floor, isclose, pi, radians, sin
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import bpy
from mathutils import Vector

package = next(key for key in bpy.context.preferences.addons.keys() if key.endswith('.fzm_builder'))
div = import_module(package + '.operators.floor_divider')
finish = import_module(package + '.operators.floor_finish')
tiles = import_module(package + '.operators.floor_tiles')
shader = import_module(package + '.operators.tile_shader')
wood = import_module(package + '.operators.floor_wood')
C = bpy.context


def select(obj):
    for other in tuple(C.selected_objects):
        other.select_set(False)
    obj.select_set(True)
    C.view_layer.objects.active = obj


def slab(name, x=0., y=0.):
    base = bpy.data.meshes.new('Empty')
    coords = [Vector(pair) for pair in ((0., 0.), (1., 0.), (1., 1.), (0., 1.))]
    mesh = div.make_slab(name, coords, 0., -.01, base, 0)
    bpy.data.meshes.remove(base)
    obj = bpy.data.objects.new(name, mesh)
    C.collection.objects.link(obj)
    obj.location = (x, y, 0.)
    obj['IS_FLOOR_BP'] = True
    return obj


def geometry(obj):
    return (tuple(tuple(v.co) for v in obj.data.vertices),
            tuple(tuple(p.vertices) for p in obj.data.polygons),
            tuple(tuple(item.uv) for item in obj.data.uv_layers['UVMap'].data),
            tuple(obj.location), tuple(obj.rotation_euler), tuple(obj.scale))


def material(obj):
    return obj.material_slots[0].material


def wood_node(mat):
    return next(node for node in mat.node_tree.nodes if node.type == 'GROUP' and node.node_tree.get(wood.WOOD_GROUP))


def check_config(mat, herringbone, angle, width, length):
    assert mat[wood.BOARD_HERRINGBONE] == herringbone
    assert isclose(mat[wood.BOARD_ANGLE], angle, abs_tol=1e-6)
    assert all(isclose(a, b, abs_tol=1e-6) for a, b in zip(mat[wood.BOARD_DIMENSIONS], (width, length)))
    layout = wood_node(mat)
    assert layout.node_tree.get(wood.WOOD_GROUP) == (2 if herringbone else 1)
    mapping = layout.inputs['Metric UV'].links[0].from_node
    if herringbone or angle:
        assert mapping.type == 'VECTOR_ROTATE' and mapping.invert
        assert isclose(mapping.inputs['Angle'].default_value, angle - (pi / 4 if herringbone else 0.), abs_tol=1e-6)
    else:
        assert mapping.type == 'UVMAP'
    return layout


def dialog_state(obj):
    # Exercise the exact invocation/draw path without needing a modal GUI.
    fields = []
    props = SimpleNamespace(is_property_set=lambda key: False)
    op = SimpleNamespace(mode='CATALOG', preset='maple', properties=props)
    ui = SimpleNamespace(prop=lambda _op, key, **kw: fields.append(key),
                         label=lambda **kw: fields.append(kw['text']))
    op.layout = ui
    context = SimpleNamespace(active_object=obj, window_manager=SimpleNamespace(
        invoke_props_dialog=lambda operator, width: {'RUNNING_MODAL'}))
    assert finish.FZM_OT_floor_finish.invoke(op, context, None) == {'RUNNING_MODAL'}
    finish.FZM_OT_floor_finish.draw(op, context)
    return op, fields


def expected_distance(x, y, width, length, angle, herringbone):
    turn = angle - (pi / 4 if herringbone else 0.)
    u, v = cos(turn) * x + sin(turn) * y, -sin(turn) * x + cos(turn) * y
    if not herringbone:
        row = floor(v / width)
        s = ((u / length + (row * .381966) % 1.) % 1.) * length
        t = v % width
    else:
        # Independent brute-force candidate checks around the sampled point.
        candidates = []
        for m in range(-4, 5):
            h = floor((v + m * length) / width)
            ss, tt = u - h * width - m * length, v - h * width + m * length
            if 0. <= ss < length and 0. <= tt < width:
                candidates.append((ss, tt))
            h = floor((u - (m + 1) * length) / width)
            ss, tt = v - h * width + (m + 1) * length - width, u - h * width - (m + 1) * length
            if 0. <= ss < length and 0. <= tt < width:
                candidates.append((ss, tt))
        assert len(candidates) == 1, (x, y, candidates)
        s, t = candidates[0]
    return min(s, length - s, t, width - t)


def render_seam_check(configs, destination):
    scene = C.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 1
    scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_percentage = 100
    size = 400
    scene.render.resolution_x, scene.render.resolution_y = 3 * size, 2 * size
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'BW'
    camera = bpy.data.objects.new('Wood QA camera', bpy.data.cameras.new('Wood QA camera'))
    C.collection.objects.link(camera)
    camera.location = (1.5, 1., 3.)
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 3.
    scene.camera = camera
    scene.render.filepath = str(destination / 'wood-seams.png')
    for name, *_ in configs:
        obj = bpy.data.objects[name]
        mat = material(obj).copy()
        obj.material_slots[0].material = mat
        ln = mat.node_tree.links
        emission = mat.node_tree.nodes.new('ShaderNodeEmission')
        ln.new(wood_node(mat).outputs['Seam'], emission.inputs[0])
        ln.new(emission.outputs[0], next(n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL').inputs['Surface'])
    assert bpy.ops.render.render(write_still=True) == {'FINISHED'}
    image = bpy.data.images.load(scene.render.filepath)
    pixels = image.pixels[:]
    for i, cfg in enumerate(configs):
        _, herringbone, angle, width, length = cfg
        # One viewport frame verifies the actual shader, including negative UVs,
        # nonintegral board proportions, and both rotated grain/joint families.
        tested = wrong = bright = 0
        for y in range(2, size - 2):
            for x in range(2, size - 2):
                d = expected_distance((x + .5) / size, (y + .5) / size, width, length, angle, herringbone)
                if .00032 < d < .00135:
                    continue  # seam transition and raster sampling tolerance
                expected = d <= .00032
                found = pixels[((size * (i // 3) + y) * size * 3 + size * (i % 3) + x) * 4] > .5
                tested += 1
                bright += expected
                wrong += found != expected
        assert bright > 100 and wrong / tested < .012, (cfg, wrong, tested, bright)
        print('Wood GPU seam match', cfg[0], round(100 * (1 - wrong / tested), 3), '%')


for obj in list(C.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

configs = []
for i in range(6):
    obj = slab(f'Wood {i}', i % 3, i // 3)
    select(obj)
    before = geometry(obj)
    herringbone, angle = i >= 3, radians((0., 90., 37., 0., 90., -37.)[i])
    w, l = .0937, .437
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset='hickory', board_angle=angle,
        herringbone=herringbone, board_width=w, board_length=l) == {'FINISHED'}
    assert geometry(obj) == before
    check_config(material(obj), herringbone, angle, w, l)
    configs.append((obj.name, herringbone, angle, w, l))

obj = bpy.data.objects['Wood 5']
select(obj)
source = material(obj)
before = geometry(obj)
assert bpy.ops.fzm_builder.floor_tile_layout(pattern='HALF', angle=.28, tile_width=.51, tile_height=.29,
    offset_u=.16, offset_v=.08, grout=.004) == {'FINISHED'}
data = asdict(tiles.get_spec(obj))
assert shader.base_material(material(obj)) == source
assert wood_node(material(obj)).inputs['Board Joints'].default_value == 0.
assert wood_node(source).inputs['Board Joints'].default_value == 1.
assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset='hickory', board_angle=radians(-37.),
    herringbone=True, board_width=w, board_length=l) == {'FINISHED'}
assert asdict(tiles.get_spec(obj)) == data
assert geometry(obj) == before
layout = check_config(material(obj), True, radians(-37.), w, l)
assert layout.inputs['Board Joints'].default_value == 0.
op, fields = dialog_state(obj)
assert op.preset == 'hickory' and op.herringbone and isclose(op.board_angle, radians(-37.), abs_tol=1e-6)
assert 'board_angle' in fields and 'herringbone' in fields
assert any('No Tile Layout' in f for f in fields)
assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE') == {'FINISHED'}
assert not tiles.get_spec(obj)
assert wood_node(material(obj)).inputs['Board Joints'].default_value == 1.
assert geometry(obj) == before
assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset='hickory', herringbone=True,
    board_width=.5, board_length=.2) == {'CANCELLED'}
assert geometry(obj) == before
check_config(material(obj), True, radians(-37.), w, l)

# Confirm 5.1.25 compatibility: a v1 board material has no newer metadata.
legacy_obj = bpy.data.objects['Wood 0']
legacy = material(legacy_obj)
del legacy[wood.BOARD_ANGLE]
del legacy[wood.BOARD_HERRINGBONE]
op, _ = dialog_state(legacy_obj)
assert op.board_angle == 0. and op.herringbone is False
legacy[wood.BOARD_ANGLE], legacy[wood.BOARD_HERRINGBONE] = 0., False

with TemporaryDirectory() as tmp:
    path = Path(tmp) / 'wood-test.blend'
    # Nonwood finish path is unchanged even if a caller passes wood controls.
    obj = slab('Solid', 5., 0.)
    select(obj)
    assert bpy.ops.fzm_builder.floor_finish(mode='COLOR', color=(.5, .4, .3, 1.),
        board_angle=radians(90.), herringbone=True) == {'FINISHED'}
    assert wood.BOARD_ANGLE not in material(obj)
    bpy.data.objects.remove(obj, do_unlink=True)
    assert bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {'FINISHED'}
    assert bpy.ops.wm.open_mainfile(filepath=str(path)) == {'FINISHED'}
    for name, *args in configs:
        obj = bpy.data.objects[name]
        check_config(material(obj), *args)
        op, _ = dialog_state(obj)
        assert op.herringbone == args[0] and isclose(op.board_angle, args[1], abs_tol=1e-6)

print('PASS floor finish arbitrary rotation, herringbone/straight, metric dimensions, unchanged geometry/tiles and save/reopen')
if destination := os.environ.get('FZM_WOOD_RENDER_DIR'):
    render_seam_check(configs, Path(destination))
