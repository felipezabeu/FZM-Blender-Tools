"""A linked, editable tile finish over 2 or 3 existing FZM Builder walls."""
from dataclasses import asdict
from math import isfinite
from pathlib import Path

import bpy
from mathutils import Vector

from .. import hb_types
from .floor_finish import create_material
from .tile_shader import PATTERNS, TileSpec, base_material, dispose_if_unused, tile_material, validate

AREA = 'FZM_SHOWER_AREA'
PART = 'FZM_SHOWER_TILE_FACE'
SOURCE = 'FZM_SHOWER_WALLS'
OPTIONS = 'FZM_SHOWER_OPTIONS'
WALL_DIVIDERS = 'FZM_WALL_FINISH_DIVIDERS'
SPAN_START = 'fzm_shower_span_start_m'
SPAN_END = 'fzm_shower_span_end_m'
JOIN = .012
SEPARATION = .0015
PLANAR = .0005
EPS = 1e-7


def controller_for(obj):
    if obj and obj.get(PART):
        obj = obj.parent
    return obj if obj and obj.get(AREA) else None


def _wall_info(obj):
    geo = hb_types.GeoNodeWall(obj)
    if not (obj.get('IS_WALL_BP') and geo.has_modifier()):
        raise ValueError("Select parametric Builder walls.")
    mat = obj.matrix_world
    start = mat.translation.copy()
    end = mat @ Vector((geo.get_input('Length'), 0, 0))
    width = mat @ Vector((0, geo.get_input('Thickness'), 0)) - start
    world_height = mat @ Vector((0, 0, geo.get_input('Height'))) - start
    if (abs(end.z - start.z) > PLANAR or abs(width.z) > PLANAR
            or world_height.xy.length > PLANAR or world_height.z <= .05
            or (end-start).xy.length <= .05):
        raise ValueError("Use upright walls of positive height and length.")
    return obj, start, end, width.xy.copy(), world_height.z


def _ordered_path(objects, order=None):
    if len(objects) not in (2, 3):
        raise ValueError("Select 2 or 3 adjoining Builder walls (one L or U).")
    walls = [_wall_info(o) for o in objects]
    level = walls[0][1].z
    if any(abs(w[1].z - level) > PLANAR for w in walls):
        raise ValueError("The walls must be on one level.")
    points, links, edges = [], [], {}
    def vertex(p):
        for i, previous in enumerate(points):
            if (previous - p).length <= JOIN:
                return i
        points.append(p.copy())
        links.append([])
        return len(points)-1

    for row in walls:
        _, a, b, _, _ = row
        i, j = vertex(a), vertex(b)
        if i == j or (i,j) in edges or (j,i) in edges:
            raise ValueError("The selected walls overlap or collapse.")
        links[i].append(j)
        links[j].append(i)
        edges[i,j] = row
    ends = [i for i, connected in enumerate(links) if len(connected) == 1]
    if len(ends) != 2 or len(points) != len(objects) + 1 or any(len(ls) > 2 for ls in links):
        raise ValueError("The walls must join end-to-end along one open path.")
    def make_path(start):
        path, prev, cur = [], None, start
        while True:
            nxt = next((n for n in links[cur] if n != prev), None)
            if nxt is None:
                return path
            row = edges.get((cur,nxt)) or edges[nxt,cur]
            _, a, b, _, _ = row
            if (cur,nxt) not in edges:
                a,b = b,a
            path.append((row, a, b))
            prev,cur = cur,nxt
    start = min(ends, key=lambda i: tuple(round(v,4) for v in points[i]))
    path = make_path(start)
    if order and [row[0] for row, _, _ in path] == list(reversed(order)):
        path = make_path(next(i for i in ends if i != start))
    if len(path) != len(objects):
        raise ValueError("The selected walls do not form one continuous path.")
    return path, level


def _finish_lines(path):
    axes = [(b-a).xy.normalized() for _,a,b in path]
    turns = [a.cross(b) for a,b in zip(axes, axes[1:])]
    if (not turns or any(abs(t) < .25 for t in turns)
            or any(turns[0] * t < 0 for t in turns[1:])):
        raise ValueError("Choose an L or U with consistent, nonparallel interior corners.")
    sign = 1 if turns[0] > 0 else -1
    lines=[]
    for direction,(row,a,b) in zip(axes,path):
        inward = Vector((-direction.y,direction.x))*sign
        plane = a.xy + inward * max(0., row[3].dot(inward))
        actual_offset = plane-a.xy
        lines.append((row, plane, b.xy+actual_offset, direction, inward))
    def shifted(line):
        return line[1] + SEPARATION * line[4]
    corners = [shifted(lines[0])]
    for prev, row in zip(lines,lines[1:]):
        a,b=shifted(prev),shifted(row)
        d,e=prev[3],row[3]
        corners.append(a + d * (b-a).cross(e)/d.cross(e))
    corners.append(lines[-1][2] + SEPARATION * lines[-1][4])
    if any((b-a).dot(line[3]) < .04 for a,b,line in zip(corners, corners[1:], lines)):
        raise ValueError("Wall thickness or angle leaves no usable space at a corner.")
    return lines, corners


def wall_span(line, a, b):
    """The tiled span in finish-path coordinates, measured from the original miter.

    Divider distances are from the actual wall's object origin along its own
    world-length axis. The shower path sometimes traverses that wall in reverse.
    An unbounded end uses the original corner, including its miter.
    """
    row, _, _, direction, _ = line
    obj, origin, end, _, _ = row
    length = (b-a).dot(direction)
    start, stop = 0., length
    limits = obj.get(WALL_DIVIDERS)
    if limits is None:
        return start, stop
    along = (end-origin).xy.normalized()
    for i, offset in enumerate(limits):
        if offset < 0.:
            continue
        station = (origin.xy + along*offset - a).dot(direction)
        if (along.dot(direction) > 0.) == (i == 0):
            start = max(0., station)
        else:
            stop = min(length, station)
    if stop-start < .04:
        raise ValueError(f"Wall Divider leaves less than 40 mm of tile on {obj.name}. "
                         "Adjust or clear its finish boundaries.")
    return start, stop


def _cut(poly, axis, line, keep_greater):
    """Clip a convex polygon to one axis, in the wall's course coordinates."""
    if not poly:
        return []
    res=[]
    def ins(p):
        return p[axis] >= line-EPS if keep_greater else p[axis] <= line+EPS
    a=poly[-1]; valid=ins(a)
    for b in poly:
        other=ins(b)
        if other != valid and abs(b[axis]-a[axis]) > EPS:
            t=max(0.,min(1.,(line-a[axis])/(b[axis]-a[axis])))
            cut=a.lerp(b,t);cut[axis]=line
            res.append(cut)
        if other:
            res.append(b)
        a,valid=b,other
    return res


def _rect(poly, start, end, bottom, top):
    for axis, line, keep in ((0,start,True),(0,end,False),(1,bottom,True),(1,top,False)):
        poly=_cut(poly,axis,line,keep)
    result=[]
    for p in poly:
        if not result or (result[-1]-p).length > EPS:
            result.append(p)
    if len(result)>1 and (result[-1]-result[0]).length <= EPS:
        result.pop()
    return result


def _sample_wall_face(obj, plane, a, direction, inward, level, bottom, height, phase, span, depsgraph):
    host = obj.evaluated_get(depsgraph)
    mesh = host.to_mesh()
    polys=[]
    try:
        mesh.calc_loop_triangles()
        normal_mat = host.matrix_world.to_3x3().inverted().transposed()
        world = [host.matrix_world @ v.co for v in mesh.vertices]
        for tri in mesh.loop_triangles:
            normal = (normal_mat @ tri.normal).normalized()
            if normal.xy.dot(inward) < .95:
                continue
            verts = [world[i] for i in tri.vertices]
            if any(abs((v.xy-plane).dot(inward)) > PLANAR for v in verts):
                continue
            points = _rect([Vector(((v.xy-a).dot(direction),v.z-level)) for v in verts],
                           *span, bottom, bottom+height)
            if len(points)<3:
                continue
            area = sum(s.cross(t) for s,t in zip(points,points[1:]+points[:1]))
            desired = Vector((direction.y,-direction.x)).dot(inward)
            if abs(area) < EPS:
                continue
            if area*desired<0:
                points.reverse()
            polys.append(points)
    finally:
        host.to_mesh_clear()
    if not polys:
        raise ValueError(f"No usable interior face found on {obj.name}; check the join and lining heights.")
    # UVs use distance along the finished corner-to-corner chain, not each
    # wall's object-local origin. Reversed host walls share phase too.
    vertices, faces, uv = [], [], []
    for poly in polys:
        ids=[]
        for p in poly:
            xy=a+p.x*direction
            ids.append(len(vertices))
            vertices.append((xy.x,xy.y,level+p.y))
            uv.append((phase+p.x,p.y))
        faces.append(ids)
    return vertices, faces, uv


def panel_data(context, objects, heights, bottom, order=None):
    if not all(isfinite(h) and h >= .05 for h in heights) or not isfinite(bottom) or bottom < 0:
        raise ValueError("Lining heights must be positive and start above the wall base.")
    context.view_layer.update()
    path, level = _ordered_path(objects, order)
    lines,corners = _finish_lines(path)
    dg=context.evaluated_depsgraph_get()
    phase=0.
    result=[]
    for i,(line,a,b) in enumerate(zip(lines,corners,corners[1:])):
        row,plane,_,d,n = line
        wall,_,_,_,available=row
        maximum=min(heights[i],available-bottom)
        if maximum < .05:
            raise ValueError(f"No lining height remains on {wall.name}.")
        length = (b-a).dot(d)
        span = wall_span(line, a, b)
        vertices,faces,uv = _sample_wall_face(wall,plane,a,d,n,level,bottom,maximum,phase,span,dg)
        result.append((wall,phase,length,vertices,faces,uv,span))
        # Use the uncropped length so the grout on other faces stays put.
        phase += length
    return result, (*corners[0],level)


def _base_finish(name, color, filepath, previous=None):
    if not filepath:
        material=create_material(dict(name=name,color=color))
    else:
        p=Path(bpy.path.abspath(filepath))
        if p.is_file():
            material=create_material(dict(name=name,color=color,image=str(p)))
        elif previous and previous.get('fzm_shower_texture_source')==filepath and any(
            n.type=='TEX_IMAGE' and n.image and n.image.packed_file for n in previous.node_tree.nodes
        ):
            # A saved packed image still works after the local file is moved.
            return previous
        else:
            raise ValueError("Choose a valid local image of one tile face.")
    material.name="FZM Shower Tile Base"
    material['fzm_shower_texture_source']=filepath
    return material


def _make_panel(name, position, data, material):
    wall,phase,length,vertices,faces,uv,span=data
    mesh=bpy.data.meshes.new(name)
    try:
        mesh.from_pydata([tuple(Vector(p)-Vector(position)) for p in vertices],[],faces)
        mesh.update()
        uv_layer=mesh.uv_layers.new(name='UVMap')
        for loop in mesh.loops:
            uv_layer.data[loop.index].uv=uv[loop.vertex_index]
        mesh.materials.append(material)
        obj=bpy.data.objects.new(name,mesh)
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
    obj[PART]=True
    obj['fzm_shower_phase_m']=phase
    obj['fzm_shower_length_m']=length
    obj['fzm_shower_wall']=wall
    obj[SPAN_START], obj[SPAN_END] = span
    return obj


def remove_panel(panel):
    mesh=panel.data
    material=mesh.materials[0] if mesh.materials else None
    # Meshes are owned by the controller. Preserve any user-created children,
    # in their same world positions, instead of deleting their subtree.
    for child in list(panel.children):
        pose=child.matrix_world.copy()
        child.parent=None
        child.matrix_world=pose
    bpy.data.objects.remove(panel,do_unlink=True)
    if mesh.users==0:
        bpy.data.meshes.remove(mesh)
    dispose_if_unused(material)


def rebuild_panels(context, controller):
    """Re-evaluate the changed wall cuts without touching saved finishes/options."""
    objects = FZM_OT_shower_area.targets(context, controller)
    options = controller[OPTIONS]
    old = [o for o in controller.children if o.get(PART)]
    materials = {o['fzm_shower_wall']: o.data.materials[0] for o in old}
    panels, position = panel_data(context, objects, options['heights'],
                                  options['bottom'], order=objects)
    collection = controller.users_collection[0] if controller.users_collection else context.collection
    transform = controller.matrix_world.inverted()
    drafts = []
    try:
        for i, panel_data_row in enumerate(panels):
            panel = _make_panel(f'Shower Tile Face {i + 1}', position, panel_data_row,
                                materials[panel_data_row[0]])
            drafts.append(panel)
            for vertex in panel.data.vertices:
                vertex.co = transform @ (vertex.co + Vector(position))
            collection.objects.link(panel)
            panel.parent = controller
    except Exception:
        for panel in drafts:
            remove_panel(panel)
        raise
    # Divider/fixture refresh is an in-place update for the user. Preserve
    # any explicitly parented extras at the same world poses.
    by_wall = {p['fzm_shower_wall']: p for p in drafts}
    context.view_layer.update()
    for panel in old:
        replacement = by_wall.get(panel['fzm_shower_wall'])
        for child in list(panel.children):
            if replacement:
                pose = child.matrix_world.copy()
                child.parent = replacement
                child.matrix_world = pose
        remove_panel(panel)
    return by_wall


def remove_controller(context, controller):
    from .shower_fixtures import fixtures_for_area, remove_fixture
    for fixture in fixtures_for_area(context, controller):
        remove_fixture(context, fixture, refresh=False)
    for child in list(controller.children):
        if child.get(PART):
            remove_panel(child)
        else:
            pose=child.matrix_world.copy()
            child.parent=None
            child.matrix_world=pose
    bpy.data.objects.remove(controller,do_unlink=True)


def create_or_update(context, objects, heights, bottom, spec, color, filepath, existing=None):
    validate(spec)
    selected = set(objects)
    for obj in context.scene.objects:
        if obj != existing and obj.get(AREA) and selected.intersection(obj.get(SOURCE, {}).values()):
            raise ValueError("A selected wall already belongs to a Shower Area. Select its tile face to edit.")
    # Evaluate all hosts and validate geometry before touching existing panels.
    panels, position=panel_data(context,objects,heights,bottom,order=objects if existing else None)
    previous=next((o.data.materials[0] for o in existing.children
                   if o.get(PART) and o.data.materials),None) if existing else None
    source=_base_finish('Shower tile',color,filepath,base_material(previous))
    material_name = None
    drafts = []
    controller = existing
    try:
        material = tile_material(source, spec, one_image_per_tile=bool(filepath))
        material_name = material.name
        for i, data in enumerate(panels):
            drafts.append(_make_panel(f'Shower Tile Face {i+1}', position, data, material))
        if controller is None:
            controller=bpy.data.objects.new('Shower Area',None)
            controller.empty_display_type='PLAIN_AXES'
            controller.empty_display_size=.17
            controller[AREA]=True
            context.collection.objects.link(controller)
        old=[o for o in controller.children if o.get(PART)]
        # The assembly is wall-linked. Refresh re-fits to current wall geometry.
        # Preserve transform to avoid moving user additions made under the
        # controller, and update panel vertex positions into that local frame.
        if existing:
            transfer=controller.matrix_world.inverted()
            for part in drafts:
                for vert in part.data.vertices:
                    vert.co=transfer@(vert.co+Vector(position))
        else:
            controller.location=position
        collection=controller.users_collection[0] if controller.users_collection else context.collection
        for panel in drafts:
            collection.objects.link(panel)
            panel.parent=controller
        from .shower_fixtures import sync_fixture_finish
        sync_fixture_finish(context, controller, drafts, spec)
        controller[SOURCE]={str(i):row[0] for i,row in enumerate(panels)}
        controller[OPTIONS]={'tile':asdict(spec),'heights':list(heights),'bottom':bottom,
                             'tile_color':tuple(color),'filepath':filepath}
        for panel in old:
            remove_panel(panel)
    except Exception:
        for panel in drafts:
            remove_panel(panel)
        if controller and existing is None:
            bpy.data.objects.remove(controller,do_unlink=True)
        if material_name:
            dispose_if_unused(bpy.data.materials.get(material_name))
        if source.users==0 and not source.use_fake_user:
            bpy.data.materials.remove(source)
        raise
    return controller


class FZM_OT_shower_area(bpy.types.Operator):
    bl_idname='fzm_builder.shower_area'
    bl_label='Shower Area'
    bl_description='Tile 2 or 3 connected Builder walls, preserving joints at corners and existing cutouts'
    bl_options={'UNDO'}

    remove: bpy.props.BoolProperty(name='Remove This Shower Area')
    height_1: bpy.props.FloatProperty(name='Wall 1 Lining Height',unit='LENGTH',default=2.15,min=.05,max=10.)
    height_2: bpy.props.FloatProperty(name='Wall 2 Lining Height',unit='LENGTH',default=2.15,min=.05,max=10.)
    height_3: bpy.props.FloatProperty(name='Wall 3 Lining Height',unit='LENGTH',default=2.15,min=.05,max=10.)
    bottom: bpy.props.FloatProperty(name='Start Above Wall Base',unit='LENGTH',default=0.,min=0.,max=10.)
    tile_width: bpy.props.FloatProperty(name='Tile Width',unit='LENGTH',default=.6096,min=.01,max=10.)
    tile_height: bpy.props.FloatProperty(name='Tile Height',unit='LENGTH',default=.3048,min=.01,max=10.)
    grout: bpy.props.FloatProperty(name='Grout Width',unit='LENGTH',default=.003,min=0.,max=.10)
    pattern: bpy.props.EnumProperty(name='Tile Layout',items=PATTERNS,default='STACK')
    angle: bpy.props.FloatProperty(name='Tile Rotation',unit='ROTATION',subtype='ANGLE')
    offset_u: bpy.props.FloatProperty(name='Shift Along Walls',unit='LENGTH')
    offset_v: bpy.props.FloatProperty(name='Shift Upward',unit='LENGTH')
    grout_color: bpy.props.FloatVectorProperty(name='Grout Color',size=4,subtype='COLOR',
        default=(.24,.23,.21,1.),min=0.,max=1.)
    tile_color: bpy.props.FloatVectorProperty(name='Tile Color',size=4,subtype='COLOR',
        default=(.72,.70,.66,1.),min=0.,max=1.)
    filepath: bpy.props.StringProperty(name='Tile-Face Photo (optional)',subtype='FILE_PATH')

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and (controller_for(context.active_object) is not None
            or 2 <= sum(bool(o.get('IS_WALL_BP')) for o in context.selected_objects) <= 3)

    @staticmethod
    def targets(context,controller):
        if controller:
            stored=controller.get(SOURCE,{})
            walls=[stored.get(str(i)) for i in range(len(stored))]
            if any(not w or w.name not in context.scene.objects for w in walls):
                raise ValueError("A linked wall is missing. Remove the area, then select another wall group.")
            return walls
        return [o for o in context.selected_objects if o.get('IS_WALL_BP')]

    def invoke(self,context,event):
        controller=controller_for(context.active_object)
        self.remove=False
        if controller:
            opt=controller[OPTIONS]
            self.height_1,self.height_2,self.height_3=opt['heights']
            self.bottom,self.filepath,self.tile_color=opt['bottom'],opt['filepath'],opt['tile_color']
            spec=opt['tile']
            self.tile_width,self.tile_height=spec['width'],spec['height']
            self.grout,self.pattern,self.angle=spec['grout'],spec['pattern'],spec['angle']
            self.offset_u,self.offset_v,self.grout_color=spec['offset_u'],spec['offset_v'],spec['color']
        return context.window_manager.invoke_props_dialog(self,width=440)

    def draw(self,context):
        controller=controller_for(context.active_object)
        layout=self.layout
        if controller:
            layout.prop(self,'remove')
        if self.remove:
            return
        if controller:
            layout.label(text='Select a tile face for Add Niche or Add Bench.')
        try:
            walls=self.targets(context,controller)
            path,_=_ordered_path(walls,walls if controller else None)
            n=len(path)
        except ValueError as err:
            path,n=[],0
            layout.label(text=str(err),icon='ERROR')
        for i,(row,_,_) in enumerate(path):
            layout.label(text=f'Wall {i+1}: {row[0].name}')
            layout.prop(self,f'height_{i+1}')
        layout.prop(self,'bottom')
        col=layout.column(align=True)
        for name in ('pattern','tile_width','tile_height','grout','angle','offset_u','offset_v','grout_color','tile_color','filepath'):
            col.prop(self,name)
        layout.label(text='Joints follow the continuous inner wall path.')
        layout.label(text='Use Wall Divider on one wall or tile face to limit its width.')
        layout.label(text='View in Material Preview or Rendered mode.')

    def execute(self,context):
        controller=controller_for(context.active_object)
        if self.remove and controller:
            remove_controller(context, controller)
            return {'FINISHED'}
        if self.remove:
            return {'CANCELLED'}
        try:
            walls=self.targets(context,controller)
            spec=TileSpec(self.pattern,self.tile_width,self.tile_height,self.grout,self.angle,
                          self.offset_u,self.offset_v,tuple(self.grout_color))
            controller=create_or_update(context,walls,(self.height_1,self.height_2,self.height_3),
                self.bottom,spec,tuple(self.tile_color),self.filepath,controller)
        except (ValueError, RuntimeError, OSError) as err:
            self.report({'WARNING'},str(err))
            return {'CANCELLED'}
        for obj in context.selected_objects:
            obj.select_set(False)
        controller.select_set(True)
        context.view_layer.objects.active=controller
        return {'FINISHED'}
