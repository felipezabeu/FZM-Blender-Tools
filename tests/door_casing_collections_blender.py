"""Reproduce casing loss when the door is also in the plan source collection."""
from importlib import import_module
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



def casing(cage):
    children = [o for o in cage.children if o.get(finishes.CASING)]
    assert len(children) == 1, (cage.name, children)
    return children[0]


def check(cage, expected_profile):
    o = casing(cage)
    assert o['profile'] == expected_profile
    assert set(o.users_collection) == set(cage.users_collection)
    C.view_layer.update()
    assert o.name in C.scene.objects and o.name in C.view_layer.objects
    assert (o.matrix_world.translation - cage.matrix_world.translation).length < 1e-6
    ev = o.evaluated_get(C.evaluated_depsgraph_get())
    assert len(ev.data.vertices) > 0
    _, (w, h, d) = finishes._cage_dimensions(cage)
    assert abs(ev.dimensions.x-w-2*o['width']) < 1e-5
    assert abs(ev.dimensions.z-h-o['width']) < 1e-5


host = wall('Host', 3., 1., 0., 6.)
d1, leaf1 = door(host, .8)
d2, leaf2 = door(host, 3., 'BIFOLD')
layout = bpy.data.collections.new('Floor Plan Content')
# The plan uses this collection by instance, not as a child of the model scene.
plan_scene = bpy.data.scenes.new('Drawing Scene')
instance = bpy.data.objects.new('Plan Instance', None)
instance.instance_type = 'COLLECTION'
instance.instance_collection = layout
plan_scene.collection.objects.link(instance)
for ob in (d1, d2):
    layout.objects.link(ob)
    assert ob.users_collection[0] == layout and layout not in C.scene.collection.children_recursive

# Re-create the missing objects as 5.1.27 left them: attached to the right
# doors but only members of the uninstanced plan source, not the 3D scene.
def invisible_casing(ob):
    o = bpy.data.objects.new('Invisible old casing', bpy.data.meshes.new('Old casing'))
    o.parent = ob
    o[finishes.CASING] = True
    layout.objects.link(o)
    assert o.name not in C.scene.objects
    return o.name
old1, old2 = (invisible_casing(o) for o in (d1,d2))

select(leaf1)
assert bpy.ops.fzm_builder.door_casing(profile='COLONIAL') == {'FINISHED'}
assert bpy.data.objects.get(old1) is None
assert bpy.data.objects.get(old2) is not None
check(d1, 'COLONIAL')
assert bpy.ops.fzm_builder.door_casing(scope='SCENE', profile='STEP_BEVEL') == {'FINISHED'}
assert bpy.data.objects.get(old2) is None
for d in (d1,d2):
    check(d, 'STEP_BEVEL')

# Width must stay live, and applying the same profile repeatedly must not
# create invisible duplicates in either collection.
hb.GeoNodeCage(d1).set_input('Dim X', .66)
d1.update_tag()
check(d1, 'STEP_BEVEL')
for _ in range(2):
    assert bpy.ops.fzm_builder.door_casing(scope='SCENE', profile='COLONIAL') == {'FINISHED'}
    for d in (d1,d2):
        check(d, 'COLONIAL')
    assert sum(bool(o.get(finishes.CASING)) for o in layout.objects) == 2

select(leaf1)
assert bpy.ops.fzm_builder.door_casing(remove=True) == {'FINISHED'}
assert not any(o.get(finishes.CASING) for o in d1.children)
check(d2, 'COLONIAL')
assert bpy.ops.fzm_builder.door_casing(profile='FLAT') == {'FINISHED'}
check(d1, 'FLAT')
print('PASS: selected and bulk apply, resize, repeat, remove/reapply, same 3D and plan links')
