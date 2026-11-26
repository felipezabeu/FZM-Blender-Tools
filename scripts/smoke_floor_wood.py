"""Blender 5.1 headless: exercise Floor Finish through its public operator."""
from importlib import import_module
from math import atan2, floor, isclose
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if PACKAGE == 'fzm_builder':
    sys.path.insert(0, str(ROOT / 'extensions'))
    addon_utils.enable(PACKAGE, default_set=True, persistent=True)
hb = import_module(PACKAGE + '.hb_types')
finish = import_module(PACKAGE + '.operators.floor_finish')
tiles = import_module(PACKAGE + '.operators.floor_tiles')
shader = import_module(PACKAGE + '.operators.tile_shader')
wood = import_module(PACKAGE + '.operators.floor_wood')


def active(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def clean():
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def build_floor():
    start_x, end_x = -2., 2.
    corners = [(start_x, -2, 0), (end_x, -2, 0), (end_x, 2, 0), (start_x, 2, 0)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        wall = hb.GeoNodeWall()
        wall.create('Fixture Wall')
        delta = Vector(b) - Vector(a)
        wall.obj.location = a
        wall.obj.rotation_euler.z = atan2(delta.y, delta.x)
        wall.set_input('Length', delta.length)
        wall.set_input('Thickness', .15)
        wall.set_input('Height', 2.5)
    bpy.context.view_layer.update()
    assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
    return next(o for o in bpy.context.scene.objects if o.get('IS_FLOOR_BP'))


def material(obj):
    return obj.material_slots[0].material


def node_of(mat):
    return next(node for node in mat.node_tree.nodes
                if node.type == 'GROUP' and node.node_tree.get(wood.WOOD_GROUP))


def dimensions(mat, width, length):
    values = list(mat[wood.BOARD_DIMENSIONS])
    node = node_of(mat)
    assert all(isclose(a, b, rel_tol=1e-6) for a, b in
        zip((*values, node.inputs['Board Width'].default_value, node.inputs['Board Length'].default_value),
            (width, length, width, length)))


def set_wood(obj, key, width, length):
    active(obj)
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset=key,
        board_width=width, board_length=length) == {'FINISHED'}


def verify_workflow(tmp):
    clean()
    region = build_floor()
    region.name = 'Primary'
    # A saved old continuous-grain material must remain as-is until requested.
    old_data = dict(finish.catalog_entries()['maple'])
    del old_data['wood_boards']
    old_material = finish.create_material(old_data)
    finish.apply_finish(region, old_material)
    scene_path = str(tmp / 'wood.blend')
    bpy.ops.wm.save_as_mainfile(filepath=scene_path)
    bpy.ops.wm.open_mainfile(filepath=scene_path)
    region = bpy.data.objects['Primary']
    assert wood.BOARD_DIMENSIONS not in material(region) and material(region)['fzm_floor_finish_source'] == 'maple'

    set_wood(region, 'maple', .12, .78)
    dimensions(material(region), .12, .78)
    before = material(region)
    verts = len(region.data.vertices)
    objects = len(bpy.context.scene.objects)
    set_wood(region, 'hickory', .17, .93)
    assert material(region) != before
    dimensions(material(region), .17, .93)
    assert len(region.data.vertices) == verts and len(bpy.context.scene.objects) == objects

    active(region)
    assert bpy.ops.fzm_builder.floor_divider(first=(0, -2), second=(0, 2)) == {'FINISHED'}
    secondary = bpy.context.active_object
    secondary.name = 'Secondary'
    assert secondary != region
    assert material(region) == material(secondary)
    set_wood(secondary, 'grey_wood', .16, .75)
    dimensions(material(secondary), .16, .75)
    dimensions(material(region), .17, .93)
    first = material(region)
    gray = material(secondary)
    assert first != gray

    active(region)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='THIRD',
        tile_width=.36, tile_height=.29, grout=.006, angle=.31) == {'FINISHED'}
    spec = tiles.get_spec(region)
    assert spec.pattern == 'THIRD'
    assert shader.base_material(material(region)) == first
    assert node_of(material(region)).inputs['Board Joints'].default_value == 0.
    assert node_of(first).inputs['Board Joints'].default_value == 1.
    assert node_of(gray).inputs['Board Joints'].default_value == 1.
    set_wood(region, 'maple', .13, .99)
    assert tiles.get_spec(region) == spec
    dimensions(shader.base_material(material(region)), .13, .99)
    assert node_of(material(region)).inputs['Board Joints'].default_value == 0.
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE') == {'FINISHED'}
    assert tiles.get_spec(region) is None
    assert node_of(material(region)).inputs['Board Joints'].default_value == 1.
    dimensions(material(region), .13, .99)

    image = bpy.data.images.new('Supplier map', width=4, height=4)
    image.pixels = [.33,.21,.10,1]*16
    image.filepath_raw = str(tmp / 'supplier.png')
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    active(secondary)
    assert bpy.ops.fzm_builder.floor_finish(mode='IMAGE', filepath=str(tmp/'supplier.png'),
        width=.37, height=.61) == {'FINISHED'}
    image_base = material(secondary)
    assert wood.BOARD_DIMENSIONS not in image_base
    assert next(n for n in image_base.node_tree.nodes if n.type=='TEX_IMAGE').image.packed_file
    assert all(isclose(a, b, rel_tol=1e-6) for a, b in zip(image_base['fzm_image_repeat_m'], (.37,.61)))
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='STACK') == {'FINISHED'}
    assert shader.base_material(material(secondary)) == image_base
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE') == {'FINISHED'}
    assert material(secondary) == image_base
    dimensions(material(region), .13, .99)

    bpy.ops.wm.save_as_mainfile(filepath=scene_path)
    (tmp/'supplier.png').unlink()
    bpy.ops.wm.open_mainfile(filepath=scene_path)
    dimensions(material(bpy.data.objects['Primary']), .13, .99)
    assert next(n for n in material(bpy.data.objects['Secondary']).node_tree.nodes
                if n.type=='TEX_IMAGE').image.packed_file
    print('PASS public operators: old finish remains intact; all wood presets, actual divided regions, edit dimensions,'
          ' no geometry edits, tile precedence and restoration, packed Local Image and save/reopen')


def verify_rendered_joints(tmp):
    clean()
    obj = build_floor()
    width, length = .121, .318
    set_wood(obj, 'hickory', width, length)
    for wall in bpy.context.scene.objects:
        if wall != obj:
            wall.hide_render = True
    mat = material(obj)
    n, l = mat.node_tree.nodes, mat.node_tree.links
    output = next(node for node in n if node.type=='OUTPUT_MATERIAL')
    bsdf = next(node for node in n if node.type=='BSDF_PRINCIPLED')
    visual_color = bsdf.inputs['Base Color'].links[0].from_socket
    assert visual_color.node.inputs[0].links[0].from_socket == node_of(mat).outputs['Seam']
    assert bsdf.inputs['Normal'].links[0].from_node.inputs['Height'].links[0].from_socket == node_of(mat).outputs['Bevel']
    emission = n.new('ShaderNodeEmission')
    l.new(node_of(mat).outputs['Seam'], emission.inputs['Color'])
    l.new(emission.outputs['Emission'], output.inputs['Surface'])

    sc = bpy.context.scene
    data = bpy.data.cameras.new('Camera')
    camera = bpy.data.objects.new('Camera', data)
    sc.collection.objects.link(camera)
    camera.location = (0, 0, 3)
    data.type = 'ORTHO'
    data.ortho_scale = .640
    sc.camera = camera
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 8
    sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = 640
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = 'Standard'
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = str(tmp/'seams.png')
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath, check_existing=False)
    pix = img.pixels[:]
    good_seams = good_clear = 0
    for y in range(8, 632):
        v = (y + .5)*.001 - .32
        yi = v / width
        r = floor(yi)
        phase = (r * .381966) % 1
        # Compare shader output to an independent periodic plank formula, away from
        # partially antialiased transitions. Both axes include negative coordinates.
        for x in range(8, 632, 2):
            u = (x + .5)*.001 - .32
            xf = u / length + phase
            d = min(abs(xf - round(xf))*length, abs(yi - round(yi))*width)
            color = pix[(y*640+x)*4]
            if d < .00053:
                assert color > .50, (u,v,d,color)
                good_seams += 1
            elif d > .003:
                assert color < .03, (u,v,d,color)
                good_clear += 1
    assert good_seams > 250 and good_clear > 120_000, (good_seams, good_clear)
    print(f'PASS Blender-rendered {good_seams} physical seam and {good_clear} board interior samples,'
          ' actual staggered end joints, varied positive and negative rows')

    if visual_path := os.environ.get('FZM_WOOD_RENDER'):
        l.new(visual_color, emission.inputs['Color'])
        data.ortho_scale = 1.9
        sc.render.filepath = visual_path
        bpy.ops.render.render(write_still=True)


with TemporaryDirectory() as tmp:
    path = Path(tmp)
    verify_workflow(path)
    verify_rendered_joints(path)
