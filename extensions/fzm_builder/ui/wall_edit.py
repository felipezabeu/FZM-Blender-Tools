"""Viewport handles for drawing connected Builder wall edits in the floor plane."""

import bpy
import gpu
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d, region_2d_to_origin_3d, region_2d_to_vector_3d,
)
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .. import hb_snap, hb_types
from ..operators.wall_edit import SceneGraph, EPS, START, END
from ..operators.wall_edit_snap import (
    Guide, SquareGuide, SquareHit, PIXELS, candidates, square_candidates, square_markers,
)

EDIT = 'fzm_builder.edit_wall'
LABELS = {'START': 'Move Wall Start', 'END': 'Move Wall End', 'MOVE': 'Move Entire Wall'}


def active_wall(context):
    obj = context.active_object
    if (context.mode == 'OBJECT' and obj and obj.get('IS_WALL_BP')
            and obj.select_get() and obj.visible_get() and not obj.library and not obj.override_library):
        return obj
    return None


def _pixels(event, region):
    return Vector((event.mouse_x - region.x, event.mouse_y - region.y))


def _on_ground(region, rv3d, xy, level):
    origin = region_2d_to_origin_3d(region, rv3d, xy, clamp=1000)
    ray = region_2d_to_vector_3d(region, rv3d, xy)
    if abs(ray.z) < .035:
        return None
    travel = (level - origin.z) / ray.z
    if rv3d.is_perspective and travel < 0.:
        return None
    return origin + travel * ray


def _guides(model, active, mode, view_layer):
    sides={'START':(START,), 'END':(END,), 'MOVE':(START,END)}[mode]
    affected={wall for side in sides for wall,_ in model.graph.members[active,side]}
    level=model.levels[active]
    result=[]
    for wall,segment in model.graph.geometry.items():
        if (wall in affected or abs(model.levels[wall]-level)>.002
                or not wall.visible_get(view_layer=view_layer)
                or wall.get('IS_FAKE_WALL') or wall.get('WALL_TYPE')=='Fake'):
            continue
        result.append(Guide(wall.name,segment.start,segment.end))
        native=model.walls[wall]
        if native.has_input('Thickness'):
            thickness=native.get_input('Thickness')
            if thickness and thickness>EPS:
                shift=wall.matrix_world.to_3x3() @ Vector((0.,thickness,0.))
                if abs(shift.z)<=.002 and shift.xy.length>EPS:
                    a,b=((p[0]+shift.x,p[1]+shift.y) for p in (segment.start,segment.end))
                    result.append(Guide(wall.name,a,b))
    return tuple(result)


def _square_guides(model,active,mode):
    graph=model.graph
    sides={'START':(START,), 'END':(END,), 'MOVE':(START,END)}[mode]
    moved={member for side in sides for member in graph.members[active,side]}
    result=[]
    for side in (START,END):
        joint=graph.geometry[active][side]
        opposite=(active,1-side)
        for wall,end in graph.members[active,side]:
            if wall==active:
                continue
            peer=graph.geometry[wall][end]
            # Legacy designed joins are normally exact. Refuse to infer a
            # right angle from a stale graph whose declared joint drifts.
            if (Vector(joint)-Vector(peer)).length>EPS:
                continue
            peer_far=(wall,1-end)
            move_joint=(active,side) in moved
            first=graph.geometry[active][1-side]
            other=graph.geometry[wall][1-end]
            if move_joint== (opposite in moved) == (peer_far in moved):
                continue  # Neither outgoing direction could change on this drag.
            result.append(SquareGuide(wall.name,joint,first,other,move_joint,
                                      opposite in moved,peer_far in moved))
    return tuple(result)


def _project_targets(operator,point):
    p=location_3d_to_region_2d(operator.region,operator.rv3d,Vector((*point,operator.level+.0254)))
    if p is None or not (0 < p.x < operator.region.width and 0 < p.y < operator.region.height):
        return None
    return p


def _preview(operator):
    context = bpy.context
    if context.area != operator.area or context.region != operator.region:
        return
    vertices = []
    for obj, segment in operator.plan.items():
        z = operator.model.levels[obj] + .0254
        vertices += [(*segment.start, z), (*segment.end, z)]
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    shader.bind()
    shader.uniform_float('viewportSize', (context.region.width, context.region.height))
    if operator.axis != 'FREE' and operator.anchor is not None:
        a = operator.anchor.copy()
        a.z += .023
        delta = Vector((1.,0.,0.) if operator.axis == 'X' else (0.,1.,0.))
        extent = max(1., operator.rv3d.view_distance * 3.0)
        shader.uniform_float('lineWidth', 1.6)
        shader.uniform_float('color', (.95,.26,.25,1.) if operator.axis == 'X' else (.32,.82,.32,1.))
        batch_for_shader(shader,'LINES',{'pos':(a-extent*delta,a+extent*delta)}).draw(shader)
    if vertices:
        shader.uniform_float('lineWidth', 4.0)
        shader.uniform_float('color', (.20, .84, 1., 1.))
        batch_for_shader(shader, 'LINES', {'pos': vertices}).draw(shader)

    if hit:=operator.snap_hit:
        color=(1.,.66,.08,1.) if hit.kind=='EDGE' else (.57,1.,.23,1.)
        z=operator.level+.044
        x,y=hit.point
        scale=max(.02,min(.3,operator.rv3d.view_distance*.012))
        shader.uniform_float('lineWidth',2.5)
        shader.uniform_float('color',color)
        pos=[(x-scale,y,z),(x+scale,y,z),(x,y-scale,z),(x,y+scale,z)]
        if hit.kind=='EDGE':
            pos.extend(((*hit.guide.start,z),(*hit.guide.end,z)))
        batch_for_shader(shader,'LINES',{'pos':pos}).draw(shader)


    if operator.plan:
        marks=square_markers(operator.right_angles,operator.offset.xy)
        if marks:
            z=operator.level+.053
            verts=[]
            for (x,y),u,v,length in marks:
                scale=min(length*.22,max(.032,min(.22,operator.rv3d.view_distance*.019)))
                q=(x+scale*u[0],y+scale*u[1],z)
                r=(x+scale*v[0],y+scale*v[1],z)
                c=(x+scale*(u[0]+v[0]),y+scale*(u[1]+v[1]),z)
                verts.extend((q,c,c,r))
            shader.uniform_float('lineWidth',3.0)
            shader.uniform_float('color',(.24,1.,.69,1.))
            batch_for_shader(shader,'LINES',{'pos':verts}).draw(shader)



def _restrict(offset, axis):
    return Vector((offset.x if axis!='Y' else 0., offset.y if axis!='X' else 0., 0.))


class FZM_OT_edit_wall(bpy.types.Operator):
    bl_idname = EDIT
    bl_label = 'Edit Connected Wall'
    bl_options = {'UNDO', 'INTERNAL'}

    edit_mode: bpy.props.EnumProperty(items=[(k, v, '') for k, v in LABELS.items()], default='MOVE')
    axis: bpy.props.EnumProperty(
        items=[('FREE','Free movement','Move on both axes'),('X','X only','Lock to world X'),('Y','Y only','Lock to world Y')],
        default='FREE',options={'SKIP_SAVE'})
    x: bpy.props.FloatProperty(unit='LENGTH', options={'SKIP_SAVE'})
    y: bpy.props.FloatProperty(unit='LENGTH', options={'SKIP_SAVE'})
    from_handle: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE', 'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return active_wall(context) is not None

    @classmethod
    def description(cls, context, properties):
        return LABELS[properties.edit_mode] + ': drag; S toggles wall snap; Q toggles square snap; X/Y locks an axis; Ctrl snaps to the grid'

    def _apply(self, context, wall, dx, dy):
        try:
            model = SceneGraph.read(context)
            if wall not in model.walls:
                raise ValueError('Select a wall created by FZM Builder.')
            plan = model.checked_plan(wall, self.edit_mode, dx, dy)
            if not plan:
                return {'CANCELLED'}
            model.commit(context, plan)
        except (AttributeError, KeyError, ValueError, TypeError, RuntimeError) as error:
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        self.report({'INFO'}, f'{len(plan)} wall(s) updated. Regenerate existing floor finishes, trims or shower lining as needed.')
        return {'FINISHED'}

    def execute(self, context):
        offset = _restrict(Vector((self.x,self.y,0.)), self.axis)
        return self._apply(context, active_wall(context), offset.x, offset.y)

    def invoke(self, context, event):
        self.wall = active_wall(context)
        if not context.area or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        self.area = context.area
        self.region = (context.region if context.region.type == 'WINDOW'
                       else next((r for r in self.area.regions if r.type == 'WINDOW'), None))
        self.rv3d = context.region_data or context.space_data.region_3d
        if not self.region or not self.rv3d:
            return {'CANCELLED'}
        self.model = SceneGraph.read(context)
        if self.wall not in self.model.walls:
            return {'CANCELLED'}
        self.level = self.model.levels[self.wall]
        self.snap_enabled=context.scene.home_builder.visual_wall_snap
        self.square_enabled=context.scene.home_builder.visual_wall_square
        self.snap_hit=None
        self.right_angles=_square_guides(self.model,self.wall,self.edit_mode)
        self.guides=_guides(self.model,self.wall,self.edit_mode,context.view_layer)
        segment=self.model.graph.geometry[self.wall]
        middle=tuple((a+b)*.5 for a,b in zip(segment.start,segment.end))
        self.anchors={'START':(('start',segment.start),), 'END':(('end',segment.end),),
                      'MOVE':(('center',middle),('start',segment.start),('end',segment.end))}[self.edit_mode]
        self.first = _pixels(event, self.region)
        self.anchor = (_on_ground(self.region, self.rv3d, self.first, self.level)
                       if self.from_handle else None)
        if self.from_handle and self.anchor is None:
            self.report({'WARNING'}, 'Use a top or angled view to move a wall in the floor plane.')
            return {'CANCELLED'}
        self.originated_on_press = self.from_handle and event.value == 'PRESS'
        self.plan, self.error, self.offset = {}, None, Vector((0., 0., 0.))
        self.draw_handle = bpy.types.SpaceView3D.draw_handler_add(_preview, (self,), 'WINDOW', 'POST_VIEW')
        context.window_manager.modal_handler_add(self)
        self._hint('Drag or click a destination' if self.from_handle else 'Click a reference point, then a destination')
        return {'RUNNING_MODAL'}

    def _hint(self, text):
        lock = '' if self.axis == 'FREE' else f'  [{self.axis} only]'
        snap='on' if self.snap_enabled else 'off'
        square='on' if self.square_enabled else 'off'
        self.area.header_text_set(f'{LABELS[self.edit_mode]}{lock}: {text}  |  S: wall snap {snap}  Q: 90° {square}  X/Y: lock  Ctrl: grid  Esc: cancel')
        self.area.tag_redraw()

    def _cleanup(self):
        if getattr(self, 'draw_handle', None):
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle, 'WINDOW')
            self.draw_handle = None
        self.area.header_text_set(None)
        self.area.tag_redraw()

    def cancel(self, context):
        self._cleanup()

    def _update(self, context, event):
        self.snap_hit=None
        point = _on_ground(self.region, self.rv3d, _pixels(event, self.region), self.level)
        if point is None:
            self.plan, self.error = {}, 'Use a top or angled view to move in the floor plane.'
            self._hint(self.error)
            return
        self.offset = point - self.anchor
        if event.ctrl:
            self.offset = hb_snap.snap_vector_to_grid(self.offset, context.scene.unit_settings, event.shift)
        self.offset = _restrict(self.offset, self.axis)
        # Ctrl retains the existing grid behavior and takes full precedence.
        # Try another target if the best would collapse a connected wall or
        # cut across an opening; do not make an invalid snap look accepted.
        if not event.ctrl and (self.snap_enabled or self.square_enabled):
            pixels=PIXELS*max(1.,context.preferences.system.ui_scale)
            project=lambda p:_project_targets(self,p)
            found=[]
            if self.snap_enabled and self.guides:
                found.extend(candidates(self.anchors,self.offset.xy,self.guides,self.axis,project,pixels))
            if self.square_enabled and self.right_angles:
                found.extend(square_candidates(self.right_angles,self.anchors[0][1],
                                               self.offset.xy,self.axis,project,pixels))
            found.sort(key=lambda hit:hit.pixels-(5. if isinstance(hit,SquareHit) else 4. if hit.kind=='CORNER' else 0.))
            for hit in found:
                try:
                    self.plan=self.model.checked_plan(self.wall,self.edit_mode,*hit.offset)
                except ValueError:
                    continue
                self.offset=Vector((*hit.offset,0.))
                self.error=None
                if isinstance(hit,SquareHit):
                    self._hint(f'90° to {hit.guide.name}')
                else:
                    self.snap_hit=hit
                    self._hint(f'Snapped {hit.reference} to {hit.guide.name} {hit.kind.lower()}')
                return
        try:
            self.plan = self.model.checked_plan(self.wall, self.edit_mode, self.offset.x, self.offset.y)
            self.error = None
        except ValueError as error:
            self.plan, self.error = {}, str(error)
        self._hint(self.error or 'Click or release to confirm')

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._cleanup()
            return {'CANCELLED'}
        if context.area != self.area or active_wall(context) != self.wall:
            self._cleanup()
            return {'CANCELLED'}
        if hb_snap.event_is_pass_through(event):
            return {'PASS_THROUGH'}
        if event.type in {'S','Q'} and event.value=='PRESS':
            if event.type=='S':
                self.snap_enabled=not self.snap_enabled
            else:
                self.square_enabled=not self.square_enabled
            if self.anchor is not None:
                self._update(context,event)
            else:
                self._hint('Click a reference point, then a destination')
            return {'RUNNING_MODAL'}
        if event.type in {'X','Y'} and event.value=='PRESS':
            self.axis='FREE' if self.axis==event.type else event.type
            if self.anchor is not None:
                self._update(context,event)
            else:
                self._hint('Click a reference point, then a destination')
            return {'RUNNING_MODAL'}
        xy = _pixels(event, self.region)
        inside = 0 <= xy.x < self.region.width and 0 <= xy.y < self.region.height
        if self.anchor is None and inside and event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.anchor = _on_ground(self.region, self.rv3d, xy, self.level)
            self._hint('Click a destination' if self.anchor else 'Use a top or angled view')
            return {'RUNNING_MODAL'}
        if self.anchor is not None and inside:
            if event.type in {'MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT', 'RIGHT_SHIFT'}:
                self._update(context, event)
            elif event.type == 'LEFTMOUSE':
                if self.originated_on_press and event.value == 'RELEASE':
                    self.originated_on_press = False
                    if (xy - self.first).length < 5.:
                        return {'RUNNING_MODAL'}
                elif event.value != 'PRESS':
                    return {'RUNNING_MODAL'}
                self._update(context, event)
                if self.error:
                    self.report({'WARNING'}, self.error)
                    return {'RUNNING_MODAL'}
                if self.plan:
                    self._cleanup()
                    return self._apply(context, self.wall, self.offset.x, self.offset.y)
        return {'RUNNING_MODAL'}


class FZM_GGT_wall_edit(bpy.types.GizmoGroup):
    bl_idname = 'FZM_GGT_wall_edit'
    bl_label = 'Wall Editing Handles'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    # These handles use region pixels; SCALE bypasses world/depth scaling.
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        obj = active_wall(context)
        return obj is not None and getattr(context.space_data, 'show_gizmo', True)

    def setup(self, context):
        self.handles = {}
        for kind in ('START', 'END', 'MOVE'):
            g = self.gizmos.new('GIZMO_GT_button_2d')
            g.properties.icon = 'HAND' if kind == 'MOVE' else 'SNAP_VERTEX'
            g.properties.draw_options = {'BACKDROP', 'OUTLINE'}
            g.properties.backdrop_fill_alpha = .9
            g.properties.show_drag = False
            g.scale_basis = 14.
            g.color = (.08, .36, .56) if kind != 'MOVE' else (.10, .49, .39)
            g.color_highlight = (.22, .72, .98)
            g.alpha, g.alpha_highlight = .90, 1.
            g.use_tooltip = True
            props = g.target_set_operator(EDIT)
            props.edit_mode, props.from_handle = kind, True
            g.hide = True
            self.handles[kind] = g

    def draw_prepare(self, context):
        obj = active_wall(context)
        points = {}
        region, rv3d = context.region, context.region_data
        if obj and region and rv3d:
            model = hb_types.GeoNodeWall(obj)
            if model.has_input('Length'):
                length = model.get_input('Length')
                for kind, x in (('START', 0), ('MOVE', length / 2), ('END', length)):
                    point = location_3d_to_region_2d(region, rv3d, obj.matrix_world @ Vector((x, 0., .0254)))
                    if point and 16 < point.x < region.width - 16 and 16 < point.y < region.height - 16:
                        points[kind] = point
                if 'START' in points and 'END' in points and (points['START'] - points['END']).length < 68:
                    points.pop('MOVE', None)
                    if (points['START'] - points['END']).length < 32:
                        points.pop('END', None)
        for kind, g in self.handles.items():
            point = points.get(kind)
            g.hide = point is None
            if point is not None:
                g.matrix_basis.translation = (*point, 0.)


register, unregister = bpy.utils.register_classes_factory((FZM_OT_edit_wall, FZM_GGT_wall_edit))
