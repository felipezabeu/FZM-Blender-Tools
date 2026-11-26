"""Ensure door/casing operators update both sides of existing baseboards."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_room_baseboards import create_wall, enable_test_addon, extent, finishes, fzm_builder, mesh_floor, near, openings, refs, select, solids, trim
hb_types = fzm_builder.hb_types


def committed(placement, wall, offset, width, z=0., **settings):
    state = SimpleNamespace(register_placement_object=lambda obj: None,
                            create_placement_dimensions=lambda: None)
    reports = []
    state.report = lambda kinds, message: reports.append(message)
    state.cut_wall = lambda w, c: openings.WallObjectPlacementMixin.cut_wall(state, w, c)
    for name in ('OBJECT_NAME', 'BP_FLAG', 'MENU_ID', 'WIDTH_PROP_NAME', 'HEIGHT_PROP_NAME',
                 'HAS_SWING', 'INITIAL_SWING_INPUTS', 'TEXT_NAME', 'TEXT_KIND'):
        setattr(state, name, getattr(placement, name))
    for key, value in settings.items():
        setattr(state, key, value)
    placement.create_placed_object(state, bpy.context)
    cage = state.placed_obj
    cage.obj.parent = wall
    cage.obj.location = offset, 0., z
    cage.set_input('Dim X', width)
    cage.set_input('Dim Y', hb_types.GeoNodeWall(wall).get_input('Thickness'))
    bpy.context.view_layer.update()
    assert placement.finish_wall_opening(state, wall), reports
    assert not any('Could not refresh baseboards' in m for m in reports), reports
    return cage.obj


def face_runs(floor, x):
    hits = []
    for section in solids(trim(floor)):
        lo, hi = extent(section, 0)
        if lo >= x - .022 and hi <= x + .022:
            hits.append(extent(section, 1))
    return sorted(hits)


def assert_gaps(floor, x, *gaps):
    actual = face_runs(floor, x)
    assert len(actual) == len(gaps) + 1, (floor.name, actual, gaps)
    for before, after, expected in zip(actual, actual[1:], gaps):
        assert near(before[1], expected[0]) and near(after[0], expected[1]), (floor.name, actual, gaps)


def side_fixtures():
    common = create_wall('Shared physical divider', (4, 0, 0), (4, 4, 0))
    left_corners = [(0, 0), (4, 0), (4, 4), (0, 4)]
    right_corners = [(4, 0), (8, 0), (8, 4), (4, 4)]
    data = []
    for n, points, interior in [('Left room', left_corners, 1),
                                ('Right room', right_corners, 3)]:
        walls = [common if i == interior else create_wall(n + str(i), (*a, 0), (*b, 0))
                 for i, (a, b) in enumerate(zip(points, points[1:] + points[:1]))]
        floor = mesh_floor(n, points)
        color = bpy.data.materials.new(n + ' trim')
        select(floor, *(walls if interior == 3 else []))
        assert bpy.ops.fzm_builder.room_baseboards(material=color.name) == {'FINISHED'}
        assert trim(floor)['wall_source'] == ('AUTO' if interior == 1 else 'SELECTED')
        data.append((floor, trim(floor), color))
    return common, data


def main(tmp):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    wall, ((left, lt, lc), (right, rt, rc)) = side_fixtures()
    x_left, x_right = 3.85, 4.0
    rows = [(left, lt, lc, x_left), (right, rt, rc, x_right)]

    unrelated = mesh_floor('Unrelated room', [(20, 0), (23, 0), (23, 4), (20, 4)])
    other_wall = create_wall('Unrelated wall', (20, 0, 0), (23, 0, 0))
    select(unrelated)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    other_mesh = trim(unrelated).data

    for f, _, _, x in rows:
        assert_gaps(f, x)

    # Native placement and legacy hinged placement use the final-click helper.
    legacy = committed(openings.home_builder_doors_windows_OT_place_door, wall, 1.2, .85)
    for f, tr, material, x in rows:
        assert_gaps(f, x, (1.2, 2.05))
        assert trim(f) == tr and tr.data.materials[0] == material
    window = committed(openings.home_builder_doors_windows_OT_place_window, wall, .45, .42, .95)
    before = lt.data, rt.data
    assert window.get('IS_WINDOW_BP') and not window.get('IS_ENTRY_DOOR_BP')
    select(window)
    assert bpy.ops.home_builder_doors_windows.delete_door_window(object_type='WINDOW') == {'FINISHED'}
    assert (lt.data, rt.data) == before
    for f, _, _, x in rows:
        assert_gaps(f, x, (1.2, 2.05))

    for casing_width, profile in [(.064, 'FLAT'), (.08, 'COLONIAL')]:
        select(legacy)
        assert bpy.ops.fzm_builder.door_casing(width=casing_width, profile=profile) == {'FINISHED'}
        for f, tr, material, x in rows:
            assert_gaps(f, x, (1.2-casing_width, 2.05+casing_width))
            assert trim(f) == tr and tr.data.materials[0] == material

    # Update a saved legacy hinged opening while casing keeps its driven width.
    select(legacy)
    assert bpy.ops.home_builder_doors_windows.door_prompts(door_width=.95, offset=1.3) == {'FINISHED'}
    for f, _, _, x in rows:
        assert_gaps(f, x, (1.22, 2.33))

    native = committed(openings.FZM_OT_place_native_door, wall, 2.55, .76,
                       door_type='BIFOLD', opening_width=.76, opening_height=2.03,
                       right_hand=False, opening_amount=0., bypass_style='FLAT', leaf_style='FLAT')
    for f, _, _, x in rows:
        assert_gaps(f, x, (1.22, 2.33), (2.55, 3.31))
    select(native)
    assert bpy.ops.fzm_builder.edit_native_door(
        opening_width=.80, opening_height=2.02, offset=2.61,
        right_hand=False, opening_amount=.3, leaf_style='FLAT',
    ) == {'FINISHED'}
    for f, _, _, x in rows:
        assert_gaps(f, x, (1.22, 2.33), (2.61, 3.41))
    select(native)
    assert bpy.ops.home_builder_doors_windows.delete_door_window() == {'FINISHED'}

    # The unified Edit Door entry must update the same trim (not just the old dialogs).
    select(legacy)
    assert bpy.ops.fzm_builder.edit_door(width=.90, offset=1.25) == {'FINISHED'}
    for f, _, _, x in rows:
        assert_gaps(f, x, (1.17, 2.23))
    assert bpy.ops.fzm_builder.edit_door(width=.95, offset=1.3) == {'FINISHED'}

    # Preserve one trim object and actual material while repairing a stale
    # mesh via rerun; a more generous casing on the left face must NOT be
    # used on the right face. Edit all shape-key bases consistently.
    casing = next(o for o in legacy.children if o.get(finishes.CASING))
    old_width = casing['width']
    for block in casing.data.shape_keys.key_blocks:
        for vertex in block.data:
            if vertex.co.y > .05:
                if vertex.co.x < 0:
                    vertex.co.x -= .03
                else:
                    vertex.co.x += .02
    casing.data.update()
    casing.update_tag()
    assert near(casing['width'], old_width)
    for floor, current, color, x in rows:
        select(floor)
        assert bpy.ops.fzm_builder.room_baseboards(wall_source=current['wall_source'], material=color.name) == {'FINISHED'}
        assert trim(floor) == current
        assert_gaps(floor, x, (1.19, 2.35) if floor == left else (1.22, 2.33))
    assert trim(unrelated).data == other_mesh

    names = legacy.name, left.name, right.name
    fixture = str(tmp / 'door-after-baseboards.blend')
    bpy.ops.wm.save_as_mainfile(filepath=fixture)
    bpy.ops.wm.open_mainfile(filepath=fixture)
    legacy, left, right = (bpy.data.objects[name] for name in names)
    assert_gaps(left, x_left, (1.19, 2.35))
    assert_gaps(right, x_right, (1.22, 2.33))

    select(legacy)
    assert bpy.ops.fzm_builder.door_casing(remove=True) == {'FINISHED'}
    assert_gaps(left, x_left, (1.3, 2.25))
    assert_gaps(right, x_right, (1.3, 2.25))
    assert bpy.ops.home_builder_doors_windows.delete_door_window() == {'FINISHED'}
    assert_gaps(left, x_left)
    assert_gaps(right, x_right)

    # A door that consumes an entire run must remain in the managed wall
    # references so removing it can restore the board without selecting floor.
    single_floor = mesh_floor('One real edge', [(30, 0), (32, 0), (32, 3), (30, 3)])
    single_wall = create_wall('Sole true wall', (30, 0, 0), (32, 0, 0))
    select(single_floor)
    assert bpy.ops.fzm_builder.room_baseboards() == {'FINISHED'}
    single_trim = trim(single_floor)
    entire = committed(openings.home_builder_doors_windows_OT_place_open_door, single_wall, 0., 2.)
    assert refs(single_trim) == {single_wall} and not single_trim.data.vertices
    select(entire)
    assert bpy.ops.home_builder_doors_windows.delete_door_window() == {'FINISHED'}
    assert trim(single_floor) == single_trim and len(solids(single_trim)) == 1

    print('PASS door-after-trim, both faces, hinged/native move/resize/deletion, casing add/change/remove and asymmetric shape, windows, manual trim, save/reopen, and fully consumed/restored wall')


if __name__ == '__main__':
    enable_test_addon()
    with TemporaryDirectory() as folder:
        main(Path(folder))
