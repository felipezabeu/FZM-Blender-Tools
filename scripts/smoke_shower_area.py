"""Blender 5.1.2 integration: shower controller, inner phase, clipping and persistence."""
from importlib import import_module
from math import atan2, isclose
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy
from mathutils import Vector

BASE=Path(__file__).resolve().parents[1]
package=os.environ.get('FZM_TEST_PACKAGE','fzm_builder')
if package=='fzm_builder':
    sys.path.insert(0,str(BASE/'extensions'))
    addon_utils.enable(package,default_set=True,persistent=True)

hb=import_module(package+'.hb_types')
sh=import_module(package+'.operators.shower_area')
ts=import_module(package+'.operators.tile_shader')


def near(a,b,tol=1e-5):
    assert isclose(a,b,abs_tol=tol),(a,b)


def select(*objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active=objs[-1] if objs else None


def buildwall(name,a,b,height=2.45):
    w=hb.GeoNodeWall()
    w.create(name)
    delta=Vector(b)-Vector(a)
    w.obj.location=Vector(a)
    w.obj.rotation_euler.z=atan2(delta.y,delta.x)
    w.set_input('Length',delta.length)
    w.set_input('Height',height)
    w.set_input('Thickness',.15)
    bpy.context.view_layer.update()
    return w.obj


def opening(wall,left,bottom,width,height):
    cage=hb.GeoNodeCage()
    cage.create('Fixture Window Opening')
    cage.obj['IS_WINDOW_BP']=True
    cage.obj.parent=wall; cage.obj.location=(left,0,bottom)
    cage.set_input('Dim X',width); cage.set_input('Dim Y',.15); cage.set_input('Dim Z',height)
    add_cut(wall,cage.obj)
    return cage.obj


def add_cut(wall,obj):
    mod=wall.modifiers.new('Fixture wall cut','BOOLEAN')
    mod.object=obj; mod.operation='DIFFERENCE'; mod.solver='EXACT'
    obj.hide_render=True
    bpy.context.view_layer.update()


def triangle_cut(wall,x,z):
    m=bpy.data.meshes.new('Triangle cutter')
    a=[(x,z),(x+.40,z),(x+.40,z+.42)]
    m.from_pydata([(u,y,v) for y in (-.08,.24) for u,v in a],[],
      [(0,1,2),(5,4,3),(3,4,1,0),(4,5,2,1),(5,3,0,2)])
    m.update()
    o=bpy.data.objects.new('Triangle cutter',m); bpy.context.collection.objects.link(o)
    o.parent=wall; o['IS_WALL_CUTTER']=True
    add_cut(wall,o)
    return o


def parts(c):
    return sorted((o for o in c.children if o.get(sh.PART)),key=lambda o:o['fzm_shower_phase_m'])


def corners_and_phase(panels):
    for i,p in enumerate(panels):
        us=[float(loop.uv.x) for loop in p.data.uv_layers['UVMap'].data]
        near(min(us),p['fzm_shower_phase_m'])
        near(max(us),p['fzm_shower_phase_m']+p['fzm_shower_length_m'])
        if i+1>=len(panels):
            continue
        next_part=panels[i+1]
        # At the miter both objects must reach identical position and U phase.
        end_i=[p.matrix_world @ p.data.vertices[loop.vertex_index].co for loop in p.data.loops
           if abs(p.data.uv_layers['UVMap'].data[loop.index].uv.x-max(us))<1e-6]
        next_uv=next_part.data.uv_layers['UVMap'].data
        start_i=[next_part.matrix_world @ next_part.data.vertices[loop.vertex_index].co for loop in next_part.data.loops
           if abs(next_uv[loop.index].uv.x-max(us))<1e-6]
        assert end_i and start_i
        assert all((v.xy-start_i[0].xy).length<1e-6 for v in end_i)
        near(max(us),next_part['fzm_shower_phase_m'])


def hit_back(obj,x,z):
    inverse=obj.matrix_world.inverted()
    p=inverse@Vector((x,1.80,z))
    q=inverse@Vector((x,1.81,z))
    return obj.ray_cast(p,(q-p).normalized())[0]


def check_clip(back):
    assert hit_back(back,.50,.95)
    assert not hit_back(back,1.15,1.01)
    assert not hit_back(back,1.93,.92)  # inside triangle itself
    assert hit_back(back,1.71,1.15)   # outside triangle despite inside square box
    assert hit_back(back,1.16,1.77)


def test(tmp):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    a=buildwall('Left Wall',(0,0,0),(0,2.6,0))
    b=buildwall('Back Wall',(0,2.6,0),(2.4,2.6,0))
    c=buildwall('Right Reversed Wall',(2.4,0,0),(2.4,2.6,0),height=1.3)
    aperture=opening(b,.95,.86,.45,.43)
    tri=triangle_cut(b,1.68,.80)
    img=bpy.data.images.new('Fixture Tile',width=4,height=4)
    img.pixels=[.5,.22,.1,1]*16
    f=str(tmp/'face.png'); img.filepath_raw=f;img.file_format='PNG';img.save()
    bpy.data.images.remove(img)
    count=len(bpy.context.scene.objects)
    select(c,a,b)
    assert bpy.ops.fzm_builder.shower_area(pattern='HALF',tile_width=.45,tile_height=.22,grout=.004,
        height_1=2,height_2=2.1,height_3=1.6,bottom=.1,filepath=f)=={'FINISHED'}
    root=bpy.context.active_object
    assert root.get(sh.AREA)
    bpy.context.view_layer.update()
    panels=parts(root)
    assert len(panels)==3 and len(bpy.context.scene.objects)==count+4
    assert [o['fzm_shower_wall'] for o in panels]==[a,b,c]
    corners_and_phase(panels)
    heights=[max(v.co.z for v in p.data.vertices) for p in panels]
    for got,expected in zip(heights,(2.1,2.2,1.3)):
        near(got,expected)
    assert all(len(p.data.polygons)<80 for p in panels)
    check_clip(panels[1])
    assert aperture.parent==b and tri.parent==b
    assert sum(m.type=='BOOLEAN' for m in b.modifiers)==2
    mat=panels[0].data.materials[0]
    assert all(p.data.materials[0]==mat for p in panels)
    n=next(n for n in mat.node_tree.nodes if n.type=='GROUP')
    tex=next(t for t in mat.node_tree.nodes if t.type=='TEX_IMAGE')
    assert tex.image.packed_file and tex.inputs['Vector'].links[0].from_socket==n.outputs['Tile UV']
    assert n.inputs['Cycle'].default_value==2
    select(a,b)
    assert bpy.ops.fzm_builder.shower_area()=={'CANCELLED'}
    assert len([o for o in bpy.context.scene.objects if o.get(sh.AREA)])==1

    user=bpy.data.objects.new('User fixture',None); bpy.context.collection.objects.link(user)
    user.parent=panels[0]; user.location=(.41,1.01,1.30)
    bpy.context.view_layer.update()
    world0=user.matrix_world.translation.copy()
    blend=str(tmp/'shower.blend')
    root_name=root.name
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    Path(f).unlink()
    bpy.ops.wm.open_mainfile(filepath=blend)
    root=bpy.data.objects[root_name]
    assert len(parts(root))==3
    assert root[sh.OPTIONS]['tile']['pattern']=='HALF'
    p=parts(root)[1]
    check_clip(p)
    select(p)
    assert bpy.ops.fzm_builder.shower_area(pattern='STACK',height_2=2.2,filepath=f)=={'FINISHED'}
    bpy.context.view_layer.update()
    panels=parts(root)
    assert len(panels)==3
    assert (bpy.data.objects['User fixture'].matrix_world.translation-world0).length<1e-5
    assert bpy.data.objects['User fixture'].parent is None
    assert bpy.data.objects['User fixture'].name in bpy.context.scene.objects
    assert next(n for n in panels[0].data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE').image.packed_file
    check_clip(panels[1]); corners_and_phase(panels)
    assert bpy.ops.fzm_builder.shower_area(remove=True)=={'FINISHED'}
    assert len([o for o in bpy.context.scene.objects if o.get(sh.PART) or o.get(sh.AREA)])==0
    a,b,c=[bpy.data.objects[name] for name in ('Left Wall','Back Wall','Right Reversed Wall')]
    assert all(obj.name in bpy.context.scene.objects for obj in (a,b,c))

    select(a,b)
    assert bpy.ops.fzm_builder.shower_area(pattern='THIRD',height_1=1.7,height_2=1.3)=={'FINISHED'}
    bpy.context.view_layer.update()
    elbows=parts(bpy.context.active_object)
    assert len(elbows)==2
    corners_and_phase(elbows)
    check_window=elbows[1]
    assert not hit_back(check_window,1.15,1.01)
    d=buildwall('Separated Wall',(8,0,0),(8,2,0))
    select(c,d)
    assert bpy.ops.fzm_builder.shower_area()=={'CANCELLED'}
    assert len([o for o in bpy.context.scene.objects if o.get(sh.AREA)])==1
    print('PASS 2/3-wall interior shower lining, reversed/short wall, two miters & shared phase, rectangular and exact triangular cuts, packed tile-face image, safe edit/reopen/remove and invalid selection')


with TemporaryDirectory() as t:
    test(Path(t))
