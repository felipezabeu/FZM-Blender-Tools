"""Apply room-side paint to the existing wall shader, not to overlay meshes."""

from collections import defaultdict
from dataclasses import dataclass

import bpy
from mathutils import Vector

from .. import hb_types
from . import baseboard_perimeter as perimeter

FINISH = 'FZM_ROOM_PAINT_FINISH'
BASE = 'FZM_ROOM_PAINT_BASE_MATERIAL'
REGIONS = 'FZM_ROOM_PAINT_REGIONS'
SIDE = 'FZM_ROOM_PAINT_NORMAL_Y'
# The supplied GeoNodeWall uses these sockets on its two long faces in local
# coordinates. Inside/Outside Face (Front/Back Surface in older assets) are
# end caps: their socket name is not a reliable indication of the room side.
SIDE_SOCKETS = (('Left Edge', 'Left Surface'), ('Right Edge', 'Right Surface'))


@dataclass(frozen=True)
class Region:
    floor: object
    start: float
    end: float
    material: object


def editable_wall(obj):
    return bool(obj and obj.type == 'MESH' and obj.get('IS_WALL_BP')
                and not (obj.library or obj.override_library))


def is_finish(material):
    return bool(material and material.get(FINISH))


def base_material(material):
    return material.get(BASE) if is_finish(material) else material


def get_regions(material):
    """Read the saved room refs kept with each wall's independent side shader."""
    if not is_finish(material):
        return ()
    return tuple(Region(item.get('floor'), item['start'], item['end'], item['material'])
                 for item in material.get(REGIONS, {}).values()
                 if item.get('floor') and item.get('material'))


def dispose(material):
    if is_finish(material) and material.users == 0 and not material.use_fake_user:
        bpy.data.materials.remove(material)


def _prepare_base(material, source):
    """Retain the original material graph and shader branch wherever it is unpainted."""
    material.use_nodes = True
    if source is not None and source.use_nodes:
        return
    node = next((n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if node and source is not None:
        for key, value in [('Base Color', source.diffuse_color),
                           ('Roughness', source.roughness), ('Metallic', source.metallic)]:
            node.inputs[key].default_value = value


def _node_layer(material, side, regions):
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    outputs = [n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
    if not outputs:
        outputs = [nodes.new('ShaderNodeOutputMaterial')]
    x, y = min(n.location.x for n in outputs), min(n.location.y for n in outputs)
    location = (x - 900, y - 430)

    def node(kind, label, pos):
        result = nodes.new(kind)
        result.label = label
        result.location = pos
        return result

    def plug(destination, value):
        if isinstance(value, bpy.types.NodeSocket):
            links.new(value, destination)
        else:
            destination.default_value = value

    def math(kind, a, b, pos, label):
        value = node('ShaderNodeMath', label, pos)
        value.operation = kind
        plug(value.inputs[0], a)
        plug(value.inputs[1], b)
        return value.outputs[0]

    coord = node('ShaderNodeTexCoord', 'Actual wall coordinates in local metres', location)
    split = node('ShaderNodeSeparateXYZ', 'Along the wall', (x - 660, y - 405))
    links.new(coord.outputs['Object'], split.inputs[0])
    position = split.outputs['X']

    geo = node('ShaderNodeNewGeometry', 'Actual face normal (not shading normal)', (x - 900, y - 730))
    convert = node('ShaderNodeVectorTransform', 'World to wall-local normal', (x - 675, y - 730))
    convert.vector_type = 'NORMAL'
    convert.convert_from = 'WORLD'
    convert.convert_to = 'OBJECT'
    links.new(geo.outputs['True Normal'], convert.inputs['Vector'])
    dot = node('ShaderNodeVectorMath', 'Only this room-facing wall side', (x - 465, y - 730))
    dot.operation = 'DOT_PRODUCT'
    links.new(convert.outputs['Vector'], dot.inputs[0])
    dot.inputs[1].default_value = (0, side, 0)
    side_mask = math('GREATER_THAN', dot.outputs['Value'], .9995,
                     (x - 260, y - 730), 'Exclude wall ends, top, jambs and trim')

    layers = []
    # Preserve the old socket until all branches are built (undo/restore).
    for i, region in enumerate(regions):
        base_y = y - 430 - 420 * i
        m0 = math('GREATER_THAN', position, region.start - 1e-6, (x - 460, base_y), 'Room start')
        m1 = math('LESS_THAN', position, region.end, (x - 460, base_y - 170), 'Room end')
        inside = math('MULTIPLY', m0, m1, (x - 260, base_y - 15), 'Room span')
        mask = math('MULTIPLY', inside, side_mask, (x - 65, base_y), 'Room-facing finish')
        coat = node('ShaderNodeBsdfPrincipled', region.material.name, (x + 150, base_y - 60))
        coat.inputs['Base Color'].default_value = region.material.diffuse_color
        coat.inputs['Roughness'].default_value = .65
        layers.append((mask, coat.outputs['BSDF']))

    for j, output in enumerate(outputs):
        socket = output.inputs['Surface']
        if socket.is_linked:
            shader = socket.links[0].from_socket
        else:
            shader = node('ShaderNodeBsdfTransparent', 'Original surface was empty',
                          (x - 250, y + j*180)).outputs[0]
        for i, (mask, coat) in enumerate(layers):
            mix = node('ShaderNodeMixShader', 'Paint on selected span only', (x + 390 + i*190, y + j*180))
            for socket_i, value in zip(mix.inputs, (mask, shader, coat)):
                links.new(value, socket_i)
            shader = mix.outputs[0]
        links.new(shader, socket)
        output.location.x = x + 430 + len(layers)*190


def make_finish(source, side, regions, name):
    """Create a non-destructive copy with paint layers OR restore the intact base."""
    if not regions:
        return source
    material = source.copy() if source is not None else bpy.data.materials.new(name)
    try:
        material.name = name
        material.use_fake_user = False
        material[FINISH] = True
        material[SIDE] = side
        if source is not None:
            material[BASE] = source
        material[REGIONS] = {str(i): {'floor': r.floor, 'start': r.start, 'end': r.end,
                                     'material': r.material}
                             for i, r in enumerate(regions)}
        _prepare_base(material, source)
        _node_layer(material, side, regions)
        return material
    except Exception:
        bpy.data.materials.remove(material)
        raise


def _swap(updates):
    """Build all materials before assigning any, preserving previous room work on failure."""
    staged = []
    try:
        for wall, socket, old, source, side, regions in updates:
            new = make_finish(source, side, regions, f'FZM Room Paint | {wall.obj.name} | {socket}')
            staged.append((wall, socket, old, new))
    except Exception:
        for _, _, _, new in staged:
            dispose(new)
        raise
    applied = []
    try:
        for wall, socket, old, new in staged:
            wall.set_input(socket, new)
            wall.obj.update_tag()
            applied.append((wall, socket, old, new))
    except Exception:
        for wall, socket, old, _ in reversed(applied):
            wall.set_input(socket, old)
            wall.obj.update_tag()
        for _, _, _, new in staged:
            dispose(new)
        raise
    old_materials = {old for _, _, old, _ in staged if is_finish(old)}
    for old in old_materials:
        dispose(old)


def room_runs(context, floor):
    """Map the floor perimeter to exact wall-side sockets and local metric x intervals."""
    context.view_layer.update()
    rings, level = perimeter.floor_boundaries(floor)
    walls = [wall for wall in perimeter.physical_walls(context, level) if editable_wall(wall.obj)]
    found = defaultdict(list)
    for edges in rings:
        by_edges = [perimeter.edge_runs(edge, walls) for edge in edges]
        for i, runs in enumerate(by_edges):
            next_edge, previous_edge = edges[(i + 1) % len(edges)], edges[i - 1]
            next_runs, prev_runs = by_edges[(i + 1) % len(edges)], by_edges[i - 1]
            next_run = next_runs[0] if next_runs and next_runs[0].left <= perimeter.MATCH else None
            prev_run = prev_runs[-1] if prev_runs and previous_edge.length - prev_runs[-1].right <= perimeter.MATCH else None
            for j, run in enumerate(runs):
                obj = run.face.wall.obj
                wall = hb_types.GeoNodeWall(obj)
                inverse = obj.matrix_world.inverted_safe()
                thickness = wall.get_input('Thickness')
                y = (inverse @ Vector((*run.face.origin, level))).y
                far = abs(y - thickness) < abs(y)
                left = perimeter.end_point(run, True, 0, previous_edge, prev_run) if j == 0 else run.face.at(run.edge, run.left)
                right = perimeter.end_point(run, False, 0, next_edge, next_run) if j == len(runs)-1 else run.face.at(run.edge, run.right)
                a, b = (inverse @ Vector((*p, level)) for p in (left, right))
                start, end = sorted((a.x, b.x))
                # The wall's nominal length measures its datum side. At a miter
                # the opposite face can extend beyond either datum endpoint,
                # leaving an old-color strip if clamped to [0, Length].
                corners = run.face.wall.corners
                if corners is not None:
                    face = (corners[3], corners[2]) if far else corners[:2]
                    low, high = sorted((inverse @ Vector((*p, level))).x for p in face)
                else:
                    low, high = 0., wall.get_input('Length')
                start, end = max(low, start), min(high, end)
                if end - start <= perimeter.EPS:
                    continue
                socket = next((name for name in SIDE_SOCKETS[far] if wall.has_input(name)), None)
                if not socket:
                    continue
                side = (1 if far else -1) * (1 if thickness >= 0 else -1)
                found[(obj, socket, side)].append((start, end))
    return dict(found)


def _merge(spans):
    joined = []
    for start, end in sorted(spans):
        if joined and start <= joined[-1][1] + 1e-5:
            joined[-1][1] = max(end, joined[-1][1])
        else:
            joined.append([start, end])
    return joined


def apply_room(context, floor, paint=None):
    """Apply the requested paint or clear only this selected room's old spans."""
    runs = room_runs(context, floor) if paint is not None else {}
    if paint is not None and not runs:
        raise ValueError('No physical wall faces match this floor perimeter at its level')
    # Include previous spans even if the floor outline moved. A room has one
    # assignment per surface; applying it again cannot leave stale old paint.
    candidates = {(obj, socket): (side, spans) for (obj, socket, side), spans in runs.items()}
    changes = []
    for obj in context.scene.objects:
        if not editable_wall(obj):
            continue
        wall = hb_types.GeoNodeWall(obj)
        for names in SIDE_SOCKETS:
            socket = next((name for name in names if wall.has_input(name)), None)
            if not socket:
                continue
            old = wall.get_input(socket)
            before = get_regions(old)
            kept = tuple(r for r in before if r.floor != floor)
            pick = candidates.get((obj, socket))
            if pick is None and before == kept:
                continue
            side, spans = pick if pick is not None else (old[SIDE], ())
            regions = kept + tuple(Region(floor, a, b, paint) for a, b in _merge(spans))
            changes.append((wall, socket, old, base_material(old), side, regions))
    _swap(changes)
    return len(changes)


def clear_walls(objects):
    changes = []
    for obj in objects:
        if not editable_wall(obj):
            continue
        wall = hb_types.GeoNodeWall(obj)
        for socket in wall.material_inputs(obj):
            old = wall.get_input(socket)
            if is_finish(old):
                changes.append((wall, socket, old, base_material(old), old[SIDE], ()))
    _swap(changes)


def update_base(wall, names, material):
    """Whole-wall/background edits retain room overlays unless scope explicitly clears them."""
    changes = []
    for name in names:
        old = wall.get_input(name)
        if is_finish(old):
            changes.append((wall, name, old, material, old[SIDE], get_regions(old)))
    _swap(changes)
    painted_sockets = {name for _, name, _, _, _, _ in changes}
    for name in names:
        if name not in painted_sockets:
            wall.set_input(name, material)
