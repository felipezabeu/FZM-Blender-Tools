"""Headless browser-free Blender test. Install this extension in a test profile first."""
from math import atan2, hypot
from collections import defaultdict

import bpy

addon = next(
    key for key in bpy.context.preferences.addons.keys()
    if key.rsplit(".", 1)[-1] == "fzm_builder"
)
mod = __import__(addon, fromlist=["hb_types"])
hb_types = mod.hb_types
from importlib import import_module
finishes = import_module(f"{addon}.operators.finishes")
sh = import_module(f"{addon}.operators.shower_area")
C = bpy.context

for item in list(C.scene.objects):
    bpy.data.objects.remove(item, do_unlink=True)


def selected(*objs):
    for o in C.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    C.view_layer.objects.active = objs[0]
    C.view_layer.update()


def wall(name, a, b):
    ob = hb_types.GeoNodeWall()
    ob.create(name)
    for label, val in (
        ("Length", hypot(b[0] - a[0], b[1] - a[1])),
        ("Height", 2.45), ("Thickness", .1),
    ):
        ob.set_input(label, val)
    ob.obj.location = (*a, 0)
    ob.obj.rotation_euler.z = atan2(b[1] - a[1], b[0] - a[0])
    return ob.obj


main = wall("Partition", (0, 0), (4, 0))
right = wall("North east", (4, 0), (4, 3))
rear = wall("North rear", (4, 3), (0, 3))
left = wall("North west", (0, 3), (0, 0))
north_walls = main, right, rear, left
selected(*north_walls)
assert bpy.ops.home_builder_walls.add_floor() == {"FINISHED"}
north = next(o for o in C.scene.objects if o.get("IS_FLOOR_BP"))

# Build the opposite room with the same real physical partition. Its outline
# substitutes a simple known rectangle for the unrelated multi-room floor detector.
wall("South west", (0, 0), (0, -3))
wall("South rear", (0, -3), (4, -3))
wall("South east", (4, -3), (4, 0))
mesh = bpy.data.meshes.new("South floor")
mesh.from_pydata([(.1,-2.9,0),(3.9,-2.9,0),(3.9,0,0),(.1,0,0)], [], [(0,1,2,3)])
mesh.update()
south = bpy.data.objects.new("South floor", mesh)
C.collection.objects.link(south)
south["IS_FLOOR_BP"] = True

door = hb_types.GeoNodeCage()
door.create("Partition Door")
door.obj["IS_ENTRY_DOOR_BP"] = True
door.obj.parent = main
door.obj.location.x = 2.65
for k, v in {"Dim X": .8, "Dim Y": .1, "Dim Z": 2.04}.items():
    door.set_input(k,v)
selected(door.obj)
assert bpy.ops.fzm_builder.door_casing(scope="SELECTED", width=.075) == {"FINISHED"}
assert any(item.get(finishes.CASING) for item in door.obj.children)
opening = main.modifiers.new("Door cutout", "BOOLEAN")
opening.operation = "DIFFERENCE"
opening.solver = "EXACT"
opening.object = door.obj

material = bpy.data.materials.new("Keep this trim finish")


def add_trim(floor, source, walls=()):
    selected(floor, *walls)
    assert bpy.ops.fzm_builder.room_baseboards(
        wall_source=source, profile="STEP_BEVEL", height=.137, thickness=.025,
        material=material.name,
    ) == {"FINISHED"}
    return next(o for o in floor.children if o.get(finishes.BASEBOARD))


trim_south = add_trim(south, "AUTO")


def islands(trim):
    neighbors = defaultdict(set)
    for edge in trim.data.edges:
        a, b = edge.vertices
        neighbors[a].add(b)
        neighbors[b].add(a)
    verts = [trim.matrix_world @ v.co for v in trim.data.vertices]
    unseen = set(neighbors)
    while unseen:
        indices = [unseen.pop()]
        for i in indices:
            for j in sorted(neighbors[i] & unseen):
                indices.append(j)
                unseen.remove(j)
        yield [verts[i] for i in indices]


def partition_spans(trim, y, tolerance=.03):
    return sorted(tuple(round(f(p.x for p in ring), 4) for f in (min, max))
                  for ring in islands(trim) if all(abs(p.y-y) < tolerance for p in ring))


def assert_corner_no_other_changes(trim, original):
    assert trim.parent == north
    assert trim["profile"] == "STEP_BEVEL"
    assert abs(trim["height"] - .137) < 1e-5 and abs(trim["thickness"] - .025) < 1e-5
    assert tuple(trim.material_slots)[0].material == material
    assert trim_south.data == original
    assert not [o for o in C.scene.objects if o.get(finishes.BASEBOARD) and o.parent not in (north,south)]


for mode in ("AUTO", "SELECTED"):
    trim = add_trim(north, mode, north_walls if mode=="SELECTED" else ())
    opposite = trim_south.data
    south_spans = partition_spans(trim_south, 0)
    before = partition_spans(trim, .1)
    assert len(before) == 2 and before[0][1] < 2.65 and before[1][0] > 3.45, (mode,before)
    assert len(south_spans) == 2, (mode,south_spans)

    # Bounds created before any tile: trim unchanged. Both start/end are measured
    # from the wall's physical start, not from the miter at the corner.
    selected(main)
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.45,use_end=True,end=1.55) == {"FINISHED"}
    assert partition_spans(trim, .1) == before

    selected(main, left)
    assert bpy.ops.fzm_builder.shower_area(tile_shape="HEX", tile_finish="WHITE_GREY_VEINS") == {"FINISHED"}
    area = C.object
    assert sh.controller_for(area) == area
    expected = [(before[0][0], .45),(1.55,before[0][1]),before[1]]
    assert partition_spans(trim, .1) == expected, (mode,partition_spans(trim,.1),expected)
    assert not [ring for ring in islands(trim) if all(abs(p.x-.1) < .031 for p in ring)]
    assert_corner_no_other_changes(trim, opposite)

    # Re-enter Add Baseboards after the tile exists, as well as the live update.
    assert add_trim(north, mode, north_walls if mode=="SELECTED" else ()) == trim
    assert partition_spans(trim, .1) == expected
    assert_corner_no_other_changes(trim, opposite)

    selected(next(p for p in area.children if p.get("fzm_shower_wall") == main))
    assert bpy.ops.fzm_builder.wall_divider(use_start=True,start=.70,use_end=True,end=2.72) == {"FINISHED"}
    expected = [(before[0][0], .7),before[1]]
    assert partition_spans(trim, .1) == expected, (mode,partition_spans(trim,.1),expected)
    assert C.object.get(sh.PART), "the new tile face stays selected"
    assert_corner_no_other_changes(trim, opposite)

    selected(area)
    assert bpy.ops.fzm_builder.shower_area(bottom=.05, tile_shape="PENNY", tile_finish="LIGHT_TERRAZZO") == {"FINISHED"}
    assert partition_spans(trim, .1) == before, (mode,partition_spans(trim,.1),before)
    assert [ring for ring in islands(trim) if all(abs(p.x-.1) < .031 for p in ring)]

    selected(area)
    assert bpy.ops.fzm_builder.shower_area(bottom=0) == {"FINISHED"}
    assert partition_spans(trim, .1) == expected
    assert_corner_no_other_changes(trim, opposite)

    # Clear dividers via the existing numeric entry point: full tile on front
    # deletes all front trim and must not change the opposite face.
    selected(main)
    assert bpy.ops.fzm_builder.wall_divider(clear=True) == {"FINISHED"}
    assert not partition_spans(trim, .1)
    assert_corner_no_other_changes(trim, opposite)

    selected(area)
    assert bpy.ops.fzm_builder.shower_area(remove=True) == {"FINISHED"}
    assert partition_spans(trim, .1) == before
    assert_corner_no_other_changes(trim, opposite)

print("PASS: automatic and selected trim; apply tile, alter divider, raise tile, restore, clear and remove tile; actual spans, opposite surface, casing and trim profile/material invariant.")
