"""Exercise the registered Add Baseboards on an open T and asymmetric tiles."""
import math
from collections import defaultdict
from importlib import import_module

import bpy

C = bpy.context
addon = next(key for key in C.preferences.addons.keys() if key.endswith('.fzm_builder'))
mod = import_module(addon)
finish = import_module(f'{addon}.operators.finishes')
sh = import_module(f'{addon}.operators.shower_area')


def select(*objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    C.view_layer.objects.active = objects[0]
    C.view_layer.update()


def wall(name, start, end, depth=.1, z=0.):
    w = mod.hb_types.GeoNodeWall()
    w.create(name)
    for label, value in (('Length', math.dist(start,end)), ('Height', 2.4), ('Thickness', depth)):
        w.set_input(label,value)
    w.obj.location = (*start,z)
    w.obj.rotation_euler.z = math.atan2(end[1]-start[1],end[0]-start[0])
    return w.obj


def islands(obj, local=False):
    graph = defaultdict(set)
    for edge in obj.data.edges:
        a,b=edge.vertices
        graph[a].add(b)
        graph[b].add(a)
    vertices=obj.data.vertices
    remaining=set(graph)
    while remaining:
        cluster=[remaining.pop()]
        for i in cluster:
            for j in sorted(graph[i] & remaining):
                remaining.remove(j)
                cluster.append(j)
        yield [(vertices[i].co if local else obj.matrix_world @ vertices[i].co) for i in cluster]


def run_add(side='SIDE_2', returns=True, **kw):
    return bpy.ops.fzm_builder.room_baseboards(
        wall_source='WALL_FACES', side=side, returns=returns, thickness=.016,
        profile='FLAT', **kw)


host=wall('Host', (0,0),(5,0))
right=wall('Right', (5,0),(5,4))
top=wall('Rear', (5,4),(0,4))
left=wall('Left', (0,4),(0,0))
select(host,right,top,left)
assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
floor=next(obj for obj in C.scene.objects if obj.get('IS_FLOOR_BP'))
select(floor)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO') == {'FINISHED'}
room_trim=next(t for t in floor.children if t.get(finish.BASEBOARD))

# Starts on wall datum, so one end is buried in host; other projects into room.
branch=wall('3-foot shower divider', (2,0),(2,.9144))
overhead=wall('Above this level', (2,.9144),(4,.9144),z=3)
select(floor)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO') == {'FINISHED'}
host_spans=[(min(v.x for v in p),max(v.x for v in p)) for p in islands(room_trim)
            if all(abs(v.y-.1)<.03 for v in p)]
assert len(host_spans)==2 and all(not a<1.95<b for a,b in host_spans),host_spans

# Split the host, then tile two connected walls through the real operator.
select(host,branch)
assert bpy.ops.fzm_builder.divide_wall() == {"FINISHED"}
select(host,branch)
assert bpy.ops.fzm_builder.shower_area(lining=.0127) == {"FINISHED"}
area=C.object
panel=next(p for p in area.children if p.get(sh.PART) and p.get("fzm_shower_wall")==branch)
select(branch)
# The tile face may be chosen using the single-wall Wall Tiles flip UI.
if any((panel.matrix_world @ v.co).x < 1.89 for v in panel.data.vertices):
    dry='SIDE_1'
    wet='SIDE_2'
else:
    dry='SIDE_2'
    wet='SIDE_1'
assert run_add(side=dry) == {'FINISHED'}
trim,=finish.wall_trim_children(branch)
pieces=list(islands(trim,True))
assert len(pieces)==2, [(min(v.x for v in p),max(v.x for v in p)) for p in pieces]
assert abs(min(v.x for p in pieces for v in p)-.1)<.00015
assert abs(max(v.x for p in pieces for v in p)-.9304)<.00015
assert len([p for p in pieces if max(v.x for v in p)-min(v.x for v in p) < .02])==1
cap=next(p for p in pieces if max(v.x for v in p)-min(v.x for v in p) < .02)
assert abs(max(v.y for v in cap)-min(v.y for v in cap)-.116)<.0002
assert run_add(side=dry,returns=False) == {'FINISHED'}
assert finish.wall_trim_children(branch)==[trim]
assert len(list(islands(trim)))==1
assert run_add(side='BOTH') == {'FINISHED'}
assert len(list(islands(trim)))==2 # no trim on the tiled side.
assert room_trim.parent == floor

# Setbacks/elevation edits keep the selected wall trim in sync.
select(area)
assert bpy.ops.fzm_builder.shower_area(bottom=.08) == {'FINISHED'}
assert len(list(islands(trim)))==3
select(area)
assert bpy.ops.fzm_builder.shower_area(bottom=0.) == {'FINISHED'}
assert len(list(islands(trim)))==2
select(area)
assert bpy.ops.fzm_builder.shower_area(remove=True) == {'FINISHED'}
assert len(list(islands(trim)))==3

# Change endpoint using the actual edit operator. It carries its return.
select(branch)
assert bpy.ops.fzm_builder.edit_wall(edit_mode='END',x=0,y=.2) == {'FINISHED'}
assert abs(max(v.y for p in islands(trim) for v in p)-1.1304)<.0002

# Even without a floor, an isolated wall gets both free returns.
loose=wall('Freestanding', (7,0),(7,1),z=.25)
select(loose)
assert run_add(side='BOTH') == {'FINISHED'}
other,=finish.wall_trim_children(loose)
assert len(list(islands(other)))==4
assert abs(min(v.z for p in islands(other) for v in p)-.25)<.00015
# A connected butt joint at one end must never get an end cap.
join=wall('Butt continuation', (7,1),(7,2),z=.25)
select(loose)
assert run_add(side='BOTH') == {'FINISHED'}
assert len(list(islands(other)))==3

assert run_add(side='BOTH', remove=True) == {'FINISHED'}
assert not finish.wall_trim_children(loose)
assert finish.wall_trim_children(branch)==[trim]
assert room_trim.parent==floor
# Door casing trims the selected-wall board, not just room-level trim.
long=wall('Door partition', (10,0),(14,0))
door=mod.hb_types.GeoNodeCage()
door.create('Independent opening')
door.obj['IS_ENTRY_DOOR_BP']=True
door.obj.parent=long
door.obj.location.x=1.5
for label,value in [('Dim X',.8),('Dim Y',.1),('Dim Z',2.)]:
    door.set_input(label,value)
select(long)
material=bpy.data.materials.new('Painted white trim')
assert run_add(side='SIDE_1',returns=False,material=material.name) == {'FINISHED'}
part,=finish.wall_trim_children(long)
def xspans(part):
    return sorted(tuple(round(f(v.x for v in p),4) for f in (min,max)) for p in islands(part,True))
assert xspans(part)==[(0.,1.5),(2.3,4.)]
select(door.obj)
assert bpy.ops.fzm_builder.door_casing(scope='SELECTED',width=.075) == {'FINISHED'}
assert xspans(part)==[(0.,1.425),(2.375,4.)]
assert part.material_slots[0].material==material
print('PASS T with no enclosed perimeter; side-specific tile; independent floor trim; free tip thickness; no joined cap; wall edit; toggles/removal')
