"""Blender 5.1+ smoke test: structural walls, old projects, solid tile and fixtures."""
from importlib import import_module
from math import atan2, hypot
import bmesh
import bpy
from mathutils import Vector

addon = next(k for k in bpy.context.preferences.addons.keys() if k.rsplit(".", 1)[-1]=="fzm_builder")
hb = import_module(f"{addon}.hb_types")
sh = import_module(f"{addon}.operators.shower_area")
fx = import_module(f"{addon}.operators.shower_fixtures")
C = bpy.context

for obj in list(C.scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)


def select(*objects):
    for o in C.selected_objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    C.view_layer.objects.active = objects[0]
    C.view_layer.update()


def wall(name, a, b):
    data = hb.GeoNodeWall()
    data.create(name)
    for key,val in {'Length': hypot(b[0]-a[0],b[1]-a[1]), 'Height':2.5, 'Thickness':.1}.items():
        data.set_input(key,val)
    data.obj.location = (*a,0.)
    data.obj.rotation_euler.z = atan2(b[1]-a[1],b[0]-a[0])
    return data.obj


def panel(area, wall):
    return next(p for p in area.children if p.get(sh.PART) and p.get('fzm_shower_wall') == wall)


def coords(item):
    return [item.matrix_world @ v.co for v in item.data.vertices]


def depth_span(item, origin, n):
    across = [(p.xy-origin).dot(n) for p in coords(item)]
    return min(across), max(across)


def assert_shell(item, model, effective):
    near,far = depth_span(item,model[1],model[4])
    assert abs(near)<1e-5 and abs(far-sh.face_offset(effective))<1e-5, (near,far,effective)
    assert abs(item[sh.LINING_THICKNESS]-effective)<1e-7

    bm=bmesh.new()
    try:
        bm.from_mesh(item.data)
        assert all(edge.is_manifold for edge in bm.edges), [e.index for e in bm.edges if not e.is_manifold]
        assert bm.calc_volume(signed=True)>0
    finally:
        bm.free()

    uv=item.data.uv_layers['UVMap']
    normals=item.matrix_world.to_3x3().inverted().transposed()
    for face in item.data.polygons:
        if (normals @ face.normal).xy.dot(model[4]) < .95:
            continue
        for u,v in zip(face.loop_indices, list(face.loop_indices)[1:] + [face.loop_indices[0]]):
            a,b = (item.matrix_world @ item.data.vertices[item.data.loops[i].vertex_index].co for i in (u,v))
            assert abs((uv.data[u].uv-uv.data[v].uv).length-(a-b).length)<3e-6


def close(a,b,tol=1e-5):
    assert abs(a-b)<tol, (a,b)


w1=wall("Tile main",(0,0),(3,0))
w2=wall("Tile return",(3,0),(3,2.6))
select(w1,w2)
assert bpy.ops.fzm_builder.shower_area.get_rna_type().name == 'Wall Tiles'
assert bpy.ops.fzm_builder.shower_area(tile_finish='WHITE_GREY_VEINS',tile_shape='HEX') == {'FINISHED'}
area=C.object
assert area.name=='Wall Tiles'
path,_=sh._ordered_path([w1,w2],[w1,w2])
models,corners=sh._finish_lines(path, sh.face_offset(sh.DEFAULT_THICKNESS))
by_wall={m[0][0]:m for m in models}
for w in (w1,w2):
    assert_shell(panel(area,w),by_wall[w],sh.DEFAULT_THICKNESS)
    one = [p for p in coords(panel(area,w)) if abs(p.z)<1e-6]
    assert min((p.xy-corners[1]).length for p in one)<1e-5, 'front miter meets'
_,back_corners=sh._finish_lines(path, 0.)
for w in (w1,w2):
    one = [p for p in coords(panel(area,w)) if abs(p.z)<1e-6]
    assert min((p.xy-back_corners[1]).length for p in one)<1e-5, 'back miter meets'

select(panel(area,w1))
assert bpy.ops.fzm_builder.shower_fixture(kind='NICHE',offset=1.1,bottom=.95,width=.42,height=.28,depth=.065,override=True) == {'FINISHED'}
recess=C.object.parent
cutter=next(obj for obj in recess.children if obj.get(fx.CUTTER))
recess_front=lambda: max((p.xy-by_wall[w1][1]).dot(by_wall[w1][4]) for p in coords(next(obj for obj in recess.children if obj.get(fx.VISUAL))))
cut_coords=[tuple(p) for p in coords(cutter)]
for w in (w1,w2):
    assert_shell(panel(area,w),by_wall[w],sh.DEFAULT_THICKNESS)
n_open, *_ = panel(area,w1).ray_cast(
    panel(area,w1).matrix_world.inverted() @ Vector((1.3,.5,1.05)), Vector((0,-1,0)))
assert not n_open, 'actual lining hole survives the niche boolean cut'

select(panel(area,w2))
assert bpy.ops.fzm_builder.shower_fixture(kind='BENCH',offset=.8,depth=.35,bottom=.0,width=.55,height=.4) == {'FINISHED'}
bench=C.object.parent
select(area)
assert bpy.ops.fzm_builder.shower_area(lining=.0254, tile_finish='LIGHT_TERRAZZO', tile_shape='PENNY') == {'FINISHED'}
for w in (w1,w2):
    assert_shell(panel(area,w),by_wall[w],.0254)
assert cutter.name in bpy.data.objects and [tuple(p) for p in coords(cutter)]==cut_coords
close(recess_front(),sh.face_offset(.0254))
bench_finish=next(obj for obj in bench.children if obj.get(fx.VISUAL))
near,far=depth_span(bench_finish,by_wall[w2][1],by_wall[w2][4])
close(near,sh.face_offset(.0254)-fx.SKIN)
close(far,sh.face_offset(.0254)+.35)
before=[p.data for p in (panel(area,w1),panel(area,w2))]
assert bpy.ops.fzm_builder.shower_area(lining=.032,bottom=1.) == {'CANCELLED'}
assert [p.data for p in (panel(area,w1),panel(area,w2))] == before
close(area[sh.OPTIONS][sh.LINING_THICKNESS],.0254)
assert [tuple(p) for p in coords(cutter)] == cut_coords

select(panel(area,w1))
assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.25,use_end=True,end=2.4) == {'FINISHED'}
assert_shell(panel(area,w1),by_wall[w1],.0254)
for coordinate, target in zip((min(p.x for p in coords(panel(area,w1))),
                               max(p.x for p in coords(panel(area,w1)))),(.25,2.4)):
    close(coordinate,target)

# Simulate a pre-thickness from-disk area (absence of both persisted keys).
select(area)
assert bpy.ops.fzm_builder.shower_area(remove=True) == {'FINISHED'}
select(w1,w2)
assert bpy.ops.fzm_builder.shower_area(lining=0) == {'FINISHED'}
area=C.object
del area[sh.OPTIONS][sh.LINING_THICKNESS]
legacy={w: [tuple(p) for p in coords(panel(area,w))] for w in (w1,w2)}
for w in (w1,w2):
    del panel(area,w)[sh.LINING_THICKNESS]
sh.rebuild_panels(C,area)
C.view_layer.update()
for w in (w1,w2):
    assert len(coords(panel(area,w)))==len(legacy[w])
    assert all((a-Vector(b)).length<2e-6 for a,b in zip(coords(panel(area,w)),legacy[w]))
    near,far=depth_span(panel(area,w),by_wall[w][1],by_wall[w][4])
    close(near,sh.SEPARATION)
    close(far,sh.SEPARATION)
select(area)
assert bpy.ops.fzm_builder.shower_area(tile_finish='WHITE_PORCELAIN') == {'FINISHED'}
assert sh.lining_thickness(area[sh.OPTIONS]) == 0.
assert bpy.ops.fzm_builder.shower_area(lining=.0127) == {'FINISHED'}
for w in (w1,w2):
    assert_shell(panel(area,w),by_wall[w],.0127)
print("PASS: renamed UI; exact solid wall tile depth, watertight miter, metric UV, niche and bench, preserved blind recess, divider, rollback and legacy thin areas.")
