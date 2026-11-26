"""Blender integration smoke for the user-facing Edit Door hardware controls."""
from importlib import import_module
from itertools import product
from math import pi
import os
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from mathutils import Matrix,Vector

x=run_path(str(Path(__file__).with_name('smoke_native_doors.py')))
bpy,hb,nd,doors,active,wall,build,new,near,volume=(x[k] for k in (
    'bpy','hb_types','nd','doors','active','wall','build_fixture','new','near','volume'))
hd=import_module(x['package']+'.operators.hinged_doors')
edit=bpy.ops.fzm_builder.edit_door
toggle=bpy.ops.fzm_builder.toggle_door_pose


def geometry(visual, finish=None):
    bpy.context.view_layer.update()
    mesh=visual.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    vertices={}
    adjacency={}
    finishes=set()
    for poly in mesh.polygons:
        material=mesh.materials[poly.material_index]
        key=material.get(hd.FINISH_MATERIAL) if material else None
        if not key:
            continue
        finishes.add(key)
        for i in poly.vertices:
            vertices[i]=mesh.vertices[i].co.copy()
            adjacency.setdefault(i,set()).update(poly.vertices)
    if finish:
        assert finishes=={finish},finishes
    else:
        assert not finishes,finishes
    components=[]
    while adjacency:
        subset=[]
        remaining=[next(iter(adjacency))]
        while remaining:
            index=remaining.pop()
            if index not in adjacency:
                continue
            remaining.extend(adjacency.pop(index))
            subset.append(vertices[index])
        components.append(subset)
    return list(vertices.values()),components


def spans(points):
    return [max(p[i] for p in points)-min(p[i] for p in points) for i in range(3)]


def mean(points):
    return sum(points,Vector())/len(points)


def check_dialog(target, expect_hardware, expect_finish):
    active(target)
    cls=doors.FZM_OT_edit_door
    got=[]
    layout=SimpleNamespace(prop=lambda self,key,**kw:got.append(key),label=lambda **kw:None,separator=lambda:None)
    modal=SimpleNamespace(layout=layout)
    ctx=SimpleNamespace(object=target,window_manager=SimpleNamespace(invoke_props_dialog=lambda *_a,**_k:{'RUNNING_MODAL'}))
    assert cls.invoke(modal,ctx,None)=={'RUNNING_MODAL'}
    cls.draw(modal,ctx)
    assert ('hardware' in got)==expect_hardware,(got,expect_hardware)
    assert ('hardware_finish' in got)==expect_finish,(got,expect_finish)
    return modal


def do_test(tmp):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    host=wall(length=13,thickness=.15)
    one=build(doors.home_builder_doors_windows_OT_place_door,host,.6)
    pair=build(doors.home_builder_doors_windows_OT_place_double_door,host,3.2)
    empty=build(doors.home_builder_doors_windows_OT_place_open_door,host,6.5)
    native,nv,ok,_=new(host,'POCKET',9.7,w=.94,right=True)
    assert ok
    scene_volume=volume(host)
    cuts=[(m.name,m.object) for m in host.modifiers if m.type=='BOOLEAN']
    av,bv=hd.visual_for(one),hd.visual_for(pair)
    ag,bg=[ob.modifiers[ob.home_builder.mod_name].node_group for ob in (av,bv)]
    assert ag==bg and ag.get('fzm_hinged_door_group')==1
    assert hd.HARDWARE not in one and hd.HARDWARE_FINISH not in one
    geometry(av);geometry(bv)
    modal=check_dialog(av,True,False)
    assert modal.hardware=='NONE' and modal.hardware_finish=='BRUSHED_NICKEL'
    check_dialog(empty,False,False)
    assert edit(hardware='KNOB')=={'CANCELLED'}
    assert not hd.visual_for(empty)
    check_dialog(nv,False,False)
    assert hd.HARDWARE not in native
    active(av)
    assert edit(hinge_hand='RIGHT',swing_direction='INSIDE',leaf_style='SHAKER_5')=={'FINISHED'}
    assert av.modifiers[av.home_builder.mod_name].node_group==ag
    before_drivers={fc.data_path:(fc.driver.variables[0].targets[0].id,fc.driver.variables[0].targets[0].data_path)
                    for fc in av.animation_data.drivers}
    observed={}
    for choice,finish in product(('KNOB','LEVER'),hd.FINISH_VALUES):
        assert edit(hardware=choice,hardware_finish=finish)=={'FINISHED'}
        assert hd.hardware_for(one)==choice and hd.finish_for(one)==finish
        pts,components=geometry(av,finish)
        assert len(components)==6
        outer=max(spans(c)[0] for c in components)
        assert (outer<.052 if choice=='KNOB' else outer>.085),outer
        assert min(v.y for v in pts)<-.035 and max(v.y for v in pts)>.068
        assert len([c for c in components if mean(c).y<0])==3
        assert len([c for c in components if mean(c).y>.034925])==3
        assert max(v.z for v in pts)-min(v.z for v in pts)<.054
        assert all(abs(mean(c).z-.9652)<1e-4 for c in components)
        assert (modal:=check_dialog(av,True,True)).hardware_finish==finish and modal.hardware==choice
        observed[choice,finish]=pts
    assert av.modifiers[av.home_builder.mod_name].node_group.get('fzm_hinged_door_group')==2
    assert bv.modifiers[bv.home_builder.mod_name].node_group==bg
    geometry(bv)
    assert before_drivers=={fc.data_path:(fc.driver.variables[0].targets[0].id,fc.driver.variables[0].targets[0].data_path)
                           for fc in av.animation_data.drivers}
    near(volume(host),scene_volume)
    assert [(m.name,m.object) for m in host.modifiers if m.type=='BOOLEAN']==cuts
    material_names={m.name for m in bpy.data.materials if m.get(hd.FINISH_MATERIAL)}
    assert material_names=={'FZM Hinged Hardware | Black','FZM Hinged Hardware | Brushed Nickel',
                            'FZM Hinged Hardware | Brushed Gold'}
    # Style-only or finish-only edits do not silently alter the other choice.
    assert edit(hardware='KNOB')=={'FINISHED'}
    assert hd.finish_for(one)=='BRUSHED_GOLD'
    _,closed=geometry(av,'BRUSHED_GOLD')
    assert toggle()=={'FINISHED'}
    _,opened=geometry(av,'BRUSHED_GOLD')
    rotation=Matrix.Rotation(-pi/2,3,'Z')
    pivot=Vector((.004,0.,0.))
    for original in closed:
        expected=pivot+rotation@(mean(original)-pivot)
        assert min((mean(moved)-expected).length for moved in opened)<2e-5
    assert toggle()=={'FINISHED'}
    # Reverse hand, change width and height: keep latch-relative location.
    assert edit(width=1.10,height=1.12,hinge_hand='LEFT',swing_direction='OUTSIDE')=={'FINISHED'}
    pts,mirrored=geometry(av,'BRUSHED_GOLD')
    assert max(v.x for v in pts)<.1 and min(v.y for v in pts)>.04 and max(v.y for v in pts)>.18
    assert all(abs(mean(c).z-1.12*.56)<1e-4 for c in mirrored)
    assert hd.options(one)[:2]==(True,'SHAKER_5')
    active(bv)
    for choice,finish in product(('KNOB','LEVER'),hd.FINISH_VALUES):
        assert edit(hardware=choice,hardware_finish=finish,leaf_style='SHAKER_2')=={'FINISHED'}
        pts,both=geometry(bv,finish)
        m=hb.GeoNodeCage(pair).get_input('Dim X')/2
        assert len(both)==12 and sum(mean(c).x<m for c in both)==6
        for comp in both:
            expected=Vector((2*m-mean(comp).x,mean(comp).y,mean(comp).z))
            assert min((mean(other)-expected).length for other in both)<2e-5
    assert edit(swing_direction='INSIDE',opening_amount=.60)=={'FINISHED'}
    pts,both=geometry(bv,'BRUSHED_GOLD')
    assert len(both)==12 and max(v.y for v in pts)<-.35
    assert edit(hardware='NONE')=={'FINISHED'}
    geometry(bv)
    assert hd.finish_for(pair)=='BRUSHED_GOLD'
    # Saved choice survives toggling the entire visual and recreates its geometry.
    active(av)
    assert edit(show_leaf=False)=={'FINISHED'} and not hd.visual_for(one)
    active(one)
    assert edit(show_leaf=True)=={'FINISHED'}
    av=hd.visual_for(one)
    geometry(av,'BRUSHED_GOLD')
    fname=str(tmp/'hinge-hardware.blend'); cname=one.name
    bpy.ops.wm.save_as_mainfile(filepath=fname)
    bpy.ops.wm.open_mainfile(filepath=fname)
    one=bpy.data.objects[cname];av=hd.visual_for(one)
    assert hd.hardware_for(one)=='KNOB' and hd.finish_for(one)=='BRUSHED_GOLD'
    geometry(av,'BRUSHED_GOLD')
    active(av)
    assert edit(hardware_finish='BLACK')=={'FINISHED'}
    geometry(av,'BLACK')
    print('PASS hardware Edit Door layout, both 3 × 2 styles for Single and Double, both sides, exact pose rotation, '
          'hand/resize, old drivers/group isolation, remove/reenable, independent finishes and save/reopen')


def check_previous_file(path):
    bpy.ops.wm.open_mainfile(filepath=path)
    obj=bpy.data.objects['Legacy Hardware Single']
    av=hd.visual_for(obj)
    assert hd.HARDWARE not in obj and hd.HARDWARE_FINISH not in obj
    original=av.modifiers[av.home_builder.mod_name].node_group
    assert original.get('fzm_hinged_door_group')==1 and not original.interface.items_tree.get(hd.HARDWARE_SOCKET)
    geometry(av)
    check_dialog(av,True,False)
    assert edit()=={'FINISHED'}
    assert av.modifiers[av.home_builder.mod_name].node_group==original
    assert edit(hardware='LEVER',hardware_finish='BRUSHED_NICKEL')=={'FINISHED'}
    geometry(av,'BRUSHED_NICKEL')
    print('PASS actual 5.1.11-saved leaf remains unchanged until opting in, and upgrades without loss')


with TemporaryDirectory() as t:
    do_test(Path(t))
if source:=os.getenv('FZM_511_LEGACY_DOOR'):
    check_previous_file(source)
