"""Run via Blender 5.1.2: -b --python-exit-code 1 --python this.py -- CASE."""
from collections import Counter
import math
import sys

import bpy
from mathutils import Vector

pkg = next(k for k in bpy.context.preferences.addons.keys() if k.endswith('.fzm_builder'))
hb_types = __import__(pkg+'.hb_types', fromlist=[''])
regions = __import__(pkg+'.operators.floor_regions', fromlist=[''])
outline = __import__(pkg+'.operators.floor_outline', fromlist=[''])
finishes = __import__(pkg+'.operators.finishes', fromlist=[''])

case=sys.argv[sys.argv.index('--')+1]
scene = bpy.context.scene
context = bpy.context
for obj in list(scene.objects):
    bpy.data.objects.remove(obj,do_unlink=True)


def wall(name, a, b, thickness=.10):
    d = Vector(b) - Vector(a)
    w = hb_types.GeoNodeWall()
    w.create(name)
    w.set_input('Length', d.xy.length)
    w.set_input('Thickness', thickness)
    w.set_input('Height', 2.55)
    w.obj.location = a
    w.obj.rotation_euler.z = math.atan2(d.y,d.x)
    context.view_layer.update()
    return w


def ring(prefix, corners):
    return [wall(f'{prefix} {i}', (*a,0.), (*b,0.))
            for i,(a,b) in enumerate(zip(corners,corners[1:]+corners[:1]))]


def floors():
    return [obj for obj in scene.objects if obj.get('IS_FLOOR_BP')]


def select(obj):
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj


def run(obj, expected='FINISHED'):
    select(obj)
    assert bpy.ops.fzm_builder.update_floor_outline() == {expected}
    context.view_layer.update()


def footprint(obj):
    rings,top,bottom,idx = outline._supported_mesh(obj,multiring=True)
    return [[(obj.matrix_world @ Vector((*p,top))).xy for p in ring] for ring in rings]


def owners(x,y):
    p=Vector((x,y))
    out=[]
    for obj in floors():
        a,*holes=footprint(obj)
        if regions.inside(a,p) and not any(regions.inside(h,p) for h in holes):
            out.append(obj)
    return out


def structure_divide(head, cut):
    endpoint = Vector(head.obj.matrix_world @ Vector((head.get_input('Length'),0,0)))
    center = Vector(head.obj.matrix_world @ Vector((cut,0,0)))
    plan = regions.plan_wall_division_bindings(context,head.obj,cut)
    def bindings():
        return {f.as_pointer(): [(key,row.get('wall').as_pointer(),row.get('reversed'))
                                  for key,row in f.get(outline.HOSTS,{}).items()]
                for f in floors()}
    saved = bindings()
    tail = wall('Structurally divided wall',center,endpoint)
    head.set_input('Length',cut)
    context.view_layer.update()
    regions.apply_wall_division_bindings(plan,head.obj,tail.obj)
    regions.restore_wall_division_bindings(plan)
    assert saved==bindings()
    regions.apply_wall_division_bindings(plan,head.obj,tail.obj)
    return tail.obj


def check_slabs():
    for obj in floors():
        counts=Counter(tuple(sorted(e)) for p in obj.data.polygons for e in p.edge_keys)
        assert set(counts.values())=={2},(case, obj.name, counts)
        assert obj.data.uv_layers.get('UVMap'),obj.name
        for lp in obj.data.loops:
            v=obj.data.vertices[lp.vertex_index].co
            assert (obj.data.uv_layers['UVMap'].data[lp.index].uv-v.xy).length<1e-6


root_walls = ring('Outer',[(0,0),(6,0),(6,4),(0,4)])
if case=='nested-first':
    ring('Nested',[(1,1),(2.5,1),(2.5,2.5),(1,2.5)])
assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
assert len(floors()) == (2 if case=='nested-first' else 1)
root=max(floors(),key=lambda f: abs(regions.area_at_origin(footprint(f)[0])))
source_mat=bpy.data.materials.new('Existing floor finish')
root.data.materials.append(source_mat)
root.material_slots[0].link='OBJECT'
root.material_slots[0].material=source_mat

if case in {'connected','t','cross','door','overlap','repeat-child','mixed','legacy','raised','dangling',
            'structure-first','structure-after','refined','refined-child','removed','paint'}:
    terminal = {'raised': .015, 'dangling': 0.}.get(case,0.)
    y1,y2=(.1,3.90) if case in {'connected','t','repeat-child','mixed','legacy'} else (0.,4.)
    if case=='dangling':
        y2=3.8
    partition=wall('Partition', (3,y1,terminal),(3,y2,terminal))
if case in {'t','cross'}:
    wall('Second Partition', (.1,2,0.),((2.9 if case=='t' else 5.9),2,0.))
if case in {'detached','mixed','bridge'}:
    ring('Nested',[(.8,.8),(2.1,.8),(2.1,2.1),(.8,2.1)])
if case=='bridge':
    wall('Dangling connection to enclosed nested room',(.1,1.5,0.),(.8,1.5,0.))
if case=='structure-first':
    tail = structure_divide(root_walls[0],3.)
    assert any(row.get('wall')==tail for row in root[outline.HOSTS].values())
if case=='legacy':
    for field in (outline.KIND,outline.HOSTS,outline.RIM,outline.TRANSFORM):
        del root[field]
if case in {'door','connected'}:
    select(root)
    assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO') == {'FINISHED'}
    trim=next(obj for obj in root.children if obj.get(finishes.BASEBOARD))
    old_trim=trim.data

if case=='door':
    # Exact cage, actual host Boolean and real center threshold for an
    # Opening (with no visual Door Leaf).
    c=hb_types.GeoNodeCage()
    c.create('Builder Opening')
    c.obj['IS_ENTRY_DOOR_BP']=True
    c.set_input('Dim X',.8)
    c.set_input('Dim Y',.10)
    c.set_input('Dim Z',2.1)
    c.obj.parent=partition.obj
    c.obj.location=(1.2,0,0)
    mod=partition.obj.modifiers.new('Opening','BOOLEAN')
    mod.object=c.obj
    mod.operation='DIFFERENCE'
    finishes.make_casing(context,c.obj,'COLONIAL',.06,.012,None)
    context.view_layer.update()

if case=='manual':
    select(root)
    assert bpy.ops.fzm_builder.floor_divider(first=(2.5,0),second=(2.5,4)) == {'FINISHED'}
    assert len(floors())==2 and all(obj.get(outline.KIND)==outline.DIVIDED for obj in floors())
    wall('Ignored new wall', (3,0,0.),(3,4,0.))
    before={obj.as_pointer():obj.data.as_pointer() for obj in floors()}
    for obj in floors():
        run(obj,'CANCELLED')
    assert before=={obj.as_pointer():obj.data.as_pointer() for obj in floors()}
    print('PASS',case,'manual no-wall split preserved'); sys.exit(0)
if case=='overlap':
    other=root.copy()
    other.data=root.data.copy()
    context.collection.objects.link(other)
    scene_meshes=tuple(obj.data for obj in floors())
    run(root,'CANCELLED')
    assert scene_meshes==tuple(obj.data for obj in floors())
    print('PASS',case); sys.exit(0)
if case=='nested-first':
    other=next(obj for obj in floors() if obj!=root)
    custom=bpy.data.materials.new('Existing independent finish')
    other.data.materials.append(custom)
    run(root)
    assert len(floors())==2 and other in floors()
    assert other.material_slots[0].material==custom and other.get(regions.ROOT)==root
    assert owners(1.5,1.5)==[other] and owners(3.5,2.5)==[root]
    assert not owners(1.05,1.5), "Nested slab and surrounding hole leave the wall footprint free."
    print('PASS',case,'independent Add Floor room adopted without duplicate slabs'); sys.exit(0)

old_key=root.as_pointer()
run(root)
sizes={'connected':2,'t':3,'cross':4,'door':2,'detached':2,'mixed':3,
       'repeat-child':2,'legacy':2,'raised':1,'dangling':1,'empty':1,'bridge':2,
       'structure-first':2,'structure-after':2,'refined':2,'refined-child':2,'removed':2,'paint':2}
assert len(floors()) == sizes[case],(case,len(floors()),[f.name for f in floors()])
assert root.as_pointer()==old_key and root.material_slots[0].material==source_mat
assert all(obj.material_slots[0].material == source_mat for obj in floors())
check_slabs()
if case in {'connected','legacy','t','cross','door','detached','mixed','repeat-child'}:
    nodes={obj.as_pointer():obj.data.as_pointer() for obj in floors()}
    for obj in floors():
        run(obj)
        assert nodes=={obj.as_pointer():obj.data.as_pointer() for obj in floors()},(case,'not no-op')
if case in {'connected','door'}:
    assert old_trim!=trim.data
    assert any(ref==partition.obj for ref in trim['walls'].values())
    assert len([o for o in root.children if o.get(finishes.BASEBOARD)])==1
if case in {'t','cross'}:
    assert len(owners(1,1))==1 and len(owners(1,3))==1 and owners(1,1)!=owners(1,3)
    assert len(owners(4,1))==1 and len(owners(4,3))==1
    assert (owners(4,1)!=owners(4,3))==(case=='cross')
if case in {'connected','door','t','cross','legacy','repeat-child','mixed'}:
    assert not owners(2.95,2.6)
    assert len(owners(1,2.8))==len(owners(4,2.8))==1
    assert owners(1,2.8)!=owners(4,2.8)
if case=='door':
    on_partition = sorted(v.co[1] for v in trim.data.vertices if abs(2.95-v.co[0]) < .065)
    edge0 = min((abs(value-1.14),value) for value in on_partition)[1]
    edge1 = min((abs(value-2.06),value) for value in on_partition)[1]
    assert abs(edge0-1.14)<1e-4 and abs(edge1-2.06)<1e-4, (edge0,edge1)
    assert len(owners(2.93,1.6))==len(owners(2.97,1.6))==1
    assert owners(2.93,1.6)!=owners(2.97,1.6)
    assert not owners(2.95,2.7)
    pts=[p for obj in floors() for ring in footprint(obj) for p in ring]
    assert sum(abs(p.x-2.95)<1e-5 and abs(p.y-1.2)<1e-5 for p in pts)==2
if case in {'detached','mixed','bridge'}:
    assert len(owners(1,1))==1 and len(owners(2.2,1))==1 and owners(1,1)!=owners(2.2,1)
    assert any(len(footprint(obj))>1 for obj in floors())
if case=='repeat-child':
    child=next(obj for obj in floors() if obj!=root)
    child_material=bpy.data.materials.new('Separate child finish')
    child.material_slots[0].material=child_material
    old=child.data.as_pointer()
    partition.obj.location.x=2.7
    context.view_layer.update()
    run(child)
    assert len(floors())==2 and child.data.as_pointer()!=old and child.material_slots[0].material==child_material
    assert not owners(2.65,2.8)
    check_slabs()
if case in {'structure-after','structure-first'}:
    if case=='structure-after':
        tail = structure_divide(root_walls[0],3.)
    assert all(any(item.get('wall')==tail for item in obj[regions.ENVELOPE].values()) for obj in floors())
    room=owners(4,2.5)[0]
    run(room)
    assert len(floors())==2 and owners(4,2.5)==[room]
    assert any(item.get('wall')==tail for item in room[outline.HOSTS].values())
    check_slabs()
if case in {'refined','refined-child'}:
    known=set(floors())
    owner=root if case=='refined' else next(o for o in known if o!=root)
    mat=bpy.data.materials.new('Independent before another wall')
    owner.material_slots[0].material=mat
    if owner in owners(1,1):
        wall('Further partition',(.1,2,0.),(2.9,2,0.))
    else:
        wall('Further partition',(3,2,0.),(5.9,2,0.))
    run(owner)
    new=set(floors())-known
    assert len(new)==1 and known.issubset(floors())
    assert next(iter(new)).material_slots[0].material==owner.material_slots[0].material==mat
    run(next(iter(new)))
    check_slabs()
if case=='paint':
    rp=__import__(pkg+'.operators.room_paint',fromlist=[''])
    west,east=owners(1,2)[0],owners(4,2)[0]
    for obj,color in ((west,'#D1917A'),(east,'#7A9CD1')):
        select(obj)
        assert bpy.ops.fzm_builder.wall_paint(scope='ROOM', input_mode='HEX', hex_color=color) == {'FINISHED'}
    both = [rp.get_regions(partition.get_input(name))
            for names in rp.SIDE_SOCKETS for name in names if partition.has_input(name)]
    assert len(both)==2 and {series[0].floor for series in both}=={west,east}
    assert len({series[0].material for series in both})==2 and all(len(series)==1 for series in both)
if case=='removed':
    known={obj.as_pointer():obj.data.as_pointer() for obj in floors()}
    bpy.data.objects.remove(partition.obj,do_unlink=True)
    run(root,'CANCELLED')
    assert known=={obj.as_pointer():obj.data.as_pointer() for obj in floors()}
if case in {'raised','dangling'}:
    assert len(owners(2.95,2.6))==1
print('PASS',case,len(floors()),'slabs')
