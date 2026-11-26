"""Blender integration smoke for hinged poses, non-destructive casing batches and reload."""
from importlib import import_module
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

from mathutils import Vector

base = run_path(str(Path(__file__).with_name('smoke_native_doors.py')))
bpy, hb, nd, doors, active, wall, build, new, near, stats, volume, inset = (
    base[n] for n in ('bpy','hb_types','nd','doors','active','wall','build_fixture',
                      'new','near','stats','volume','inset_panel_volumes'))
hd = import_module(base['package']+'.operators.hinged_doors')
fin = import_module(base['package']+'.operators.finishes')
edit = bpy.ops.home_builder_doors_windows.door_prompts
casing = bpy.ops.fzm_builder.door_casing


def select(*objs):
    prev=bpy.context.selected_objects
    for o in prev:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active=objs[-1] if objs else None


def case(obj):
    return next((c for c in obj.children if c.get(fin.CASING)),None)


def bounds(obj):
    mesh=base['evaluated_mesh'](obj)
    return tuple(tuple(fn(v.co[i] for v in mesh.vertices) for i in range(3)) for fn in (min,max))


def test(tmp):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    scene=bpy.context.scene
    room=wall(length=12,thickness=.15)
    distant=wall(length=7,thickness=.115,height=2.60,y=5.)
    one=build(doors.home_builder_doors_windows_OT_place_door,room,.5)
    two=build(doors.home_builder_doors_windows_OT_place_double_door,room,3.1)
    plain=build(doors.home_builder_doors_windows_OT_place_open_door,room,6.5)
    closet, closet_leaf, ok, _ = new(room,'BYPASS',8.05,w=1.3)
    assert ok
    outside=build(doors.home_builder_doors_windows_OT_place_door,distant,.45)
    one.name,two.name,plain.name,closet.name,outside.name='Single','Pair','Open','Closet','Other Wall'
    a,b=hd.visual_for(one),hd.visual_for(two)
    assert a and b and len(a.modifiers)==1 and len(b.modifiers)==1
    assert not hd.visual_for(plain) and not hd.visual_for(closet)
    assert one.display_type=='WIRE' and not one.show_in_front
    scene.home_builder.show_entry_door_and_window_cages=False
    scene.home_builder.show_entry_door_and_window_cages=True
    assert one.display_type=='WIRE' and not one.show_in_front
    assert plain.display_type=='TEXTURED'
    aperture=hb.GeoNodeCage(one)
    w,h,d=(aperture.get_input(k) for k in ('Dim X','Dim Z','Dim Y'))
    wall0=volume(room)
    mod0=tuple(m.object for m in room.modifiers if m.type=='BOOLEAN')
    _,lo,hi,mats=stats(a)
    assert mats=={'white'}
    near(lo[0],.004); near(hi[0],w-.004)
    near(lo[2],.011); near(hi[2],h-.005)
    assert lo[1]>=-1e-6 and hi[1]<=d+1.e-6, (lo,hi,d)
    active(a)
    for style,count in (('SHAKER',1),('SHAKER_2',2),('SHAKER_5',5),('SIX_PANEL',6)):
        assert edit(leaf_style=style)=={'FINISHED'}
        assert len(inset(a))==count,(style,len(inset(a)))
        assert hd.visual_for(one)==a
        assert hd.options(two)==(True,'FLAT',0.)
        assert one.location.x==.5 and aperture.get_input('Dim X')==w and aperture.get_input('Dim Z')==h
        near(volume(room),wall0)
    assert edit(leaf_style='SHAKER_5',opening_amount=1.)=={'FINISHED'}
    s=hd.swing_for(one)
    if not s.get_input('Is Left'):
        assert bpy.ops.home_builder_doors_windows.flip_door_hand()=={'FINISHED'}
    if not s.get_input('Swing Inside'):
        assert bpy.ops.home_builder_doors_windows.flip_door_swing()=={'FINISHED'}
    _,lo,hi,_=stats(a)
    assert s.get_input('Swing Inside') and s.get_input('Is Left')
    assert hi[0] > w-.008 and lo[0] > w-.05
    assert lo[1] < -.65 and hi[1]<1e-6
    assert bpy.ops.home_builder_doors_windows.flip_door_hand()=={'FINISHED'}
    _,lo,hi,_=stats(a)
    assert hi[0]<.05 and lo[1]<-.65 and hi[1]<1e-6
    assert bpy.ops.home_builder_doors_windows.flip_door_swing()=={'FINISHED'}
    _,lo,hi,_=stats(a)
    assert hi[0]<.05 and lo[1]>=d-1e-6 and hi[1]>d+.65
    assert bpy.ops.home_builder_doors_windows.toggle_double_door()=={'FINISHED'}
    _,lo,hi,_=stats(a)
    assert hi[0]>w-.008 and lo[0]<.01 and len(inset(a))==10
    assert bpy.ops.home_builder_doors_windows.toggle_double_door()=={'FINISHED'}
    assert edit(door_width=.02,leaf_style='FLAT')=={'CANCELLED'}
    assert hd.options(one)==(True,'SHAKER_5',1.) and aperture.get_input('Dim X')==w
    assert edit(show_leaf=False)=={'FINISHED'}
    assert not hd.visual_for(one) and one.display_type=='TEXTURED' and one.show_in_front
    assert hd.options(one)==(False,'SHAKER_5',1.)
    active(one)
    assert edit(show_leaf=True,opening_amount=0.)=={'FINISHED'}
    a=hd.visual_for(one)
    assert len(inset(a))==5
    active(plain)
    assert edit(show_leaf=True)=={'CANCELLED'}
    assert not hd.visual_for(plain)
    active(b)
    assert edit(leaf_style='SHAKER_2',opening_amount=.20)=={'FINISHED'}
    assert len(inset(b))==4
    near(volume(room),wall0)
    assert tuple(m.object for m in room.modifiers if m.type=='BOOLEAN')==mod0

    select(one,a,b,plain,room)
    assert casing(profile='COLONIAL',width=.068,projection=.020)=={'FINISHED'}
    cases=[case(o) for o in (one,two,plain)]
    assert all(c and c['profile']=='COLONIAL' and c['fzm_casing_profile_revision']==2 for c in cases)
    assert not case(closet) and not case(outside)
    assert len([o for o in bpy.context.scene.objects if o.get(fin.CASING)])==3
    assert len(fin.CASING_PROFILES['COLONIAL']) > 25
    assert fin.PROFILES['COLONIAL'] != fin.CASING_PROFILES['COLONIAL'] # baseboard unaffected
    for door,case_obj in zip((one,two,plain),cases):
        cage=hb.GeoNodeCage(door)
        lo,hi=bounds(case_obj)
        near(lo[0],-.068)
        near(hi[0],cage.get_input('Dim X')+.068)
        near(hi[2],cage.get_input('Dim Z')+.068)
        assert case_obj.parent==door
        assert volume(case_obj)>0
    active(a)
    assert edit(door_width=w+.075,door_height=h+.04)=={'FINISHED'}
    assert case(one)==cases[0]
    _,hi=bounds(cases[0])
    near(hi[0],w+.075+.068); near(hi[2],h+.04+.068)
    a2=hd.visual_for(one)
    _,loa2,hia2,_=stats(a2)
    near(hia2[0],w+.075-.004); near(hia2[2],h+.04-.005)
    assert case(two)==cases[1]
    near(bounds(cases[1])[1][0],hb.GeoNodeCage(two).get_input('Dim X')+.068)

    # All applies only to the current scene, not separately managed rooms.
    off=bpy.data.scenes.new('Unrelated Scene')
    off.collection.objects.link(outside)
    distant.parent=None
    scene.collection.objects.unlink(outside)
    assert outside.name not in scene.objects
    select(closet_leaf)
    assert casing(scope='SCENE',profile='FLAT',width=.063)=={'FINISHED'}
    assert all(case(o)['profile']=='FLAT' for o in (one,two,plain,closet))
    assert not case(outside)
    # Invalid later target prevents partial bulk replacement.
    other=hb.GeoNodeCage()
    other.create('Invalid Door')
    other.obj['IS_ENTRY_DOOR_BP']=True
    other.set_input('Dim X',0.)
    preserved=case(two)
    select(two,other.obj)
    assert casing(profile='COLONIAL')=={'CANCELLED'}
    assert case(two)==preserved
    bpy.data.objects.remove(other.obj,do_unlink=True)
    select(a2,plain)
    assert casing(remove=True)=={'FINISHED'}
    assert not case(one) and not case(plain) and case(two) and case(closet)
    names=(one.name,two.name,a2.name)
    file=tmp/'hinges.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(file))
    bpy.ops.wm.open_mainfile(filepath=str(file))
    one,two,a2=[bpy.data.objects[n] for n in names]
    assert hd.visual_for(one)==a2
    assert case(two) and hd.options(one)==(True,'SHAKER_5',0.)
    select(a2)
    assert edit(leaf_style='SIX_PANEL')=={'FINISHED'} and len(inset(a2))==6
    parent_wall=one.parent
    assert any(m.type=='BOOLEAN' and m.object==one for m in parent_wall.modifiers)
    assert bpy.ops.home_builder_doors_windows.delete_door_window()=={'FINISHED'}
    assert names[0] not in bpy.data.objects and names[2] not in bpy.data.objects
    assert sum(m.type=='BOOLEAN' for m in parent_wall.modifiers)==3
    print('PASS hinged geometry + actual Door Prompts (compatible styles, hand and swing, toggle, resize, removal/reload); '
          'bulk casing selected/dedupe, scene boundaries, independent resizing, failure rollback, old cutters')


with TemporaryDirectory() as temp:
    test(Path(temp))
