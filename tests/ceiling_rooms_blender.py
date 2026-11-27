"""Run with packaged FZM Builder enabled in Blender 5.1.2."""
from importlib import import_module
import math

import bpy
from mathutils import Vector

package = next(key for key in bpy.context.preferences.addons.keys() if key.endswith('.fzm_builder'))
hb = import_module(package + '.hb_types')
mod = import_module(package + '.operators.ceiling_rooms')
reg = import_module(package + '.operators.floor_regions')
C = bpy.context


def clear():
    for obj in list(C.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def wall(name, a, b, *, h=2.6, half=False):
    d = Vector(b) - Vector(a)
    w = hb.GeoNodeWall()
    w.create(name)
    w.set_input('Length', d.xy.length)
    w.set_input('Thickness', .1)
    w.set_input('Height', h)
    w.obj.location = a
    w.obj.rotation_euler.z = math.atan2(d.y, d.x)
    if half:
        w.obj['IS_HALF_WALL'] = True
    return w.obj


def ring(label, coordinates, z=0, h=2.6):
    return [wall(label + str(i), (*a, z), (*b, z), h=h)
            for i, (a, b) in enumerate(zip(coordinates, coordinates[1:] + coordinates[:1]))]


def surfaces():
    return [obj for obj in C.scene.objects if obj.get(mod.CEILING)]


def owners(x, y, z=None):
    C.view_layer.update()
    p = Vector((x, y))
    matches = []
    for obj in surfaces():
        rings, height = mod.ceiling_footprint(obj)
        if z is not None and abs(z - height) > 1e-5:
            continue
        if reg.inside(rings[0], p) and not any(reg.inside(hole, p) for hole in rings[1:]):
            matches.append(obj)
    return matches


def add():
    assert bpy.ops.home_builder_walls.add_ceiling() == {'FINISHED'}


def update(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    C.view_layer.objects.active = obj
    assert bpy.ops.fzm_builder.update_ceiling_outline() == {'FINISHED'}


def check():
    for obj in surfaces():
        mesh = obj.data
        assert all(p.normal.z < -.999 for p in mesh.polygons), obj.name
        assert mesh.uv_layers.active.name == 'UVMap'
        assert not mesh.validate()
        for lp in mesh.loops:
            point = mesh.vertices[lp.vertex_index].co
            assert (mesh.uv_layers.active.uv[lp.index].vector - point.xy).length < 1e-6
    for a in surfaces():
        ai, ah = mod.ceiling_footprint(a)
        for b in surfaces():
            bi, bh = mod.ceiling_footprint(b)
            if a != b and abs(ah - bh) < 1e-5:
                assert not reg._positive_overlap(ai, bi)


# A full spanning wall and a T create three ceiling surfaces without a floor;
# a real open half-height wall does not partition the ceiling.
clear()
perimeter = [(0, 0), (6, 0), (6, 4), (0, 4)]
ring('Outer ', perimeter)
wall('Room divider', (3, .1, 0), (3, 3.9, 0))
wall('T', (.1, 2, 0), (2.90, 2, 0))
wall('Half wall', (4.5, .1, 0), (4.5, 3.9, 0), h=1, half=True)
add()
assert len(surfaces()) == 3, [o.name for o in surfaces()]
assert len(owners(1, 1)) == len(owners(1, 3)) == len(owners(4, 1)) == 1
assert owners(1, 1) != owners(1, 3) != owners(4, 1)
assert owners(4, 1) == owners(5, 1)
assert not owners(2.95, 1)
first = {obj.name: obj.data.as_pointer() for obj in surfaces()}
add()
assert first == {obj.name: obj.data.as_pointer() for obj in surfaces()}
check()

# Older, manually elevated ceiling should keep same object, UV, material,
# children and physical height when its new internal room is split off.
clear()
ring('Outer ', perimeter)
legacy_mesh = bpy.data.meshes.new('Legacy mesh')
legacy_mesh.from_pydata([(*p, 2.92) for p in perimeter], [], [(3, 2, 1, 0)])
uv = legacy_mesh.uv_layers.new(name='UVMap')
for loop in legacy_mesh.loops:
    uv.uv[loop.index].vector = legacy_mesh.vertices[loop.vertex_index].co.xy
legacy = bpy.data.objects.new('Legacy ceiling', legacy_mesh)
C.collection.objects.link(legacy)
legacy[mod.CEILING] = True
wall('Open spur', (0., 2.8, 0), (.65, 2.8, 0))
ring('Nested middle ', [(1, 1), (2.5, 1), (2.5, 2.5), (1, 2.5)])
palette = bpy.data.materials.new('Existing ceiling finish')
legacy.data.materials.append(palette)
legacy.material_slots[0].link = 'OBJECT'
legacy.material_slots[0].material = palette
legacy.location.z = .1
attachment = bpy.data.objects.new('Existing pendant attachment', None)
C.collection.objects.link(attachment)
attachment.parent = legacy
C.view_layer.update()
update(legacy)
assert len(surfaces()) == 2 and legacy in surfaces()
assert attachment.parent == legacy
assert len(mod.ceiling_footprint(legacy)[0]) == 2
assert all(o.material_slots[0].material == palette and abs(mod.ceiling_footprint(o)[1] - 3.02) < 1e-5
           for o in surfaces())
assert owners(4, 2) == [legacy] and owners(1.5, 1.5) != [legacy]
inner, = owners(1.5, 1.5)
inner_palette = bpy.data.materials.new('Existing interior ceiling finish')
inner.material_slots[0].material = inner_palette
update(inner)
assert inner.material_slots[0].material == inner_palette
check()

# Preserve independent legacy nested room and stacked room objects, each at
# its actual level; update of one level must not alter the other level.
clear()
ring('Low ', perimeter, z=.4, h=2.42)
ring('High ', perimeter, z=3.1, h=2.58)
add()
assert len(surfaces()) == 2
low, = owners(1, 1, 2.82)
high, = owners(1, 1, 5.68)
original_high = high.data.as_pointer()
wall('Lower split', (3, .1, .4), (3, 3.9, .4), h=2.42)
update(low)
assert len(surfaces()) == 3 and high.data.as_pointer() == original_high
assert owners(1, 1, 2.82) != owners(4, 1, 2.82)
assert owners(1, 1, 5.68) == owners(4, 1, 5.68) == [high]
check()

# No speculative index-based rectangles for open wall chains.
clear()
wall('Only wall', (0, 0, 0), (3, 0, 0))
assert bpy.ops.home_builder_walls.add_ceiling() == {'CANCELLED'}
assert not surfaces()
print('ROOM CEILING PARTITIONS PASSED')
