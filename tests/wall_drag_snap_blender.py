"""Exercise the viewport modal update on real walls and real wall baseboards."""
from importlib import import_module
from math import atan2, isclose
from types import SimpleNamespace
import bpy
from mathutils import Vector

C = bpy.context
pkg = next(k for k in C.preferences.addons.keys() if k.endswith('.fzm_builder'))
hb = import_module(pkg+'.hb_types')
ui = import_module(pkg+'.ui.wall_edit')
finish = import_module(pkg+'.operators.finishes')
edit = import_module(pkg+'.operators.wall_edit')


def wall(name, a, b, thickness=.18, z=0):
    delta = Vector(b)-Vector(a)
    w = hb.GeoNodeWall()
    w.create(name)
    for key,val in [('Length',delta.length),('Thickness',thickness),('Height',2.5),
                    ('Left Angle',0),('Right Angle',0)]:
        w.set_input(key,val)
    w.obj.location=(*a,z)
    w.obj.rotation_euler.z=atan2(delta.y,delta.x)
    C.view_layer.update()
    return w.obj


def select(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    C.view_layer.objects.active=o
    C.view_layer.update()


receiving=wall('T receiving wall',(0,0),(5,0))
branch=wall('Wall being dragged',(2.2,1.8),(2.27,.38))
above=wall('Wall from another floor',(0,.31),(5,.31),z=3.)
hidden=wall('Not visible',(0,.32),(5,.32))
hidden.hide_set(True)
fake=wall('Nonphysical layout wall',(0,.34),(5,.34))
fake['IS_FAKE_WALL']=True
select(receiving)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='WALL_FACES',side='SIDE_2',
                                          returns=True,thickness=.06,profile='FLAT')=={'FINISHED'}
trim,=finish.wall_trim_children(receiving)
trim_edge=max((trim.matrix_world @ v.co).y for v in trim.data.vertices)
assert trim_edge>.20,trim_edge
graph=edit.SceneGraph.read(C)
guides=ui._guides(graph,branch,'END',C.view_layer)
assert {g.name for g in guides}=={receiving.name}
assert len(guides)==4
assert sum(g.long_side for g in guides)==2
assert isclose(max(max(g.start[1],g.end[1]) for g in guides),.18,abs_tol=1e-6)

# Send projected cursor locations through the registered modal's update, not
# only directly into the mathematical helper. Region projection is stubbed
# for reproducible pixels; the edit plan below is the real Blender plan.
real_ground,real_pixels,real_project=ui._on_ground,ui._pixels,ui._project_targets
def drag(obj, target, *, mode='END', S=True, Q=True, axis='FREE', ui_scale=1.):
    global graph
    graph=edit.SceneGraph.read(C)
    seg=graph.graph.geometry[obj]
    ref,end=(seg.start,seg.end) if mode=='START' else (seg.end,seg.start)
    hints=[]
    op=SimpleNamespace(typed_distance='',axis=axis,anchor=Vector((*ref,0.)),
                       region=None,rv3d=None,level=0,
                       model=graph,wall=obj,edit_mode=mode,
                       guides=ui._guides(graph,obj,mode,C.view_layer),
                       right_angles=ui._square_guides(graph,obj,mode),fixed_end=end,
                       snap_enabled=S,square_enabled=Q,
                       anchors=((mode.lower(),ref),),_hint=hints.append)
    ui._on_ground=lambda *args:Vector((*target,0.))
    ui._pixels=lambda *args:None
    ui._project_targets=lambda _, p:tuple(x*1000 for x in p)
    context=SimpleNamespace(preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=ui_scale)))
    try:
        ui.FZM_OT_edit_wall._update(op,context,SimpleNamespace(ctrl=False))
    finally:
        ui._on_ground,ui._pixels,ui._project_targets=real_ground,real_pixels,real_project
    assert not op.error, hints
    return op,hints[-1],op.plan[obj][edit.START if mode=='START' else edit.END]


def close(x,y):
    return (Vector(x)-Vector(y)).length < 1e-6


op,h,pt=drag(branch,(2.22,trim_edge-.001))
assert close(pt,(2.22,trim_edge-.001)) and op.snap_hit is None and op.edge_square_marker is None
op,h,pt=drag(branch,(2.207,.189),Q=False)
assert close(pt,(2.207,.18)) and op.snap_hit.kind=='EDGE'
op,h,pt=drag(branch,(2.207,.189))
assert close(pt,(2.2,.18)) and op.edge_square_marker and h=='90° to T receiving wall edge'
assert close(op.edge_square_marker[0],pt)
assert abs(Vector(op.edge_square_marker[1]).dot(Vector(op.edge_square_marker[2])))<1e-6
_,_,pt=drag(branch,(2.205,.189),S=False)
assert close(pt,(2.2,.18))
_,_,pt=drag(branch,(2.205,.189),S=False,Q=False)
assert close(pt,(2.205,.189))
op,h,pt=drag(branch,(2.27,.189),axis='Y')
assert close(pt,(2.27,.18)) and op.edge_square_marker is None  # Axis has priority.

# Commit the actual winning plan; the tool still doesn't create a graph link.
op,h,pt=drag(branch,(2.206,.190))
op.model.commit(C,op.plan)
after=edit.SceneGraph.read(C)
assert close(after.graph.geometry[branch].end,(2.2,.18))
assert after.graph.members[branch,edit.END]=={(branch,edit.END)}

# Test a rotated mitered target and drag the START rather than the END.
host2=wall('Rotated target',(10,1),(14,3))
hb.GeoNodeWall(host2).set_input('Left Angle',.28)
hb.GeoNodeWall(host2).set_input('Right Angle',-.15)
t=Vector((2,1)).normalized()
n=Vector((-t.y,t.x))
point=Vector((12,2))+n*.18
anchor=point+n*1.6
slanted=wall('Reversed-end target',point+n*.13+t*.03,anchor)
op,h,pt=drag(slanted,point+n*.007+t*.004,mode='START')
assert close(pt,point) and op.edge_square_marker and h=='90° to Rotated target edge'

# More than one guide may be very close in screen space, but a perpendicular
# beyond the actual face must not snap to an infinitely extended wall.
tip=wall('Out past the wall',(15,3.63),(15,4.75))
_,_,pt=drag(tip,(14.001,3.005),mode='START',S=False)
assert close(pt,(14.001,3.005))

# Original Q snapping still works on an actually connected joint.
linked1=wall('Connected one',(20,0),(22,0))
linked2=wall('Connected two',(22,0),(22.07,2))
hb.GeoNodeWall(linked1).obj_x.home_builder.connected_object=linked2
op,h,pt=drag(linked2,(22.008,2),S=False)
assert close(pt,(22.,2.)) and h=='90° to Connected one' and op.edge_square_marker is None

print('PASS: viewport drag with real rodapés, exact new T-angle, both ends, miter/rotation, caps, filters, axis lock, old connected angle, no new links')
