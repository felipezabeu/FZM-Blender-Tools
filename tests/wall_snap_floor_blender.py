"""Physical cap and miter snapping plus floor recovery, via installed add-on."""
from importlib import import_module
from math import atan2
import sys
import bpy
from mathutils import Vector

C=bpy.context
pkg=next(k for k in C.preferences.addons.keys() if k.endswith('.fzm_builder'))
types=import_module(pkg+'.hb_types')
outline=import_module(pkg+'.operators.floor_outline')
ui=import_module(pkg+'.ui.wall_edit')
snap=import_module(pkg+'.operators.wall_edit_snap')
edit=import_module(pkg+'.operators.wall_edit')
regions=import_module(pkg+'.operators.floor_regions')
for obj in list(C.scene.objects):
    bpy.data.objects.remove(obj,do_unlink=True)


def wall(name,a,b,origin=(0,0)):
    vec=Vector(b)-Vector(a)
    obj=types.GeoNodeWall()
    obj.create(name)
    for key,val in [('Length',vec.length),('Thickness',.18),('Height',2.5),
                    ('Left Angle',0),('Right Angle',0)]:
        obj.set_input(key,val)
    obj.obj.location=(*Vector(a)+Vector(origin),0)
    obj.obj.rotation_euler.z=atan2(vec.y,vec.x)
    C.view_layer.update()
    return obj


def select(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    C.view_layer.objects.active=obj
    C.view_layer.update()


a=wall('Exterior window wall',(0,0),(6,0))
b=wall('Adjacent wall',(6,.30),(6,4))
c=wall('North',(6,4),(0,4))
d=wall('West',(0,4),(0,0))
win=types.GeoNodeCage()
win.create('Small window')
win.obj['IS_WINDOW_BP']=True
win.obj.parent=a.obj
win.obj.location.x=5
for key,val in [('Dim X',.4),('Dim Y',.18),('Dim Z',.5)]:
    win.set_input(key,val)
assert bpy.ops.home_builder_walls.add_floor()=={'FINISHED'}
root,=[f for f in C.scene.objects if f.get('IS_FLOOR_BP')]
assert root[outline.KIND]==outline.BOUNDS
if 'legacy' in sys.argv:
    for key in (outline.HOSTS,outline.RIM,outline.TRANSFORM):
        del root[key]
select(root)
assert bpy.ops.fzm_builder.update_floor_outline()=={'CANCELLED'}

a.set_input('Right Angle', .34)
C.view_layer.update()
model=edit.SceneGraph.read(C)
guides=[g for g in ui._guides(model,b.obj,'START',C.view_layer) if g.name==a.obj.name]
assert len(guides)==4
evaluated=a.obj.evaluated_get(C.evaluated_depsgraph_get())
points={(round(v.co.x,5),round(v.co.y,5)) for v in evaluated.data.vertices if v.co.z==0}
assert {(round(x,5),round(y,5)) for g in guides for x,y in (g.start,g.end)}==points
_,cap,_,_=guides
goal=tuple((x+y)*.5 for x,y in zip(cap.start,cap.end))
project=lambda p: tuple(v*1000 for v in p)
origin=model.graph.geometry[b.obj].start
hits=snap.candidates((('start',origin),),(goal[0]-origin[0]+.003,goal[1]-origin[1]),guides,'FREE',project)
assert hits[0].kind=='EDGE' and hits[0].guide==cap
corner_hits=snap.candidates((('start',origin),),(cap.end[0]-origin[0]+.002,cap.end[1]-origin[1]+.001),guides,'FREE',project)
assert corner_hits[0].kind=='CORNER' and Vector(corner_hits[0].point)==Vector(cap.end)
model.commit(C,model.checked_plan(b.obj,'START',*hits[0].offset))
assert (b.obj.matrix_world.translation.xy-Vector(hits[0].point)).length<.00005
assert win.obj.parent==a.obj and abs(win.obj.location.x-5)<1e-5
select(root)
assert bpy.ops.fzm_builder.update_floor_outline()=={'FINISHED'}
rim,*_=outline._supported_mesh(root)
assert min(p.x for p in rim)>.1799 and min(p.y for p in rim)>.1799
assert max(p.y for p in rim)<3.8201
assert root[outline.KIND]==outline.LINKED

# Now close an interior wall against the physical inner faces. This produces
# two slabs without filling the wall footprint, despite the offset exterior cap.
wall('Interior partition',(2.9,.18),(2.9,3.82))
select(root)
assert bpy.ops.fzm_builder.update_floor_outline()=={'FINISHED'}
slabs=[f for f in C.scene.objects if f.get('IS_FLOOR_BP')]
assert len(slabs)==2
def owns(point):
    return [f for f in slabs if regions.inside(outline._supported_mesh(f)[0],Vector(point))]
assert len(owns((1,2)))==len(owns((4,2)))==1
assert owns((1,2))!=owns((4,2))
assert not owns((.05,2)) and not owns((2.80,2))
print('PASS: real miter/cap guides, corner preference, window unchanged, real gap rejected, fallback recovered, floor inside walls, closed rooms split.')
