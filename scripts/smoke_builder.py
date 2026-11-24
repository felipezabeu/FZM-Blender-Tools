"""Exercise an installed Home Builder baseline or FZM Builder in Blender headless."""

import argparse
from importlib import import_module
from math import atan2, isclose
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import bpy
from mathutils import Vector
from PIL import Image


def active(obj):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def evaluated_volume(obj):
    import bmesh

    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return bm.calc_volume()
    finally:
        bm.free()
        evaluated.to_mesh_clear()


def build_wall(types, start, end):
    wall = types.GeoNodeWall()
    wall.create("Smoke Wall")
    delta = Vector(end) - Vector(start)
    wall.obj.location = start
    wall.obj.rotation_euler.z = atan2(delta.y, delta.x)
    wall.set_input("Length", delta.length)
    wall.set_input("Thickness", 0.15)
    wall.set_input("Height", 2.5)
    bpy.context.view_layer.update()
    return wall


def build_opening(operators, placement, wall, offset, z=0):
    # Exercise the production creation and boolean methods without a viewport.
    state = SimpleNamespace(
        register_placement_object=lambda obj: None,
        create_placement_dimensions=lambda: None,
    )
    for name in (
        "OBJECT_NAME", "BP_FLAG", "MENU_ID", "WIDTH_PROP_NAME", "HEIGHT_PROP_NAME",
        "HAS_SWING", "INITIAL_SWING_INPUTS", "TEXT_NAME", "TEXT_KIND",
    ):
        setattr(state, name, getattr(placement, name))
    placement.create_placed_object(state, bpy.context)
    placed = state.placed_obj
    placed.obj.parent = wall.obj
    placed.obj.location = (offset, 0, z)
    placed.set_input("Dim Y", wall.get_input("Thickness"))
    operators.WallObjectPlacementMixin.cut_wall(state, wall.obj, placed.obj)
    bpy.context.view_layer.update()
    return placed, state.swing_obj


def smoke(package, temp, save_fixture, load_fixture, export_pdf):
    assert bpy.app.version == (5, 1, 2), bpy.app.version
    assert package in bpy.context.preferences.addons.keys(), package
    types = import_module(f"{package}.hb_types")
    doors = import_module(f"{package}.operators.doors_windows")
    walls = import_module(f"{package}.operators.walls")
    cabinets = import_module(f"{package}.product_libraries.frameless.types_frameless")
    assets = import_module(f"{package}.hb_assets")
    addon = import_module(package)

    assert addon.load_file_post in bpy.app.handlers.load_post
    assert any(
        lib.name == assets.BUNDLED_LIBRARY_NAME
        and Path(lib.path) == Path(assets.get_addon_assets_path())
        for lib in bpy.context.preferences.filepaths.asset_libraries
    )
    assert (Path(assets.get_addon_assets_path()) / "blender_assets.cats.txt").is_file()
    png = temp / "reference.png"
    pdf = temp / "pillow-smoke.pdf"
    image = Image.new("RGB", (16, 16), "white")
    image.save(png)
    image.save(pdf)
    assert pdf.read_bytes().startswith(b"%PDF")
    print("PASS add-on registration, asset catalog, installed Pillow PNG/PDF", flush=True)

    if load_fixture:
        bpy.ops.wm.open_mainfile(filepath=str(load_fixture))
        main = next(scene for scene in bpy.data.scenes if scene.get("IS_MAIN_SCENE"))
        assert main.hb_frameless.cabinet_styles
        bpy.context.window.scene = main
        door = next(obj for obj in bpy.context.scene.objects if obj.get("IS_ENTRY_DOOR_BP"))
        assert isclose(types.GeoNodeCage(door).get_input("Dim X"), 0.85, abs_tol=1e-6)
        assert any(mod.type == "BOOLEAN" and mod.object == door for mod in door.parent.modifiers)
        print("PASS opened upstream fixture with editable FZM properties and wall cut", flush=True)
        return

    scene_name = bpy.context.scene.name
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.scene.hb_frameless.ensure_default_style()
    corners = [(0, 0, 0), (5, 0, 0), (5, 4, 0), (0, 4, 0)]
    boundary = [build_wall(types, start, end)
                for start, end in zip(corners, corners[1:] + corners[:1])]
    assert len(walls.find_wall_chains()) == 1
    assert walls.is_closed_loop(walls.get_room_boundary_points(walls.find_wall_chains()[0]))
    wall = boundary[0]
    original_wall_volume = evaluated_volume(wall.obj)
    assert original_wall_volume > 1.0

    door, swing = build_opening(doors, doors.home_builder_doors_windows_OT_place_door, wall, 0.25)
    opening, open_swing = build_opening(
        doors, doors.home_builder_doors_windows_OT_place_open_door, boundary[1], 1.0,
    )
    window, window_swing = build_opening(
        doors, doors.home_builder_doors_windows_OT_place_window, boundary[2], 1.0, z=1.0,
    )
    assert open_swing is None and window_swing is None and window.obj.get("IS_WINDOW_BP")
    assert opening.obj.get("IS_ENTRY_DOOR_BP") and swing.obj.get("IS_2D_ANNOTATION")
    assert evaluated_volume(wall.obj) < original_wall_volume
    active(door.obj)
    assert bpy.ops.home_builder_doors_windows.door_prompts.poll()
    for name, socket in (("flip_door_hand", "Is Left"),
                         ("flip_door_swing", "Swing Inside"),
                         ("toggle_double_door", "Is Double")):
        before = swing.get_input(socket)
        assert getattr(bpy.ops.home_builder_doors_windows, name)() == {"FINISHED"}
        assert swing.get_input(socket) != before
    door.set_input("Dim X", 0.85)
    bpy.context.view_layer.update()
    assert isclose(swing.get_input("Dim X"), 0.85, abs_tol=1e-6)
    active(window.obj)
    window_name = window.obj.name
    assert bpy.ops.home_builder_doors_windows.delete_door_window(object_type="WINDOW") == {"FINISHED"}
    assert window_name not in bpy.data.objects
    assert all(mod.type != "BOOLEAN" for mod in boundary[2].obj.modifiers)
    print("PASS wall geometry, single door, opening, window, hand/swing/double, resize and delete", flush=True)

    assert bpy.ops.home_builder_walls.add_floor() == {"FINISHED"}
    floor = next(obj for obj in bpy.context.scene.objects if obj.get("IS_FLOOR_BP"))
    initial_floor = evaluated_volume(floor)
    assert isclose(initial_floor, 0.20, rel_tol=1e-5)
    cutter_type = walls.home_builder_walls_OT_draw_floor_cutter
    cut_points = [Vector((x, y, 0)) for x, y in [(1, 1), (2, 1), (2, 2), (1, 2)]]
    cutter = cutter_type.create_cutter_mesh(None, bpy.context, cut_points)
    cutter_type.add_boolean_to_floor(None, floor, cutter)
    assert isclose(evaluated_volume(floor), 0.19, rel_tol=1e-5)
    assert bpy.ops.home_builder_walls.add_room_lights() == {"FINISHED"}
    assert any(obj.type == "LIGHT" for obj in bpy.context.scene.objects)

    reference = bpy.data.objects.new("Smoke Reference", None)
    bpy.context.collection.objects.link(reference)
    reference.empty_display_type = "IMAGE"
    reference.data = bpy.data.images.load(str(png))
    reference.data.pack()
    cabinet = cabinets.BaseCabinet()
    cabinet.create("Smoke Base Cabinet")
    assert cabinet.obj.children and cabinet.obj.get("IS_FRAMELESS_CABINET_CAGE")
    assert bpy.ops.home_builder_layouts.create_plan_view() == {"FINISHED"}
    assert any(scene.get("IS_LAYOUT_VIEW") for scene in bpy.data.scenes)
    print("PASS closed floor volume and Floor Cutter, lights, reference image data, cabinet and plan layout", flush=True)

    if export_pdf:
        exported = temp / "layout.pdf"
        with patch("subprocess.run"):
            result = bpy.ops.home_builder_layouts.export_all_to_pdf(filepath=str(exported), dpi="150")
        assert result == {"FINISHED"}, result
        assert exported.read_bytes().startswith(b"%PDF")
        print("PASS layout render and PDF export operator", flush=True)

    floor_name = floor.name
    path = save_fixture or temp / "reopen.blend"
    assert bpy.ops.wm.save_as_mainfile(filepath=str(path)) == {"FINISHED"}
    assert bpy.ops.wm.open_mainfile(filepath=str(path)) == {"FINISHED"}
    bpy.context.window.scene = bpy.data.scenes[scene_name]
    restored = bpy.data.objects.get("Door")
    assert restored is not None and isclose(types.GeoNodeCage(restored).get_input("Dim X"), 0.85, abs_tol=1e-6)
    assert any(mod.type == "BOOLEAN" and mod.object == restored for mod in restored.parent.modifiers)
    assert isclose(evaluated_volume(bpy.data.objects[floor_name]), 0.19, rel_tol=1e-5)
    assert bpy.data.objects["Smoke Reference"].data.packed_file
    print("PASS save/reopen, door dimensions, wall and floor boolean references, packed image", flush=True)

    # Register the upstream behavior explicitly so future room-floor work can
    # distinguish the legacy command from an opt-in strict FZM command.
    empty = bpy.data.scenes.new("Smoke Open Perimeter")
    bpy.context.window.scene = empty
    build_wall(types, (0, 0, 0), (4, 0, 0))
    assert bpy.ops.home_builder_walls.add_floor() == {"FINISHED"}
    assert any(obj.get("IS_FLOOR_BP") for obj in empty.objects)
    print("OBSERVED legacy Add Floor creates a rectangle for an open perimeter", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="Installed module, e.g. bl_ext.user_default.fzm_builder")
    parser.add_argument("--export-pdf", action="store_true")
    fixture = parser.add_mutually_exclusive_group()
    fixture.add_argument("--save-fixture", type=Path)
    fixture.add_argument("--load-fixture", type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    with TemporaryDirectory(prefix="builder-smoke-") as folder:
        smoke(args.package, Path(folder), args.save_fixture, args.load_fixture, args.export_pdf)
