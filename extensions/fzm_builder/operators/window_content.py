"""Optional lightweight glazing for a parametric window opening.

The existing cage remains the wall cutter and the owner of the dimensions.
Drivers keep one modeled frame and pane in that opening across edits and reloads.
"""
from math import isfinite

import bpy

from .. import hb_types
from .native_doors import Assembly


VISUAL = 'FZM_WINDOW_3D_VISUAL'
OLD_DISPLAY = 'FZM_WINDOW_OLD_DISPLAY'
OLD_IN_FRONT = 'FZM_WINDOW_OLD_IN_FRONT'


def cage_for(obj):
    if obj is not None and obj.get(VISUAL):
        obj = obj.parent
    return obj if obj is not None and obj.get('IS_WINDOW_BP') else None


def visual_for(window):
    return next((child for child in window.children if child.get(VISUAL)), None)


def size_error(width, height, depth):
    if not all(isfinite(n) and n > 0 for n in (width, height, depth)):
        return 'Use positive, finite window opening dimensions and wall depth.'
    return None


def _material(role):
    mat = next((m for m in bpy.data.materials if m.get('fzm_window_3d_material') == role), None)
    if mat is not None:
        return mat
    glass = role == 'glass'
    mat = bpy.data.materials.new('FZM Window | Glass' if glass else 'FZM Window | White Frame')
    mat['fzm_window_3d_material'] = role
    mat.use_nodes = True
    # Thin, lightly tinted presentation glazing; see through it in Eevee
    # without requiring ray-tracing or changing the user's scene settings.
    color = (.63, .84, .90, .24) if glass else (.83, .83, .80, 1.)
    mat.diffuse_color = color
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color[:3], 1.)
    bsdf.inputs['Roughness'].default_value = .10 if glass else .36
    if glass:
        bsdf.inputs['Alpha'].default_value = color[3]
        bsdf.inputs['Transmission Weight'].default_value = .55
        mat.surface_render_method = 'DITHERED'
    return mat


def _group():
    name = 'FZM Window Frame and Glass v1'
    existing = bpy.data.node_groups.get(name)
    if existing is not None and existing.get('fzm_window_3d_group') == 1:
        return existing
    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group['fzm_window_3d_group'] = 1
    group.is_modifier = True
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='INPUT',
                               socket_type='NodeSocketGeometry').hide_in_modifier = True
    for name, default in (('Width', 1.22), ('Height', .91), ('Depth', .14)):
        socket = group.interface.new_socket(name=name, in_out='INPUT', socket_type='NodeSocketFloat')
        socket.default_value = default
        socket.min_value = 0.
        socket.hide_in_modifier = True

    a = Assembly(group)
    a.materials.update({key: _material(key) for key in ('frame', 'glass')})
    w, h, d = (a.inputs.outputs[k] for k in ('Width','Height','Depth'))
    short = a.calc('MINIMUM', w, h)
    inset = a.calc('MINIMUM', .002, a.mul(short, .025))
    rail = a.calc('MINIMUM', .045, a.mul(short, .21))
    inner_margin = a.add(inset, rail)
    outer_w, outer_h = (a.sub(n, a.mul(inset, 2.)) for n in (w, h))
    pane_w, pane_h = (a.sub(n, a.mul(inner_margin, 2.)) for n in (w, h))
    frame_d = a.calc('MINIMUM', .09, a.mul(d, .88))
    pane_d = a.calc('MINIMUM', .006, a.mul(frame_d, .42))
    cx, cy, cz = (a.mul(n, .5) for n in (w, d, h))
    rail_mid = a.add(inset, a.mul(rail, .5))
    side = [
        a.box((rail, frame_d, outer_h), (x, cy, cz), 'frame')
        for x in (rail_mid, a.sub(w, rail_mid))
    ]
    top_bottom = [
        a.box((pane_w, frame_d, rail), (cx, cy, z), 'frame')
        for z in (rail_mid, a.sub(h, rail_mid))
    ]
    pane = a.box((pane_w, pane_d, pane_h), (cx, cy, cz), 'glass')
    # Guard direct socket edits too, not just the prompts.
    valid = a.mul(a.mul(a.calc('GREATER_THAN', w, 0.), a.calc('GREATER_THAN', h, 0.)),
                  a.calc('GREATER_THAN', d, 0.))
    safe = group.nodes.new('GeometryNodeSwitch')
    safe.input_type = 'GEOMETRY'
    a.wire(valid, safe.inputs['Switch'])
    a.wire(a.join(*side, *top_bottom, pane), safe.inputs['True'])
    a.wire(safe.outputs[0], a.output.inputs['Geometry'])
    return group


def _remove_visual(obj):
    mesh = obj.data
    for child in list(obj.children):
        pose = child.matrix_world.copy()
        child.parent = None
        child.matrix_world = pose
    bpy.data.objects.remove(obj, do_unlink=True)
    if not mesh.users:
        bpy.data.meshes.remove(mesh)


def set_visual(window, enabled):
    obj = visual_for(window)
    if not enabled:
        if obj is not None:
            _remove_visual(obj)
            window.display_type = window.get(OLD_DISPLAY, 'WIRE')
            window.show_in_front = bool(window.get(OLD_IN_FRONT, False))
            for key in (OLD_DISPLAY, OLD_IN_FRONT):
                if key in window:
                    del window[key]
        return None

    if obj is None:
        cage = hb_types.GeoNodeCage(window)
        collection = next(iter(window.users_collection), bpy.context.collection)
        group = _group()
        obj = bpy.data.objects.new('Window | Frame and Glass', bpy.data.meshes.new('FZM Window Input'))
        try:
            collection.objects.link(obj)
            obj.parent = window
            obj[VISUAL] = True
            obj['MENU_ID'] = 'HOME_BUILDER_MT_window_commands'
            obj.lock_location = obj.lock_rotation = obj.lock_scale = (True, True, True)
            mod = obj.modifiers.new('FZM Window Frame and Glass', 'NODES')
            mod.node_group = group
            obj.home_builder.mod_name = mod.name
            model = hb_types.GeoNodeObject(obj)
            for key, cage_key in (('Width','Dim X'), ('Height','Dim Z'), ('Depth','Dim Y')):
                model.driver_input(key, 'size', [cage.var_input(cage_key, 'size')])
        except Exception:
            _remove_visual(obj)
            raise
        window[OLD_DISPLAY] = window.display_type
        window[OLD_IN_FRONT] = window.show_in_front
    # The cutter remains a usable Boolean target and cannot cover the glazing.
    window.display_type = 'WIRE'
    window.show_in_front = False
    return obj
