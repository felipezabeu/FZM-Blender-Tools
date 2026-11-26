"""Run with Blender 5.1: blender -b --python-exit-code 1 --python scripts/smoke_room_baseboards.py."""

from importlib import import_module
from math import atan2
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import addon_utils
import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
package = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if package == 'fzm_builder':
    sys.path.insert(0, str(ROOT / 'extensions'))
fzm_builder = import_module(package)
openings = import_module(package + '.operators.doors_windows')
finishes = import_module(package + '.operators.finishes')
wall_ops = import_module(package + '.operators.walls')


def enable_test_addon():
    if not addon_utils.check(package)[1]:
        addon_utils.enable(package, default_set=True, persistent=True)


def select(*objects):
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.context.view_layer.update()


def create_wall(name, a, b, t=.15):
    wall = fzm_builder.hb_types.GeoNodeWall()
    wall.create(name)
    delta = Vector(b) - Vector(a)
    wall.obj.location = a
    wall.obj.rotation_euler.z = atan2(delta.y, delta.x)
    for key, val in [('Length', delta.length), ('Thickness', t), ('Height', 2.55)]:
        wall.set_input(key, val)
    bpy.context.view_layer.update()
    return wall.obj


def walls(points, prefix='Wall', level=0):
    return [create_wall(f'{prefix}-{i}', (*a, level), (*b, level))
            for i, (a, b) in enumerate(zip(points, points[1:] + points[:1]))]


def mesh_floor(name, points, z=0):
    # Use the same source slab construction as the Add Floor tool.
    o = wall_ops.home_builder_walls_OT_add_floor.create_floor_mesh(
        None, name, [Vector((*p, z)) for p in points + points[:1]],
    )
    o['IS_FLOOR_BP'] = True
    return o


def opening(placement, wall, offset, width, elevation):
    state = SimpleNamespace(
        register_placement_object=lambda obj: None,
        create_placement_dimensions=lambda: None,
    )
    for key in ('OBJECT_NAME', 'BP_FLAG', 'MENU_ID', 'WIDTH_PROP_NAME', 'HEIGHT_PROP_NAME',
                'HAS_SWING', 'INITIAL_SWING_INPUTS', 'TEXT_NAME', 'TEXT_KIND'):
        setattr(state, key, getattr(placement, key))
    placement.create_placed_object(state, bpy.context)
    placed = state.placed_obj
    placed.obj.parent = wall
    placed.obj.location = (offset, 0, elevation)
    placed.set_input('Dim X', width)
    placed.set_input('Dim Y', fzm_builder.hb_types.GeoNodeWall(wall).get_input('Thickness'))
    openings.WallObjectPlacementMixin.cut_wall(state, wall, placed.obj)
    bpy.context.view_layer.update()
    return placed.obj


def trim(floor):
    result = [child for child in floor.children if child.get(finishes.BASEBOARD)]
    assert len(result) == 1 and result[0].type == 'MESH', floor.name
    return result[0]


def coords(obj):
    bpy.context.view_layer.update()
    return [obj.matrix_world @ v.co for v in obj.data.vertices]


def solids(obj):
    """Return one vertex cluster per loft, asserting each is a closed solid."""
    coords(obj)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        assert all(edge.is_manifold for edge in bm.edges), obj.name
        unseen = set(bm.verts)
        result = []
        while unseen:
            stack = [unseen.pop()]
            seen = []
            while stack:
                v = stack.pop()
                seen.append(v)
                for e in v.link_edges:
                    n = e.other_vert(v)
                    if n in unseen:
                        unseen.remove(n)
                        stack.append(n)
            result.append([obj.matrix_world @ v.co for v in seen])
        return result
    finally:
        bm.free()


def near(a, b, tol=2e-4):
    return abs(a - b) <= tol


def extent(samples, index):
    return min(p[index] for p in samples), max(p[index] for p in samples)


def expect_segment(all_solids, fixed_axis, fixed_min, fixed_max, along_min, along_max):
    for samples in all_solids:
        x = extent(samples, fixed_axis)
        y = extent(samples, 1 - fixed_axis)
        if all(near(a, b) for a, b in zip(x + y, (fixed_min, fixed_max, along_min, along_max))):
            return samples
    raise AssertionError([(extent(s, fixed_axis), extent(s, 1-fixed_axis)) for s in all_solids])


def refs(obj):
    return set(obj['walls'].values())


def room_and_partition(tmp):
    pt = [(0, 0), (5, 0), (5, 4), (0, 4)]
    boundary = walls(pt)
    assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
    floor, = (obj for obj in bpy.context.scene.objects if obj.get('IS_FLOOR_BP'))

    # Real, cased doorway and window on the same wall; high window has no gap.
    door = opening(openings.home_builder_doors_windows_OT_place_door, boundary[0], 1, .9, 0)
    select(door)
    assert bpy.ops.fzm_builder.door_casing(width=.064) == {'FINISHED'}
    opening(openings.home_builder_doors_windows_OT_place_window, boundary[2], 1.1, 1.15, 1.0)
    opening(openings.home_builder_doors_windows_OT_place_open_door, boundary[1], 2.8, .7, 0)

    # An unrelated room and a same-XY wall on a story above must not be matched.
    other_points = [(7, 0), (9.5, 0), (9.5, 3), (7, 3)]
    other_walls = walls(other_points, 'Other')
    other = mesh_floor('Other Floor', other_points)
    upper = create_wall('Upper Story', (0, 0, 2.6), (5, 0, 2.6))
    select(other)
    assert bpy.ops.fzm_builder.room_baseboards(profile='COLONIAL') == {'FINISHED'}
    other_trim = trim(other)
    unaffected = other_trim.data
    assert refs(other_trim) == set(other_walls)
    assert len(solids(other_trim)) == 4

    select(floor)
    assert bpy.context.selected_objects[:] == [floor]
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    t = trim(floor)
    assert refs(t) == set(boundary) and upper not in refs(t)
    assert t['wall_source'] == 'AUTO'
    ss = solids(t)
    assert len(ss) == 6, len(ss)
    assert all(near(extent(s, 2)[0], 0) and near(extent(s, 2)[1], .1143) for s in ss)
    # Exact inset and miter at bottom left; casing adds .064 clearance either side.
    a = expect_segment(ss, 1, .15, .166, .15, .936)
    expect_segment(ss, 1, .15, .166, 1.964, 4.85)
    expect_segment(ss, 1, 3.834, 3.85, .15, 4.85)
    assert any(near(p.x, .166) and near(p.y, .166) for p in a)
    assert not any(abs(p.x-1.45)<.4 and abs(p.y-.15)<.05 for p in coords(t))
    expect_segment(ss, 0, 4.834, 4.85, .15, 2.8)
    expect_segment(ss, 0, 4.834, 4.85, 3.5, 3.85)
    expect_segment(ss, 0, .15, .166, .15, 3.85)

    # Old multi-selection entry point keeps the manual closed-loop mode.
    select(floor, *boundary)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    assert trim(floor) == t and t['wall_source'] == 'SELECTED'
    select(floor)
    assert bpy.ops.fzm_builder.room_baseboards(wall_source='SELECTED') == {'FINISHED'}
    assert trim(floor) == t and t['wall_source'] == 'SELECTED'

    # The diagonal divider is an unfinished virtual edge: no trim there, even
    # with a fake guide along it. Adjacent true runs cut to the same diagonal.
    assert bpy.ops.fzm_builder.floor_divider(first=(1, 0), second=(3, 4)) == {'FINISHED'}
    piece = bpy.context.active_object
    fake = create_wall('Virtual guide', (1, 0, 0), (3, 4, 0))
    fake['IS_FAKE_WALL'] = True
    select(piece)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    select(floor)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    assert trim(floor) == t and t['wall_source'] == 'AUTO'
    for side in (floor, piece):
        s = trim(side)
        assert fake not in refs(s)
        assert not all(o in refs(s) for o in boundary)
    all_solids = [s for f in (floor, piece) for s in solids(trim(f))]
    assert sum(1 for s in all_solids if any(near(p.x, 1.075) and near(p.y, .15) for p in s)) == 0
    assert sum(1 for s in all_solids if any(near(p.x, 2.925) and near(p.y, 3.85) for p in s)) == 2
    assert other_trim.data == unaffected

    # Put a real wall along exactly that floor seam. Trim should be on each
    # opposite physical face, never through the partition or along its axis.
    partition = create_wall('Real partition', (1, 0, 0), (3, 4, 0))
    for side in (floor, piece):
        select(side)
        assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
        assert partition in refs(trim(side)) and fake not in refs(trim(side))
    n = Vector((-2, 1)).normalized()
    anchor = Vector((1, 0))
    faces = []
    for side in (floor, piece):
        solids_here = solids(trim(side))
        hits = [s for s in solids_here if max(abs((p.xy-anchor).dot(n)) for p in s) < .18 and
                max(p.y for p in s)-min(p.y for p in s) > 3]
        assert len(hits) == 1
        faces.append(sorted(round((p.xy-anchor).dot(n), 3) for p in hits[0]))
    assert sorted({min(x) for x in faces}) == [-.016, .15], faces

    # Failed auto re-generation leaves saved settings/mesh alone.
    snapshot = (t.data, t['wall_source'])
    for o in (*boundary, partition):
        o['IS_FAKE_WALL'] = True
    select(floor)
    assert bpy.ops.fzm_builder.room_baseboards() == {'CANCELLED'}
    assert (t.data, t['wall_source']) == snapshot
    assert other_trim.data == unaffected
    for o in (*boundary, partition):
        del o['IS_FAKE_WALL']

    fixture = str(tmp/'baseboards.blend')
    pairs = {o.name: trim(o).name for o in (floor, piece, other)}
    bpy.ops.wm.save_as_mainfile(filepath=fixture)
    bpy.ops.wm.open_mainfile(filepath=fixture)
    for name, trim_name in pairs.items():
        o = bpy.data.objects[name]
        assert trim(o).name == trim_name and solids(trim(o))
    select(bpy.data.objects['Other Floor'])
    assert bpy.ops.fzm_builder.room_baseboards(remove=True) == {'FINISHED'}
    assert not [o for o in bpy.data.objects['Other Floor'].children if o.get(finishes.BASEBOARD)]
    assert bpy.data.objects[pairs['Floor']].get(finishes.BASEBOARD)


def concave_and_rotated():
    pts = [(10, 0), (14, 0), (14, 2), (12, 2), (12, 4), (10, 4)]
    boundary = walls(pts, 'Concave', 2.65)
    floor = mesh_floor('Concave Upper Floor', pts, 2.65)
    select(floor)
    assert bpy.ops.fzm_builder.room_baseboards(profile='STEP_BEVEL') == {'FINISHED'}
    t = trim(floor)
    assert refs(t) == set(boundary) and len(solids(t)) == 6
    assert any(near(p.x, 11.85) and near(p.y, 1.85) for p in coords(t))

    # Transform both wall generation and floor into world space, and append
    # an interior wall whose axis crosses rather than follows an edge.
    o = mesh_floor('Transformed', [(0,0), (3,0), (3,2.5), (0,2.5)])
    o.location = (22,-4,3.1); o.rotation_euler.z = .45; o.scale=(1.3,.85,1.0)
    bpy.context.view_layer.update()
    tc = [o.matrix_world @ Vector((*p,0)) for p in ((0,0),(3,0),(3,2.5),(0,2.5))]
    ww = [create_wall('Rotated '+str(i), b, a) for i,(a,b) in enumerate(zip(tc,tc[1:]+tc[:1]))]
    cross = create_wall('Crossing only', tc[0]+Vector((.6,-1,0)), tc[0]+Vector((.6,1,0)))
    select(o)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    rt = trim(o)
    assert refs(rt) == set(ww) and cross not in refs(rt) and len(solids(rt)) == 4
    assert all(near(extent(s, 2)[0], 3.1) and near(extent(s, 2)[1], 3.2143) for s in solids(rt))


def partial_walls_and_shallow_divider():
    # A wall does not need to run from one floor vertex to the next, and a
    # real gap between collinear sections must not be bridged with baseboard.
    o = mesh_floor('Partial Perimeter', [(0,10),(8,10),(8,13),(0,13)])
    first = create_wall('Partial first', (0,10,0), (2,10,0))
    second = create_wall('Partial second', (8,10,0), (3,10,0))
    select(o)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    t = trim(o)
    ss = solids(t)
    assert refs(t) == {first, second} and len(ss) == 2
    expect_segment(ss, 1, 10.15, 10.166, 0, 2)
    expect_segment(ss, 1, 10, 10.016, 3, 8)

    p = mesh_floor('Shallow Seam', [(14,10),(22,10),(22,12),(14,12)])
    bottom = create_wall('Against seam', (14,10,0), (22,10,0))
    select(p)
    assert bpy.ops.fzm_builder.floor_divider(first=(15,10), second=(22,10.7)) == {'FINISHED'}
    q = bpy.context.active_object
    for o in (p, q):
        select(o)
        assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
        assert refs(trim(o)) == {bottom}
    ss = solids(trim(p)) + solids(trim(q))
    assert len(ss) == 2
    # The trim caps at x=16.5/16.66, not at the original virtual corner x=15.
    for x, y in [(16.5,10.15),(16.66,10.166)]:
        assert all(any(near(v.x,x) and near(v.y,y) for v in s) for s in ss)


if __name__ == '__main__':
    enable_test_addon()
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    with TemporaryDirectory() as folder:
        room_and_partition(Path(folder))
        concave_and_rotated()
        partial_walls_and_shallow_divider()
    print('PASS floor-only Add Baseboards, interior miters, openings and casing, diagonal virtual split, real partition on both sides, multiple levels and rooms, concavity, transformed floor, manual editing, preservation on failure, reopen and removal')
