from math import atan2, hypot, cos, sin
import bpy
from mathutils import Vector
import importlib
package = next((name for name in bpy.context.preferences.addons.keys() if name.endswith('.fzm_builder')), None)
assert package, 'Run against an enabled FZM Builder extension in an isolated Blender profile.'
hb_types = importlib.import_module(package+'.hb_types')
def opmodule(name):
    return importlib.import_module(package+'.operators.'+name)

floor_outline, shower_area, room_paint, finishes, native_doors = map(opmodule,(
    'floor_outline','shower_area','room_paint','finishes','native_doors'))
calculate_wall_miter_angles = opmodule('walls').calculate_wall_miter_angles

def wall(name, start, end, width=.20, kind='Exterior'):
    obj = hb_types.GeoNodeWall()
    obj.create(name)
    dx, dy = end[0]-start[0], end[1]-start[1]
    obj.obj.location = (*start, 0)
    obj.obj.rotation_euler.z = atan2(dy, dx)
    for key,value in {'Length':hypot(dx,dy), 'Thickness':width, 'Height':2.4,
                      'Left Angle':0.,'Right Angle':0.}.items():
        obj.set_input(key,value)
    obj.obj["WALL_TYPE"] = kind
    return obj.obj

def select(*objects):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]
    bpy.context.view_layer.update()

def opening(host, name, x, kind):
    cage=hb_types.GeoNodeCage()
    cage.create(name)
    obj=cage.obj
    obj.parent=host
    obj.location=(x,0.,0. if kind=='DOOR' else .95)
    obj['IS_ENTRY_DOOR_BP' if kind=='DOOR' else 'IS_WINDOW_BP']=True
    for key,value in {'Dim X':.70,'Dim Y':.20,'Dim Z':2.02 if kind=='DOOR' else .72}.items():
        cage.set_input(key,value)
    cut=host.modifiers.new("Boolean_"+name,'BOOLEAN')
    cut.object=obj;cut.operation='DIFFERENCE';cut.solver='EXACT'
    obj.hide_render=True
    part=bpy.data.objects.new('Preserve constrained visual orientation',None)
    bpy.context.collection.objects.link(part)
    part.parent=obj
    part.location=(.37,.22,.11)
    return obj,part

def digest(objects):
    bpy.context.view_layer.update()
    return [(obj.name,obj.parent.name if obj.parent else None,
             tuple(round(x,5) for row in obj.matrix_world for x in row),
             tuple((m.type, getattr(m,'object',None).name if getattr(m,'object',None) else None) for m in obj.modifiers),
             round(hb_types.GeoNodeWall(obj).get_input('Length'),6) if obj.get('IS_WALL_BP') else None)
            for obj in objects]

def scene_walls():
    return [o for o in bpy.context.scene.objects if o.get('IS_WALL_BP')]

host = wall('Long exterior', (0.,0.),(5.,0.))
proper = wall('Right part',(5.,0.),(5.,3.))
back = wall('Rear',(5.,3.),(0.,3.))
left = wall('Left part',(0.,3.),(0.,0.))
hb_types.GeoNodeWall(proper).connect_to_wall(hb_types.GeoNodeWall(host))
hb_types.GeoNodeWall(back).connect_to_wall(hb_types.GeoNodeWall(proper))
hb_types.GeoNodeWall(left).connect_to_wall(hb_types.GeoNodeWall(back))
hb_types.GeoNodeWall(left).obj_x.home_builder.connected_object=host
for obj in scene_walls():
    calculate_wall_miter_angles(obj)
select(host,proper,back,left)
assert bpy.ops.home_builder_walls.add_floor()=={'FINISHED'}
floor=next(o for o in bpy.context.scene.objects if o.get('IS_FLOOR_BP'))
paint = bpy.data.materials.new('Original room accent')
paint.diffuse_color=(.23,.45,.25,1.)
assert room_paint.apply_room(bpy.context,floor,paint)>0
door,dvis=opening(host,'Head opening',.45,'DOOR')
window,wvis=opening(host,'Tail opening',3.25,'WINDOW')
branch=wall('Face-snapped interior',(2.,.20),(2.,1.75),.10,'Interior')
bad=wall('Opening crossing branch',(.7,.20),(.7,1.75),.10,'Interior')
x_cross=wall('Crossing not terminating',(2.75,-1),(2.75,1.8),.10,'Interior')
assert bpy.ops.fzm_builder.shower_area.poll() is False
select(floor,host,proper,back,left)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='SELECTED', height=.093,thickness=.013,
                                          material=paint.name)=={'FINISHED'}
trim=next(o for o in floor.children if o.get(finishes.BASEBOARD))

select(host,bad)
pre=digest([host,proper,door,window,dvis,wvis])
assert bpy.ops.fzm_builder.divide_wall.poll()
assert bpy.ops.fzm_builder.divide_wall()=={'CANCELLED'}
assert digest([host,proper,door,window,dvis,wvis])==pre and len(scene_walls())==7
select(host,x_cross)
assert bpy.ops.fzm_builder.divide_wall()=={'CANCELLED'}
assert digest([host,proper,door,window,dvis,wvis])==pre and len(scene_walls())==7
# An untouched exterior midpoint still cannot be silently tiled.
select(host,branch)
assert bpy.ops.fzm_builder.shower_area()=={'CANCELLED'}
select(host)
assert bpy.ops.fzm_builder.wall_divider(use_end=True,end=1.1)=={'FINISHED'}
select(host,branch)
assert bpy.ops.fzm_builder.divide_wall()=={'CANCELLED'}
select(host)
assert bpy.ops.fzm_builder.wall_divider(clear=True)=={'FINISHED'}
select(host,branch)
pose_head=host.matrix_world.copy(); pose=[o.matrix_world.copy() for o in (proper,door,window,dvis,wvis)]
old = hb_types.GeoNodeWall(host)
orig_left,orig_right=old.get_input('Left Angle'),old.get_input('Right Angle')
assert bpy.ops.fzm_builder.divide_wall()=={'FINISHED'}
tail=bpy.context.object
select(tail)
assert len(scene_walls())==8 and tail!=host
h,t=hb_types.GeoNodeWall(host),hb_types.GeoNodeWall(tail)
bpy.context.view_layer.update()
assert abs(h.get_input('Length')-2.) < 1.e-5
assert abs(t.get_input('Length')-3.) < 1.e-5
assert h.get_input('Left Angle')==orig_left and h.get_input('Right Angle')==0.
assert t.get_input('Left Angle')==0. and t.get_input('Right Angle')==orig_right
assert (tail.matrix_world.translation-Vector((2,0,0))).length<1e-5
assert (t.obj_x.matrix_world.translation-Vector((5,0,0))).length<1e-5
assert (host.matrix_world.translation-pose_head.translation).length<1e-5
assert trim.parent==floor and abs(trim['height']-.093)<1.e-6 and abs(trim['thickness']-.013)<1.e-6
assert trim.data.materials[0]==paint and tail in finishes._wall_refs(trim,bpy.context.scene)
assert t.get_connected_wall('left').obj==host and t.get_connected_wall('right').obj==proper
assert window.parent==tail and door.parent==host
for obj,prior in zip((proper,door,window,dvis,wvis),pose):
    assert all(abs(v-w)<1.e-5 for row,old in zip(obj.matrix_world,prior) for v,w in zip(row,old)),obj.name
assert abs(window.location.x-1.25)<1.e-5
assert {m.object for m in host.modifiers if m.type=='BOOLEAN'}=={door}
assert {m.object for m in tail.modifiers if m.type=='BOOLEAN'}=={window}
assert hb_types.GeoNodeWall(tail).get_input('Thickness')==hb_types.GeoNodeWall(host).get_input('Thickness')
assert tail.get('WALL_TYPE')==host.get('WALL_TYPE')
for obj,expected_end in ((host,2.),(tail,3.)):
    geo=hb_types.GeoNodeWall(obj)
    spans=[r for socket in geo.material_inputs(obj) for r in room_paint.get_regions(geo.get_input(socket))]
    assert any(abs(r.end-expected_end)<.21 and abs(r.start)<.21 and r.floor==floor and r.material==paint for r in spans),(obj.name,spans)
assert {entry['wall'] for entry in floor[floor_outline.HOSTS].values()}.issuperset((tail,host))
select(floor)
assert bpy.ops.fzm_builder.update_floor_outline()=={'FINISHED'}

# Both wall halves now form an end corner with the same face-snapped branch;
# Shower Area picks only the half explicitly selected.
for half in (host,tail):
    select(branch,half)
    assert bpy.ops.fzm_builder.shower_area(tile_finish='LIGHT_TERRAZZO')=={'FINISHED'},half.name
    area=bpy.context.object
    assert {c.get('fzm_shower_wall') for c in area.children if c.get(shower_area.PART)}=={branch,half}
    panel=next(c for c in area.children if c.get('fzm_shower_wall')==half)
    xs=[(panel.matrix_world@v.co).x for v in panel.data.vertices]
    assert (max(xs) <= 2.001 if half==host else min(xs) >= 1.898), (half.name,min(xs),max(xs))
    if half==tail:
        select(panel)
        assert bpy.ops.fzm_builder.wall_divider(use_end=True,end=1.1)=={'FINISHED'}
        assert bpy.ops.fzm_builder.wall_divider(clear=True)=={'FINISHED'}
        # A bench can use the new matched corner path.
        assert bpy.ops.fzm_builder.shower_fixture(kind='BENCH',offset=.45,width=.35,depth=.22)=={'FINISHED'}
    shower_area.remove_controller(bpy.context,area)
print('PASS structural T with real Builder objects: explicit split, left cap/miter and right successor, door and window Boolean/world transforms, paint, floor association, either Wall Tiles half, Wall Divider and bench; rejects opening crossing and X.')


# Rotated room, opposite wall face and backwards branch. Pocket travel counts
# even where the actual Boolean opening itself does not touch the new joint.
def transform(p):
    c,s=cos(.419),sin(.419)
    return (12.+c*p[0]-s*p[1],7.+s*p[0]+c*p[1])

long_rot = wall('Rotated long',transform((0.,0.)),transform((6.,0.)))
branch_rot = wall('Backwards interior',transform((3.,-2.)),transform((3.,0.)),.10,'Interior')
pocket,_ = opening(long_rot,'Pocket extents',2.,'DOOR')
cage=hb_types.GeoNodeCage(pocket)
native_doors.create_visual(cage,'POCKET','FLAT',.4,True)
select(long_rot,branch_rot)
pre=digest([long_rot,pocket])
assert bpy.ops.fzm_builder.divide_wall()=={'CANCELLED'}
assert digest([long_rot,pocket])==pre
select(long_rot)
bpy.data.objects.remove(pocket,do_unlink=True)
mod = long_rot.modifiers.get('Boolean_Pocket extents')
if mod is not None:
    long_rot.modifiers.remove(mod)
select(long_rot,branch_rot)
assert bpy.ops.fzm_builder.divide_wall()=={'FINISHED'}
rot_tail=bpy.context.object
assert (rot_tail.matrix_world.translation-Vector((*transform((3.,0.)),0.))).length<3e-5
select(branch_rot,rot_tail)
assert bpy.ops.fzm_builder.shower_area()=={'FINISHED'}
print('PASS rotated host and backwards branch; rejects native pocket travel across the split while leaving opening unchanged.')
