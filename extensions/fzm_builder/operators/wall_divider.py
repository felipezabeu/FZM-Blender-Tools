"""Non-structural horizontal bounds for one wall's Shower Area tile finish."""
from math import isfinite

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

from . import shower_area as sh


def divider_wall(obj):
    if obj and obj.get(sh.PART):
        obj = obj.get('fzm_shower_wall')
    if obj and obj.get('IS_WALL_BP') and not (obj.library or obj.override_library):
        return obj
    return None


def _area_for(context, wall):
    return next((o for o in context.scene.objects if o.get(sh.AREA)
                 and wall in o.get(sh.SOURCE, {}).values()), None)


def _length_and_axis(wall):
    _, start, end, _, _ = sh._wall_info(wall)
    delta = (end-start).xy
    return delta.length, start.xy, delta.normalized()


def _pick_distance(context, wall, origin, direction):
    """Ray-cast the actual wall, then project its hit onto the wall-length axis."""
    transform = wall.matrix_world
    inverse = transform.inverted()
    hit, point, _, _ = wall.ray_cast(
        inverse@origin, (inverse.to_3x3()@direction).normalized(),
        depsgraph=context.evaluated_depsgraph_get(),
    )
    if not hit:
        return None
    length, start, axis = _length_and_axis(wall)
    return max(0., min(length, ((transform@point).xy-start).dot(axis)))


def _check_fixtures(context, area, wall):
    """Reject trimming a fixture, not silently moving or leaving it unsupported."""
    from .shower_fixtures import fixtures_for_area, VISUAL
    objects = sh.FZM_OT_shower_area.targets(context, area)
    path, _ = sh._ordered_path(objects, objects)
    lines, corners = sh._finish_lines(path)
    i = next(i for i, line in enumerate(lines) if line[0][0] == wall)
    a, d = corners[i], lines[i][3]
    left, right = sh.wall_span(lines[i], a, corners[i+1])
    for fixture in fixtures_for_area(context, area):
        if fixture.parent != wall:
            continue
        for item in fixture.children:
            if not item.get(VISUAL):
                continue
            # Project mesh vertices rather than a world AABB (rotated walls).
            stations = [((item.matrix_world @ v.co).xy-a).dot(d) for v in item.data.vertices]
            if stations and (min(stations) < left-sh.PLANAR or max(stations) > right+sh.PLANAR):
                raise ValueError(f"Wall Divider would cut across {fixture.name}. Move or edit the fixture first.")


def set_wall_dividers(context, wall, start, stop):
    """Save bounds; refresh the linked tile face or roll back on any failure."""
    if not all(isfinite(v) for v in (start, stop)):
        raise ValueError("Use finite divider distances.")
    context.view_layer.update()
    length, _, _ = _length_and_axis(wall)
    if start >= length or stop > length:
        raise ValueError("Place each divider within the physical wall length.")
    # An endpoint within tolerance of its physical wall end is untrimmed,
    # preserving any automatic miter at that corner.
    start = -1. if start <= sh.PLANAR else start
    stop = -1. if stop < 0. or length-stop <= sh.PLANAR else stop
    if (stop if stop >= 0. else length) - max(0.,start) < .04:
        raise ValueError("Leave at least 40 mm between finish boundaries.")
    previous = tuple(wall[sh.WALL_DIVIDERS]) if sh.WALL_DIVIDERS in wall else None

    def store(bounds):
        if bounds is not None:
            wall[sh.WALL_DIVIDERS] = list(bounds)
        elif sh.WALL_DIVIDERS in wall:
            del wall[sh.WALL_DIVIDERS]

    store((start, stop) if start >= 0. or stop >= 0. else None)
    area = _area_for(context, wall)
    try:
        if area:
            _check_fixtures(context, area, wall)
            active = context.active_object
            tile_selected = bool(active and active.get(sh.PART) and active.parent == area)
            panels = sh.rebuild_panels(context, area)
            if tile_selected:
                panel = panels[wall]
                panel.select_set(True)
                context.view_layer.objects.active = panel
    except Exception:
        store(previous)
        raise


class FZM_OT_wall_divider(bpy.types.Operator):
    bl_idname = 'fzm_builder.wall_divider'
    bl_label = 'Wall Divider'
    bl_description = 'Set where the tile finish starts and ends without splitting the structural wall'
    bl_options = {'UNDO'}

    use_start: bpy.props.BoolProperty(name='Limit Start')
    start: bpy.props.FloatProperty(name='Start Distance', unit='LENGTH', min=0.)
    use_end: bpy.props.BoolProperty(name='Limit End')
    end: bpy.props.FloatProperty(name='End Distance', unit='LENGTH', min=0.)
    clear: bpy.props.BoolProperty(name='Clear Wall Dividers')

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and divider_wall(context.active_object) is not None

    def invoke(self, context, _event):
        wall = divider_wall(context.active_object)
        start, end = wall.get(sh.WALL_DIVIDERS, (-1., -1.))
        length, _, _ = _length_and_axis(wall)
        self.clear = False
        self.use_start, self.use_end = start >= 0., end >= 0.
        self.start = start if self.use_start else 0.
        self.end = end if self.use_end else length
        return context.window_manager.invoke_props_dialog(self,width=380)

    def draw(self, context):
        layout = self.layout
        wall = divider_wall(context.active_object)
        if wall is None:
            return
        layout.label(text=wall.name)
        layout.label(text='Distances from this wall’s origin, along the wall.')
        if sh.WALL_DIVIDERS in wall:
            layout.prop(self, 'clear')
        if not self.clear:
            for enabled, distance in (('use_start','start'), ('use_end','end')):
                row = layout.row(align=True)
                row.prop(self, enabled)
                sub = row.row()
                sub.enabled = getattr(self, enabled)
                sub.prop(self, distance)
        layout.label(text='Tile finish only. The wall is not cut.', icon='INFO')

    def execute(self, context):
        wall = divider_wall(context.active_object)
        try:
            if not wall:
                raise ValueError("Select a Builder wall or tile face.")
            start = self.start if self.use_start and not self.clear else -1.
            stop = self.end if self.use_end and not self.clear else -1.
            set_wall_dividers(context, wall, start, stop)
        except (ValueError, RuntimeError, KeyError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        return {'FINISHED'}


def _window_region_at(area, mouse_x, mouse_y):
    """Find the actual viewport quadrant, never a sidebar/header over it."""
    def contains(region):
        return (region.x <= mouse_x < region.x + region.width
                and region.y <= mouse_y < region.y + region.height)

    space = area.spaces.active
    for region in area.regions:
        if region.type == 'UI' and not space.show_region_ui:
            continue
        if region.type == 'TOOLS' and not space.show_region_toolbar:
            continue
        if region.type != 'WINDOW' and contains(region):
            return None
    return next((r for r in area.regions if r.type == 'WINDOW' and contains(r)), None)


def _visible_bounds(context):
    """Cache geometry extents for orthographic rays during this click gesture."""
    return [obj.matrix_world @ Vector(co)
            for obj in context.visible_objects
            if obj.type in {'MESH','CURVE','SURFACE','FONT','META','CURVES','VOLUME','POINTCLOUD'}
            or obj.is_instancer
            for co in obj.bound_box]


def _ray_origin(region, rv3d, coords, direction, bounds):
    if rv3d.is_perspective:
        return view3d_utils.region_2d_to_origin_3d(region, rv3d, coords)
    # An orthographic view can have a multi-kilometre Clip End. Starting
    # Blender's ray there loses precision on remodel-scale meshes. First
    # compute its view-plane point, then start just before the nearest
    # visible geometry, including foreground obstructions and walls behind the orbit center.
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coords, clamp=0.0)
    nearest = min(((p-origin).dot(direction) for p in bounds),
                  default=-max(rv3d.view_distance, 1.))
    return origin + direction*(nearest-1.)


def _clicked_boundary(context, origin, direction):
    """Resolve the wall under the pointer, including an existing tile face."""
    depsgraph = context.evaluated_depsgraph_get()
    hit, point, _normal, _index, obj, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
    if not hit or not obj:
        return None
    obj = obj.original if obj.is_evaluated else obj
    wall = divider_wall(obj)
    if wall is None or not obj.visible_get(view_layer=context.view_layer, viewport=context.space_data):
        return None
    length, start, axis = _length_and_axis(wall)
    return wall, max(0., min(length, (point.xy-start).dot(axis)))


class FZM_OT_pick_wall_divider(bpy.types.Operator):
    bl_idname = 'fzm_builder.pick_wall_divider'
    bl_label = 'Pick Wall Divider'
    bl_description = 'Click a Builder wall or its tile face without having to select it first'
    bl_options = {'UNDO'}

    boundary: bpy.props.EnumProperty(items=(
        ('START','Start','Tile begins at the point you pick'),
        ('END','End','Tile ends at the point you pick')))

    @classmethod
    def poll(cls, context):
        return (context.mode == 'OBJECT' and context.window is not None
                and context.area is not None and context.area.type == 'VIEW_3D')

    def invoke(self, context, _event):
        self.area = context.area
        self.window = context.window
        self.bounds = _visible_bounds(context)
        self.area.header_text_set(f"Wall Divider: click a wall or tile face to set tile {self.boundary.lower()} | Esc: cancel")
        self.window.cursor_modal_set('CROSSHAIR')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, _context):
        try:
            self.area.header_text_set(None)
            self.area.tag_redraw()
        finally:
            self.window.cursor_modal_restore()

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        commit = event.type == 'LEFTMOUSE' and event.value == 'PRESS'
        if not commit and event.type != 'MOUSEMOVE':
            return {'RUNNING_MODAL'}
        region = _window_region_at(self.area, event.mouse_x, event.mouse_y)
        if region is None:
            return {'RUNNING_MODAL'}
        coords = (event.mouse_x-region.x, event.mouse_y-region.y)
        try:
            with context.temp_override(window=self.window, area=self.area, region=region):
                rv3d = context.region_data
                if rv3d is None:
                    return {'RUNNING_MODAL'}
                direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coords)
                origin = _ray_origin(region, rv3d, coords, direction, self.bounds)
                candidate = _clicked_boundary(context, origin, direction)
                if candidate is None:
                    if commit:
                        self.report({'WARNING'}, 'Click the visible surface of a Builder wall or its tile face.')
                    return {'RUNNING_MODAL'}
                wall, offset = candidate
                if commit:
                    limits = list(wall.get(sh.WALL_DIVIDERS, (-1., -1.)))
                    limits[0 if self.boundary == 'START' else 1] = offset
                    set_wall_dividers(context, wall, *limits)
                else:
                    units = context.scene.unit_settings
                    distance = bpy.utils.units.to_string(units.system, 'LENGTH',
                                offset*units.scale_length, precision=3)
                    self.area.header_text_set(f"Wall Divider: {wall.name} · {self.boundary.title()} {distance} from origin | Esc: cancel")
        except (ValueError, RuntimeError, KeyError) as error:
            if commit:
                self.report({'WARNING'}, str(error))
            return {'RUNNING_MODAL'}
        if commit:
            self.cancel(context)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}
