"""Optional visual leaf on legacy hinged cages; no replacement of the opening."""
from math import isfinite, pi

import bpy

from .. import hb_types
from . import native_doors as nd

ENABLED = 'FZM_HINGED_3D_ENABLED'
VISUAL = 'FZM_HINGED_3D_VISUAL'
STYLE = 'FZM_HINGED_3D_STYLE'
POSE = 'FZM_HINGED_3D_OPEN'
DISPLAY = 'FZM_HINGED_OLD_DISPLAY'
IN_FRONT = 'FZM_HINGED_OLD_IN_FRONT'


def cage_for(obj):
    if obj and obj.get(VISUAL):
        obj = obj.parent
    return obj if obj and obj.get('IS_ENTRY_DOOR_BP') and not obj.get(nd.TYPE_KEY) else None


def swing_for(door):
    if not door:
        return None
    for child in door.children:
        if not (child.get('FZM_DOOR_SWING') or child.get('IS_2D_ANNOTATION')):
            continue
        swing = hb_types.GeoNodeObject(child)
        if swing.has_modifier() and all(swing.has_input(k) for k in ('Swing Inside','Is Left','Is Double')):
            return swing
    return None


def visual_for(door):
    return next((o for o in door.children if o.get(VISUAL)), None)


def options(door):
    return (bool(visual_for(door)), door.get(STYLE, nd.STYLE_FLAT), float(door.get(POSE, 0.)))


def size_error(width, height, double):
    if not isfinite(width) or not isfinite(height):
        return 'Door dimensions must be finite.'
    if width < (.52 if double else .30) or height < .68:
        return 'This opening is too small for a 3D hinged leaf. Keep the leaf off or enlarge the opening.'
    return None


def _scalar_select(a, condition, no, yes):
    switch = a.nodes.new('GeometryNodeSwitch')
    switch.input_type = 'FLOAT'
    for value, name in ((condition,'Switch'), (no,'False'), (yes,'True')):
        a.wire(value,switch.inputs[name])
    return switch.outputs[0]


def build_group():
    name = 'FZM Hinged Door Leaf v1'
    previous = bpy.data.node_groups.get(name)
    if previous is not None and previous.get('fzm_hinged_door_group') == 1:
        return previous
    group = bpy.data.node_groups.new(name,'GeometryNodeTree')
    group['fzm_hinged_door_group'] = 1
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry').hide_in_modifier = True
    for key, default, maximum in (('Width',.81,10.),('Height',2.03,8.),('Depth',.15,2.),
                                  (nd.STYLE,0.,5.),(nd.OPEN,0.,1.),('Inside',1.,1.),
                                  ('Left',1.,1.),('Double',0.,1.)):
        socket = group.interface.new_socket(name=key,in_out='INPUT',socket_type='NodeSocketFloat')
        socket.default_value, socket.min_value, socket.max_value = default,0.,maximum
        socket.hide_in_modifier=True
    a=nd.Assembly(group)
    w,h,d=(a.inputs.outputs[k] for k in ('Width','Height','Depth'))
    inside,left,double=(a.calc('GREATER_THAN',a.inputs.outputs[k],.5) for k in ('Inside','Left','Double'))
    room_sign=_scalar_select(a,inside,1.,-1.)
    gap = .004
    thickness = .034925
    leaf_w = _scalar_select(a,double,a.sub(w,2*gap),a.mul(a.sub(w,2*gap+.005),.5))
    leaf_h = a.sub(h,.016)
    center_z = a.add(.011,a.mul(leaf_h,.5))
    leaf = a.leaf(leaf_w,leaf_h,thickness=thickness)
    # Pivot around the room-side corner so the panel clears the jamb.
    # Existing annotation conventions:
    # Inside is -Y, and Is Left puts the pivot at maximum X.
    pivot_y = _scalar_select(a,inside,d,0.)
    local_y = a.mul(room_sign,-thickness/2)
    theta = a.mul(a.mul(a.inputs.outputs[nd.OPEN],pi/2),room_sign)

    def at_jamb(sign):
        x0 = a.mul(leaf_w,sign*.5)
        angle = a.mul(theta,sign)
        c,s = a.calc('COSINE',angle),a.calc('SINE',angle)
        pivot_x = gap if sign > 0 else a.sub(w,gap)
        x = a.add(pivot_x,a.sub(a.mul(x0,c),a.mul(local_y,s)))
        y = a.add(pivot_y,a.add(a.mul(x0,s),a.mul(local_y,c)))
        return a.transform(leaf,(x,y,center_z),angle)

    low,high=at_jamb(1),at_jamb(-1)
    output=a.select(double,a.select(left,low,high),a.join(low,high))
    min_width=_scalar_select(a,double,.52,.30)
    too_small=a.add(a.calc('LESS_THAN',w,min_width),a.calc('LESS_THAN',h,.68))
    mask=a.nodes.new('GeometryNodeSwitch')
    mask.input_type='GEOMETRY'
    a.wire(too_small,mask.inputs['Switch'])
    a.wire(output,mask.inputs['False'])
    a.wire(mask.outputs[0],a.output.inputs['Geometry'])
    group.is_modifier=True
    return group


def _remove_visual(obj):
    mesh=obj.data
    for child in list(obj.children):
        pose=child.matrix_world.copy()
        child.parent=None
        child.matrix_world=pose
    bpy.data.objects.remove(obj,do_unlink=True)
    if not mesh.users:
        bpy.data.meshes.remove(mesh)


def set_visual(door, enabled, style, pose):
    swing=swing_for(door)
    if not swing:
        if enabled:
            raise ValueError('Only Single and Double hinged doors can have a 3D leaf.')
        return None
    if style not in {item[0] for item in nd.STYLES} or not isfinite(pose):
        raise ValueError('Choose a supported door style and pose.')
    obj=visual_for(door)
    pose=max(0.,min(1.,pose))
    if enabled:
        if obj is None:
            cage = hb_types.GeoNodeCage(door)
            collection = door.users_collection[0] if door.users_collection else bpy.context.collection
            group=build_group()
            obj=bpy.data.objects.new('Hinged Door | 3D Leaf',bpy.data.meshes.new('FZM Hinged Door Input'))
            try:
                collection.objects.link(obj)
                obj.parent=door
                obj[VISUAL]=True
                obj['MENU_ID']='HOME_BUILDER_MT_door_commands'
                obj.lock_location=obj.lock_rotation=obj.lock_scale=(True,True,True)
                mod=obj.modifiers.new('FZM Hinged Door Leaf','NODES')
                mod.node_group=group
                obj.home_builder.mod_name=mod.name
                visual=hb_types.GeoNodeObject(obj)
                for key,cage_key in (('Width','Dim X'),('Height','Dim Z'),('Depth','Dim Y')):
                    visual.driver_input(key,'size',[cage.var_input(cage_key,'size')])
                for key,swing_key in (('Inside','Swing Inside'),('Left','Is Left'),('Double','Is Double')):
                    visual.driver_input(key,'state',[swing.var_input(swing_key,'state')])
            except Exception:
                _remove_visual(obj)
                raise
            door[DISPLAY]=door.display_type
            door[IN_FRONT]=door.show_in_front
        visual=hb_types.GeoNodeObject(obj)
        visual.set_input(nd.STYLE,float(nd.STYLE_VALUES[style]))
        visual.set_input(nd.OPEN,pose)
        obj.update_tag()
        door[ENABLED]=True
        # Keep the cutter usable for the wall but prevent a solid cage covering
        # the new closed leaf in Solid viewport mode.
        door.display_type='WIRE'
        door.show_in_front=False
    elif obj:
        _remove_visual(obj)
        door.display_type=door.get(DISPLAY,'WIRE')
        door.show_in_front=bool(door.get(IN_FRONT,False))
        for key in (ENABLED,DISPLAY,IN_FRONT):
            if key in door:
                del door[key]
    door[STYLE],door[POSE]=style,pose
    return obj
