"""Explicitly split the receiving wall at the physical T made by two selected walls."""
from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Matrix, Vector

from .. import hb_types

JOIN = .012
LEVEL = .002
END_CLEARANCE = .075
CUT_CLEARANCE = .002
EPS = 1e-5


@dataclass
class Wall:
    obj: object
    geo: object
    matrix: object
    inverse: object
    length: float
    thickness: float

    @classmethod
    def read(cls, obj):
        if (not obj or obj.type != 'MESH' or not obj.get('IS_WALL_BP') or obj.library
                or obj.override_library or obj.get('IS_FAKE_WALL') or obj.get('WALL_TYPE') == 'Fake'):
            raise ValueError("Select two editable structural FZM Builder walls in Object Mode.")
        geo = hb_types.GeoNodeWall(obj)
        if not all(geo.has_input(key) for key in ('Length','Thickness','Height','Left Angle','Right Angle')):
            raise ValueError(f"{obj.name} is not an editable parametric wall.")
        matrix = obj.matrix_world.copy()
        axes = [matrix.to_3x3().col[i] for i in range(3)]
        if (matrix.to_3x3().determinant() < 0 or
                any(abs(v.length-1.) > 5e-4 for v in axes)
                or any(abs(axes[i].dot(axes[j])) > 5e-4 for i,j in ((0,1),(0,2),(1,2)))
                or max(abs(axes[0].z),abs(axes[1].z),abs(axes[2].z-1.)) > 5e-4):
            raise ValueError(f"Apply scale and keep {obj.name} upright before dividing.")
        length,thickness = (geo.get_input(key) for key in ('Length','Thickness'))
        if not isfinite(length) or not isfinite(thickness) or length <= EPS or abs(thickness) <= EPS:
            raise ValueError(f"{obj.name} needs valid wall dimensions.")
        return cls(obj,geo,matrix,matrix.inverted(),length,thickness)

    def endpoints(self):
        return (self.matrix.translation,self.matrix @ Vector((self.length,0.,0.)))


def _candidate(host, branch):
    """Recognize an actual branch end touching this wall's footprint, not an X crossing."""
    a,b = [host.inverse @ p for p in branch.endpoints()]
    if max(abs(a.z),abs(b.z)) > LEVEL or abs(b.y-a.y)/(b-a).length < .25:
        return None
    cut = a.x - a.y*(b.x-a.x)/(b.y-a.y)
    if not END_CLEARANCE <= cut <= host.length-END_CLEARANCE:
        return None
    lo,hi = sorted((0.,host.thickness))
    contacts = [p for p in (a,b)
                if -JOIN <= p.x <= host.length+JOIN and lo-JOIN <= p.y <= hi+JOIN]
    if len(contacts) != 1:
        return None
    # Validate the other (free) end really continues out of the physical wall.
    free = b if contacts[0] is a else a
    if lo-JOIN <= free.y <= hi+JOIN:
        return None
    return cut


def find_division(context, objects):
    if len(objects) != 2:
        raise ValueError("Select the long wall and the branch wall that meets it.")
    context.view_layer.update()
    first,second = [Wall.read(obj) for obj in objects]
    found = [(host,branch,cut) for host,branch in ((first,second),(second,first))
             if (cut:=_candidate(host,branch)) is not None]
    if len(found) != 1:
        raise ValueError("Need one clear T: snap a branch end to the middle of the other wall, at least 75 mm from either end.")
    return found[0]


def _opening_span(host, obj, depsgraph):
    item = obj.evaluated_get(depsgraph)
    bounds = item.bound_box
    if obj.type != 'MESH' or len(bounds) != 8 or all(tuple(v)==(-1.,-1.,-1.) for v in bounds):
        raise ValueError(f"Cannot verify the opening limits of {obj.name}.")
    axis = [(host.inverse @ item.matrix_world @ Vector(v)).x for v in bounds]
    start,end = min(axis),max(axis)
    if not all(isfinite(x) for x in (start,end)) or end-start <= EPS:
        raise ValueError(f"Cannot verify the opening limits of {obj.name}.")
    from . import native_doors
    if obj.get(native_doors.TYPE_KEY) == 'POCKET':
        part = native_doors.visual_for(obj)
        if not part:
            raise ValueError(f"Cannot verify the pocket side of {obj.name}.")
        width = hb_types.GeoNodeCage(obj).get_input('Dim X')
        if not isfinite(width) or width <= 0:
            raise ValueError(f"Cannot verify the pocket width of {obj.name}.")
        _,_,right = native_doors.get_options(part)
        if right:
            end += max(0.,width-.018)
        else:
            start -= max(0.,width-.018)
    return start,end


def _editable(obj, scene):
    return bool(obj and not (obj.library or obj.override_library) and obj.name in scene.objects
                and len(obj.users_scene)==1)


def _ordinary_constraint(con, target):
    return (con.type=='COPY_LOCATION' and con.target==target and not con.mute
            and abs(con.influence-1.) < EPS and con.owner_space==con.target_space=='WORLD'
            and con.use_x and con.use_y and con.use_z and not con.use_offset
            and not (con.invert_x or con.invert_y or con.invert_z))


def _motion_dependencies(context, host):
    obj, endpoint = host.obj, host.geo.obj_x
    if (not _editable(obj,context.scene) or obj.animation_data or obj.parent or obj.data.vertices
            or obj.rotation_mode != 'XYZ' or any(abs(v)>EPS for v in obj.delta_location)
            or any(abs(v)>EPS for v in obj.delta_rotation_euler)
            or any(abs(v-1.)>EPS for v in obj.delta_scale) or not endpoint
            or not _editable(endpoint,context.scene) or endpoint.parent != obj
            or endpoint.children or endpoint.constraints):
        raise ValueError(f"Cannot safely divide {obj.name}: it has custom transforms, mesh data, animation, or a changed endpoint.")
    if len(obj.constraints) > 1 or any(
        not con.target or not con.target.get('obj_x') or not _ordinary_constraint(con,con.target)
        for con in obj.constraints if con.type == 'COPY_LOCATION'
    ) or any(con.type != 'COPY_LOCATION' for con in obj.constraints):
        raise ValueError(f"Resolve custom constraints on {obj.name} before dividing it.")
    animation = endpoint.animation_data
    if (not animation or animation.action or animation.nla_tracks or len(animation.drivers)!=1):
        raise ValueError(f"Cannot safely retarget the endpoint driver on {obj.name}.")
    curve = animation.drivers[0]
    variables = curve.driver.variables
    if (curve.data_path!='location' or curve.array_index!=0 or len(variables)!=1
            or variables[0].type!='SINGLE_PROP' or variables[0].targets[0].id!=obj
            or abs(endpoint.location.x-host.length)>5e-4
            or abs(endpoint.location.y)>EPS or abs(endpoint.location.z)>EPS):
        raise ValueError(f"Cannot safely retarget the endpoint driver on {obj.name}.")
    transfers = []
    for other in bpy.data.objects:
        for con in other.constraints:
            if getattr(con,'target',None) == endpoint:
                if (not other.get('IS_WALL_BP') or not _editable(other,context.scene)
                        or not _ordinary_constraint(con,endpoint)):
                    raise ValueError(f"{other.name} has a custom connection to the wall endpoint.")
                transfers.append((other,con))
    pointer = endpoint.home_builder.connected_object
    if (len(transfers)>1 or (transfers and pointer and pointer != transfers[0][0])
            or (pointer and (not pointer.get('IS_WALL_BP') or not _editable(pointer,context.scene)))):
        raise ValueError(f"Resolve ambiguous neighboring wall connections at the end of {obj.name}.")
    return endpoint, pointer or (transfers[0][0] if transfers else None), transfers


def _attachment_plan(context, host, endpoint, cut):
    """Only recognized local cutters can change parent. Keep their complete hierarchies."""
    obj = host.obj
    depsgraph = context.evaluated_depsgraph_get()
    cut_mods = {}
    for mod in obj.modifiers:
        if mod.type == 'NODES' and mod.name == obj.home_builder.mod_name:
            continue
        tool = getattr(mod,'object',None)
        if (mod.type!='BOOLEAN' or mod.operation!='DIFFERENCE' or mod.operand_type!='OBJECT'
                or not tool or tool.parent!=obj or not _editable(tool,context.scene)
                or not any(tool.get(key) for key in ('IS_ENTRY_DOOR_BP','IS_WINDOW_BP','IS_WALL_CUTTER'))):
            raise ValueError(f"Cannot safely divide {obj.name} while the modifier {mod.name} is present.")
        cut_mods.setdefault(tool,[]).append(mod.name)
    transfer = {}
    for child in obj.children:
        if child == endpoint:
            continue
        if (child not in cut_mods or child.parent_type!='OBJECT' or child.animation_data
                or child.constraints or not _editable(child,context.scene)):
            raise ValueError(f"{child.name} is a custom or unsupported wall attachment. Detach it before dividing.")
        low,high = _opening_span(host,child,depsgraph)
        if low-CUT_CLEARANCE <= cut <= high+CUT_CLEARANCE:
            raise ValueError(f"The split would cut through or touch {child.name}. Move that opening first.")
        if low > cut:
            transfer[child] = tuple(cut_mods[child])
    return transfer


def _paint_plan(host,cut):
    from . import room_paint as paint
    created, result = [], []
    try:
        for socket in host.geo.material_inputs(host.obj):
            material = host.geo.get_input(socket)
            if not paint.is_finish(material):
                continue
            base,side = paint.base_material(material),material[paint.SIDE]
            choices = []
            # The new cut is square, but the two outside ends retain their
            # physical miters (which can run outside the old wall datum).
            for low, high, offset in ((float('-inf'), cut, 0.), (cut, float('inf'), cut)):
                spans = tuple(paint.Region(r.floor, max(low, r.start)-offset,
                                           min(high, r.end)-offset, r.material)
                              for r in paint.get_regions(material)
                              if min(high, r.end)-max(low, r.start)>EPS)
                new = paint.make_finish(base,side,spans,material.name)
                if paint.is_finish(new):
                    created.append(new)
                choices.append(new)
            result.append((socket,material,*choices))
    except Exception:
        for m in created:
            paint.dispose(m)
        raise
    return result


def _refresh_trims(context, head, tail, branch):
    from . import finishes
    for item in context.scene.objects:
        if item.get(finishes.BASEBOARD) and _editable(item,context.scene):
            refs = finishes._wall_refs(item,context.scene)
            if head in refs and (item.get('wall_source') or 'SELECTED') == 'SELECTED':
                finishes._save_wall_refs(item,refs|{tail})
    return finishes.refresh_wall_baseboards(context,(head,tail)) + finishes.refresh_attached_baseboards(
        context, (branch,) if branch else ())


def divide_wall(context, objects):
    from . import finishes, room_paint, shower_area
    from .floor_regions import (apply_wall_division_bindings, plan_wall_division_bindings,
                                restore_wall_division_bindings)
    host,branch,cut = find_division(context,objects)
    head = host.obj
    if finishes.wall_trim_children(head):
        raise ValueError("Remove Wall Baseboards from the long wall before dividing it, then reapply to both halves.")
    if head.get(shower_area.WALL_DIVIDERS) or any(
            o.get(shower_area.AREA) and head in o.get(shower_area.SOURCE,{}).values()
            for o in context.scene.objects):
        raise ValueError("Remove the existing Wall Divider or Shower Area from the long wall before dividing it.")
    endpoint,outgoing,neighbors = _motion_dependencies(context,host)
    moved = _attachment_plan(context,host,endpoint,cut)
    floors = plan_wall_division_bindings(context,head,cut)
    right_angle = host.geo.get_input('Right Angle')
    previous_endpoint = endpoint.home_builder.connected_object
    head_matrix = host.matrix.copy()
    paint = _paint_plan(host,cut)
    tail = tail_endpoint = mesh = None
    restored = {}
    floor_attempted = False
    try:
        tail = head.copy()
        tail.name = f"{head.name} (Divided)"
        if "FZM_WALL_START_PEER" in tail:
            del tail["FZM_WALL_START_PEER"]
        mesh = head.data.copy()
        tail.data = mesh
        tail.constraints.clear()
        for name in {mod.name for mod in head.modifiers if mod.type == 'BOOLEAN'} - {
                n for names in moved.values() for n in names}:
            tail.modifiers.remove(tail.modifiers[name])
        collections = list(head.users_collection)
        for collection in collections:
            collection.objects.link(tail)
        tail.matrix_world = head_matrix @ Matrix.Translation((cut,0.,0.))
        tail_endpoint = endpoint.copy()
        tail_endpoint.name = 'obj_x'
        tail_endpoint.parent = tail
        for collection in endpoint.users_collection:
            collection.objects.link(tail_endpoint)
        tail_endpoint.animation_data.drivers[0].driver.variables[0].targets[0].id = tail
        tail_endpoint.home_builder.connected_object = outgoing
        rest = hb_types.GeoNodeWall(tail)
        if rest.obj_x != tail_endpoint:
            raise RuntimeError("The new wall endpoint was not created correctly.")
        rest.set_input('Length',host.length-cut)
        rest.set_input('Left Angle',0.)
        for socket,_,_,right in paint:
            rest.set_input(socket,right)
        rest.connect_to_wall(host.geo)
        host.geo.set_input('Length',cut)
        host.geo.set_input('Right Angle',0.)
        for _,con in neighbors:
            con.target = tail_endpoint
        context.view_layer.update()
        if any((actual-expected).length>5e-4 for actual,expected in (
                (tail.matrix_world.translation,(head_matrix @ Vector((cut,0.,0.)))),
                (tail_endpoint.matrix_world.translation,(head_matrix @ Vector((host.length,0.,0.)))))):
            raise RuntimeError("The existing wall connections would move an endpoint.")
        for child in moved:
            old_world = child.matrix_world.copy()
            restored[child] = (child.matrix_parent_inverse.copy(),child.matrix_basis.copy())
            child.parent = tail
            # Door/window prompts use local X relative to their owner's origin.
            child.matrix_parent_inverse.identity()
            child.matrix_world = old_world
        for socket,_,left,_ in paint:
            host.geo.set_input(socket,left)
        floor_attempted = True
        apply_wall_division_bindings(floors,head,tail)
        # No data-block deletion or change to existing modifier order before all
        # supported references and child transforms have been retargeted.
        for names in moved.values():
            for name in names:
                head.modifiers.remove(head.modifiers[name])
    except Exception:
        if floor_attempted:
            restore_wall_division_bindings(floors)
        for child,(inverse,basis) in restored.items():
            child.parent = head
            child.matrix_parent_inverse = inverse
            child.matrix_basis = basis
        for _,con in neighbors:
            con.target = endpoint
        endpoint.home_builder.connected_object = previous_endpoint
        host.geo.set_input('Length',host.length)
        host.geo.set_input('Right Angle',right_angle)
        for socket,source,_,_ in paint:
            host.geo.set_input(socket,source)
        if tail_endpoint:
            bpy.data.objects.remove(tail_endpoint,do_unlink=True)
        if tail:
            bpy.data.objects.remove(tail,do_unlink=True)
        if mesh and mesh.users==0:
            bpy.data.meshes.remove(mesh)
        for _,_,left,right in paint:
            room_paint.dispose(left)
            room_paint.dispose(right)
        raise
    for material in {source for _,source,_,_ in paint}:
        room_paint.dispose(material)
    context.view_layer.update()
    return tail,branch.obj,_refresh_trims(context,head,tail,branch.obj)


def _selected_walls(context):
    return [obj for obj in context.selected_objects if obj.get('IS_WALL_BP')]


class FZM_OT_divide_wall(bpy.types.Operator):
    bl_idname = 'fzm_builder.divide_wall'
    bl_label = 'Divide Wall'
    bl_description = "Split the receiving wall at a selected branch's T-junction, creating two editable walls"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and len(_selected_walls(context))==2

    def invoke(self,context,event):
        try:
            host,branch,cut = find_division(context,_selected_walls(context))
            self._prompt = f"Split {host.obj.name} where {branch.obj.name} meets it?"
        except (ValueError,RuntimeError) as error:
            self.report({'WARNING'},str(error))
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self,width=410)

    def draw(self,context):
        self.layout.label(text=self._prompt)
        self.layout.label(text="Wall Divider for tile limits is a separate tool.")

    def execute(self,context):
        try:
            tail,branch,warnings = divide_wall(context,_selected_walls(context))
        except (ValueError,RuntimeError,TypeError,AttributeError,KeyError) as error:
            self.report({'WARNING'},str(error))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        tail.select_set(True)
        context.view_layer.objects.active = tail
        self.report({'INFO'},f"Created {tail.name}. Select {branch.name} and one half for Wall Tiles.")
        for warning in warnings:
            self.report({'WARNING'},warning)
        return {'FINISHED'}
