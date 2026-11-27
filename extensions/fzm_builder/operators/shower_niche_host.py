"""Opt-in live Boolean from a Shower Area to selected Builder walls."""
import bpy

SCHEMA = 'fzm_shower_host_cut_schema'
OUTPUT = 'FZM Host Cutters'
OWNER = 'fzm_shower_cutter_source'
MANAGED = 'fzm_shower_cutter_helper'
SCALARS = {'NodeSocketBool', 'NodeSocketFloat', 'NodeSocketInt', 'NodeSocketMenu'}


def area_modifier(obj):
    if not obj or obj.type != 'MESH':
        return None
    for m in obj.modifiers:
        if m.type == 'NODES' and m.node_group and m.node_group.get(SCHEMA) == 1:
            return m
    return None


def _selected(context):
    return context.selected_objects if context.mode == 'OBJECT' else ()


def _walls(objects):
    return [obj for obj in objects if obj.get('IS_WALL_BP')
            and not obj.get('IS_FAKE_WALL') and obj.get('WALL_TYPE') != 'Fake'
            and obj.type == 'MESH' and obj.is_editable and not obj.override_library]


def _is_cut(mod):
    return mod.type == 'BOOLEAN' and mod.object and mod.object.get(MANAGED)


def _inputs_for_cutter(source):
    # The asset exposes one extra, invisible Geometry Nodes output. Follow
    # only that part of the graph to identify the numeric controls to drive.
    node = next((n for n in source.nodes if n.type == 'GROUP_OUTPUT' and n.is_active_output), None)
    socket = node.inputs.get(OUTPUT) if node else None
    if not socket or not socket.is_linked:
        raise ValueError('This Shower Area does not expose its niche cut shapes. Append the new asset.')
    stack = [link.from_socket for link in socket.links]
    visited, ids = set(), set()
    while stack:
        out = stack.pop()
        if out in visited:
            continue
        visited.add(out)
        if out.node.type == 'GROUP_INPUT':
            ids.add(out.identifier)
        else:
            stack.extend(link.from_socket for inp in out.node.inputs if inp.enabled
                         for link in inp.links)
    inputs = [s for s in source.interface.items_tree
              if s.item_type == 'SOCKET' and s.in_out == 'INPUT' and s.identifier in ids]
    if not inputs or any(s.socket_type not in SCALARS for s in inputs):
        raise ValueError('Unsupported Shower Area cutter inputs. Append the current asset.')
    return inputs


def _delete_helper(obj):
    mesh = obj.data
    group = obj.modifiers[0].node_group if obj.modifiers and obj.modifiers[0].type == 'NODES' else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh and not mesh.users:
        bpy.data.meshes.remove(mesh)
    if group and not group.users:
        bpy.data.node_groups.remove(group)


def _make_helper(context, area, source):
    inputs = _inputs_for_cutter(source.node_group)
    group = bpy.data.node_groups.new('FZM | Live Shower Niche Cutter', 'GeometryNodeTree')
    group.is_modifier = True
    mesh = bpy.data.meshes.new('FZM | Shower Niche Cutter')
    helper = bpy.data.objects.new('FZM | Shower Niche Cutter', mesh)
    try:
        context.scene.collection.objects.link(helper)
        helper.parent = area
        helper[MANAGED] = True
        helper["IS_CUTTING_OBJ"] = True
        helper[OWNER] = area
        helper.display_type = 'WIRE'
        helper.hide_render = True
        helper.hide_select = True
        for layer in context.scene.view_layers:
            helper.hide_set(True, view_layer=layer)
        if hasattr(helper, 'visible_camera'):
            helper.visible_camera = False
        group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
        group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        inner = group.nodes.new('GeometryNodeGroup')
        inner.node_tree = source.node_group
        inp = group.nodes.new('NodeGroupInput')
        inp.location.x = -350
        out = group.nodes.new('NodeGroupOutput')
        out.location.x = 330
        group.links.new(inner.outputs[OUTPUT], out.inputs['Geometry'])
        wrapper_inputs = []
        for s in inputs:
            socket = group.interface.new_socket(name=s.name, in_out='INPUT', socket_type=s.socket_type)
            group.links.new(inp.outputs[socket.name], inner.inputs[s.name])
            if hasattr(socket, 'force_non_field'):
                socket.force_non_field = True
            wrapper_inputs.append((s, socket))
        mod = helper.modifiers.new('Shower Niche Cut Volume', 'NODES')
        mod.node_group = group
        for s, dest in wrapper_inputs:
            if s.identifier not in source:
                raise ValueError('Shower Area modifier input is missing. Append the current asset.')
            mod[dest.identifier] = source[s.identifier]
            source_path = source.path_from_id() + f'["{s.identifier}"]'
            dest_path = mod.path_from_id() + f'["{dest.identifier}"]'
            fcurve = helper.driver_add(dest_path)
            driver = fcurve.driver
            driver.type = 'AVERAGE'  # Native scoped property driver, no script.
            var = driver.variables.new()
            var.type = 'SINGLE_PROP'
            var.targets[0].id = area
            var.targets[0].data_path = source_path
        helper.update_tag()
        return helper
    except Exception:
        has_group = any(m.type == 'NODES' and m.node_group == group for m in helper.modifiers)
        _delete_helper(helper)
        if not has_group and not group.users:
            bpy.data.node_groups.remove(group)
        raise


def _helper(context, area):
    return next((child for child in area.children
                 if child.name in context.scene.objects and child.get(MANAGED)
                 and child.get(OWNER) == area), None)


class FZM_OT_cut_shower_niche_host(bpy.types.Operator):
    bl_idname = 'fzm_builder.cut_shower_niche_host'
    bl_label = 'Cut Wall for Shower Niches'
    bl_description = ('Select a current Shower Area and the Builder walls behind it. '
                      'Cut only those walls; openings follow the niche positions and sizes')
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(_walls(_selected(context)))

    def execute(self, context):
        selected = _selected(context)
        areas = [(o, m) for o in selected if (m := area_modifier(o))]
        if len(areas) != 1:
            self.report({'WARNING'}, 'Select one current Shower Area and the Builder wall(s) behind it.')
            return {'CANCELLED'}
        area, source = areas[0]
        helper = _helper(context, area)
        created = helper is None
        added = []
        try:
            if helper is None:
                helper = _make_helper(context, area, source)
            for wall in _walls(selected):
                if any(_is_cut(mod) and mod.object == helper for mod in wall.modifiers):
                    continue
                mod = wall.modifiers.new('FZM Shower Niche Cut', 'BOOLEAN')
                added.append((wall, mod))
                mod.operation = 'DIFFERENCE'
                mod.solver = 'EXACT'
                mod.object = helper
        except (KeyError, ValueError, TypeError, RuntimeError) as exc:
            for wall, mod in reversed(added):
                wall.modifiers.remove(mod)
            if helper and created:
                _delete_helper(helper)
            self.report({'WARNING'}, f'Could not link the niche cut: {exc}')
            return {'CANCELLED'}
        if not added:
            self.report({'INFO'}, 'These walls already follow the Shower Area.')
        else:
            self.report({'INFO'}, f'Linked live shower niche cuts to {len(added)} wall(s).')
        return {'FINISHED'}


class FZM_OT_remove_shower_niche_host(bpy.types.Operator):
    bl_idname = 'fzm_builder.remove_shower_niche_host'
    bl_label = 'Remove Shower Niche Cut'
    bl_description = 'Remove this non-destructive cut from selected Builder walls'
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(_is_cut(m) for w in _walls(_selected(context)) for m in w.modifiers)

    def execute(self, context):
        selected = _selected(context)
        areas = {o for o in selected if area_modifier(o)}
        helpers = set()
        count = 0
        for wall in _walls(selected):
            for mod in list(wall.modifiers):
                if _is_cut(mod) and (not areas or mod.object.get(OWNER) in areas):
                    helpers.add(mod.object)
                    wall.modifiers.remove(mod)
                    count += 1
        for obj in helpers:
            if not any(m.type == 'BOOLEAN' and m.object == obj
                       for user in bpy.data.objects if user.type == 'MESH' for m in user.modifiers):
                _delete_helper(obj)
        self.report({'INFO'}, f'Removed {count} managed niche cut(s).')
        return {'FINISHED'}


register, unregister = bpy.utils.register_classes_factory((
    FZM_OT_cut_shower_niche_host, FZM_OT_remove_shower_niche_host,
))
