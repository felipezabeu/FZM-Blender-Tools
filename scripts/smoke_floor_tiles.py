"""Blender 5.1.2 headless: metric shader follows floor geometry and existing finishes."""
from importlib import import_module
from math import cos, isclose, sin
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy
from mathutils import Vector

BASE = Path(__file__).resolve().parents[1]
package = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if package == 'fzm_builder':
    sys.path.insert(0, str(BASE / 'extensions'))
    addon_utils.enable(package, default_set=True, persistent=True)

mod = lambda name: import_module(package + '.' + name)
core = mod('tile_core')
hb = mod('hb_types')
floor_divider = mod('operators.floor_divider')
tiles = mod('operators.floor_tiles')
shader = mod('operators.tile_shader')


def active(o):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o


def create_floor(name, coords, z=0):
    placeholder = bpy.data.meshes.new('Empty')
    mesh = floor_divider.make_slab(name, [Vector(p) for p in coords], z, z-.01, placeholder, 0)
    bpy.data.meshes.remove(placeholder)
    o = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(o)
    o['IS_FLOOR_BP'] = True
    return o


def layout_node(obj):
    return next(n for n in obj.material_slots[0].material.node_tree.nodes
                if n.type == 'GROUP' and n.node_tree.get('fzm_metric_tile_group'))


def hit(obj, x, y):
    dg = bpy.context.evaluated_depsgraph_get()
    return obj.evaluated_get(dg).ray_cast(Vector((x,y,2)), Vector((0,0,-1)))[0]


def compare_mask_render(tmp):
    # Test compiled Blender shader (not just reference formulas), including
    # rotation and negative course coordinates. White is grout, black is tile.
    o = create_floor('Mask sample', [(-1.,-1.), (1.,-1.), (1.,1.), (-1.,1.)])
    active(o)
    spec = dict(pattern='THIRD', tile_width=.29, tile_height=.23, grout=.04,
        angle=.33, offset_u=-.17, offset_v=.11)
    assert bpy.ops.fzm_builder.floor_tile_layout(**spec) == {'FINISHED'}
    mat = o.material_slots[0].material
    n, l = mat.node_tree.nodes, mat.node_tree.links
    out = next(node for node in n if node.type=='OUTPUT_MATERIAL' and node.is_active_output)
    em = n.new('ShaderNodeEmission')
    l.new(layout_node(o).outputs['Grout'], em.inputs['Color'])
    l.new(em.outputs['Emission'], out.inputs['Surface'])
    sc = bpy.context.scene
    camera_data = bpy.data.cameras.new('Sample camera')
    camera = bpy.data.objects.new('Sample camera',camera_data)
    sc.collection.objects.link(camera); camera.location=(0,0,3)
    camera_data.type='ORTHO'; camera_data.ortho_scale=2
    sc.camera=camera
    sc.render.engine = 'CYCLES'
    sc.cycles.samples=2
    sc.cycles.use_denoising=False
    sc.render.resolution_x = sc.render.resolution_y = 100
    sc.render.resolution_percentage=100
    sc.view_settings.view_transform='Standard'
    sc.render.image_settings.file_format='PNG'
    sc.render.filepath=str(tmp/'mask.png')
    bpy.ops.render.render(write_still=True)
    img=bpy.data.images.load(sc.render.filepath,check_existing=False)
    pix=img.pixels[:]
    ca,sa=cos(spec['angle']),sin(spec['angle'])
    checked=0
    for a in range(10,90,4):
        for b in range(10,90,4):
            x,y=(a+.5)/50-1,(b+.5)/50-1
            u,v=ca*x+sa*y,-sa*x+ca*y
            s,t,is_grout=core.tile_sample(u,v,.29,.23,.04,'THIRD',-.17,.11)
            if min(s,abs(s-.29), .33-s, t,abs(t-.23), .27-t)<.016:
                continue  # polygon antialiasing near transition
            assert abs(pix[(b*100+a)*4]-int(is_grout)) < .12, (x,y,s,t,is_grout,pix[(b*100+a)*4])
            checked+=1
    assert checked>170,checked
    print(f'PASS Blender-rendered rotation/brick metric grout parity ({checked} interior samples)')


def test(tmp):
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    floor = create_floor('Region L', [(0,0),(4,0),(4,1),(2,1),(2,3),(0,3)])
    other = create_floor('Region spare', [(8,0),(10,0),(10,2),(8,2)])
    active(floor)
    img=bpy.data.images.new('Supplier surface', width=4,height=4)
    img.pixels = [.32,.18,.12,1]*16
    img.filepath_raw = str(tmp/'supplier.png')
    img.file_format='PNG';img.save()
    bpy.data.images.remove(img)
    assert bpy.ops.fzm_builder.floor_finish(mode='IMAGE', filepath=str(tmp/'supplier.png'), width=.47, height=.71)=={'FINISHED'}
    original=floor.material_slots[0].material
    source_tex=next(n for n in original.node_tree.nodes if n.type=='TEX_IMAGE')
    bpy.ops.mesh.primitive_cube_add(size=.38,location=(1.5,.5,0))
    cutter=bpy.context.object; cutter.hide_render=True
    bool_mod=floor.modifiers.new('Floor Cutter','BOOLEAN');bool_mod.object=cutter
    bool_mod.operation='DIFFERENCE'
    before = (len(floor.data.vertices),len(bpy.context.scene.objects))
    active(floor)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='HALF',tile_width=.5,tile_height=.27,grout=.007,angle=.26,
        offset_u=.045,offset_v=-.011)=={'FINISHED'}
    wrapped=floor.material_slots[0].material
    assert shader.base_material(wrapped)==original
    assert next(n for n in wrapped.node_tree.nodes if n.type=='TEX_IMAGE').image==source_tex.image
    assert tuple(wrapped.get('fzm_image_repeat_m'))==tuple(original.get('fzm_image_repeat_m'))
    layout=layout_node(floor)
    assert isclose(layout.inputs['Pitch U'].default_value,.507,rel_tol=1e-6)
    assert layout.inputs['Cycle'].default_value==2
    assert before==(len(floor.data.vertices),len(bpy.context.scene.objects))
    assert hit(floor,.5,.5) and not hit(floor,3,2) and not hit(floor,1.5,.5)
    assert 'FZM_TILE_SURFACE' not in original and not tiles.get_spec(other)

    active(other)
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset='maple') == {'FINISHED'}
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='STACK',tile_width=.42,tile_height=.22)=={'FINISHED'}
    original_other = shader.base_material(other.material_slots[0].material)
    assert original_other['fzm_floor_finish_source']=='maple'
    assert layout_node(other).inputs['Cycle'].default_value==1
    assert layout_node(floor).inputs['Cycle'].default_value==2
    assert bpy.ops.fzm_builder.floor_finish(mode='COLOR',color=(.2,.4,.1,1))=={'FINISHED'}
    assert tiles.get_spec(other).pattern=='STACK'
    assert shader.base_material(other.material_slots[0].material)['fzm_floor_finish_source']=='solid_color'
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE')=={'FINISHED'}
    assert not other.material_slots[0].material.get(shader.TILE_MATERIAL)
    assert not tiles.get_spec(other)
    active(floor)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='HALF', tile_width=.02, tile_height=.02, grout=.06)=={'CANCELLED'}
    assert floor.material_slots[0].material==wrapped

    saved=str(tmp/'tiles.blend')
    bpy.ops.wm.save_as_mainfile(filepath=saved)
    (tmp/'supplier.png').unlink()
    bpy.ops.wm.open_mainfile(filepath=saved)
    floor=bpy.data.objects['Region L']
    wrapped=floor.material_slots[0].material
    original=shader.base_material(wrapped)
    assert original is not None and tiles.get_spec(floor).pattern=='HALF'
    assert next(n for n in wrapped.node_tree.nodes if n.type=='TEX_IMAGE').image.packed_file
    assert hit(floor,.5,.5) and not hit(floor,3,2) and not hit(floor,1.5,.5)
    active(floor)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE')=={'FINISHED'}
    assert floor.material_slots[0].material==original
    print('PASS concave/cutter clipping with unchanged geometry, independent region layouts and base materials, supplier image packing, edit/clear and save/reopen')
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    compare_mask_render(tmp)


with TemporaryDirectory() as t:
    test(Path(t))
