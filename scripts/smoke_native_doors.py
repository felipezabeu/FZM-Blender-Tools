"""Headless test of the FZM native placement, editing, geometry and save flow."""
import json
from math import isclose, isfinite
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import addon_utils
import bmesh
import bpy
from mathutils import Vector


BASE = Path(__file__).resolve().parents[1]
package = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if package == 'fzm_builder':
    sys.path.insert(0, str(BASE / 'extensions'))
    addon_utils.enable(package, default_set=True, persistent=True)

from importlib import import_module
hb_types = import_module(package + '.hb_types')
doors = import_module(package + '.operators.doors_windows')
nd = import_module(package + '.operators.native_doors')


def near(a, b, tolerance=8e-5):
    assert isclose(a, b, abs_tol=tolerance), (a, b)


def active(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def wall(length=8, thickness=.15, height=2.7, y=0):
    o = hb_types.GeoNodeWall()
    o.create('Test Wall')
    o.obj.location.y = y
    o.set_input('Length', length)
    o.set_input('Thickness', thickness)
    o.set_input('Height', height)
    bpy.context.view_layer.update()
    return o.obj


def evaluated_mesh(obj):
    bpy.context.view_layer.update()
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data


def volume(obj):
    bm = bmesh.new()
    try:
        bm.from_mesh(evaluated_mesh(obj))
        assert bm.faces
        return abs(bm.calc_volume())
    finally:
        bm.free()


def stats(obj):
    m = evaluated_mesh(obj)
    lo = [min(v.co[i] for v in m.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in m.vertices) for i in range(3)]
    faces = list(m.polygons)
    mat_names = {m.materials[p.material_index].get('fzm_native_door_material') for p in faces}
    return len(m.vertices), lo, hi, mat_names


def inset_panel_volumes(obj):
    mesh = evaluated_mesh(obj)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        unseen = set(bm.faces)
        volumes = []
        while unseen:
            connected = []
            stack = [unseen.pop()]
            while stack:
                face = stack.pop()
                connected.append(face)
                for edge in face.edges:
                    for neighbor in edge.link_faces:
                        if neighbor in unseen:
                            unseen.remove(neighbor)
                            stack.append(neighbor)
            if mesh.materials[connected[0].material_index].get('fzm_native_door_material') != 'inset':
                continue
            assert len(connected) == 6, len(connected)
            zs = [v.co.z for face in connected for v in face.verts]
            assert all(isfinite(z) for z in zs)
            assert max(zs) - min(zs) >= .04
            volumes.append((min(zs), max(zs)))
        return volumes
    finally:
        bm.free()


def contains_local_point(obj, p):
    """Use both projected position and a volumetric crossing, not a bbox."""
    obj_eval = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    point = Vector(p)
    hits, direction = 0, Vector((1., .19, .11)).normalized()
    while True:
        result, location, normal, index = obj_eval.ray_cast(point, direction)
        if not result:
            return bool(hits % 2)
        hits += 1
        point = location + direction * .00002
        assert hits < 12


def build_fixture(cls, target, x, *, native=False, **settings):
    # These are the very methods used by the modal placement operator (after
    # the click), run without the GPU preview/real pointer in background mode.
    state = SimpleNamespace(register_placement_object=lambda obj: None,
                            create_placement_dimensions=lambda: None,
                            report=lambda cats, msg: reports.append(msg))
    reports = []
    for name in (
        'OBJECT_NAME', 'BP_FLAG', 'MENU_ID', 'WIDTH_PROP_NAME', 'HEIGHT_PROP_NAME',
        'HAS_SWING', 'INITIAL_SWING_INPUTS', 'TEXT_NAME', 'TEXT_KIND',
    ):
        setattr(state, name, getattr(cls, name))
    for name, val in settings.items():
        setattr(state, name, val)
    state.cut_wall = lambda w, c: doors.WallObjectPlacementMixin.cut_wall(state, w, c)
    cls.create_placed_object(state, bpy.context)
    cage = state.placed_obj.obj
    cage.parent = target
    cage.location = (x, 0, 0)
    state.placed_obj.set_input('Dim Y', hb_types.GeoNodeWall(target).get_input('Thickness'))
    bpy.context.view_layer.update()
    valid = cls.finish_wall_opening(state, target)
    if native:
        return cage, state.door_visual, valid, reports
    assert valid
    return cage


def new(target, kind, x, w=1.3, h=2.05, style='FLAT', right=False, opening=0):
    return build_fixture(doors.FZM_OT_place_native_door, target, x, native=True,
        door_type=kind, opening_width=w, opening_height=h, right_hand=right,
        opening_amount=opening, bypass_style=style, leaf_style=style)


def main(tmp):
    assert bpy.app.version == (5, 1, 2)
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for key in ('place_native_door', 'edit_native_door', 'floor_divider', 'floor_finish'):
        assert getattr(bpy.ops.fzm_builder, key).get_rna_type()
    assert set(nd.NAMES) == {'BYPASS', 'BIFOLD', 'POCKET'}
    near(nd.default_size('BYPASS')[0], 60*.0254)
    near(nd.default_size('POCKET')[1], 80*.0254)

    legacy_wall = wall(y=5)
    baseline = volume(legacy_wall)
    legacy_single = build_fixture(doors.home_builder_doors_windows_OT_place_door, legacy_wall, .2)
    legacy_double = build_fixture(doors.home_builder_doors_windows_OT_place_double_door, legacy_wall, 2.)
    legacy_open = build_fixture(doors.home_builder_doors_windows_OT_place_open_door, legacy_wall, 5.)
    assert volume(legacy_wall) < baseline
    assert all(nd.visual_for(o) is None and nd.TYPE_KEY not in o for o in (legacy_single, legacy_double, legacy_open))
    assert any('Door Swing' in c.name for c in legacy_single.children)
    assert any('Door Swing' in c.name for c in legacy_double.children)
    assert not any('Door Swing' in c.name for c in legacy_open.children)
    active(legacy_single)
    assert bpy.ops.home_builder_doors_windows.door_prompts.poll()
    assert not bpy.ops.fzm_builder.edit_native_door.poll()
    legacy_names = [o.name for o in (legacy_single, legacy_double, legacy_open)]
    legacy = str(tmp / "legacy-only.blend")
    bpy.ops.wm.save_as_mainfile(filepath=legacy)
    bpy.ops.wm.open_mainfile(filepath=legacy)
    assert all(not bpy.data.objects[n].get(nd.TYPE_KEY) for n in legacy_names)

    walls = [wall(y=8 + i * 3) for i in range(4)]
    keys = ('BYPASS', 'BIFOLD', 'POCKET')
    made = []
    for target, kind in zip(walls, keys):
        initial = volume(target)
        c, v, result, reports = new(target, kind, 2.)
        assert result and not reports
        assert c.hide_render and not v.hide_render and v.parent == c
        assert nd.cage_for(v) == c and nd.get_options(v) == ('FLAT', 0., False)
        assert sum(m.type == 'BOOLEAN' and m.object == c for m in target.modifiers) == 1
        near(initial - volume(target), 1.30 * 2.05 * .15, tolerance=.012)
        assert not contains_local_point(target, (2.6, .075, 1))
        assert contains_local_point(target, (4.1, .075, 1))
        n, lo, hi, mats = stats(v)
        assert n > 10 and 'white' in mats and 'metal' in mats and 'mirror' not in mats
        near(hi[2], 2.05-.001)
        if kind != 'POCKET':
            near(lo[0], 0)
            near(hi[0], 1.3)
        else:
            assert lo[0] < -1.25  # internal track, not a second opening
        made.append((target, c, v, n))

    # A second bypass shares a node group but receives independent edit values.
    c2, v2, ok, reports = new(walls[3], 'BYPASS', 1.5, style='MIRROR', opening=.25)
    assert ok and not reports and 'mirror' in stats(v2)[3]
    target, c, v, flat_count = made[0]
    assert v.modifiers[0].node_group == v2.modifiers[0].node_group
    active(v)  # user clicks the visible leaf rather than having to find the cage
    assert bpy.ops.fzm_builder.edit_native_door.poll()
    assert not bpy.ops.home_builder_doors_windows.door_prompts.poll()
    assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.6, opening_height=2.2,
        offset=2.2, bypass_style='SHAKER', opening_amount=.62) == {'FINISHED'}
    n, lo, hi, mats = stats(v)
    assert n > flat_count and 'inset' in mats and 'mirror' not in mats
    near(hi[0],1.6); near(hi[2],2.199); near(c.location.x,2.2)
    near(nd.get_options(v)[1],.62)
    assert nd.get_options(v2)[0] == 'MIRROR'
    near(nd.get_options(v2)[1],.25)
    assert not contains_local_point(target, (3.72,.075,1.5))  # cutter grew/moved
    assert contains_local_point(target, (2.1,.075,1.5))  # prior opening start restored

    for target, c, v, count in made[1:]:
        kind = c[nd.TYPE_KEY]
        active(v)
        closed = stats(v)
        # Edit with style, hand, and pose interacting, not just divergent switch tests.
        assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.4, opening_height=2.1,
            offset=2.8, leaf_style='SIX_PANEL', opening_amount=.8, right_hand=True) == {'FINISHED'}
        n, lo, hi, mats = stats(v)
        assert n > count and 'inset' in mats
        assert nd.get_options(v)[0] == 'SIX_PANEL' and nd.get_options(v)[2]
        near(hi[2],2.099)
        if kind == 'POCKET':
            assert hi[0] > 2.65
            assert contains_local_point(target, (5.1,.075,1))  # cavity marking doesn't cut wall face
            assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.4, opening_height=2.1,
                offset=6.4, leaf_style='FLAT', opening_amount=.1, right_hand=True) == {'CANCELLED'}
            assert nd.get_options(v)[0] == 'SIX_PANEL'
        else:
            assert hi[1] > .3 and hi[1] > closed[2][1]

    pending_c, pending_v, ok, messages = new(walls[3], 'POCKET', .15, w=1.0)
    assert not ok and any('pocket side' in m for m in messages)
    assert not any(m.type == 'BOOLEAN' and m.object == pending_c for m in walls[3].modifiers)
    bpy.data.objects.remove(pending_v, do_unlink=True)
    for child in list(pending_c.children):
        bpy.data.objects.remove(child, do_unlink=True)
    bpy.data.objects.remove(pending_c, do_unlink=True)

    # Test all panel options on every type through the actual edit operator,
    # counting connected recessed panels rather than just checking labels.
    modes = {'SHAKER': 1, 'SHAKER_2': 2, 'SHAKER_5': 5, 'SIX_PANEL': 6}
    for target, c, v, _ in made:
        kind = c[nd.TYPE_KEY]
        active(v)
        props = {'bypass_style' if kind == 'BYPASS' else 'leaf_style': ''}
        key = next(iter(props))
        for style, count in modes.items():
            props[key] = style
            assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.37, opening_height=2.08,
                offset=2.6, opening_amount=.7, right_hand=True, **props) == {'FINISHED'}
            assert nd.get_options(v)[0] == style
            assert len(inset_panel_volumes(v)) == count * (1 if kind == 'POCKET' else 2)
            if kind == 'POCKET':
                # Open leaf partly enters the persistent solid wall; the
                # old boolean retains only the visible doorway, not the cavity.
                assert stats(v)[2][0] > 2.65
                assert contains_local_point(target, (4.45,.06,1))
                assert not contains_local_point(target, (3.5,.06,1))
    assert nd.get_options(v2)[0] == 'MIRROR'

    # Verify a narrow bifold still has finite thickness and six recessed panels.
    # Its leaf is narrower than a common cabinet front.
    narrow = wall(length=3., y=27)
    _, nv, ok, _ = new(narrow, 'BIFOLD', .7, w=.48, style='SIX_PANEL')
    assert ok and stats(nv)[0] >= 200
    assert stats(nv)[2][0] <= .48 + 1e-5 and 'inset' in stats(nv)[3]
    active(nv)
    assert bpy.ops.fzm_builder.edit_native_door(opening_width=.45, opening_height=.66,
        offset=.6, leaf_style='SHAKER_5', opening_amount=.78, right_hand=True) == {'FINISHED'}
    assert len(inset_panel_volumes(nv)) == 10

    clone = str(tmp / "all-native-doors.blend")
    saved = [(c.name, v.name, nd.get_options(v), stats(v)) for _, c, v, _ in made]
    bpy.ops.wm.save_as_mainfile(filepath=clone)
    bpy.ops.wm.open_mainfile(filepath=clone)
    for cname, vname, options, mesh in saved:
        c, v = bpy.data.objects[cname], bpy.data.objects[vname]
        assert v.parent == c and nd.get_options(v) == options and stats(v) == mesh
        assert any(m.type == 'BOOLEAN' and m.object == c for m in c.parent.modifiers)
    assert all(n in bpy.data.objects for n in legacy_names)

    # Deletion from visible leaf removes its owning cutter and restores wall material.
    c, v = bpy.data.objects[saved[0][0]], bpy.data.objects[saved[0][1]]
    target = c.parent
    before_delete = volume(target)
    active(v)
    assert bpy.ops.home_builder_doors_windows.delete_door_window() == {'FINISHED'}
    assert saved[0][0] not in bpy.data.objects and saved[0][1] not in bpy.data.objects
    near(volume(target) - before_delete, 1.37 * 2.08 * .15, tolerance=.012)
    print("PASS native placement, styles/materials, cage booleans, per-door controls, turning/folding/sliding, constraints, legacy Single/Double/Open & re-open, deletion")


def legacy_upgrade(filename, tmp):
    bpy.ops.wm.open_mainfile(filepath=filename)
    entries = json.loads(bpy.context.scene['test_515_native_doors'])
    assert len(entries) == 4
    original_groups = {}
    for item in entries:
        obj = bpy.data.objects[item['name']]
        original_groups[obj.name] = obj.modifiers[0].node_group
        assert original_groups[obj.name].name.startswith("FZM Native Door v1")
        assert nd.get_options(obj)[0] == item['style']
        near(nd.get_options(obj)[1], item['opening'])
        assert stats(obj)[0] == item['nverts']
    bypass_item = entries[0]
    bypass = bpy.data.objects[bypass_item['name']]
    active(bypass)
    assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.14, opening_height=2.05,
        offset=2.3, bypass_style='SHAKER', opening_amount=.37) == {'FINISHED'}
    assert bypass.modifiers[0].node_group == original_groups[bypass.name]
    assert stats(bypass)[0] == bypass_item['nverts']
    old_cage = bypass.parent
    other_bypass = bpy.data.objects[entries[3]['name']]
    assert other_bypass.modifiers[0].node_group == original_groups[bypass.name]

    assert bpy.ops.fzm_builder.edit_native_door(opening_width=1.48, opening_height=2.33,
        offset=2.6, bypass_style='SHAKER_5', opening_amount=.58) == {'FINISHED'}
    group = bypass.modifiers[0].node_group
    assert group.name.startswith("FZM Native Door v2")
    assert stats(bypass)[2][0] >= 1.479
    near(stats(bypass)[2][2], 2.329)
    assert len(inset_panel_volumes(bypass)) == 10
    assert nd.get_options(other_bypass)[0] == 'MIRROR'
    assert other_bypass.modifiers[0].node_group == original_groups[bypass.name]
    near(hb_types.GeoNodeCage(old_cage).get_input('Dim X'), 1.48)

    for item in entries[1:]:
        obj = bpy.data.objects[item['name']]
        assert obj.modifiers[0].node_group == original_groups[obj.name]
        assert nd.get_options(obj)[0] == item['style']
        assert stats(obj)[0] == item['nverts']

    dst = str(tmp / 'migrated_legacy_doors.blend')
    bpy.ops.wm.save_as_mainfile(filepath=dst)
    bpy.ops.wm.open_mainfile(filepath=dst)
    bypass = bpy.data.objects[bypass_item['name']]
    assert nd.get_options(bypass)[0] == 'SHAKER_5'
    near(stats(bypass)[2][2], 2.329)
    assert len(inset_panel_volumes(bypass)) == 10
    assert bpy.data.objects[entries[3]['name']].modifiers[0].node_group.name.startswith("FZM Native Door v1")
    print("PASS actual 5.1.5 file: old styles/geometry preserved, chosen door only upgraded to new Shaker 5 with width/height drivers and save/reopen")


with TemporaryDirectory() as t:
    main(Path(t))
    if (fixture := os.environ.get('FZM_TEST_515_BLEND')):
        legacy_upgrade(fixture, Path(t))
