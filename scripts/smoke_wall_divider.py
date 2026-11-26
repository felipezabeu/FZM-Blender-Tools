"""Blender 5.1 integration: width clipping and compatibility with existing saves.

For a real previous-version save, run this script twice (same absolute paths):
  FZM_DIVIDER_LEGACY_SOURCE=/path/to/5.1.8 FZM_DIVIDER_SEED=/tmp/legacy.blend blender -b --python-exit-code 1 --python scripts/smoke_wall_divider.py
  FZM_DIVIDER_SEED=/tmp/legacy.blend blender -b --python-exit-code 1 --python scripts/smoke_wall_divider.py
A normal run synthesizes the old metadata if no genuine legacy seed is supplied.
"""
from importlib import import_module
from math import atan2, isclose
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import addon_utils
import bpy
from mathutils import Vector


BASE = Path(__file__).resolve().parents[1]
legacy = os.environ.get('FZM_DIVIDER_LEGACY_SOURCE')
seed = os.environ.get('FZM_DIVIDER_SEED')
package = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if package == 'fzm_builder':
    sys.path.insert(0, str((Path(legacy) if legacy else BASE)/'extensions'))
    addon_utils.enable(package, default_set=True, persistent=True)
hb = import_module(package+'.hb_types')
sh = import_module(package+'.operators.shower_area')
sf = import_module(package+'.operators.shower_fixtures')


def select(*objects):
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[-1]


def wall(name, a, b):
    result = hb.GeoNodeWall()
    result.create(name)
    delta = Vector(b)-Vector(a)
    result.obj.location = a
    result.obj.rotation_euler.z = atan2(delta.y, delta.x)
    result.set_input('Length', delta.length)
    result.set_input('Thickness', .15)
    result.set_input('Height', 2.45)
    bpy.context.view_layer.update()
    return result.obj


def save_seed(filepath):
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    a = wall('A normal path', (0,0,0), (4,0,0))
    b = wall('B reversed path', (4,2.7,0), (4,0,0))

    cage = hb.GeoNodeCage()
    cage.create('Existing door opening')
    cage.obj.parent = a
    cage.obj.location = (1.85,0,0)
    cage.obj['IS_DOOR_BP'] = True
    cage.set_input('Dim X',.5)
    cage.set_input('Dim Y',.15)
    cage.set_input('Dim Z',1.86)
    cut = a.modifiers.new('Existing door cut', 'BOOLEAN')
    cut.object = cage.obj
    cut.operation = 'DIFFERENCE'
    cut.solver = 'EXACT'
    cage.obj.hide_render = True
    select(a,b)
    assert bpy.ops.fzm_builder.shower_area(pattern='THIRD', tile_width=.52)=={'FINISHED'}
    area = bpy.context.active_object
    select(panel(area,a))
    assert bpy.ops.fzm_builder.shower_fixture(kind='NICHE', offset=.65, width=.4,
        bottom=1.1, depth=.075)=={'FINISHED'}
    for p in area.children:
        for key in ('fzm_shower_span_start_m','fzm_shower_span_end_m'):
            if key in p:
                del p[key]
    bpy.ops.wm.save_as_mainfile(filepath=str(filepath))


def panel(area, w):
    return next(o for o in area.children if o.get(sh.PART) and o.get('fzm_shower_wall') == w)


def hit(tile, point, direction):
    transform = tile.matrix_world.inverted()
    return tile.ray_cast(transform@Vector(point),
                         (transform.to_3x3()@Vector(direction)).normalized())[0]


def projected(panel, k):
    values = [(panel.matrix_world @ v.co)[k] for v in panel.data.vertices]
    return min(values), max(values)


def uv_span(panel):
    uv = [r.uv.x for r in panel.data.uv_layers['UVMap'].data]
    return min(uv), max(uv)


def near(a, b):
    assert isclose(a, b, abs_tol=1e-5), (a,b)


def test_legacy(filepath, result_path):
    bpy.ops.wm.open_mainfile(filepath=str(filepath))
    a, b = (bpy.data.objects[name] for name in ('A normal path', 'B reversed path'))
    area = next(o for o in bpy.context.scene.objects if o.get(sh.AREA))
    assert bpy.types.HOME_BUILDER_PT_room_layout_shower.bl_parent_id == 'HOME_BUILDER_PT_room_layout'
    assert len(sh.FZM_OT_shower_area.targets(bpy.context, area)) == 2
    wd = import_module(package+'.operators.wall_divider')
    near(wd._pick_distance(bpy.context,a,Vector((.4,.5,.7)),Vector((0,-1,0))),.4)
    near(wd._pick_distance(bpy.context,b,Vector((3.5,2.,.7)),Vector((1,0,0))),.7)
    assert wd._pick_distance(bpy.context,a,Vector((2.05,.50,.7)),Vector((0,-1,0))) is None
    # The click target is resolved from the first visible mesh, not selection.
    # Select the area controller (the default after creation), then ray-pick
    # the tile face in front of the actual wall, and finally an obstruction.
    select(area)
    origin, direction = Vector((.4,3.,.7)), Vector((0,-1,0))
    first = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(),origin,direction)
    assert first[0] and first[4].get(sh.PART)
    target, station = wd._clicked_boundary(bpy.context,origin,direction)
    assert target == a
    near(station,.4)
    bpy.ops.mesh.primitive_cube_add(size=.28,location=(.4,1.8,.7))
    occluder=bpy.context.active_object
    assert wd._clicked_boundary(bpy.context,origin,direction) is None
    bpy.data.objects.remove(occluder,do_unlink=True)
    bpy.context.view_layer.update()
    assert not a.get(sh.WALL_DIVIDERS) and not b.get(sh.WALL_DIVIDERS)
    old_a, old_b = panel(area,a), panel(area,b)
    assert sh.SPAN_START not in old_a and sh.SPAN_END not in old_b
    saved_material = old_a.data.materials[0]
    niche = next(o for o in bpy.context.scene.objects if o.get(sf.FIXTURE) == 'NICHE')
    old_cutters = [(m.name,m.object) for m in a.modifiers if m.type=='BOOLEAN']
    old_a_min, old_a_max = uv_span(old_a)
    old_b_min, old_b_max = uv_span(old_b)
    near(old_a_max,old_b_min)

    extra = bpy.data.objects.new('Custom tile child',None)
    bpy.context.collection.objects.link(extra)
    extra.parent=old_a
    extra.location=(.8,.2,2.1)
    bpy.context.view_layer.update()
    position = extra.matrix_world.translation.copy()

    # Trim the departure end of the upright wall (start), preserving the actual
    # corner miter and both walls' jointly aligned grout.
    select(old_a)
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.4)=={'FINISHED'}
    left, right = panel(area,a), panel(area,b)
    assert bpy.context.active_object == left and extra.parent == left
    assert (extra.matrix_world.translation-position).length < 1e-5
    origin = Vector((.2,.50,.7))
    first = bpy.context.scene.ray_cast(bpy.context.evaluated_depsgraph_get(),origin,direction)
    assert first[0] and first[4]==a
    target, station = wd._clicked_boundary(bpy.context,origin,direction)
    assert target==a
    near(station,.2)
    near(projected(left,0)[0],.4)
    near(uv_span(left)[0],old_a_min+.4)
    near(uv_span(left)[1],old_a_max)
    near(uv_span(right)[0],old_b_min)
    near(uv_span(right)[1],old_b_max)
    assert left.data.materials[0] == saved_material
    assert not hit(left,(.2,.50,.7),(0,-1,0))          # uncovered start
    assert hit(left,(1.5,.50,.7),(0,-1,0))            # tiling span
    assert not hit(left,(2.05,.50,.7),(0,-1,0))        # preexisting door
    assert not hit(left,(.8,.50,1.2),(0,-1,0))         # existing niche
    assert [(m.name,m.object) for m in a.modifiers if m.type=='BOOLEAN'] == old_cutters

    # Keep the tile immediately beside the physical miter but stop before the
    # end of the *path*; for this reversed wall it is the wall's local START.
    select(b)
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.7)=={'FINISHED'}
    left,right = panel(area,a),panel(area,b)
    near(projected(right,1)[1],2.0)
    near(uv_span(right)[0],old_b_min)
    near(uv_span(right)[1],old_b_max-.7)
    assert bpy.context.active_object == b
    assert len(b.modifiers) == 1  # no physical cuts on B
    # New full-width bench uses this finish span, not the original full wall.
    select(right)
    assert bpy.ops.fzm_builder.shower_fixture(kind='BENCH', full_width=True)=={'FINISHED'}
    bench = bpy.context.active_object
    near(projected(bench,1)[1], 2.)
    assert bench.parent.parent == b

    # Wrong ordering or clipping an existing fixture must not modify bounds,
    # previous panel, actual wall, or the saved recess.
    select(left)
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=1.05)=={'CANCELLED'}
    assert bpy.context.active_object == left and panel(area,a) == left
    assert niche.name in bpy.context.scene.objects
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=2.5,use_end=True,end=2.2)=={'CANCELLED'}
    near(a[sh.WALL_DIVIDERS][0],.4)
    near(projected(panel(area,a),0)[0],.4)
    assert len([o for o in bpy.context.scene.objects if o.get(sh.PART)]) == 2

    # Two interior bounds, then save/reopen and refresh through Shower Area.
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.4,use_end=True,end=3.1)=={'FINISHED'}
    near(projected(panel(area,a),0)[1],3.1)
    bpy.ops.wm.save_as_mainfile(filepath=str(result_path))
    bpy.ops.wm.open_mainfile(filepath=str(result_path))
    a = bpy.data.objects['A normal path']
    area = next(o for o in bpy.context.scene.objects if o.get(sh.AREA))
    select(panel(area,a))
    assert bpy.ops.fzm_builder.shower_area(pattern='HALF',height_1=2.05)=={'FINISHED'}
    left = panel(area,a)
    bpy.context.view_layer.update()
    near(projected(left,0)[0],.4); near(projected(left,0)[1],3.1)
    near(projected(left,2)[1],2.05)
    assert not hit(left,(2.05,.50,.7),(0,-1,0))
    assert not hit(left,(.8,.50,1.2),(0,-1,0))
    select(left)
    assert bpy.ops.fzm_builder.wall_divider(clear=True)=={'FINISHED'}
    left = panel(area,a)
    assert sh.WALL_DIVIDERS not in a
    near(uv_span(left)[0],old_a_min); near(uv_span(left)[1],old_a_max)

    # Declare a divider before making any Shower Area; removal of an area
    # should not change this finish-only preference for recreating it.
    select(area)
    assert bpy.ops.fzm_builder.shower_area(remove=True)=={'FINISHED'}
    select(a)
    assert bpy.ops.fzm_builder.wall_divider(use_end=True,end=3.1)=={'FINISHED'}
    b = bpy.data.objects['B reversed path']
    select(a,b)
    assert bpy.ops.fzm_builder.shower_area()=={'FINISHED'}
    new_area = bpy.context.active_object
    bpy.context.view_layer.update()
    near(projected(panel(new_area,a),0)[1],3.1)
    near(projected(panel(new_area,b),1)[1],2.)
    print('PASS Wall Divider: 5.1.8 fixture compatibility, forward/reverse local spans, real corner UVs,'
          ' door/niche clipping, new bench bounds, rollback, refresh, clear, persistence and dedicated panel')


if legacy:
    assert seed, 'FZM_DIVIDER_SEED required when generating a legacy save'
    save_seed(seed)
else:
    with TemporaryDirectory() as tmp:
        path = Path(seed) if seed else Path(tmp)/'legacy.blend'
        if not seed:
            save_seed(path)
        test_legacy(path, Path(tmp)/'bounded-shower.blend')
