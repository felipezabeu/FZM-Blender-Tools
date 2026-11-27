"""Optional visual leaf on legacy hinged cages; no replacement of the opening."""
from math import isfinite, pi

import bpy

from .. import hb_types
from . import berkway_doors, door_panel_fill, native_doors as nd
from . import hinged_kinematics as kin
from .hinged_kinematics import LEAF_THICKNESS, select_scalar as _scalar_select

ENABLED = 'FZM_HINGED_3D_ENABLED'
VISUAL = 'FZM_HINGED_3D_VISUAL'
STYLE = 'FZM_HINGED_3D_STYLE'
POSE = 'FZM_HINGED_3D_OPEN'
DISPLAY = 'FZM_HINGED_OLD_DISPLAY'
IN_FRONT = 'FZM_HINGED_OLD_IN_FRONT'
HARDWARE = 'FZM_HINGED_3D_HARDWARE'
HARDWARE_SOCKET = 'Hardware Style'
HARDWARE_FINISH = 'FZM_HINGED_3D_HARDWARE_FINISH'
FINISH_SOCKET = 'Hardware Finish'
FINISH_ITEMS = (
    ('BLACK','Matte Black','Dark matte finish'),
    ('BRUSHED_NICKEL','Brushed Nickel','Neutral brushed nickel finish'),
    ('BRUSHED_GOLD','Brushed Gold','Warm brushed gold finish'),
)
FINISH_VALUES = {'BLACK': 0., 'BRUSHED_NICKEL': 1., 'BRUSHED_GOLD': 2.}
DEFAULT_FINISH = 'BRUSHED_NICKEL'
FINISH_MATERIAL = 'fzm_hinged_hardware_finish'
HARDWARE_ITEMS = (
    ('NONE', 'None', 'Keep the hinged leaf without a knob or lever'),
    ('KNOB', 'Knob', 'Round satin-metal knob on both faces of each hinged leaf'),
    ('LEVER', 'Lever', 'Satin-metal lever on both faces, pointing toward the hinge'),
)
HARDWARE_VALUES = {'NONE': 0., 'KNOB': 1., 'LEVER': 2.}
HINGED_INPUTS = ('Width', 'Height', 'Depth', nd.STYLE, nd.OPEN, 'Inside', 'Left', 'Double')

STYLE_BERKWAY = 'BERKWAY'
STYLES = (*nd.STYLES, (STYLE_BERKWAY,'Berkway','White flush slab with fine routed grooves',6))
STYLE_VALUES = {**nd.STYLE_VALUES,STYLE_BERKWAY:6.}
HARDWARE_VERSIONS = {2,4,6,7}
SUPPORTED_VERSIONS = {1,2,3,4,5,6,7}
PHOTO_SHAKER_STYLES = {nd.STYLE_SHAKER, nd.STYLE_SHAKER_2, nd.STYLE_SHAKER_5}


def cage_for(obj):
    obj = nd.cage_for(obj)
    return obj if obj and not obj.get(nd.TYPE_KEY) else None


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


def hardware_for(door):
    """Older meshes and missing custom properties mean no hardware."""
    value = door.get(HARDWARE, 'NONE')
    return value if isinstance(value,str) and value in HARDWARE_VALUES else 'NONE'


def finish_for(door):
    value = door.get(HARDWARE_FINISH, DEFAULT_FINISH)
    return value if isinstance(value,str) and value in FINISH_VALUES else DEFAULT_FINISH


def _finish_material(key):
    label=next(name for code,name,_ in FINISH_ITEMS if code==key)
    name=f'FZM Hinged Hardware | {label}'
    material=bpy.data.materials.get(name)
    if material and material.get(FINISH_MATERIAL)==key:
        return material
    rgb, metallic, roughness, anisotropy = {
        'BLACK': ((.019,.021,.026),.34,.59,0.),
        'BRUSHED_NICKEL': ((.48,.49,.50),.87,.30,.20),
        'BRUSHED_GOLD': ((.68,.44,.18),.84,.33,.23),
    }[key]
    material=bpy.data.materials.new(name)
    material[FINISH_MATERIAL]=key
    material.diffuse_color=(*rgb,1.)
    material.metallic=metallic
    material.roughness=roughness
    material.use_nodes=True
    shader=next(node for node in material.node_tree.nodes if node.type=='BSDF_PRINCIPLED')
    shader.inputs['Base Color'].default_value=(*rgb,1.)
    shader.inputs['Metallic'].default_value=metallic
    shader.inputs['Roughness'].default_value=roughness
    shader.inputs['Anisotropic'].default_value=anisotropy
    return material


def size_error(width, height, double):
    if not isfinite(width) or not isfinite(height):
        return 'Door dimensions must be finite.'
    if width < (.52 if double else .30) or height < .68:
        return 'This opening is too small for a 3D hinged leaf. Keep the leaf off or enlarge the opening.'
    return None


def _hardware(a, leaf_w, height, center_z, thickness, latch_sign):
    """Generate real paired hardware meshes in the leaf's own local frame."""
    def shape(kind, radius, center, *, depth=None, scale=(1.,1.,1.)):
        is_cylinder = kind == 'GeometryNodeMeshCylinder'
        node = a.nodes.new(kind)
        node.inputs['Radius'].default_value = radius
        if is_cylinder:
            node.inputs['Vertices'].default_value = 24
            node.inputs['Depth'].default_value = depth
        else:
            node.inputs['Segments'].default_value = 24
            node.inputs['Rings'].default_value = 12
        move = a.nodes.new('GeometryNodeTransform')
        a.wire(node.outputs['Mesh'],move.inputs['Geometry'])
        a.wire(a.vector(center),move.inputs['Translation'])
        move.inputs['Scale'].default_value = scale
        if is_cylinder:
            move.inputs['Rotation'].default_value = (pi/2,0.,0.)
        return move.outputs['Geometry']

    cylinder,sphere='GeometryNodeMeshCylinder','GeometryNodeMeshUVSphere'
    backset=a.calc('MINIMUM',.060,a.mul(leaf_w,.18))
    latch=a.mul(a.sub(a.mul(leaf_w,.5),backset),latch_sign)
    z=a.sub(a.calc('MINIMUM',.9652,a.mul(height,.56)),center_z)
    half=thickness/2
    base=[]; knob=[]; lever=[]
    for side in (-1,1):
        # Rosettes slightly penetrate the leaf surface so the hardware is
        # attached even at the edge of a recessed panel.
        base.append(shape(cylinder,.025,(latch,side*(half+.001),z),depth=.005))
        base.append(shape(cylinder,.010,(latch,side*(half+.019),z),depth=.037))
        knob.append(shape(sphere,.024,(latch,side*(half+.046),z),scale=(1.,.84,1.)))
        grip=a.add(latch,-latch_sign*.035)
        lever.append(shape(sphere,.012,(grip,side*(half+.038),z),scale=(4.,.85,.90)))
    style=a.inputs.outputs[HARDWARE_SOCKET]
    grip=a.select(a.calc('GREATER_THAN',style,1.5),a.join(*knob),a.join(*lever))
    hardware=a.join(*base,grip)
    def with_material(code):
        node=a.nodes.new('GeometryNodeSetMaterial')
        a.wire(hardware,node.inputs['Geometry'])
        node.inputs['Material'].default_value=_finish_material(code)
        return node.outputs['Geometry']
    finish=a.inputs.outputs[FINISH_SOCKET]
    shaded=a.select(a.calc('GREATER_THAN',finish,.5),with_material('BLACK'),with_material('BRUSHED_NICKEL'))
    shaded=a.select(a.calc('GREATER_THAN',finish,1.5),shaded,with_material('BRUSHED_GOLD'))
    return a.calc('GREATER_THAN',style,.5),shaded


def build_group(version=1):
    name = f'FZM Hinged Door Leaf v{version}'
    previous = bpy.data.node_groups.get(name)
    if previous is not None and previous.get('fzm_hinged_door_group') == version:
        return previous
    group = bpy.data.node_groups.new(name,'GeometryNodeTree')
    group['fzm_hinged_door_group'] = version
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry').hide_in_modifier = True
    inputs=(('Width',.81,10.),('Height',2.03,8.),('Depth',.15,2.),(nd.STYLE,0.,6. if version>=5 else 5.),
            (nd.OPEN,0.,1.),('Inside',1.,1.),('Left',1.,1.),('Double',0.,1.))
    if version in HARDWARE_VERSIONS:
        # Append to keep every v1 FCurve and pose/style socket identifier stable.
        inputs=(*inputs,(HARDWARE_SOCKET,0.,2.),(FINISH_SOCKET,FINISH_VALUES[DEFAULT_FINISH],2.))
    if version >= 7:
        inputs=(*inputs,(door_panel_fill.INPUT,0.,1.))
    for key, default, maximum in inputs:
        socket = group.interface.new_socket(name=key,in_out='INPUT',socket_type='NodeSocketFloat')
        socket.default_value, socket.min_value, socket.max_value = default,0.,maximum
        socket.hide_in_modifier=True
    a=nd.Assembly(group)
    w,h,d=(a.inputs.outputs[k] for k in ('Width','Height','Depth'))
    inside,left,double=(a.calc('GREATER_THAN',a.inputs.outputs[k],.5) for k in ('Inside','Left','Double'))
    pivot_y, room_sign = kin.hinge_y_and_direction(a, d, inside)
    thickness = LEAF_THICKNESS
    leaf_w = kin.leaf_width(a, w, double)
    leaf_h = a.sub(h,.016)
    center_z = a.add(.011,a.mul(leaf_h,.5))
    profile = {}
    if version >= 7:
        glass = a.calc('GREATER_THAN', a.inputs.outputs[door_panel_fill.INPUT], .5)
        material = a.nodes.new('GeometryNodeSwitch')
        material.input_type = 'MATERIAL'
        a.wire(glass,material.inputs['Switch'])
        a.wire(nd.material('inset'),material.inputs['False'])
        a.wire(door_panel_fill.glass_material(),material.inputs['True'])
        insert = _scalar_select(a,glass,thickness-.011,.006)
        profile = dict(shaker_variant='HINGED',shaker_insert_material=material.outputs[0],
                       shaker_insert_thickness=insert)
    leaf = a.leaf(leaf_w,leaf_h,thickness=thickness,six_variant='FULL' if version>=3 else None,**profile)
    if version>=5:
        berkway=berkway_doors.build_leaf(a,leaf_w,leaf_h,thickness)
        leaf=a.select(a.calc('GREATER_THAN',a.inputs.outputs[nd.STYLE],5.5),leaf,berkway)
    # Pivot around the room-side corner so the panel clears the jamb.
    local_y = a.mul(room_sign,-thickness/2)
    theta = a.mul(a.mul(a.inputs.outputs[nd.OPEN],kin.SWING_ANGLE),room_sign)

    def at_jamb(sign):
        x0 = a.mul(leaf_w,sign*.5)
        angle = a.mul(theta,sign)
        c,s = a.calc('COSINE',angle),a.calc('SINE',angle)
        pivot_x = kin.hinge_x(a, w, sign > 0)
        x = a.add(pivot_x,a.sub(a.mul(x0,c),a.mul(local_y,s)))
        y = a.add(pivot_y,a.add(a.mul(x0,s),a.mul(local_y,c)))
        part=leaf
        if version in HARDWARE_VERSIONS:
            enabled,hardware=_hardware(a,leaf_w,h,center_z,thickness,sign)
            part=a.select(enabled,leaf,a.join(leaf,hardware))
        return a.transform(part,(x,y,center_z),angle)

    low,high=at_jamb(1),at_jamb(-1)
    output=a.select(double,a.select(left,low,high),a.join(low,high))
    # Match the accepted Single/Double clamps in the new group: prior
    # shipped graphs had these two switch constants reversed. Never mutate
    # a saved old graph in place.
    min_width=(_scalar_select(a,double,.30,.52) if version>=5 else _scalar_select(a,double,.52,.30))
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


def _upgrade_group(obj, version):
    modifier=obj.modifiers[obj.home_builder.mod_name]
    previous=modifier.node_group
    old_version=previous.get('fzm_hinged_door_group')
    if old_version == version:
        return
    if old_version not in SUPPORTED_VERSIONS:
        raise ValueError("This custom hinged door group cannot be upgraded.")
    new=build_group(version)
    keys=(*HINGED_INPUTS,HARDWARE_SOCKET,FINISH_SOCKET) if old_version in HARDWARE_VERSIONS else HINGED_INPUTS
    for key in keys:
        old_socket=previous.interface.items_tree.get(key)
        new_socket=new.interface.items_tree.get(key)
        if not old_socket or not new_socket or old_socket.identifier != new_socket.identifier:
            raise ValueError("Cannot preserve the inputs of this existing hinged door.")
    modifier.node_group=new


def _desired_version(old, style, hardware, finish):
    if old == 7 or style in PHOTO_SHAKER_STYLES:
        return 7
    with_hardware = old in HARDWARE_VERSIONS or hardware != 'NONE'
    if old in (5,6) or style == STYLE_BERKWAY:
        return 6 if with_hardware else 5
    with_reference = old in (3,4) or style == nd.STYLE_SIX_PANEL or (hardware != 'NONE' and finish == 'BLACK')
    return (4 if with_hardware else 3) if with_reference else (2 if with_hardware else 1)


def set_visual(door, enabled, style, pose, hardware=None, finish=None, fill=None):
    swing=swing_for(door)
    if not swing:
        if enabled:
            raise ValueError('Only Single and Double hinged doors can have a 3D leaf.')
        return None
    if style not in {item[0] for item in STYLES} or not isfinite(pose):
        raise ValueError('Choose a supported door style and pose.')
    hardware=hardware_for(door) if hardware is None else hardware
    if hardware not in HARDWARE_VALUES:
        raise ValueError("Choose None, Knob or Lever.")
    finish=finish_for(door) if finish is None else finish
    if finish not in FINISH_VALUES:
        raise ValueError("Choose Matte Black, Brushed Nickel or Brushed Gold.")
    if fill is None or style != nd.STYLE_SHAKER_5:
        fill=door_panel_fill.panel_fill_for(door)
    if fill not in {'SOLID','FROSTED'}:
        raise ValueError('Choose Solid or Frosted Glass.')
    obj=visual_for(door)
    pose=max(0.,min(1.,pose))
    if enabled:
        if obj is None:
            cage = hb_types.GeoNodeCage(door)
            collection = door.users_collection[0] if door.users_collection else bpy.context.collection
            group=build_group(_desired_version(1,style,hardware,finish))
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
        old_version=obj.modifiers[obj.home_builder.mod_name].node_group.get('fzm_hinged_door_group')
        version=_desired_version(old_version,style,hardware,finish)
        if old_version != version and (style in PHOTO_SHAKER_STYLES or style in (nd.STYLE_SIX_PANEL,STYLE_BERKWAY) or hardware != 'NONE'):
            _upgrade_group(obj,version)
        visual=hb_types.GeoNodeObject(obj)
        if visual.has_input(HARDWARE_SOCKET):
            visual.set_input(HARDWARE_SOCKET,HARDWARE_VALUES[hardware])
            visual.set_input(FINISH_SOCKET,FINISH_VALUES[finish])
        if visual.has_input(door_panel_fill.INPUT):
            visual.set_input(door_panel_fill.INPUT,float(style==nd.STYLE_SHAKER_5 and fill=='FROSTED'))
        visual.set_input(nd.STYLE,float(STYLE_VALUES[style]))
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
    if style == nd.STYLE_SHAKER_5:
        if fill == 'FROSTED':
            door[door_panel_fill.KEY]=fill
        elif door_panel_fill.KEY in door:
            del door[door_panel_fill.KEY]
    if hardware == 'NONE':
        if HARDWARE in door:
            del door[HARDWARE]
    else:
        door[HARDWARE]=hardware
    if finish != DEFAULT_FINISH:
        door[HARDWARE_FINISH]=finish
    elif HARDWARE_FINISH in door:
        del door[HARDWARE_FINISH]
    return obj
