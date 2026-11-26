"""Verify four reference shapes through the installed Builder operators."""
from importlib import import_module
from math import isclose

import bmesh
import bpy

C = bpy.context
addon = next(key for key in C.preferences.addons.keys() if key.endswith('.fzm_builder'))
mod = import_module(addon)
finishes = import_module(f'{addon}.operators.finishes')
profiles = import_module(f'{addon}.operators.trim_profiles')
width, height, depth = .8, 2.0, .10
wall = mod.hb_types.GeoNodeWall()
wall.create('Test partition')
for key, value in [('Length',4), ('Thickness',depth), ('Height',2.5)]:
    wall.set_input(key,value)
door = mod.hb_types.GeoNodeCage()
door.create('Door opening')
door.obj.parent = wall.obj
door.obj.location.x = 1.2
door.obj['IS_ENTRY_DOOR_BP'] = True
for key,value in [('Dim X',width),('Dim Y',depth),('Dim Z',height)]:
    door.set_input(key,value)


def select(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    C.view_layer.objects.active = obj
    C.view_layer.update()


def solid(mesh):
    bm=bmesh.new()
    try:
        bm.from_mesh(mesh)
        assert len(bm.faces) and all(f.calc_area() > 1e-10 for f in bm.faces)
        assert all(e.is_manifold for e in bm.edges)
        assert bm.calc_volume() > 0
    finally:
        bm.free()


def close(a,b):
    return isclose(a,b,abs_tol=1e-5)


def verify_casing(casing,w,h,d,section):
    depsgraph = C.evaluated_depsgraph_get()
    mesh=casing.evaluated_get(depsgraph).data
    solid(mesh)
    inner_height, outer_height = section[-1][1], max(p for _,p in section)
    for side in (-1,1):
        y = lambda out: (0 if side<0 else d) + side*(.018*out-.001)
        for a,o in section:
            off=a*.064
            for x,z in [(-off,0.),(-off,h+off),(w+off,h+off),(w+off,0.)]:
                assert any(close(v.co.x,x) and close(v.co.z,z) and close(v.co.y,y(o))
                           for v in mesh.vertices), (side,a,o,x,z)
        assert abs(y(outer_height)-y(inner_height))>.01


for style in ('COLONIAL','STEP_BEVEL'):
    select(door.obj)
    assert bpy.ops.fzm_builder.door_casing(scope='SELECTED',profile=style,width=.064,projection=.018)=={'FINISHED'}
    casing,= [o for o in door.obj.children if o.get(finishes.CASING)]
    assert casing['fzm_casing_profile_revision']==profiles.REVISION
    for w,h,d in [(width,height,depth),(.92,2.14,.14)]:
        for key,value in [('Dim X',w),('Dim Z',h),('Dim Y',d)]:
            door.set_input(key,value)
        C.view_layer.update()
        verify_casing(casing,w,h,d,profiles.CASING_PROFILES[style])

    select(wall.obj)
    assert bpy.ops.fzm_builder.room_baseboards(wall_source='WALL_FACES',
        side='SIDE_1',returns=True,profile=style,height=.14,thickness=.018) == {'FINISHED'}
    trim,=finishes.wall_trim_children(wall.obj)
    assert trim['fzm_baseboard_profile_revision']==profiles.REVISION
    solid(trim.data)
    section=profiles.BASEBOARD_PROFILES[style]
    for up,out in section:
        assert any(close(v.co.x,0.) and close(v.co.z,up*.14) and close(v.co.y,-out*.018)
                   for v in trim.data.vertices) or any(
                   close(v.co.z,up*.14) and close(v.co.y,-out*.018) for v in trim.data.vertices)
    assert close(max(v.co.z for v in trim.data.vertices),.14)
    assert len(section) != len(profiles.LEGACY_BASEBOARD_PROFILES[style])
    # Existing saved board refresh keeps the previous profile until reapplying.
    del trim['fzm_baseboard_profile_revision']
    assert not finishes.refresh_attached_baseboards(C,[wall.obj])
    assert all(any(close(v.co.z,a*.14) for a,_ in profiles.LEGACY_BASEBOARD_PROFILES[style])
               for v in trim.data.vertices)
    assert bpy.ops.fzm_builder.room_baseboards(wall_source='WALL_FACES',
        side='SIDE_1',returns=True,profile=style,height=.14,thickness=.018) == {'FINISHED'}
    assert trim['fzm_baseboard_profile_revision']==profiles.REVISION

assert profiles.baseboard('FLAT',1) == profiles.baseboard('FLAT',profiles.REVISION)
assert profiles.CASING_PROFILES['FLAT'] == profiles.BASEBOARD_PROFILES['FLAT']
print('PASS: four trim cross-sections; both casing faces and miters; driven resizing; watertight runs; legacy and Flat preserved.')
