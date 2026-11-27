"""Non-destructive paint on generated door leaves, without tinting hardware or glazing."""
import bpy


KEY = 'fzm_door_paint'
MODIFIER_KEY = 'fzm_door_paint_source'
PAINT_INPUT = 'Paint Material'
COATS = {'white', 'inset'}


def editable(obj):
    return obj and not (obj.library or obj.override_library)


def _base_modifier(visual):
    return visual.modifiers.get(visual.home_builder.mod_name)


def _paint_sources(group):
    # These builder graphs store original leaf coatings on unlinked inputs;
    # frosted glass, mirror, tracks, and handles are separately marked.
    return sorted({
        socket.default_value
        for node in group.nodes for socket in node.inputs
        if socket.type == 'MATERIAL' and not socket.is_linked and socket.default_value
        and socket.default_value.get('fzm_native_door_material') in COATS
    }, key=lambda mat: mat.name)


def can_paint(visual):
    base = _base_modifier(visual)
    return bool(editable(visual) and base and base.type == 'NODES' and base.node_group
                and _paint_sources(base.node_group))


def _group(source):
    name = f'FZM Door Paint | {source.name}'
    existing = bpy.data.node_groups.get(name)
    if existing and existing.get(MODIFIER_KEY) == source:
        return existing
    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group[MODIFIER_KEY] = source
    group.is_modifier = True
    for direction in ('INPUT', 'OUTPUT'):
        group.interface.new_socket(name='Geometry', in_out=direction, socket_type='NodeSocketGeometry')
    group.interface.new_socket(name=PAINT_INPUT, in_out='INPUT', socket_type='NodeSocketMaterial')
    inputs = group.nodes.new('NodeGroupInput')
    output = group.nodes.new('NodeGroupOutput')
    geometry = inputs.outputs['Geometry']
    node = group.nodes.new("GeometryNodeRealizeInstances")
    group.links.new(geometry, node.inputs["Geometry"])
    geometry = node.outputs["Geometry"]
    for original in _paint_sources(source):
        # Some legacy leaf parts are instances; the base assembly uses material
        # assignments before instancing, so realize before the replacements.
        replace = group.nodes.new('GeometryNodeReplaceMaterial')
        replace.inputs['Old'].default_value = original
        group.links.new(geometry, replace.inputs['Geometry'])
        group.links.new(inputs.outputs[PAINT_INPUT], replace.inputs['New'])
        geometry = replace.outputs['Geometry']
    group.links.new(geometry, output.inputs['Geometry'])
    return group


def sync(visual):
    """Keep paint when the underlying leaf is edited or recreated."""
    base = _base_modifier(visual)
    material = visual.parent.get(KEY) if visual.parent else None
    modifier = next((m for m in visual.modifiers if m.type == 'NODES' and m.node_group
                     and m.node_group.get(MODIFIER_KEY)), None)
    if not material or not base or not base.node_group:
        if modifier:
            visual.modifiers.remove(modifier)
        return
    if not modifier:
        modifier = visual.modifiers.new('FZM Door Paint', 'NODES')
    if not modifier.node_group or modifier.node_group.get(MODIFIER_KEY) != base.node_group:
        modifier.node_group = _group(base.node_group)
    identifier = modifier.node_group.interface.items_tree[PAINT_INPUT].identifier
    modifier[identifier] = material
    visual.update_tag()
