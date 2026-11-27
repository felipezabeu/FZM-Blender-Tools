"""Slide a placed door as one assembly, constrained to its existing wall."""

import math
from dataclasses import dataclass

import bpy
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from .. import hb_types
from . import door_units, finishes, native_doors

MOVE = 'fzm_builder.move_door_along_wall'
EPS = 1.e-5
KEYMAPS = []


@dataclass(frozen=True)
class Slide:
    cage: object
    wall: object
    offset: float
    first: float
    last: float
    axis_scale: float

    def clamp(self, offset):
        return max(self.first, min(self.last, offset))

    def location_for(self, offset, original_x):
        return original_x + (self.clamp(offset) - self.offset) / self.axis_scale


def _local_axes(obj, wall):
    transform = wall.matrix_world.inverted_safe() @ obj.matrix_world
    axis = transform.to_3x3() @ Vector((1., 0., 0.))
    return transform.translation, axis


def _pocket(obj, width):
    if obj.get(native_doors.TYPE_KEY) == 'POCKET' and (visual := native_doors.visual_for(obj)):
        _, _, right = native_doors.get_options(visual)
        return (0., max(0., width - .018)) if right else (max(0., width - .018), 0.)
    return 0., 0.


def _slide_for(cage):
    wall = cage.parent
    if not door_units.local(wall) or not wall.get('IS_WALL_BP'):
        raise ValueError('Choose a door attached to a local FZM wall.')
    params = hb_types.GeoNodeWall(wall)
    opening = hb_types.GeoNodeCage(cage)
    width = opening.get_input('Dim X')
    height = opening.get_input('Dim Z')
    length = params.get_input('Length')
    if not all(isinstance(v, (float, int)) and math.isfinite(v) and v > 0.
               for v in (length, width, height)):
        raise ValueError('The wall or door does not have valid dimensions.')
    origin, width_axis = _local_axes(cage, wall)
    movement_axis = cage.matrix_parent_inverse.to_3x3() @ Vector((1., 0., 0.))
    if (not all(math.isfinite(v) for v in (*origin, *movement_axis, *width_axis))
            or width_axis.x <= EPS or abs(width_axis.y) > EPS or abs(width_axis.z) > EPS
            or movement_axis.x <= EPS or abs(movement_axis.y) > EPS or abs(movement_axis.z) > EPS):
        raise ValueError('This door no longer aligns with its wall. Reposition it in Edit Door first.')
    width *= width_axis.x
    pocket_left, pocket_right = _pocket(cage, width)
    before, after = pocket_left, width + pocket_right
    first, last = before, length - after
    # Keep the opening in its current free span; don't sweep through a nearby
    # door/window while the wall Boolean and connected trim are being previewed.
    for other in wall.children:
        if other == cage or not (other.get(door_units.DOOR) or other.get('IS_WINDOW_BP')):
            continue
        dims = hb_types.GeoNodeCage(other)
        if not dims.has_modifier() or not all(dims.has_input(k) for k in ('Dim X', 'Dim Z')):
            continue
        w, h = dims.get_input('Dim X'), dims.get_input('Dim Z')
        if not all(isinstance(v, (float, int)) and math.isfinite(v) and v > 0. for v in (w, h)):
            continue
        pt, axis = _local_axes(other, wall)
        if min(pt.z + h, origin.z + height) - max(pt.z, origin.z) <= EPS:
            continue
        left, right = sorted((pt.x, pt.x + w * axis.x))
        a, b = _pocket(other, right - left)
        left, right = left - a, right + b
        if right <= origin.x - before + EPS:
            first = max(first, right + before)
        elif left >= origin.x + after - EPS:
            last = min(last, left - after)
        else:
            raise ValueError('This door already overlaps another opening. Adjust its offset in Edit Door first.')
    if first > last + EPS:
        raise ValueError('The whole door opening does not fit on this wall.')
    return Slide(cage, wall, origin.x, first, max(last, first), movement_axis.x)


def _active_cage(context):
    obj = context.active_object if context.mode == 'OBJECT' else None
    cage = door_units.cage_for(obj)
    if (door_units.local(obj) and door_units.local(cage)
            and obj.select_get(view_layer=context.view_layer)):
        return cage
    return None


def _promote_selection(context, cage):
    """Only the cutter/controller is active, never a display part."""
    for obj in tuple(context.selected_objects):
        if obj != cage and door_units.cage_for(obj) == cage:
            obj.select_set(False, view_layer=context.view_layer)
    cage.select_set(True, view_layer=context.view_layer)
    context.view_layer.objects.active = cage


def _pointer_slide(start, pointer, axis, projection_parameter):
    """Ignore pointer motion across the wall and return the host-X distance."""
    # Mouse distance projected onto the visible wall axis, in pixels. Mapping
    # the projected segment back with reciprocal W handles perspective too.
    if axis.length_squared < 1.e-6:
        return 0.
    t = (pointer - start).dot(axis) / axis.length_squared
    near_w, far_w = projection_parameter
    denominator = far_w + t * (near_w - far_w)
    if denominator <= EPS:
        return math.copysign(math.inf, t)
    return t * near_w / denominator


class FZM_OT_move_door_along_wall(bpy.types.Operator):
    bl_idname = MOVE
    bl_label = 'Move Door Along Wall'
    bl_description = 'Slide the selected door and its wall opening together along the current wall'
    bl_options = {'UNDO'}

    offset: bpy.props.FloatProperty(name='Offset From Wall Start', unit='LENGTH',
                                    description='Target offset along the existing wall, clamped to its free span')

    @classmethod
    def poll(cls, context):
        if not context.area or context.area.type != 'VIEW_3D':
            return False
        cage = _active_cage(context)
        # Ordinary, unrelated and mixed selections keep Blender's normal G.
        # The door pieces' transform locks still prevent a mixed move from
        # separating them or from bypassing the wall clamp.
        return bool(cage and all(door_units.cage_for(obj) == cage for obj in context.selected_objects))

    def _begin(self, context):
        cage = _active_cage(context)
        try:
            if not cage:
                raise ValueError('Select one placed door.')
            if any(door_units.cage_for(obj) != cage for obj in context.selected_objects):
                raise ValueError('Select only this door before moving it along the wall.')
            if not cage.visible_get(view_layer=context.view_layer):
                raise ValueError('Show this door’s controller before moving it.')
            context.view_layer.update()
            self._slide = _slide_for(cage)
        except (RuntimeError, ValueError, KeyError) as exc:
            self.report({'WARNING'}, str(exc))
            return False
        self._selection = tuple(context.selected_objects)
        self._active = context.active_object
        self._original = cage.location.x
        self._chosen = None
        return True

    def _apply(self, value):
        cage = self._slide.cage
        self._chosen = self._slide.clamp(value)
        cage.location.x = self._slide.location_for(self._chosen, self._original)
        cage.update_tag()

    def _finish(self, context):
        current = self._slide.cage
        _promote_selection(context, current)
        if abs(current.location.x - self._original) > EPS:
            context.view_layer.update()
            finishes.refresh_opening_baseboards(context, (current,), self.report)
        return {'FINISHED'}

    def execute(self, context):
        if not self.properties.is_property_set('offset') or not self._begin(context):
            return {'CANCELLED'}
        if not math.isfinite(self.offset):
            self.report({'WARNING'}, 'Use a finite offset.')
            return {'CANCELLED'}
        self._apply(self.offset)
        return self._finish(context)

    def invoke(self, context, event):
        if self.properties.is_property_set('offset'):
            return self.execute(context)
        if not self._begin(context):
            return {'CANCELLED'}
        self._region = context.region
        self._area = context.area
        view = context.region_data
        if not self._region or self._region.type != 'WINDOW' or not view:
            return {'CANCELLED'}
        cage = self._slide.cage
        opening = hb_types.GeoNodeCage(cage)
        # Anchor at door mid-height for a side or perspective view, but the
        # curve and the clicked leaf stay draggable from any screen point.
        p0 = cage.matrix_world @ Vector((0., 0., opening.get_input('Dim Z') * .5))
        step = (self._slide.wall.matrix_world.to_3x3() @ Vector((1., 0., 0.)))
        # Use a short, symmetric reference segment so it stays in front of
        # the camera when working close to the opening.
        step *= .25
        p0 -= step * .5
        p1 = p0 + step
        p = location_3d_to_region_2d(self._region, view, p0)
        q = location_3d_to_region_2d(self._region, view, p1)
        if p is None or q is None or (q - p).length < 1.:
            self.report({'WARNING'}, 'Turn your view so you can see along the wall, then move the door again.')
            return {'CANCELLED'}
        self._projection = (q - p, tuple((view.perspective_matrix @ Vector((*pt, 1.))).w for pt in (p0, p1)))
        self._mouse = Vector((event.mouse_x, event.mouse_y))
        _promote_selection(context, cage)
        self._hint()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _hint(self):
        self._area.header_text_set('Move Door Along Wall  |  Left Click / Enter: confirm  |  Esc: cancel')

    def _cancel(self, context):
        self._area.header_text_set(None)
        try:
            cage = self._slide.cage
            cage.location.x = self._original
            cage.update_tag()
            for obj in self._selection:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True, view_layer=context.view_layer)
            if cage not in self._selection:
                cage.select_set(False, view_layer=context.view_layer)
            context.view_layer.objects.active = self._active
        except ReferenceError:
            pass

    def cancel(self, context):
        self._cancel(context)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._cancel(context)
            return {'CANCELLED'}
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            axis, depth = self._projection
            travel = .25 * _pointer_slide(self._mouse, Vector((event.mouse_x, event.mouse_y)), axis, depth)
            self._apply(self._slide.offset + travel)
        elif event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            self._area.header_text_set(None)
            return self._finish(context)
        return {'RUNNING_MODAL'}


def _protect_existing():
    door_units.protect_saved_doors(bpy.data.objects)
    return None


def register():
    bpy.utils.register_class(FZM_OT_move_door_along_wall)
    addon = bpy.context.window_manager.keyconfigs.addon
    if addon:
        mapping = addon.keymaps.new(name='Object Mode', space_type='EMPTY', region_type='WINDOW')
        item = mapping.keymap_items.new(MOVE, 'G', 'PRESS', head=True)
        KEYMAPS.append((mapping, item))
    # Add-on enable runs with restricted bpy.data; use the first UI tick.
    bpy.app.timers.register(_protect_existing, first_interval=0.)


def unregister():
    if bpy.app.timers.is_registered(_protect_existing):
        bpy.app.timers.unregister(_protect_existing)
    for mapping, item in KEYMAPS:
        mapping.keymap_items.remove(item)
    KEYMAPS.clear()
    bpy.utils.unregister_class(FZM_OT_move_door_along_wall)
