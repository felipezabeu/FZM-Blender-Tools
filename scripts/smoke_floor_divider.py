"""Headless integration smoke test for FZM floor subdivision and materials."""

from math import atan2, isclose
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import bmesh
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extensions"))
import fzm_builder
from fzm_builder.operators import floor_divider, floor_finish


def active(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def build_wall(types, start, end):
    wall = types.GeoNodeWall()
    wall.create("Fixture Wall")
    delta = Vector(end) - Vector(start)
    wall.obj.location = start
    wall.obj.rotation_euler.z = atan2(delta.y, delta.x)
    wall.set_input("Length", delta.length)
    wall.set_input("Thickness", 0.15)
    wall.set_input("Height", 2.5)
    bpy.context.view_layer.update()
    return wall


def approx(a, b):
    return isclose(a, b, rel_tol=1e-5, abs_tol=1e-6)


def volume(obj, evaluated=True):
    bpy.context.view_layer.update()
    target = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()) if evaluated else obj
    bm = bmesh.new()
    try:
        bm.from_mesh(target.data)
        assert all(e.is_manifold for e in bm.edges)
        return abs(bm.calc_volume())
    finally:
        bm.free()


def floors():
    return [o for o in bpy.context.scene.objects if o.get('IS_FLOOR_BP')]


def material(obj):
    return obj.material_slots[0].material


def local_catalog_temp(tmp):
    # Simulate a new profile with no presets and no user configuration writes.
    floor_finish.catalog_root = lambda: tmp / 'catalog'


def test(tmp):
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    corners = [(0, 0, 0), (5, 0, 0), (5, 4, 0), (0, 4, 0)]
    for start, end in zip(corners, corners[1:] + corners[:1]):
        build_wall(fzm_builder.hb_types, start, end)
    assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
    assert len(floors()) == 1
    legacy = str(tmp / 'unsplit-floor.blend')
    bpy.ops.wm.save_as_mainfile(filepath=legacy)
    bpy.ops.wm.open_mainfile(filepath=legacy)
    old = floors()[0]
    assert approx(volume(old), .20)
    original_faces = len(old.data.polygons)
    active(old)
    assert bpy.ops.fzm_builder.floor_divider(first=(2, 0), second=(2, 3)) == {'CANCELLED'}
    assert len(floors()) == 1 and len(old.data.polygons) == original_faces
    assert bpy.ops.fzm_builder.floor_divider(first=(1, 0), second=(4, 0)) == {'CANCELLED'}
    assert len(floors()) == 1

    # Attach a pre-existing Floor Cutter that straddles the planned split.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(2, 2, 0))
    cutter = bpy.context.object
    cutter['IS_FLOOR_CUTTER'] = True
    cutter.hide_render = True
    cutter.parent = old
    modifier = old.modifiers.new('Fixture Floor Cutter', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.object = cutter
    baseline = volume(old)
    assert approx(baseline, .19), baseline
    active(old)
    assert bpy.ops.fzm_builder.floor_divider(first=(2, 0), second=(2, 4)) == {'FINISHED'}
    new = bpy.context.active_object
    assert old != new and len(floors()) == 2
    assert old.data != new.data and approx(volume(old) + volume(new), baseline)
    assert sorted(round(volume(o, False), 4) for o in (old, new)) == [.08, .12]
    assert all(o.modifiers[0].object == cutter for o in (old, new))
    for o in (old, new):
        mesh = o.data
        for loop in mesh.loops:
            assert (mesh.vertices[loop.vertex_index].co.xy - mesh.uv_layers['UVMap'].data[loop.index].uv).length < 1e-6

    local_catalog_temp(tmp)
    assert {'maple', 'hickory', 'grey_wood'} <= set(floor_finish.catalog_entries())
    active(old)
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset='maple') == {'FINISHED'}
    maple = material(old)
    assert maple["fzm_floor_finish_source"] == "maple"
    assert any(n.type == 'TEX_NOISE' for n in maple.node_tree.nodes)
    image = bpy.data.images.new('Fixture', width=4, height=4)
    image.pixels = [.6, .3, .2, 1] * 16
    image.filepath_raw = str(tmp / 'surface.png')
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    active(new)
    before = set(floor_finish.catalog_entries())
    assert bpy.ops.fzm_builder.floor_finish(mode='IMAGE', filepath=str(tmp/'surface.png'), width=.23, height=.9) == {'FINISHED'}
    assert set(floor_finish.catalog_entries()) == before
    tex = material(new)
    assert material(old) == maple and tex != maple
    node = next(n for n in tex.node_tree.nodes if n.type == 'TEX_IMAGE')
    assert node.image.packed_file
    scale = next(n for n in tex.node_tree.nodes if n.type == 'VECT_MATH')
    assert approx(scale.inputs[1].default_value[0], 1/.23)
    assert approx(scale.inputs[1].default_value[1], 1/.9)
    assert bpy.ops.fzm_builder.floor_finish(mode='IMAGE', filepath=str(tmp/'missing.png')) == {'CANCELLED'}
    assert material(new) == tex
    assert bpy.ops.fzm_builder.floor_finish(mode='IMAGE', filepath=str(tmp/'surface.png'), width=.2,
        height=.8, add_to_catalog=True, preset_name="Supplier QA") == {'FINISHED'}
    custom = (set(floor_finish.catalog_entries()) - before).pop()
    (tmp/'surface.png').unlink()
    assert bpy.ops.fzm_builder.floor_finish(mode='CATALOG', preset=custom) == {'FINISHED'}
    assert material(new)["fzm_floor_finish_name"] == 'Supplier QA'
    assert material(old) == maple

    # Concave chords, rejection of a chord leaving the floor, and a second split.
    lshape = [Vector(p) for p in ((0,0),(4,0),(4,2),(2,2),(2,4),(0,4))]
    assert approx(sum(abs(floor_divider.area(r)) for r in
        floor_divider.split_ring(lshape, Vector((1,0)), Vector((1,4)))), 12)
    try:
        floor_divider.split_ring(lshape, Vector((4,2)), Vector((2,4)))
    except ValueError:
        pass
    else:
        raise AssertionError('Outside concave chord accepted')
    active(new)
    poly, *_ = floor_divider.top_outline(new.data)
    x0, x1 = min(p.x for p in poly), max(p.x for p in poly)
    assert bpy.ops.fzm_builder.floor_divider(first=(x0, 1), second=(x1, 1)) == {'FINISHED'}
    assert len(floors()) == 3
    assert bpy.ops.fzm_builder.floor_finish(mode='COLOR', color=(.2,.4,.5,1)) == {'FINISHED'}
    assert material(old) == maple and material(new)["fzm_floor_finish_source"] == custom
    assert approx(sum(volume(o) for o in floors()), baseline)
    fixture = str(tmp/'fzm-floor.blend')
    bpy.ops.wm.save_as_mainfile(filepath=fixture)
    bpy.ops.wm.open_mainfile(filepath=fixture)
    assert len(floors()) == 3
    assert approx(sum(volume(o) for o in floors()), baseline)
    assert {material(o)["fzm_floor_finish_name"] for o in floors()} == {
        "Maple (generic)", "Supplier QA", "Solid Color"
    }
    assert all(n.image.packed_file for o in floors() for n in material(o).node_tree.nodes if n.type == 'TEX_IMAGE')
    print("PASS: existing Floor, invalid dividers, concave outline, manifold volumes, existing cutter, metric UV, sequential division, catalog / color / local image independence, preset reuse and saved Blender reopen")


import addon_utils
addon_utils.enable("fzm_builder", default_set=True, persistent=True)
with TemporaryDirectory() as d:
    test(Path(d))
