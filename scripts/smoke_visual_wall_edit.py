"""Blender 5.1 regression for connected wall edits through registered Blender operators."""
from importlib import import_module
from math import atan2, pi, isclose
from pathlib import Path
import os
import sys
import tempfile

import addon_utils
import bpy

from mathutils import Vector

package = os.environ.get('FZM_TEST_PACKAGE','fzm_builder')
if package == 'fzm_builder' and package not in bpy.context.preferences.addons:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'extensions'))
    addon_utils.enable(package, default_set=True, persistent=True)
hb = import_module(package + '.hb_types')
walls = import_module(package + '.operators.walls')
solver = import_module(package + '.operators.wall_edit')


def active(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def near(a, b):
    assert isclose(a, b, abs_tol=8e-5), (a, b)


def fresh_wall(name, start, end):
    w=hb.GeoNodeWall()
    w.create(name)
    w.obj.location=start
    d=Vector(end)-Vector(start)
    w.obj.rotation_euler.z=atan2(d.y,d.x)
    for s,n in [('Length',d.length),('Thickness',.15),('Height',2.5)]:
        w.set_input(s,n)
    return w


def fixture():
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    vertices=[(0,0,0),(4,0,0),(4,3,0),(0,3,0)]
    result=[fresh_wall(name,a,b) for name,a,b in zip(('A','B','C','D'),vertices,vertices[1:]+vertices[:1])]
    for i in range(1,4):
        result[i].connect_to_wall(result[i-1])
    result[3].obj_x.home_builder.connected_object=result[0].obj
    foreign=fresh_wall('Independent coincident origin', (4,0,0), (5,-1,0))
    other_level=fresh_wall('Higher floor', (4,0,3), (4,3,3))
    bpy.context.view_layer.update()
    return result, foreign, other_level


def geometry(w):
    return tuple(tuple(p) for p in walls.get_wall_endpoints(w.obj))


def assert_closed(w):
    for a,b in zip(w,w[1:]+w[:1]):
        e,s=geometry(a)[1],geometry(b)[0]
        assert solver.distance(e,s)<1e-5,(a.obj.name,e,s)
    chain=next(c for c in walls.find_wall_chains() if len(c)==4)
    polygon=walls.get_room_boundary_points(chain)
    assert walls.is_closed_loop(polygon),polygon


def close_point(p, v):
    assert solver.distance(p,v)<.00005,(p,v)


def opening(wall, name, key, x, width):
    cage=hb.GeoNodeCage()
    cage.create(name)
    cage.obj[key]=True
    cage.obj.parent=wall.obj
    cage.obj.location=(x,-.01,.05)
    for k,n in [('Dim X',width),('Dim Y',.17),('Dim Z',1.8)]:
        cage.set_input(k,n)
    mod=wall.obj.modifiers.new(name+' cutter','BOOLEAN')
    mod.object=cage.obj
    mod.operation='DIFFERENCE'
    return cage.obj


def main():
    ws, foreign, upstairs = fixture()
    a,b,c,d=ws
    assert_closed(ws)
    orig_foreign,orig_up=geometry(foreign),geometry(upstairs)
    door=opening(a,'Door','IS_ENTRY_DOOR_BP',2.9,.8)
    window=opening(b,'Window','IS_WINDOW_BP',1.,.65)
    bpy.context.view_layer.update()
    door_before=door.matrix_world.translation.copy()
    window_before=window.matrix_world.translation.copy()
    active(b.obj)
    op=bpy.ops.fzm_builder.edit_wall
    assert op(edit_mode='MOVE',x=.6,y=0)=={'FINISHED'}
    close_point(geometry(b)[0],(4.6,0))
    close_point(geometry(b)[1],(4.6,3))
    close_point(geometry(a)[1],(4.6,0))
    close_point(geometry(c)[0],(4.6,3))
    near(door.matrix_world.translation.x,door_before.x)
    near(window.matrix_world.translation.x,window_before.x+.6)
    assert any(m.type=='BOOLEAN' and m.object==window for m in b.obj.modifiers)
    assert any(m.type=='BOOLEAN' and m.object==door for m in a.obj.modifiers)
    assert len(b.obj.constraints)==1 and b.obj.constraints[0].target==a.obj_x
    assert geometry(foreign)==orig_foreign and geometry(upstairs)==orig_up
    assert_closed(ws)
    active(a.obj)
    assert op(edit_mode='START',x=-.5,y=-.2)=={'FINISHED'}
    close_point(geometry(a)[0],(-.5,-.2))
    close_point(geometry(d)[1],(-.5,-.2))
    near(a.get_input('Left Angle'),-d.get_input('Right Angle'))
    assert abs(a.get_input('Left Angle')) > pi/8
    assert_closed(ws)
    active(a.obj)
    before=tuple(geometry(w) for w in ws)
    assert op(edit_mode='END',x=-2.,y=0.)=={'CANCELLED'}
    assert before==tuple(geometry(w) for w in ws)
    active(d.obj)
    assert op(edit_mode='END',x=0.5,y=3.2)=={'CANCELLED'}
    assert before==tuple(geometry(w) for w in ws)
    active(foreign.obj)
    assert op(edit_mode='MOVE',x=.1,y=-.5)=={'FINISHED'}
    close_point(geometry(foreign)[0],(4.1,-.5))
    assert before==tuple(geometry(w) for w in ws)
    assert bpy.ops.home_builder_walls.add_floor()=={'FINISHED'}
    assert len([o for o in bpy.context.scene.objects if o.get('IS_FLOOR_BP')])==1
    with tempfile.TemporaryDirectory() as folder:
        path=str(Path(folder)/'older-connected-walls-edited.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
    ws=[hb.GeoNodeWall(bpy.data.objects[c]) for c in 'ABCD']
    assert_closed(ws)
    a,b,c,d=ws
    assert d.obj_x.home_builder.connected_object==a.obj
    assert b.obj.constraints[0].target==a.obj_x
    active(c.obj)
    branch=fresh_wall('Branch',geometry(c)[1]+(0,),(-1.,3.7,0.))
    branch.connect_to_wall(c)
    bpy.context.view_layer.update()
    assert op(edit_mode='END',x=0.,y=.2)=={'FINISHED'}
    close_point(geometry(c)[1],geometry(d)[0])
    close_point(geometry(c)[1],geometry(branch)[0])
    print('PASS connected four-wall loop, whole-wall move, shared corner, miter, opening safety, independent walls and levels, floor creation, save/reopen and explicit junction')


if __name__=='__main__':
    main()
