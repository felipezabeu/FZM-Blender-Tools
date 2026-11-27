"""Plan separate room ceilings from the same physical wall graph as floors."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Matrix, Vector

from .. import hb_types
from . import floor_outline as outlines, floor_regions as regions
from .floor_divider import inside
from .floor_thresholds import physical_floor_ring

CEILING = 'IS_CEILING_BP'
ENVELOPE = 'FZM_CEILING_ENVELOPE'
HOSTS = 'FZM_CEILING_ROOM_HOSTS'
BASE_LEVEL = 'FZM_CEILING_BASE_LEVEL'
EPS = outlines.SHAPE_EPS
WORLD = Matrix.Identity(4)


@dataclass
class Plan:
    envelope: frozenset
    hosts: frozenset
    base: float
    rings: list
    datum: list
    height: float
    obj: object = None
    inherit: object = None


def editable_ceiling(obj):
    return bool(obj and obj.get(CEILING) and obj.type == 'MESH'
                and not (obj.library or obj.override_library))


def ceiling_footprint(obj):
    """Return physical planar world XY boundary rings (outer first) and world Z."""
    mesh = obj.data
    verts = [obj.matrix_world @ v.co for v in mesh.vertices]
    if not verts or not mesh.polygons:
        raise ValueError('This ceiling does not contain a planar room surface.')
    z = verts[0].z
    if any(not all(isfinite(v) for v in pt) or abs(pt.z - z) > outlines.LEVEL_EPS for pt in verts):
        raise ValueError('A sloped or non-planar ceiling cannot be updated as a room ceiling.')
    counts = Counter(tuple(sorted(e)) for p in mesh.polygons for e in p.edge_keys)
    if any(n not in (1, 2) for n in counts.values()):
        raise ValueError('A non-manifold ceiling cannot be updated.')
    links = defaultdict(set)
    for (a, b), count in counts.items():
        if count == 1:
            links[a].add(b)
            links[b].add(a)
    if not links or any(len(adj) != 2 for adj in links.values()):
        raise ValueError('A continuous room boundary could not be read from this ceiling.')
    rings = []
    remaining = set(links)
    while remaining:
        start = current = min(remaining)
        prev = -1
        ring = []
        while current in remaining:
            ring.append(verts[current].xy)
            remaining.remove(current)
            nxt = next(i for i in sorted(links[current]) if i != prev)
            prev, current = current, nxt
        if current != start:
            raise ValueError('A continuous room boundary could not be read from this ceiling.')
        outlines._validate_ring(ring)
        rings.append(ring)
    rings.sort(key=lambda ring: -abs(regions.area_at_origin(ring)))
    if any(not inside(rings[0], hole[0]) or regions.crosses(rings[0], hole) for hole in rings[1:]):
        raise ValueError('A ceiling with disconnected pieces cannot be updated automatically.')
    return rings, z


def _wall_height(wall):
    item = hb_types.GeoNodeWall(wall)
    value = item.get_input('Height') if item.has_input('Height') else None
    if value is None or not isfinite(value) or value <= EPS:
        return None
    if wall.get('WALL_TYPE') == 'Half' or wall.get('IS_HALF_WALL'):
        return None
    height = (wall.matrix_world @ Vector((0., 0., value))).z
    return height if isfinite(height) else None


def _heights(hosts, base, fallback):
    values = [_wall_height(w) for w, _ in hosts]
    values = [h for h in values if h is not None and h > base + EPS]
    if not values:
        return base + fallback
    counts = Counter(round(height / outlines.LEVEL_EPS) for height in values)
    key = max(counts, key=lambda candidate: (counts[candidate], candidate))
    return next(height for height in values if round(height / outlines.LEVEL_EPS) == key)


def _records(obj, name):
    return [(row.get('wall'), bool(row.get('reversed')))
            for _, row in sorted(obj.get(name, {}).items()) if row.get('wall')]


def _envelopes(context, walls):
    from .walls import find_wall_chains

    # Generating from walls alone supports scenes without any Floor objects;
    # a saved floor envelope also recovers reversed and structurally split walls.
    cycles = []
    levels = []
    for edge in sorted(walls, key=lambda row: row.level):
        if not levels or abs(levels[-1] - edge.level) > outlines.LEVEL_EPS:
            levels.append(edge.level)
    for base in levels:
        same = [edge for edge in walls if abs(edge.level - base) <= outlines.LEVEL_EPS]
        cycles.extend(regions._closed_components(same, physical_contacts=True))
        cycles.extend([(wall, False) for wall in chain]
                      for chain in find_wall_chains([edge.obj for edge in same]))
    for obj in context.view_layer.objects:
        if obj.get('IS_FLOOR_BP'):
            cycles.append(_records(obj, regions.ENVELOPE) or _records(obj, outlines.HOSTS))

    candidates = []
    seen = set()
    lookup = {edge.obj: edge for edge in walls}
    for hosts in cycles:
        key = frozenset(w for w, _ in hosts)
        if len(key) < 3 or key in seen or not key <= lookup.keys():
            continue
        base = lookup[hosts[0][0]].level
        try:
            outline = outlines._new_outline(hosts, WORLD, base)
        except ValueError:
            continue  # Open chains or partial floor spans don't define envelopes.
        seen.add(key)
        candidates.append((abs(regions.area_at_origin(outline)), hosts, outline, base))
    candidates.sort(key=lambda row: (-row[0], tuple(sorted(w.name for w, _ in row[1]))))
    accepted = []
    for size, hosts, outline, base in candidates:
        # Nested loops are handled by the same plan that partitions floors.
        # A smaller bounded face found by the chain search is likewise
        # subordinate to the full envelope, not a second independent layout.
        subordinate = False
        for _, _, other, level in accepted:
            if abs(level - base) > outlines.LEVEL_EPS:
                continue
            overlap = regions._overlap_area([outline], [other])
            if overlap >= size - max(EPS, size * 1e-5):
                subordinate = True
                break
            if overlap > EPS:
                raise ValueError('Closed wall perimeters overlap ambiguously. No ceilings were changed.')
        if not subordinate:
            accepted.append((size, hosts, outline, base))
    return accepted


def _physical(context, node, base, *, interior):
    spans = node.spans or [(wall, reverse, a, b)
                          for (wall, reverse), (a, b) in zip(node.hosts, regions.edges(node.ring))]
    outer = physical_floor_ring(
        [(wall, a, b) for wall, _, a, b in spans], WORLD, base, context.scene,
        interior=interior, partial=bool(node.spans), include_thresholds=False,
    )
    outlines._validate_ring(outer)
    return outer


def ceiling_plan(context):
    """Find bounded room footprints and default elevations without making objects."""
    context.view_layer.update()
    walls = [edge for obj in context.view_layer.objects if (edge := outlines.wall_edge(obj))
             and _wall_height(obj) is not None]
    candidates = _envelopes(context, walls)
    if not candidates:
        raise ValueError('No closed physical wall loops were found. Close the room walls first.')

    default = context.scene.home_builder.ceiling_height
    result = []
    for _, hosts, outline, base in candidates:
        root, _, peers = regions.plan_regions(hosts, outline, WORLD, WORLD, base, walls)
        key = frozenset(wall for wall, _ in hosts)
        family = []
        def room(node):
            outer = _physical(context, node, base, interior=True)
            holes = [_physical(context, child, base, interior=False) for child in node.children]
            if any(regions.crosses(outer, hole) or not all(inside(outer, p) for p in hole) for hole in holes):
                raise ValueError('An interior wall loop leaves its surrounding ceiling.')
            shape = [outer, *holes]
            if any(regions._positive_overlap(plan.rings, shape) for plan in family):
                raise ValueError('The proposed room ceilings overlap. No ceilings were changed.')
            plan = Plan(key, node.key, base, shape, [node.ring, *node.holes],
                        _heights(node.hosts, base, default))
            family.append(plan)
            for child in node.children:
                room(child)
        for node in (root, *peers):
            room(node)
        result.extend(family)
    return result


def _area(rings):
    return abs(regions.area_at_origin(rings[0])) - sum(abs(regions.area_at_origin(hole)) for hole in rings[1:])


def _source_groups(plans):
    result = defaultdict(list)
    for plan in plans:
        result[plan.envelope].append(plan)
    return result


def _assign(context, plans, selected):
    """Reuse old room objects before assigning split-off faces to their source."""
    by_family = _source_groups(plans)
    sources = []
    for obj in sorted(context.view_layer.objects, key=lambda value: value.name):
        if not obj.get(CEILING) or obj.type != 'MESH':
            continue
        try:
            rings, z = ceiling_footprint(obj)
        except ValueError:
            if obj == selected:
                raise
            continue
        saved_envelope = frozenset(w for w, _ in _records(obj, ENVELOPE))
        saved_walls = frozenset(w for w, _ in _records(obj, HOSTS))
        floor_z = obj.get(BASE_LEVEL)
        if floor_z is None:
            # Explicit linked objects know their level; legacy surfaces are
            # associated by overlap and nearest expected room elevation.
            supported = [group for group in by_family.values() if z > group[0].base + EPS]
        else:
            supported = [group for group in by_family.values()
                         if abs(group[0].base - floor_z) <= outlines.LEVEL_EPS]
        area = _area(rings)
        if area <= EPS:
            continue
        family = by_family.get(saved_envelope)
        if family is None:
            matches = []
            for group in supported:
                coverage = sum(regions._overlap_area(rings, plan.datum) for plan in group)
                if coverage > EPS:
                    matches.append((abs(z - group[0].height), -coverage, group))
            if not matches:
                continue
            matches.sort(key=lambda row: row[:2])
            if (len(matches) > 1 and abs(matches[0][0]-matches[1][0]) <= outlines.LEVEL_EPS
                    and abs(matches[0][1]-matches[1][1]) <= EPS):
                raise ValueError(f'{obj.name}: more than one matching wall loop. No ceilings were changed.')
            family = matches[0][2]
        exact = [p for p in family if saved_walls and p.hosts == saved_walls]
        if not exact:
            exact = [p for p in family if outlines._same_ring(rings[0], p.rings[0], outlines.CLOSE)
                     or outlines._same_ring(rings[0], p.datum[0], outlines.CLOSE)]
        sources.append((obj, family, rings, exact))

    if selected is not None:
        row = next((row for row in sources if row[0] == selected), None)
        if row is None:
            raise ValueError('This ceiling could not be associated with a closed wall loop.')
        plans = row[1]
        sources = [item for item in sources if item[1] is plans]

    def bind(plan, source):
        if plan.obj is not None and plan.obj != source:
            raise ValueError('Existing ceilings overlap the same room. Resolve those objects before updating.')
        plan.obj = source
        plan.inherit = source

    for obj, family, rings, exact in sources:
        if len(exact) == 1:
            bind(exact[0], obj)
    for obj, family, rings, exact in sources:
        if len(exact) == 1:
            continue
        overlaps = [(regions._overlap_area(rings, plan.datum), i, plan) for i, plan in enumerate(family)]
        overlaps = [(size, i, plan) for size, i, plan in overlaps if size > EPS]
        if not overlaps:
            raise ValueError(f'{obj.name}: its room no longer has a unique closed wall loop.')
        open_rooms = [row for row in overlaps if row[2].obj is None]
        if not open_rooms:
            raise ValueError('Existing ceilings overlap the same room. No ceilings were changed.')
        _, _, primary = max(open_rooms, key=lambda row: (row[0], -row[1]))
        bind(primary, obj)
    for obj, family, rings, _ in sources:
        for plan in family:
            if plan.obj is not None:
                continue
            # An original ceiling supplies a new region only when it used
            # to cover that entire region, not a nearby unrelated room.
            expected = _area(plan.rings)
            cover = regions._overlap_area(rings, plan.rings)
            if expected - cover <= max(EPS, expected * 1e-5):
                if plan.inherit is not None and plan.inherit != obj:
                    raise ValueError('A new room has more than one possible source ceiling.')
                plan.inherit = obj
    return plans


def _new_mesh(plan, source):
    coords, faces, _ = regions.triangulate_region(plan.rings[0], plan.rings[1:])
    z = plan.height
    inverse = WORLD
    if source is not None:
        _, z = ceiling_footprint(source)
        inverse = source.matrix_world.inverted()
    verts = [inverse @ Vector((*point, z)) for point in coords]

    # Reject bespoke mesh editing instead of destroying it during a wall update.
    if source is not None:
        old = source.data
        index = {p.material_index for p in old.polygons}
        smooth = {p.use_smooth for p in old.polygons}
        attrs = {attribute.name for attribute in old.attributes if not attribute.is_internal}
        if (len(index) != 1 or len(smooth) != 1 or old.has_custom_normals
                or attrs - {layer.name for layer in old.uv_layers} - outlines.INTERNAL_ATTRS
                or old.shape_keys or source.vertex_groups
                or any(c.parent_type in {'VERTEX', 'VERTEX_3'} for c in source.children)):
            raise ValueError(f'{source.name} has custom ceiling geometry or face finishes; it was not overwritten.')
        layers, active = outlines._uv_layers(old)
        index = next(iter(index))
        smooth = next(iter(smooth))
    else:
        layers = [('UVMap', True, False, Vector((1., 0.)), Vector((0., 1.)), Vector((0., 0.)))]
        active, index, smooth = 'UVMap', 0, False
    mesh = bpy.data.meshes.new('Ceiling Room Surface')
    try:
        # Reverse in world space, which also works for mirrored object transforms.
        mesh.from_pydata(verts, [], [tuple(reversed(face)) for face in faces])
        if mesh.validate():
            raise ValueError('The generated ceiling mesh needed repairs.')
        if source is not None:
            for material in source.data.materials:
                mesh.materials.append(material)
            for key, value in source.data.items():
                mesh[key] = value
        for name, render, clone, u, v, origin in layers:
            layer = mesh.uv_layers.new(name=name, do_init=False)
            layer.active_render = render
            layer.active_clone = clone
            for loop in mesh.loops:
                point = mesh.vertices[loop.vertex_index].co
                layer.uv[loop.index].vector = u * point.x + v * point.y + origin
        if active:
            mesh.uv_layers.active = mesh.uv_layers[active]
        for face in mesh.polygons:
            face.material_index = index
            face.use_smooth = smooth
        mesh.update()
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise


def _same_shape(have, want):
    return (outlines._same_ring(have[0], want[0])
            and regions._match_holes(have[1:], want[1:]))


def _bind(obj, plan):
    obj[CEILING] = True
    obj[BASE_LEVEL] = plan.base
    for key, walls in ((ENVELOPE, plan.envelope), (HOSTS, plan.hosts)):
        obj[key] = {f'{i:04d}': {'wall': wall}
                    for i, wall in enumerate(sorted(walls, key=lambda w: w.name))}


def execute_ceilings(operator, context, selected=None):
    if context.mode != 'OBJECT':
        operator.report({'WARNING'}, 'Switch to Object Mode first.')
        return {'CANCELLED'}
    meshes, created, applied = [], [], []
    try:
        plans = _assign(context, ceiling_plan(context), selected)
        staged = []
        for plan in plans:
            if plan.obj is not None:
                if not editable_ceiling(plan.obj):
                    raise ValueError(f'{plan.obj.name} is read-only. No ceilings were changed.')
                if _same_shape(ceiling_footprint(plan.obj)[0], plan.rings):
                    continue
            source = plan.inherit
            mesh = _new_mesh(plan, source)
            meshes.append(mesh)
            staged.append((plan, source, mesh))
        for plan, source, mesh in staged:
            if plan.obj is None:
                obj = source.copy() if source is not None else bpy.data.objects.new('Ceiling', mesh)
                created.append(obj)
                obj.name = 'Ceiling – Room'
                if source is not None:
                    outlines._set_mesh(obj, mesh, outlines._slots(source))
                for collection in (source.users_collection if source is not None else [context.collection]):
                    collection.objects.link(obj)
                plan.obj = obj
            else:
                obj = plan.obj
                applied.append((obj, obj.data, outlines._slots(obj)))
                outlines._set_mesh(obj, mesh, applied[-1][2])
        for plan in plans:
            _bind(plan.obj, plan)
    except (ValueError, RuntimeError, KeyError, TypeError, AttributeError) as error:
        for obj, old, slots in reversed(applied):
            outlines._set_mesh(obj, old, slots)
        for obj in reversed(created):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        operator.report({'WARNING'}, str(error))
        return {'CANCELLED'}
    for _, old, _ in applied:
        if old.users == 0:
            bpy.data.meshes.remove(old)
    operator.report({'INFO'}, f'Room ceilings: {len(created)} added, {len(applied)} updated.')
    return {'FINISHED'}
