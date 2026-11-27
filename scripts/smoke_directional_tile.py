"""Run with Blender 5.1: --background --factory-startup --python-exit-code 1 --python this_file."""
from dataclasses import asdict
from importlib import import_module
from math import atan2
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
hb = mod('hb_types')
catalog = mod('operators.tile_catalog')
div = mod('operators.floor_divider')
tiles = mod('operators.floor_tiles')
shader = mod('operators.tile_shader')
shower = mod('operators.shower_area')

def select(*objects):
    for o in tuple(bpy.context.selected_objects):
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]

def slab(name, x=0):
    placeholder = bpy.data.meshes.new('Empty')
    coords = [Vector(v) for v in ((x,0), (x+2,0), (x+2,2), (x,2))]
    m = div.make_slab(name,coords,0,-.01,placeholder,0)
    bpy.data.meshes.remove(placeholder)
    o = bpy.data.objects.new(name,m)
    bpy.context.collection.objects.link(o)
    o['IS_FLOOR_BP'] = True
    return o

def wall(name, a, b):
    w = hb.GeoNodeWall()
    w.create(name)
    delta = Vector(b)-Vector(a)
    w.obj.location = Vector(a)
    w.obj.rotation_euler.z = atan2(delta.y,delta.x)
    w.set_input('Length',delta.length)
    w.set_input('Height',2.45)
    w.set_input('Thickness',.15)
    bpy.context.view_layer.update()
    return w.obj

def actual_faces(mat, code, pattern, expect_shape='RECTANGLE'):
    src = shader.base_material(mat)
    assert src[catalog.PORCELAIN_TAG] == code
    assert src["fzm_floor_finish_name"] == catalog.VARIANTS[code][-1]
    nodes = mat.node_tree.nodes
    pbr = next(n for n in nodes if n.label == catalog.PORCELAIN_LAYOUT_TARGET)
    active = pbr.inputs['Base Color'].links[0].from_node
    assert active.type == 'TEX_IMAGE' and active.image.packed_file and active.extension == 'EXTEND'
    assert active.image.size[0] > 100 and active.image.size[1] > 100
    assert code in active.image.name and 'r2' in active.image.name
    assert tuple(active.image.size)==(1254,1254)
    layout = next(n for n in nodes if n.type == 'GROUP' and n.node_tree.get('fzm_metric_tile_group') == 2)
    colrow = next(n for n in nodes if n.type == 'COMBXYZ' and n.inputs[0].is_linked
                  and n.inputs[0].links[0].from_socket == layout.outputs['Tile Column'])
    assert colrow.inputs[1].links[0].from_socket == layout.outputs['Tile Row']
    assert any(n.type == 'SEPXYZ' and n.inputs[0].is_linked
               and n.inputs[0].links[0].from_socket == layout.outputs['Tile UV'] for n in nodes)
    assert layout.inputs['Cycle'].default_value == {'STACK':1., 'HALF':2., 'THIRD':3.}[pattern]
    assert ('Mosaic '+expect_shape in layout.node_tree.name) == (expect_shape in {'HEX','PENNY'})
    return layout

def geometry(o):
    return tuple((tuple(v.co),) for v in o.data.vertices), tuple(tuple(f.vertices) for f in o.data.polygons)

for o in list(bpy.context.scene.objects):
    bpy.data.objects.remove(o,do_unlink=True)
controls = [('WHITE_GREY_VEINS','05','STACK'),('WHITE_GREY_VEINS_06','06','HALF'),('WHITE_GREY_VEINS_07','07','THIRD')]
floors=[]
for i,(preset,code,pattern) in enumerate(controls):
    o = slab('Floor '+code,i*2.15)
    floors.append(o)
    g = geometry(o)
    select(o)
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG',preset=preset)=={'FINISHED'}
    assert o.material_slots[0].material[catalog.PORCELAIN_TAG]==code
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern=pattern,tile_width=.50,tile_height=.32,
        grout=.006,angle=.16,offset_u=-.12,offset_v=.03)=={'FINISHED'}
    m=o.material_slots[0].material
    actual_faces(m,code,pattern)
    assert geometry(o)==g
    prior=asdict(tiles.get_spec(o))
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG',preset=preset)=={'FINISHED'}
    assert asdict(tiles.get_spec(o))==prior
    actual_faces(o.material_slots[0].material,code,pattern)
    for shape in ('SQUARE','HEX','PENNY'):
        assert bpy.ops.fzm_builder.floor_tile_layout(pattern='STACK',tile_shape=shape,mosaic_size=.04)=={'FINISHED'}
        actual_faces(o.material_slots[0].material,code,'STACK',shape)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern=pattern,tile_width=.50,tile_height=.32,
        grout=.006,angle=0.,offset_u=0.,offset_v=0.)=={'FINISHED'}

a=wall('Left Wall',(0,0,0),(0,2.6,0))
b=wall('Back Wall',(0,2.6,0),(2.4,2.6,0))
c=wall('Right Wall',(2.4,0,0),(2.4,2.6,0))
select(c,a,b)
for preset,code,pattern in controls:
    assert bpy.ops.fzm_builder.shower_area(pattern=pattern,tile_width=.45,tile_height=.22,grout=.004,
        height_1=2.,height_2=2.15,height_3=2.05,lining=.0127,tile_finish=preset)=={'FINISHED'}
    ctl=bpy.context.active_object
    assert ctl[shower.OPTIONS]['finish']==preset
    panels=[o for o in ctl.children if o.get(shower.PART)]
    assert len(panels)==3
    assert len({o.data.materials[0] for o in panels})==1
    actual_faces(panels[0].data.materials[0],code,pattern)

with TemporaryDirectory() as t:
    path=Path(t)
    bpy.ops.wm.save_as_mainfile(filepath=str(path/'portability.blend'))
    # Load a new project state and verify every material retains packed data,
    # and that previously selected wall finish restores via its original key.
    bpy.ops.wm.open_mainfile(filepath=str(path/'portability.blend'))
    for _,code,pattern in controls:
        actual_faces(bpy.data.objects['Floor '+code].material_slots[0].material,code,pattern)
    root=next(o for o in bpy.context.scene.objects if o.get(shower.AREA))
    assert root[shower.OPTIONS]['finish']=='WHITE_GREY_VEINS_07'
    panels=[o for o in root.children if o.get(shower.PART)]
    actual_faces(panels[0].data.materials[0],'07','THIRD')
    # Stock procedural beige and custom solid finishes still use the unchanged family.
    o=bpy.data.objects['Floor 05']
    select(o)
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG',preset='WHITE_BEIGE_VEINS')=={'FINISHED'}
    m=o.material_slots[0].material
    assert not m.get(catalog.PORCELAIN_TAG)
    assert any(n.type=='TEX_WAVE' for n in m.node_tree.nodes)
    assert bpy.ops.fzm_builder.floor_finish(mode='COLOR',color=(.4,.5,.6,1.))=={'FINISHED'}
    assert not o.material_slots[0].material.get(catalog.PORCELAIN_TAG)
    assert bpy.ops.fzm_builder.floor_tile_layout(pattern='NONE')=={'FINISHED'}
    assert not tiles.get_spec(o)
print('PASS 3 Floor Finish and Wall Tiles variants, stack/brick, all mosaics, unchanged slab geometry, packed save/reopen and non-marble presets')
