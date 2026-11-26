"""Selection-scoped 3D Viewport button for a placed door's existing open pose."""
from math import isfinite

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from .. import hb_types
from ..operators import hinged_doors as hd, native_doors as nd

TOGGLE = 'fzm_builder.toggle_door_pose'
LAST_OPEN = 'FZM_DOOR_VIEWPORT_LAST_OPEN'
EPS = 1e-6


def _target(context):
    """Resolve the active leaf/cage, never an unselected or unsupported object."""
    active = context.active_object
    if context.mode != 'OBJECT' or not active or not active.select_get(view_layer=context.view_layer):
        return None
    if not active.visible_get(view_layer=context.view_layer):
        return None
    cage = nd.cage_for(active)
    if not cage or cage.library or cage.override_library:
        return None
    if not cage.parent or not cage.parent.get('IS_WALL_BP'):
        return None
    native = cage.get(nd.TYPE_KEY)
    if native:
        visual = nd.visual_for(cage)
    else:
        visual = hd.visual_for(cage) if hd.swing_for(cage) else None
    if not visual or visual.library or visual.override_library or not visual.visible_get(view_layer=context.view_layer):
        return None
    model = hb_types.GeoNodeObject(visual)
    if not model.has_modifier() or not model.has_input(nd.OPEN):
        return None
    opening = model.get_input(nd.OPEN)
    if not isinstance(opening,(int,float)) or not isfinite(opening):
        return None
    return cage,visual,model,max(0.,min(1.,opening))


def _is_open(target):
    return bool(target and target[-1] > EPS)


def command_label(context):
    target = _target(context)
    if not target:
        return ''
    return 'Close Door' if _is_open(target) else 'Open Door'


class FZM_OT_toggle_door_pose(bpy.types.Operator):
    bl_idname = TOGGLE
    bl_label = 'Open / Close Door'
    bl_description = 'Toggle the selected door’s visible 3D pose without changing its opening or style'
    bl_options = {'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _target(context) is not None

    @classmethod
    def description(cls, context, properties):
        if _is_open(_target(context)):
            return 'Close Door (remembers this open amount for next time)'
        return 'Open Door (restores its last amount, or opens to the default maximum)'

    def execute(self, context):
        target = _target(context)
        if not target:
            return {'CANCELLED'}
        cage,visual,model,current = target
        opening = 0.
        if not _is_open(target):
            amount = cage.get(LAST_OPEN,1.)
            opening = min(amount,1.) if isinstance(amount,(int,float)) and isfinite(amount) and amount > EPS else 1.
        try:
            # Change only the existing pose socket; touching a style socket
            # could upgrade a saved legacy native door's node group.
            model.set_input(nd.OPEN,opening)
            if not cage.get(nd.TYPE_KEY):
                cage[hd.POSE] = opening  # Door Prompts saves/restores hinged style and pose on the cage.
            if current > EPS:
                cage[LAST_OPEN] = current
            visual.update_tag()
        except (KeyError,RuntimeError,ValueError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def _anchor(context, cage):
    """Project the center of the fixed aperture instead of the moving leaf."""
    region, rv3d = context.region, context.region_data
    if not region or region.type != 'WINDOW' or not rv3d:
        return None
    dims = hb_types.GeoNodeCage(cage)
    if not dims.has_modifier():
        return None
    try:
        w,d,h = (dims.get_input(k) for k in ('Dim X','Dim Y','Dim Z'))
    except (ValueError,KeyError):
        return None
    if not all(isinstance(v,(int,float)) and isfinite(v) for v in (w,d,h)) or min(w,h) <= 0.:
        return None
    # The control remains accessible with the leaf open, including a fully
    # slid pocket leaf that is hidden behind the wall.
    center = cage.matrix_world @ Vector((w*.5,d*.5,h*.5))
    clip = rv3d.perspective_matrix @ Vector((*center, 1.))
    if clip.w <= EPS or not (-clip.w <= clip.z <= clip.w):
        return None
    p = location_3d_to_region_2d(region,rv3d,center)
    if p is None or not (-1 < p.x < region.width and -1 < p.y < region.height):
        return None
    # UI/toolbars belong to adjacent regions and may overlay the view area.
    lo_x,lo_y = 20,20
    hi_x,hi_y = region.width-20,region.height-24
    size = context.preferences.system.ui_scale
    for other in context.area.regions:
        if other.type in {'TOOLS','UI'} and other.width > 1:
            if other.x < region.x + region.width*.5:
                lo_x = max(lo_x,other.x-region.x+other.width+24*size)
            else:
                hi_x = min(hi_x,other.x-region.x-24*size)
    # Don't orphan the control at an unrelated corner of a narrow/split view.
    if not (lo_x <= p.x <= hi_x and lo_y <= p.y <= hi_y):
        return None
    return p.x, p.y


class FZM_GGT_door_pose(bpy.types.GizmoGroup):
    bl_idname = 'FZM_GGT_door_pose'
    bl_label = 'Door Open / Close'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    # These handles use region pixels; SCALE bypasses world/depth scaling.
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls,context):
        return _target(context) is not None

    def setup(self, context):
        # Blender caches the built-in button icon on first draw. Use two
        # prebound buttons at the same point rather than stale changing icons.
        def make_button(icon):
            gizmo = self.gizmos.new('GIZMO_GT_button_2d')
            gizmo.properties.icon = icon
            gizmo.properties.draw_options = {'BACKDROP', 'OUTLINE'}
            gizmo.properties.backdrop_fill_alpha = .85
            gizmo.properties.show_drag = False
            gizmo.use_tooltip = True
            gizmo.color = (.10,.27,.44)
            gizmo.alpha = .88
            gizmo.color_highlight = (.18,.55,.87)
            gizmo.alpha_highlight = 1.
            gizmo.scale_basis = 17.
            gizmo.target_set_operator(TOGGLE)
            gizmo.hide = True
            return gizmo

        self.open_button = make_button('PLAY')
        self.close_button = make_button('LOOP_BACK')

    def draw_prepare(self, context):
        target = _target(context)
        point = _anchor(context,target[0]) if target else None
        opened = _is_open(target)
        self.open_button.hide = point is None or opened
        self.close_button.hide = point is None or not opened
        if point is not None:
            button = self.close_button if opened else self.open_button
            button.matrix_basis.translation = (*point,0.)


register, unregister = bpy.utils.register_classes_factory((FZM_OT_toggle_door_pose,FZM_GGT_door_pose))
