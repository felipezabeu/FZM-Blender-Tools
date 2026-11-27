"""Regression test for the viewport context menu and selected-door sidebar."""
from importlib import import_module
from types import SimpleNamespace

import bpy

C = bpy.context
package = next(key for key in C.preferences.addons.keys() if key.endswith('.fzm_builder'))
hb = import_module(package + '.hb_types')
ops = import_module(package + '.operators.doors_windows')
nd = import_module(package + '.operators.native_doors')
hinged = import_module(package + '.operators.hinged_doors')
finishes = import_module(package + '.operators.finishes')


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


menu = import_module(package + '.ui.menu_apend')
sidebar = import_module(package + '.ui.view3d_sidebar')
pose = import_module(package + '.ui.door_pose')
units = import_module(package + '.operators.door_units')


class Layout:
    """Record buttons drawn by the real callbacks (Blender has no headless UILayout)."""
    def __init__(self):
        self.actions = []
        self.operator_context = 'INVOKE_DEFAULT'

    def __getattr__(self, name):
        if name in {'column', 'row', 'box'}:
            return lambda **kwargs: self
        if name in {'prop', 'separator'}:
            return lambda *args, **kwargs: None
        if name in {'operator', 'menu', 'label'}:
            def record(target=None, **kwargs):
                self.actions.append(target or kwargs.get('text'))
                return SimpleNamespace()
            return record
        raise AttributeError(name)


def render(draw):
    layout = Layout()
    draw(SimpleNamespace(layout=layout), C)
    return layout.actions


def right_click_actions():
    return render(menu.draw_object_mode_right_click_menu)


def sidebar_actions():
    return render(sidebar.HOME_BUILDER_PT_room_layout_doors_windows.draw)


edit = 'fzm_builder.edit_door'
toggle = 'home_builder_doors_windows.toggle_double_door'
swing = 'home_builder_doors_windows.flip_door_swing'
hand = 'home_builder_doors_windows.flip_door_hand'
shortcuts = {edit, toggle, swing, hand, pose.TOGGLE}

# The door is placed on a real wall with a live opening, casing and plan arc.
host = wall('Host', 0, 0, 0, 8)
cage, leaf = door(host, 1.)
select(leaf)
assert bpy.ops.fzm_builder.door_casing(profile='COLONIAL') == {'FINISHED'}
casing = next(part for part in cage.children if part.get(finishes.CASING))
arc = hinged.swing_for(cage)
assert arc
for part in (leaf, casing, arc.obj, cage):
    select(part)
    assert units.cage_for(part) == cage, part.name
    for actions in (right_click_actions(), sidebar_actions()):
        assert shortcuts <= set(actions), (part.name, actions)
        assert 'HOME_BUILDER_MT_door_commands' not in actions, actions

# Check the actual operator state changes and visibility, with casing selected.
select(casing)
left = arc.get_input('Is Left')
inside = arc.get_input('Swing Inside')
origin = cage.location.copy()
assert bpy.ops.home_builder_doors_windows.flip_door_hand() == {'FINISHED'}
assert arc.get_input('Is Left') != left
assert bpy.ops.home_builder_doors_windows.flip_door_swing() == {'FINISHED'}
assert arc.get_input('Swing Inside') != inside
assert bpy.ops.home_builder_doors_windows.toggle_double_door() == {'FINISHED'}
assert arc.get_input('Is Double') and cage.location == origin
for actions in (right_click_actions(), sidebar_actions()):
    assert shortcuts - {hand} <= set(actions) and hand not in actions, actions
assert bpy.ops.home_builder_doors_windows.toggle_double_door() == {'FINISHED'}
assert not arc.get_input('Is Double') and hand in right_click_actions()
assert pose.command_label(C) == 'Open Door'
assert bpy.ops.fzm_builder.toggle_door_pose() == {'FINISHED'}
assert pose.command_label(C) == 'Close Door'

# A pocket or bifold still gets Edit Door and pose, but no hinged operations.
for offset, kind in ((3., 'POCKET'), (6., 'BIFOLD')):
    _, part = door(host, offset, kind)
    select(part)
    for actions in (right_click_actions(), sidebar_actions()):
        assert {edit, pose.TOGGLE} <= set(actions) and not {toggle, swing, hand} & set(actions), (kind, actions)

select(host)
assert not shortcuts & set(right_click_actions())
assert not shortcuts & set(sidebar_actions())
assert 'HOME_BUILDER_MT_wall_commands' in right_click_actions(), right_click_actions()
select(leaf)
print('PASS: direct context menu and sidebar; leaf, casing, plan arc, cage; actual flips and single / double; pocket, bifold and wall')
