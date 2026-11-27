"""Smoke real placement/update/delete and GLB fixture geometry in Blender 5.1."""
from importlib import import_module
import json
from math import isclose, pi
import os
from pathlib import Path
import struct
from mathutils import Vector

import bpy

C = bpy.context
key = next(key for key in C.preferences.addons.keys() if key.endswith('.fzm_builder'))
addon = import_module(key)
lights = import_module(key + '.operators.room_lights')
TEMP = Path(os.environ['FZM_TEST_TEMP'])


def select(*objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    C.view_layer.objects.active = objects[0] if objects else None
    C.view_layer.update()


def ceiling(name, x0, x1, y0, y1, level, split=False):
    if split:
        # An L-shaped ceiling; both bounds and face center vary from the
        # missing top-right quadrant. Real evaluated shape must be sampled.
        verts = [(x0,y0), (x1,y0), (x1,1), (1,1), (1,y1), (x0,y1)]
    else:
        verts = [(x0,y0), (x1,y0), (x1,y1), (x0,y1)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(*point,level) for point in verts], [], [tuple(reversed(range(len(verts))))])
    obj = bpy.data.objects.new(name, mesh)
    C.collection.objects.link(obj)
    obj['IS_CEILING_BP'] = True
    return obj


def get_lights():
    return {obj for obj in C.scene.objects if lights.is_light(obj)}


def glb(path, include_lights):
    bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', export_lights=include_lights)
    data = path.read_bytes()
    length, tag = struct.unpack_from('<II', data, 12)
    assert tag == 0x4E4F534A
    return json.loads(data[20:20 + length])


def check_spot(light, at):
    assert light.data.type == 'SPOT'
    assert isclose(light.data.energy, 12.)
    assert isclose(light.data.shadow_soft_size, .04, abs_tol=1e-7)
    mesh, = [child for child in light.children if child.get(lights.FIXTURE_MESH)]
    assert len(mesh.data.polygons) > 100 and len(mesh.data.materials) == 3
    assert all(poly.normal.z < 0. for poly in mesh.data.polygons)
    # The emitting light begins below every trim/lens face, pointing down.
    assert isclose((mesh.matrix_world.translation).z, at, abs_tol=1e-6)
    assert all((mesh.matrix_world @ v.co).z > light.matrix_world.translation.z
               for v in mesh.data.vertices)
    assert (light.matrix_world.to_3x3() @ Vector((0,0,-1))).z < -.99
    return mesh


main = ceiling('First Ceiling', 0, 4, 0, 4, 2.7, split=True)
other = ceiling('Other Ceiling', 5, 8, 0, 2, 3.2)
select(main)
assert bpy.ops.home_builder_walls.add_room_lights() == {'FINISHED'}
pots = get_lights()
assert len(pots) == 5, [tuple(o.location) for o in pots]
for obj in pots:
    assert obj.location.x < 1. or obj.location.y < 1.
    check_spot(obj, 2.7)
assert len({o.children[0].data for o in pots}) == 1

# Select the visible mesh as the user would, and edit one light.
spot = min(pots, key=lambda obj: obj.name)
part = spot.children[0]
select(part)
assert bpy.ops.home_builder_walls.update_room_lights(light_temperature=4000.) == {'FINISHED'}
assert spot[lights.LIGHT_TEMP] == 4000.
assert all(obj[lights.LIGHT_TEMP] == 3000. for obj in pots - {spot})
assert part in spot.children[:]
assert bpy.ops.home_builder_walls.update_room_lights(advanced=True, light_power=19., light_radius=.075) == {'FINISHED'}
assert isclose(spot.data.energy, 19.) and isclose(spot.data.shadow_soft_size, .075, abs_tol=1e-7)
assert all(isclose(obj.data.energy, 12.) for obj in pots - {spot})
assert bpy.ops.home_builder_walls.update_room_lights(fixture_type='POT_4') == {'FINISHED'}
assert len(spot.children) == 1 and spot.data.energy == 19.

# GLB must include visible fixture even if scene lights aren't exported.
for include_lights in (False, True):
    js = glb(TEMP / ('with-lights.glb' if include_lights else 'without-lights.glb'), include_lights)
    mesh_nodes = [n for n in js['nodes'] if 'Pot Light | Trim and Lens' in n.get('name', '') and 'mesh' in n]
    assert len(mesh_nodes) == len(pots), mesh_nodes
    assert len(js['meshes'][mesh_nodes[0]['mesh']]['primitives']) == 3
    assert any('emissiveFactor' in material for material in js['materials'])
    assert ('KHR_lights_punctual' in js.get('extensionsUsed', [])) == include_lights
    if include_lights:
        sources = js['extensions']['KHR_lights_punctual']['lights']
        assert len([o for o in sources if o['type'] == 'spot']) == len(pots)

# Legacy records are kept as lights (no migration until user converts).
legacy_data = bpy.data.lights.new('Legacy Builder Point', 'POINT')
legacy_data.energy = 170.
legacy_data.shadow_soft_size = .17
legacy_data.color = lights.kelvin_to_rgb(3300.)
legacy = bpy.data.objects.new('Old One', legacy_data)
C.collection.objects.link(legacy)
legacy.location = (6., 1., 3.15)
legacy['IS_ROOM_LIGHT'] = True
select(legacy)
assert bpy.ops.home_builder_walls.update_room_lights(light_temperature=3500.) == {'FINISHED'}
assert legacy.data == legacy_data and legacy.data.energy == 170. and not legacy.children
assert isclose(legacy.data.shadow_soft_size,.17,abs_tol=1e-7)
assert bpy.ops.home_builder_walls.update_room_lights(fixture_type='POT_4') == {'FINISHED'}
C.view_layer.update()
check_spot(legacy, 3.2)
legacy_child = legacy.children[0]
select(legacy_child)
assert bpy.ops.home_builder_walls.update_room_lights(fixture_type='POINT') == {'FINISHED'}
assert not legacy.children and legacy.data.type == 'POINT'
assert isclose(legacy.location.z, 3.15, abs_tol=1e-6)

# Explicit per-light delete removes that trim, without deleting all room lights.
select(part)
assert bpy.ops.home_builder_walls.delete_room_lights() == {'FINISHED'}
assert len(get_lights()) == 5
assert len([o for o in C.scene.objects if o.get(lights.FIXTURE_MESH)]) == 4

# Add custom on the other ceiling: prior point radiative settings remain its default.
select(other)
assert bpy.ops.home_builder_walls.add_room_lights(fixture_type='POINT', light_spacing=3.) == {'FINISHED'}
new = [obj for obj in get_lights() if obj.data.type == 'POINT' and obj != legacy]
assert len(new) == 1 and new[0].data.energy == 200. and not new[0].children

fixture_count = len([o for o in C.scene.objects if o.get(lights.FIXTURE_MESH)])
bpy.ops.wm.save_as_mainfile(filepath=str(TEMP / 'room-lights.blend'))
bpy.ops.wm.open_mainfile(filepath=str(TEMP / 'room-lights.blend'))
assert len([o for o in C.scene.objects if o.get(lights.FIXTURE_MESH)]) == fixture_count
assert bpy.ops.home_builder_walls.delete_room_lights(scope='ALL') == {'FINISHED'}
assert not get_lights() and not any(o.get(lights.FIXTURE_MESH) for o in C.scene.objects)
# Without a ceiling, the room-wall fallback still works for legacy projects.
for obj in list(C.scene.objects):
    if obj.get('IS_CEILING_BP'):
        bpy.data.objects.remove(obj, do_unlink=True)
for i, (x,y,rotation,length) in enumerate(((0,0,0,4), (4,0,pi/2,3),
                                         (4,3,pi,4), (0,3,-pi/2,3))):
    wall = addon.hb_types.GeoNodeWall()
    wall.create('Wall ' + str(i))
    wall.set_input('Height', 2.25)
    wall.set_input('Length', length)
    wall.obj.location = (x, y, .75)
    wall.obj.rotation_euler.z = rotation
select()
assert bpy.ops.home_builder_walls.add_room_lights(
    fixture_type='POINT', light_spacing=3., light_power=125.
) == {'FINISHED'}
point, = get_lights()
assert point.data.energy == 125. and isclose(point.location.z, 3. - .0254, abs_tol=1e-6)
print('ROOM LIGHTS / SELECTED UPDATES / LIFECYCLE / WALL FALLBACK / GLB PASSED')
