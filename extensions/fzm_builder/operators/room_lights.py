"""Shared placement, viewport fixture and lifecycle for Builder room lights."""

import math

import bpy
from mathutils import Matrix, Vector

ROOM_LIGHT = 'IS_ROOM_LIGHT'
FIXTURE_MESH = 'FZM_ROOM_LIGHT_FIXTURE_MESH'
LIGHT_KIND = 'FZM_ROOM_LIGHT_KIND'
LIGHT_TEMP = 'FZM_ROOM_LIGHT_TEMPERATURE'
POT_SHIFT = 'FZM_ROOM_LIGHT_POT_SHIFT'
LEGACY_OFFSET = 'FZM_ROOM_LIGHT_CEILING_OFFSET'
POT = 'POT_4'
POINT = 'POINT'

PRESETS = [
    (POT, '4″ Recessed Pot Light', 'Downward spot with visible 4-inch trim and lens'),
    (POINT, 'Custom Point', 'Omnidirectional Blender point light with no fixture mesh'),
]
POT_POWER = 12.0
POT_RADIUS = .040
POINT_POWER = 200.0
POINT_RADIUS = .1
# The spot emits below the lens rather than through an opaque trim mesh.
# Its direction is along local -Z.
POT_DROP = .009


def is_light(obj):
    return bool(obj and obj.type == 'LIGHT' and obj.get(ROOM_LIGHT)
                and not (obj.library or obj.override_library))


def light_from(obj):
    if is_light(obj):
        return obj
    if obj and obj.type == 'MESH' and obj.get(FIXTURE_MESH) and is_light(obj.parent):
        return obj.parent
    return None


def selected(context):
    return sorted({light for obj in context.selected_objects if (light := light_from(obj))},
                  key=lambda light: light.name)


def targets(context, scope):
    if scope != 'ALL':
        lights = selected(context)
        if lights or scope == 'SELECTED':
            return lights
    return sorted((obj for obj in context.scene.objects if is_light(obj)), key=lambda obj: obj.name)


def is_pot(obj):
    return obj.get(LIGHT_KIND) == POT and obj.data.type == 'SPOT'


def kelvin_to_rgb(temperature):
    """Preserve existing Builder approximation for compatible color updates."""
    temp = temperature / 100.0
    red = 255 if temp <= 66 else 329.698727446 * (temp - 60) ** -0.1332047592
    green = (99.4708025861 * math.log(temp) - 161.1195681661 if temp <= 66
             else 288.1221695283 * (temp - 60) ** -0.0755148492)
    blue = (255 if temp >= 66 else 0 if temp <= 19 else
            138.5177312231 * math.log(temp - 10) - 305.0447927307)
    return tuple(max(0., min(255., value)) / 255. for value in (red, green, blue))


def temperature_for(obj):
    # Existing files had RGB only. If the color was manually changed and is
    # not near our Kelvin curve, avoid guessing an unusual default.
    if LIGHT_TEMP in obj:
        return float(obj[LIGHT_TEMP])
    actual = tuple(obj.data.color)
    def error(k):
        return sum((channel - ref) ** 2 for channel, ref in zip(actual, kelvin_to_rgb(k)))
    candidate = min(range(2000, 6501, 25), key=error)
    return float(candidate if error(candidate) < .01 else 3000)


def _fixture_material(label, rgb, roughness, emission=0.):
    marker = 'fzm_room_light_material_v1'
    name = f'FZM Pot Light | {label}'
    material = bpy.data.materials.get(name)
    if material and material.get(marker) == label:
        return material
    material = bpy.data.materials.new(name)
    material[marker] = label
    material.diffuse_color = (*rgb, 1.)
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*rgb, 1.)
    shader.inputs['Roughness'].default_value = roughness
    if emission:
        shader.inputs['Emission Color'].default_value = (*rgb, 1.)
        shader.inputs['Emission Strength'].default_value = emission
    return material


def _fixture_mesh():
    name = 'FZM 4-inch Pot Light Trim and Lens'
    mesh = bpy.data.meshes.get(name)
    if mesh and mesh.get(FIXTURE_MESH) == 1:
        return mesh

    # Nominal 4″ opening; the flange is wider so it covers the edge of the cut.
    # Model the front surfaces at or below the ceiling rather than cutting the
    # room mesh: keeps export simple, no destructive boolean or coplanar faces.
    count = 40
    profile = ((.0635, -.00025), (.0628, -.0026), (.0508, -.00315),
               (.0473, -.00072), (.0432, -.00072))
    verts = [(r * math.cos(math.tau * i / count), r * math.sin(math.tau * i / count), z)
             for r, z in profile for i in range(count)]
    faces, slots = [], []
    for ring in range(len(profile) - 1):
        for i in range(count):
            j = (i + 1) % count
            faces.append((ring * count + j, ring * count + i,
                          (ring + 1) * count + i, (ring + 1) * count + j))
            slots.append(int(ring >= 2))
    faces.append(tuple(reversed(range((len(profile) - 1) * count, len(profile) * count))))
    slots.append(2)

    mesh = bpy.data.meshes.new(name)
    mesh[FIXTURE_MESH] = 1
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(_fixture_material('Trim', (.82, .81, .77), .32))
    mesh.materials.append(_fixture_material('Recess', (.19, .18, .16), .55))
    mesh.materials.append(_fixture_material('Frosted Lens', (.84, .83, .79), .38, 1.25))
    for polygon, slot in zip(mesh.polygons, slots):
        polygon.material_index = slot
    mesh.update()
    return mesh


def _managed_parts(light):
    return [obj for obj in light.children if obj.type == 'MESH' and obj.get(FIXTURE_MESH)]


def remove_fixture(light):
    for obj in _managed_parts(light):
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def ensure_fixture(light, collection):
    parts = _managed_parts(light)
    if parts:
        return parts[0]
    obj = bpy.data.objects.new('4-inch Pot Light | Trim and Lens', _fixture_mesh())
    collection.objects.link(obj)
    obj[FIXTURE_MESH] = True
    obj.parent = light
    obj.location.z = POT_DROP
    obj.color = (.9, .88, .83, 1.)
    return obj


def _collection(scene):
    name = f'{scene.name} - Lights'
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
    if name not in scene.collection.children:
        scene.collection.children.link(collection)
    return collection


def _apply_values(obj, temperature, power=None, radius=None):
    data = obj.data
    if data.users > 1 and (temperature is not None or power is not None or radius is not None):
        data = obj.data = data.copy()
    if temperature is not None:
        obj[LIGHT_TEMP] = temperature
        data.color = kelvin_to_rgb(temperature)
    if power is not None:
        data.energy = power
    if radius is not None and hasattr(data, 'shadow_soft_size'):
        data.shadow_soft_size = radius


def _spot_settings(data):
    # Blender Spot aims along -Z at zero rotation and spill fades at the edge.
    data.spot_size = math.radians(85.)
    data.spot_blend = .47


def create(scene, at, kind, temperature, power, radius, offset):
    pot = kind == POT
    data = bpy.data.lights.new('4-inch Pot Light' if pot else 'Room Light',
                               type='SPOT' if pot else 'POINT')
    obj = bpy.data.objects.new(data.name, data)
    col = _collection(scene)
    col.objects.link(obj)
    obj.location = at
    obj[ROOM_LIGHT] = True
    obj[LIGHT_KIND] = kind
    obj[LEGACY_OFFSET] = offset
    if pot:
        _spot_settings(data)
        obj.location.z -= POT_DROP
        obj[POT_SHIFT] = offset - POT_DROP
        ensure_fixture(obj, col)
    else:
        obj.location.z -= offset
    _apply_values(obj, temperature, power, radius)
    return obj


def ceiling_candidates(context, *, selected_first=False):
    def is_ceiling(obj):
        return obj.type == 'MESH' and obj.get('IS_CEILING_BP') and obj.visible_get(view_layer=context.view_layer)
    if selected_first:
        preferred = [obj for obj in context.selected_objects if is_ceiling(obj)]
        if preferred:
            return preferred
    return [obj for obj in context.view_layer.objects if is_ceiling(obj)]


class Ceiling:
    def __init__(self, obj, depsgraph):
        self.obj = obj.evaluated_get(depsgraph)
        self.matrix = self.obj.matrix_world.copy()
        self.inverse = self.matrix.inverted_safe()
        corners = [self.matrix @ Vector(co) for co in self.obj.bound_box]
        self.lower = tuple(min(co[i] for co in corners) for i in range(3))
        self.upper = tuple(max(co[i] for co in corners) for i in range(3))
        self.local_z = self.inverse.to_3x3() @ Vector((0., 0., 1.))

    def level_at(self, x, y):
        if not (self.lower[0] <= x <= self.upper[0] and self.lower[1] <= y <= self.upper[1]):
            return None
        start = self.inverse @ Vector((x, y, self.lower[2] - .05))
        # Test the real evaluated surface; concave outlines and nested-room
        # holes don't receive lights outside their actual ceiling.
        hit, pos, _, _ = self.obj.ray_cast(start, self.local_z)
        return (self.matrix @ pos).z if hit else None


def sample_ceilings(context, *, selected_first=False):
    depsgraph = context.evaluated_depsgraph_get()
    return [Ceiling(obj, depsgraph) for obj in ceiling_candidates(context, selected_first=selected_first)]


def nearby_ceiling(ceilings, world):
    options = [z for surface in ceilings if (z := surface.level_at(world.x, world.y)) is not None
               and -.015 <= z - world.z <= .45]
    return min(options, key=lambda z: abs(z - world.z)) if options else None


def update(scene, obj, mode, temperature, power, radius, ceilings):
    converting_to_pot = mode == POT and not is_pot(obj)
    converting_to_point = mode == POINT and (obj.data.type != 'POINT' or _managed_parts(obj))
    if converting_to_pot or converting_to_point:
        old = obj.data
        pot = converting_to_pot
        replacement = bpy.data.lights.new('4-inch Pot Light' if pot else 'Room Light',
                                          type='SPOT' if pot else 'POINT')
        replacement.color = old.color
        world = obj.matrix_world.copy()
        if pot:
            _spot_settings(replacement)
            z = nearby_ceiling(ceilings, world.translation)
            if z is None:
                z = world.translation.z + float(obj.get(LEGACY_OFFSET, .0254))
            delta = z - POT_DROP - world.translation.z
            world.translation.z += delta
            # Reset tilt for a recessed fixture: Blender's local -Z is down.
            # Keep the position on its host plane and align both light and trim.
            world = Matrix.Translation(world.translation)
            obj[POT_SHIFT] = delta
            ensure_fixture(obj, next(iter(obj.users_collection), None) or _collection(scene))
        else:
            world.translation.z -= float(obj.get(POT_SHIFT, 0.))
            if POT_SHIFT in obj:
                del obj[POT_SHIFT]
            remove_fixture(obj)
        obj.matrix_world = world
        obj.data = replacement
        if old.users == 0:
            bpy.data.lights.remove(old)
        obj[LIGHT_KIND] = mode
        if power is None:
            power = POT_POWER if pot else POINT_POWER
        if radius is None:
            radius = POT_RADIUS if pot else POINT_RADIUS
    elif is_pot(obj):
        # Rebuild a missing managed mesh without making duplicates.
        ensure_fixture(obj, next(iter(obj.users_collection), None) or _collection(scene))
    _apply_values(obj, temperature, power, radius)


def remove(obj):
    remove_fixture(obj)
    for child in list(obj.children):
        matrix = child.matrix_world.copy()
        child.parent = None
        child.matrix_world = matrix
    data = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if data.users == 0:
        bpy.data.lights.remove(data)
