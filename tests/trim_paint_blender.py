"""Smoke test for door and baseboard paint against the installed extension."""
from collections import Counter
from importlib import import_module
import os
from pathlib import Path
from types import SimpleNamespace

import bpy

C = bpy.context
package = next(key for key in C.preferences.addons.keys() if key.endswith('.fzm_builder'))
hb = import_module(package + '.hb_types')
ops = import_module(package + '.operators.doors_windows')
nd = import_module(package + '.operators.native_doors')
hinged = import_module(package + '.operators.hinged_doors')
finishes = import_module(package + '.operators.finishes')
trim = import_module(package + '.operators.trim_paint')


def select(*objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    C.view_layer.objects.active = objects[0]
    C.view_layer.update()


def wall(name, x, y, angle, length):
    obj = hb.GeoNodeWall()
    obj.create(name)
    obj.set_input('Thickness', .14)
    obj.set_input('Length', length)
    obj.set_input('Height', 2.65)
    obj.obj.location = (x, y, 0)
    obj.obj.rotation_euler.z = angle
    return obj.obj


def door(host, x, kind=None, style='FLAT'):
    cls = ops.FZM_OT_place_native_door if kind else ops.home_builder_doors_windows_OT_place_door
    state = SimpleNamespace(report=lambda cats, msg: print(msg),
                            register_placement_object=lambda obj: None,
                            create_placement_dimensions=lambda: None)
    for name in ('OBJECT_NAME', 'BP_FLAG', 'MENU_ID', 'WIDTH_PROP_NAME', 'HEIGHT_PROP_NAME',
                 'HAS_SWING', 'INITIAL_SWING_INPUTS', 'TEXT_NAME', 'TEXT_KIND'):
        setattr(state, name, getattr(cls, name))
    if kind:
        state.door_type, state.opening_width, state.opening_height = kind, 1.1, 2.03
        state.opening_amount, state.right_hand = 0., True
        state.bypass_style = state.leaf_style = style
    state.cut_wall = lambda w, c: ops.WallObjectPlacementMixin.cut_wall(state, w, c)
    cls.create_placed_object(state, C)
    cage = state.placed_obj
    cage.obj.parent = host
    cage.obj.location = (x, 0, 0)
    cage.set_input('Dim Y', hb.GeoNodeWall(host).get_input('Thickness'))
    C.view_layer.update()
    assert cls.finish_wall_opening(state, host)
    return cage.obj, nd.visual_for(cage.obj) if kind else hinged.visual_for(cage.obj)


def faces_with_material(obj):
    C.view_layer.update()
    mesh = obj.evaluated_get(C.evaluated_depsgraph_get()).data
    return Counter(mesh.materials[p.material_index].name if len(mesh.materials) else ''
                   for p in mesh.polygons)


def paint(target, color='#B6B5AB', **opts):
    return bpy.ops.fzm_builder.wall_paint(target=target, hex_color=color, **opts)


def assert_door(before, after, applied):
    expected = Counter()
    for name, count in before.items():
        material = bpy.data.materials.get(name)
        expected[applied.name if material and material.get('fzm_native_door_material') in trim.COATS
                 else name] += count
    assert after == expected, (before, after, expected)
    assert applied.name in after


front = wall('Front', 0, 0, 0, 13)
east = wall('East', 13, 0, 1.57079632679, 4)
north = wall('North', 13, 4, 3.14159265359, 13)
west = wall('West', 0, 4, -1.57079632679, 4)
d1, v1 = door(front, 1.)
d2, v2 = door(front, 2.5)
pairs = [door(front, 4., 'BIFOLD', 'SIX_PANEL'), door(front, 6., 'BYPASS', 'MIRROR'),
         door(front, 8., 'BYPASS', 'SHAKER_2'), door(front, 10., 'POCKET', 'FLAT')]
select(v1)
assert bpy.ops.fzm_builder.edit_door(leaf_style='SHAKER_5', hardware='LEVER',
                                    hardware_finish='BRUSHED_GOLD', panel_fill='FROSTED') == {'FINISHED'}
paintable = [(d1, v1), (d2, v2), *[pair for pair in pairs if pair[1] != pairs[1][1]]]
before = {part: faces_with_material(part) for _, part in [*paintable, pairs[1]]}
assert len(before[v1]) >= 3, before[v1]
select(v1)
assert paint('DOORS') == {'FINISHED'}
assert_door(before[v1], faces_with_material(v1), d1[trim.KEY])
assert faces_with_material(v2) == before[v2]

assert paint('DOORS', '#EDEAE5', trim_scope='ALL') == {'FINISHED'}
for cage, visual in paintable:
    assert_door(before[visual], faces_with_material(visual), cage[trim.KEY])
assert faces_with_material(pairs[1][1]) == before[pairs[1][1]]
select(v2)
assert bpy.ops.fzm_builder.edit_door(leaf_style='SHAKER_5', opening_amount=.6) == {'FINISHED'}
assert v2.modifiers[-1].node_group.get(trim.MODIFIER_KEY) == v2.modifiers[0].node_group
assert v2.parent[trim.KEY].name in faces_with_material(v2)
saved_color = v2.parent[trim.KEY].name
select(v1)
assert paint('DOORS', trim_white=True) == {'FINISHED'}
assert faces_with_material(v1) == before[v1]

# An existing manually assigned casing must remain untouched unless opted in.
legacy = bpy.data.materials.new('Custom legacy casing')
select(v1, v2)
assert bpy.ops.fzm_builder.door_casing(profile='COLONIAL', material=legacy.name) == {'FINISHED'}
def casing_for(cage):
    return next(part for part in cage.children if part.get(finishes.CASING))

c1, c2 = casing_for(d1), casing_for(d2)
geometry1 = c1.data
select(c1)
assert paint('DOORS', '#ABCDEF') == {'FINISHED'}
assert c1.material_slots[0].material == legacy
assert paint('DOORS', paint_leaf=False, casing_mode='MATCH') == {'FINISHED'}
assert c1.material_slots[0].material == d1[trim.KEY]
assert c1.data == geometry1 and len(c1.data.shape_keys.key_blocks) == 4
assert paint('DOORS', '#314159') == {'FINISHED'}
assert c1.material_slots[0].material == d1[trim.KEY]
assert c2.material_slots[0].material == legacy
assert paint('DOORS', trim_white=True) == {'FINISHED'}
assert c1.material_slots[0].material == nd.material('white')
assert faces_with_material(v1) == before[v1]

# Custom mode uses its own input and does not change the leaf. A later
# casing rebuild must keep it, even if the profile tool has a default material.
select(v1)
assert paint('DOORS', paint_leaf=False, casing_mode='CUSTOM', casing_hex_color='#D4B624') == {'FINISHED'}
independent = c1.material_slots[0].material
assert independent.name.endswith('#D4B624')
assert faces_with_material(v1) == before[v1]
assert paint('DOORS', '#654321') == {'FINISHED'}
assert independent == c1.material_slots[0].material
assert bpy.ops.fzm_builder.door_casing(profile='STEP_BEVEL', material=legacy.name) == {'FINISHED'}
c1 = casing_for(d1)
assert independent == c1.material_slots[0].material
assert len(c1.data.shape_keys.key_blocks) == 4
assert c2.material_slots[0].material == legacy
select(v1)
try:
    paint('DOORS', '#111111', casing_mode='CUSTOM', casing_hex_color='invalid')
except RuntimeError:
    pass  # Blender promotes the operator's validation report to RuntimeError.
assert d1[trim.KEY].name.endswith('#654321') and c1.material_slots[0].material == independent

# A casing may be painted before its geometry exists without generating it.
d3, v3 = pairs[-1]
select(v3)
assert paint('DOORS', paint_leaf=False, casing_mode='CUSTOM', casing_input_mode='RGB',
             casing_rgb_color=(.2, .4, .6)) == {'FINISHED'}
assert not any(part.get(finishes.CASING) for part in d3.children)
assert bpy.ops.fzm_builder.door_casing() == {'FINISHED'}
assert casing_for(d3).material_slots[0].material.name.endswith('#336699')

if path_to_palette := os.environ.get('FZM_SW_TEST_ASE'):
    assert bpy.ops.fzm_builder.import_paint_palette(filepath=path_to_palette) == {'FINISHED'}
    select(casing_for(d3))
    assert paint('DOORS', paint_leaf=False, casing_mode='CUSTOM', casing_input_mode='PALETTE',
                 casing_paint_code='Snowbound (SW 7004)') == {'FINISHED'}
    assert casing_for(d3).material_slots[0].material.name.endswith('Snowbound (SW 7004)')

select(front, east, north, west)
assert bpy.ops.home_builder_walls.add_floor() == {'FINISHED'}
floor = next(obj for obj in C.scene.objects if obj.get('IS_FLOOR_BP'))
select(floor)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO') == {'FINISHED'}
base = next(obj for obj in floor.children if obj.get(finishes.BASEBOARD))
select(east)
assert bpy.ops.fzm_builder.room_baseboards(wall_source='WALL_FACES') == {'FINISHED'}
loose, = finishes.wall_trim_children(east)
assert all(obj.material_slots[0].material.get('fzm_baseboard_white') for obj in (base, loose))
select(floor)
assert paint('BASEBOARDS', '#E2DDD0') == {'FINISHED'}
board_color = base.material_slots[0].material
assert board_color.name.endswith('#E2DDD0') and loose.material_slots[0].material.get('fzm_baseboard_white')
assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO', height=.13) == {'FINISHED'}
assert base.material_slots[0].material == board_color
select(loose)
assert paint('BASEBOARDS', '#B6B5AB') == {'FINISHED'}
assert loose.material_slots[0].material.name.startswith('FZM Paint #B6B5AB')
assert paint('BASEBOARDS', trim_white=True) == {'FINISHED'}
assert loose.material_slots[0].material.get('fzm_baseboard_white')
select(floor)
assert bpy.ops.fzm_builder.wall_paint(target='WALLS', scope='ROOM', hex_color='#123456') == {'FINISHED'}
assert base.material_slots[0].material == board_color and v2.parent[trim.KEY].name == saved_color
path = str(Path(os.environ['FZM_TEST_TEMP']) / 'paint-roundtrip.blend')
v2_name, base_name, casing_name = v2.name, base.name, c1.name
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
assert saved_color in faces_with_material(bpy.data.objects[v2_name])
assert bpy.data.objects[base_name].material_slots[0].material.name.endswith('#E2DDD0')
casing_reopened = bpy.data.objects[casing_name]
assert casing_reopened.material_slots[0].material.name.endswith('#D4B624')
assert casing_reopened.parent[finishes.CASING_PAINT_MODE] == 'CUSTOM'
print('DOOR, CASING, AND BASEBOARD PAINT PASSED')
