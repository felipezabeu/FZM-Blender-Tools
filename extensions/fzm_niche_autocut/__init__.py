# SPDX-License-Identifier: GPL-3.0-or-later
"""FZM Shower Niche AutoCut: live, opt-in, non-destructive Boolean cuts."""
import itertools
import re
import uuid

import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = "fzm_shower_niche_root"
CUTTER = "fzm_shower_niche_cutter"
PART = "fzm_shower_niche_part"
ACTIVE = "fzm_niche_autocut_active"
KEY = "_fzm_niche_autocut_uuid"
BOUNDS = "_fzm_niche_autocut_uncut_bounds"
IGNORE = "fzm_niche_autocut_ignore"
PFX = "FZM Niche AutoCut ["
TAG = re.compile(r"^FZM Niche AutoCut \[([0-9a-f]{16})\](?:\.\d+)?$")
INTERVAL = .18
EPS = 0.000001
NARROW_MAX = 6000
MAX_LOOP_CHECK = 1_200_000
TRACKING = set()
DIRTY = False
BUSY = False
LAST = {}

def editable(o):
    return o.library is None and o.override_library is None and o.is_editable

def is_part(o):
    while o:
        if o.get(ROOT) or o.get(CUTTER) or o.get(PART):
            return True
        o = o.parent
    return False

def root_for(o):
    while o:
        if o.get(ROOT):
            return o
        o = o.parent

def owner(m):
    if m.type != 'BOOLEAN':
        return None
    match = TAG.fullmatch(m.name)
    if match and (m.object is None or m.object.get(CUTTER)):
        return match[1]

def cutter_for(root):
    return next((c for c in root.children_recursive if c.type=='MESH' and c.get(CUTTER)), None)

def ids(roots):
    seen=set()
    for root in sorted(roots,key=lambda o:o.name):
        key=root.get(KEY)
        if not isinstance(key,str) or not re.fullmatch(r"[0-9a-f]{16}",key) or key in seen:
            key=uuid.uuid4().hex[:16]
            root[KEY]=key
        seen.add(key)
        yield key,root

def bounds(ob, dg, eval_only=False):
    if eval_only:
        ev=ob.evaluated_get(dg)
        if ev.type!='MESH' or ev.data is None or not len(ev.data.polygons):
            return None
        box=ev.bound_box
    else:
        box=ob.bound_box
    if not box:
        return None
    lo=Vector(min(v[i] for v in box) for i in range(3))
    hi=Vector(max(v[i] for v in box) for i in range(3))
    return (lo,hi) if min(hi-lo)>EPS else None

def saved_bounds(o):
    z=o.get(BOUNDS)
    if z is not None and len(z)==6:
        return Vector(z[:3]),Vector(z[3:])

def union(a,b):
    if a is None: return b
    if b is None: return a
    return (Vector(min(a[0][i],b[0][i]) for i in range(3)),
            Vector(max(a[1][i],b[1][i]) for i in range(3)))

def world_box(box,mat):
    lo,hi=box
    center=mat@((lo+hi)*.5)
    basis=mat.to_3x3()
    h=(hi-lo)*.5
    edge=tuple(basis.col[i]*h[i] for i in range(3))
    rad=tuple(sum(abs(e[i]) for e in edge) for i in range(3))
    return center,edge,rad

def overlap(a,b,strict=True):
    d=b[0]-a[0]; e,f=a[1],b[1]
    pad=EPS if strict else -EPS
    if any(abs(d[i])>=a[2][i]+b[2][i]-pad for i in range(3)):
        return False
    # Separating axis test for transformed boxes, including rotated niches.
    axes=[s[i].cross(s[(i+1)%3]) for s in (e,f) for i in range(3)]
    axes.extend(x.cross(y) for x in e for y in f)
    for axis in axes:
        if axis.length_squared<1e-22: continue
        axis.normalize()
        if abs(d.dot(axis))>=sum(abs(axis.dot(x)) for x in (*e,*f))-pad:
            return False
    return True

CUBE_FACES=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
# Object local coordinate vertex order (product iterates Z, then Y, then X).
def corners(box,mat):
    lo,hi=box
    return [mat @ Vector((lo[0] if a==0 else hi[0],lo[1] if b==0 else hi[1],lo[2] if c==0 else hi[2]))
            for a,b,c in itertools.product((0,1),repeat=3)]

def contains(tree,p):
    step=1e-5
    votes=0
    for d in ((.875,.223,.438),(-.176,.831,.471),(.32,-.55,.77)):
        direction=Vector(d).normalized()
        origin=p.copy()
        n=0
        for _ in range(160):
            x,_normal,_index,_dist=tree.ray_cast(origin,direction)
            if x is None:break
            n+=1; origin=x+step*direction
        votes+=n%2
    return votes>=2

def solid_mesh(mesh):
    """Conservative edge-incidence check for the Boolean Exact input."""
    if len(mesh.loops)>MAX_LOOP_CHECK or len(mesh.polygons)<4 or not len(mesh.edges):
        return False
    indices=np.empty(len(mesh.loops),dtype=np.int32)
    mesh.loops.foreach_get('edge_index',indices)
    return bool(np.all(np.bincount(indices,minlength=len(mesh.edges))==2))

def geometry_for(ob,dg):
    ev=ob.evaluated_get(dg)
    mesh=ev.data
    if mesh is None or mesh.bl_rna.identifier!='Mesh' or not solid_mesh(mesh):
        return None
    if len(mesh.polygons)>NARROW_MAX:
        return mesh,None
    tree=BVHTree.FromObject(ob,dg)
    return (mesh,tree) if tree else None

def intersects(mesh,tree,o,w,cbox):
    if tree is None:
        # Bounded cost: exact Blender Boolean resolves the hit for dense solids.
        return True
    lo,hi=cbox
    t=o.matrix_world.inverted_safe()@w
    pts=corners(cbox,t)
    bvh=BVHTree.FromPolygons(pts,CUBE_FACES)
    if tree.overlap(bvh):
        return True
    if contains(tree,t@((lo+hi)*.5)):
        return True
    # Strict containment the other way, even when no polygon surfaces cross.
    ct=t.inverted_safe()
    for v in mesh.vertices:
        p=ct@v.co
        if all(lo[k]+EPS<p[k]<hi[k]-EPS for k in range(3)):
            return True
    return False

AREA_ORIG="_fzm_niche_uncut_shower_group"
AREA_NODES=('Store Named Attribute.011','Store Named Attribute.018','Store Named Attribute.025')

def area_modifier(o):
    if 'controles_revestimento' not in o or 'porcelanato_faces' not in o:
        return None
    for m in o.modifiers:
        if m.type!='NODES' or m.node_group is None:
            continue
        g=m.node_group
        if g.get(AREA_ORIG):
            return m
        if all(g.nodes.get(n) and g.nodes[n].bl_idname=='GeometryNodeStoreNamedAttribute'
               and g.nodes[n].inputs['Name'].default_value=='box_parede_metros' for n in AREA_NODES):
            return m
    return None

def area_cuts(m):
    g=m.node_group
    if not g.get(AREA_ORIG):
        return {}
    return {n.label.removeprefix("FZM Niche [").removesuffix("]"):n.inputs['Object'].default_value
            for n in g.nodes if n.bl_idname=='GeometryNodeObjectInfo'
            and n.label.startswith("FZM Niche [")}

def replace_group(m,g):
    attrs=dict(m.items())
    m.node_group=g
    # Switching to a variant whose interface was cloned preserves
    # modifier values, including material, independent dimensions and menus.
    for k,v in attrs.items():
        if k in m and m[k]!=v:
            m[k]=v

def reconcile_area(m,want):
    """Non-destructive live cuts before known wall UV/finish fields."""
    if area_cuts(m)==want:
        return 0,0
    previous=m.node_group
    base=previous.get(AREA_ORIG) or previous
    old_count=len(area_cuts(m))
    if not want:
        replace_group(m,base)
        if previous!=base and not previous.users:
            bpy.data.node_groups.remove(previous)
        return 0,old_count
    new=base.copy()
    new.name=base.name+" | AutoCut"
    new.use_fake_user=False
    new[AREA_ORIG]=base
    try:
        cutters=[]
        for key,cut in sorted(want.items()):
            node=new.nodes.new('GeometryNodeObjectInfo')
            node.label="FZM Niche ["+key+"]"
            node.transform_space='RELATIVE'
            node.inputs['Object'].default_value=cut
            node.inputs['As Instance'].default_value=False
            node.location=(2420,-5850-len(cutters)*195)
            cutters.append(node.outputs['Geometry'])
        for i,n in enumerate(AREA_NODES):
            anchor=new.nodes[n]
            target=anchor.inputs['Geometry']
            old_source=target.links[0].from_socket
            cut=new.nodes.new('GeometryNodeMeshBoolean')
            cut.label='FZM Niche • corte antes do revestimento'
            cut.operation='DIFFERENCE'
            cut.solver='EXACT'
            cut.inputs['Self Intersection'].default_value=True
            cut.inputs['Hole Tolerant'].default_value=True
            cut.location=(3000,-5820-i*260)
            new.links.new(old_source,cut.inputs['Mesh 1'])
            for source in cutters:
                new.links.new(source,cut.inputs['Mesh 2'])
            new.links.new(cut.outputs['Mesh'],target)
        replace_group(m,new)
    except Exception:
        if not new.users:
            bpy.data.node_groups.remove(new)
        raise
    if previous!=base and not previous.users:
        bpy.data.node_groups.remove(previous)
    return len(want),old_count

def live_scene(scene):
    return (any(o.get(ACTIVE) and o.get(ROOT) for o in scene.objects)
            or any(owner(m) or (m.type=='NODES' and m.node_group and m.node_group.get(AREA_ORIG))
                   for o in scene.objects if o.type=='MESH' for m in o.modifiers))

def reconcile(scene=None,view_layer=None):
    """One check in Object Mode; create/remove live modifiers only."""
    global BUSY
    scene=scene or bpy.context.scene
    view_layer=view_layer or bpy.context.view_layer
    if scene is None or view_layer is None or BUSY or bpy.context.mode!='OBJECT':
        return None
    BUSY=True
    try:
        # Ignore linked or read-only owners; stay in the current scene/layer.
        dg=bpy.context.evaluated_depsgraph_get()
        roots=[o for o in view_layer.objects if o.get(ROOT) and o.get(ACTIVE) and editable(o)]
        live={}
        for key,root in ids(roots):
            cut=cutter_for(root)
            if cut is None or view_layer.objects.get(cut.name) is None: continue
            b=bounds(cut,dg,eval_only=True)
            if b is None:continue
            w=cut.matrix_world.copy()
            live[key]=(cut,b,w,world_box(b,w))

        nadd=nremove=nskip=0
        for o in scene.objects:
            if o.type!='MESH' or not editable(o) or o.mode!='OBJECT':
                continue
            mods=[(owner(m),m) for m in o.modifiers if owner(m)]
            area=area_modifier(o)
            area_previous=area_cuts(area) if area else {}
            had_cuts=bool(mods or area_previous)
            if not live and not had_cuts:
                continue
            usable=(live and not is_part(o) and not o.get(IGNORE)
                    and view_layer.objects.get(o.name) is not None
                    and o.visible_get(view_layer=view_layer) and len(o.users_scene)==1
                    and (area is not None or 'controles_revestimento' not in o or 'porcelanato_faces' not in o)
                    and (area is None or any(area.get(k) for k in ('Socket_29','Socket_30','Socket_31'))))
            want={}
            if usable:
                local=bounds(o,dg,eval_only=True)
                if had_cuts:
                    # Preserve the pre-cut support: a hole (or total subtraction)
                    # must not make us remove its own modifier on the next tick.
                    local=union(local,saved_bounds(o) or bounds(o,dg))
                if local:
                    a=world_box(local,o.matrix_world)
                    hits=[(k,cut,b,w) for k,(cut,b,w,bb) in live.items() if overlap(a,bb)]
                    if hits:
                        # Existing pairs use the pre-cut support OBB, avoiding
                        # self-feedback when the Boolean erased the intersecting geometry.
                        present={**{k:m.object for k,m in mods},**area_previous}
                        source=None
                        checked=False
                        for k,cut,b,w in hits:
                            if present.get(k)==cut:
                                want[k]=cut
                                continue
                            if not checked:
                                source=geometry_for(o,dg)
                                checked=True
                            if source and intersects(source[0],source[1],o,w,b):
                                want[k]=cut
                            elif source is None:
                                nskip+=1
                        if want and (not had_cuts or saved_bounds(o) is None):
                            o[BOUNDS]=[*local[0],*local[1]]
            if area:
                adds,removes=reconcile_area(area,want)
                nadd+=adds; nremove+=removes
                want={}
            for k,m in mods:
                if want.get(k)!=m.object or k not in want:
                    o.modifiers.remove(m)
                    nremove+=1
                else:
                    # Never replace, alter or apply somebody else's Boolean.
                    del want[k]
            for k,cut in want.items():
                m=o.modifiers.new(name=PFX+k+"]",type='BOOLEAN')
                m.operation='DIFFERENCE'
                m.solver='EXACT'
                m.object=cut
                nadd+=1
            if BOUNDS in o and not ((area and area_cuts(area)) or any(owner(m) for m in o.modifiers)):
                del o[BOUNDS]

        if live or roots:
            TRACKING.add(scene.name)
        else:
            TRACKING.discard(scene.name)
        count=sum(int(bool(owner(m)))+(len(area_cuts(m)) if m.type=='NODES' and m.node_group and m.node_group.get(AREA_ORIG) else 0)
                  for o in scene.objects if o.type=='MESH' for m in o.modifiers)
        LAST[scene.name]=(count,nskip)
        return nadd,nremove,count,nskip
    finally:
        BUSY=False

def _tick():
    global DIRTY
    if DIRTY:
        if bpy.context.mode!='OBJECT':
            return .5
        DIRTY=False
        reconcile()
    return None

def request():
    global DIRTY
    DIRTY=True
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick,first_interval=INTERVAL)

@persistent
def changed(scene,dg):
    if BUSY or scene.name not in TRACKING or scene!=bpy.context.scene:
        return
    # Ignore updates from cameras/lights/materials when the niche is stationary.
    for upd in dg.updates:
        item=upd.id
        if isinstance(item,(bpy.types.Scene,bpy.types.Mesh,bpy.types.NodeTree,bpy.types.Collection)) or (
                isinstance(item,bpy.types.Object) and item.type=='MESH'):
            request()
            break

@persistent
def on_load(_):
    TRACKING.clear()
    LAST.clear()
    for scene in bpy.data.scenes:
        if live_scene(scene):TRACKING.add(scene.name)
    if bpy.context.scene and bpy.context.scene.name in TRACKING:
        request()

def matching_instance(o):
    if o is None or o.type != 'EMPTY' or o.instance_type != 'COLLECTION' or not o.instance_collection:
        return None
    objects=tuple(o.instance_collection.all_objects)
    roots=[x for x in objects if x.type=='MESH' and x.get(ROOT)]
    cutters=[x for x in objects if x.type=='MESH' and x.get(CUTTER)]
    if len(objects)==2 and len(roots)==len(cutters)==1:
        root,cut=roots[0],cutters[0]
        if root!=cut and root.parent is None and cut.parent==root:
            return root,cut
    return None

def local_container(context, o):
    if not editable(o) or len(o.users_scene)!=1 or context.scene.objects.get(o.name)!=o:
        raise ValueError('O nicho precisa ser uma cópia local, em uma única cena.')
    containers=set(o.users_collection)
    layers=[context.view_layer.layer_collection]
    while layers:
        layer=layers.pop(0)
        if layer.exclude or not layer.is_visible:
            continue
        collection=layer.collection
        if collection in containers and editable(collection):
            return collection
        layers.extend(layer.children)
    raise ValueError('Mova o nicho para uma coleção local e visível na cena.')

def clear_status(o):
    for k in (ACTIVE,KEY,BOUNDS,IGNORE):
        if k in o:
            del o[k]

def clone_cutter(source, old_root, new_root, collection):
    # Copy the native driver data, remap only its authored targets. These are
    # simple single-property AVERAGE drivers: no script execution is needed.
    child=source.copy()
    try:
        child.parent=new_root
        child.matrix_parent_inverse=source.matrix_parent_inverse.copy()
        child.matrix_basis=source.matrix_basis.copy()
        nrebound=0
        for fcurve in child.animation_data.drivers if child.animation_data else ():
            driver=fcurve.driver
            if driver.type!='AVERAGE' or len(driver.variables)!=1 or driver.variables[0].type!='SINGLE_PROP':
                raise ValueError('O cortador não usa os controles nativos esperados para o nicho.')
            target=driver.variables[0].targets[0]
            if target.id!=old_root:
                raise ValueError('O cortador selecionado não pertence a esse modelo de nicho.')
            try:
                new_root.path_resolve(target.data_path)
            except ValueError as exc:
                raise ValueError('Os controles não correspondem. Use o arquivo original da mesma versão.') from exc
            target.id=new_root
            nrebound+=1
        if not nrebound:
            raise ValueError('O cortador não inclui os controles de dimensão do nicho.')
        clear_status(child)
        child.hide_render=True
        child.display_type='WIRE'
        collection.objects.link(child)
        return child
    except Exception:
        bpy.data.objects.remove(child,do_unlink=True)
        raise

def activate_obj(context,o):
    for selected in context.selected_objects:
        selected.select_set(False,view_layer=context.view_layer)
    o.hide_set(False,view_layer=context.view_layer)
    o.select_set(True,view_layer=context.view_layer)
    context.view_layer.objects.active=o

class FZMNC_OT_realize(bpy.types.Operator):
    bl_idname='fzm_niche_cut.realize'
    bl_label='Tornar nicho editável'
    bl_description='Converte esta instância do Shower Niche em um nicho com modificadores e cortador próprios'
    bl_options={'REGISTER','UNDO'}
    start_cut: bpy.props.BoolProperty(name='Ligar recorte automático',default=False)

    @classmethod
    def poll(cls,c):
        return c.mode=='OBJECT' and matching_instance(c.active_object) is not None

    def execute(self,c):
        pivot=c.active_object
        source=pivot.instance_collection
        ref,ref_cut=matching_instance(pivot)
        try:
            coll=local_container(c,pivot)
        except ValueError as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        root=ref.copy()
        try:
            # Keep the original empty as an inert placement anchor. This
            # retains the complete instance matrix, even composed shear from
            # a rotated child under a non-uniformly scaled parent. Only this
            # one instance is affected, not the template or its siblings.
            root.parent=pivot
            root.matrix_parent_inverse=Matrix.Translation(-Vector(source.instance_offset))
            root.matrix_basis=ref.matrix_basis.copy()
            clear_status(root)
            coll.objects.link(root)
            child=clone_cutter(ref_cut,ref,root,coll)
        except (ValueError,RuntimeError,TypeError) as exc:
            bpy.data.objects.remove(root,do_unlink=True)
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        pivot.instance_type='NONE'
        pivot.instance_collection=None
        pivot.hide_set(True,view_layer=c.view_layer)
        c.view_layer.update()
        activate_obj(c,root)
        if self.start_cut:
            root[ACTIVE]=True
            result=reconcile(c.scene,c.view_layer)
            self.report({'INFO'},f'Nicho editável: {result[2]} corte(s) automáticos nesta cena.')
        else:
            self.report({'INFO'},'Nicho editável. Abra Modifiers ou ligue o recorte automático.')
        return {'FINISHED'}

class FZMNC_OT_recover(Operator, ImportHelper):
    bl_idname='fzm_niche_cut.recover'
    bl_label='Buscar o cortador no arquivo do nicho'
    bl_description='Recupera o cortador que falta sem mover ou substituir o nicho visível'
    bl_options={'REGISTER','UNDO'}

    filename_ext='.blend'
    filter_glob: bpy.props.StringProperty(default='*.blend',options={'HIDDEN'})
    root_name: bpy.props.StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls,c):
        o=root_for(c.active_object)
        return c.mode=='OBJECT' and o is not None and editable(o) and cutter_for(o) is None

    def invoke(self,c,event):
        self.root_name=root_for(c.active_object).name
        return ImportHelper.invoke(self,c,event)

    def execute(self,c):
        root=c.scene.objects.get(self.root_name) if self.root_name else root_for(c.active_object)
        if root is None or not root.get(ROOT) or cutter_for(root) is not None:
            self.report({'WARNING'},'Selecione o Shower Niche que está sem cortador.')
            return {'CANCELLED'}
        try:
            coll=local_container(c,root)
        except ValueError as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        before_objects={o.as_pointer() for o in bpy.data.objects}
        before_cols={o.as_pointer() for o in bpy.data.collections}
        tmp=None
        imported=()
        try:
            with bpy.data.libraries.load(self.filepath,link=False) as (src,dst):
                if 'Shower Niche' not in src.collections:
                    raise ValueError('Escolha o arquivo 29_Shower_Niche_Parametrico.blend.')
                dst.collections=['Shower Niche']
            tmp=dst.collections[0]
            if tmp is None:
                raise ValueError('Não foi possível ler a coleção Shower Niche.')
            imported=tuple(tmp.all_objects)
            roots=[o for o in imported if o.get(ROOT)]
            cutters=[o for o in imported if o.get(CUTTER)]
            if len(imported)!=2 or len(roots)!=1 or len(cutters)!=1 or cutters[0].parent!=roots[0]:
                raise ValueError('Use uma cópia original da biblioteca, com o nicho e seu cortador.')
            clone_cutter(cutters[0],roots[0],root,coll)
        except (OSError,ValueError,RuntimeError,TypeError) as exc:
            self.report({'WARNING'},str(exc))
            return {'CANCELLED'}
        finally:
            # Discard only temporary IDs freshly loaded by this operator,
            # never pre-existing project instances or any other scene objects.
            if tmp is not None and tmp.as_pointer() not in before_cols:
                bpy.data.collections.remove(tmp,do_unlink=True)
                for obj in imported:
                    if obj.as_pointer() not in before_objects and not obj.users_collection:
                        bpy.data.objects.remove(obj,do_unlink=True)
        c.view_layer.update()
        activate_obj(c,root)
        if root.get(ACTIVE):
            reconcile(c.scene,c.view_layer)
        self.report({'INFO'},'Cortador recuperado. A posição do nicho foi mantida.')
        return {'FINISHED'}

class FZMNC_OT_toggle(bpy.types.Operator):
    bl_idname='fzm_niche_cut.toggle'
    bl_label='Alternar recorte automático'
    bl_description='Liga ou desliga apenas os Booleans gerenciados deste nicho, sem aplicar nada na malha'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,c):
        o=root_for(c.active_object)
        return c.mode=='OBJECT' and o is not None and editable(o)

    def execute(self,c):
        o=root_for(c.active_object)
        if not o.get(ACTIVE) and cutter_for(o) is None:
            self.report({'WARNING'},'Falta o cortador: use Buscar o cortador no arquivo do nicho, ou Append → Collection → Shower Niche.')
            return {'CANCELLED'}
        o[ACTIVE]=not bool(o.get(ACTIVE))
        result=reconcile(c.scene,c.view_layer)
        if o.get(ACTIVE):
            self.report({'INFO'},f'Recorte ligado. {result[2]} corte(s) automáticos nesta cena.')
        else:
            self.report({'INFO'},'Recorte automático desligado neste nicho.')
        return {'FINISHED'}

class FZMNC_OT_refresh(bpy.types.Operator):
    bl_idname='fzm_niche_cut.refresh'
    bl_label='Atualizar cortes'
    bl_description='Verifica os cruzamentos de novo no View Layer atual'
    bl_options={'REGISTER','UNDO'}

    def execute(self,c):
        result=reconcile(c.scene,c.view_layer)
        if result is None:return {'CANCELLED'}
        self.report({'INFO'},f'{result[2]} corte(s) ativos. {result[3]} candidato(s) não sólido(s) ignorados.')
        return {'FINISHED'}

class FZMNC_OT_ignore(bpy.types.Operator):
    bl_idname='fzm_niche_cut.ignore'
    bl_label='Proteger/Desproteger esta malha'
    bl_description='Exclui ou reinclui esta malha nos cortes automáticos; não muda os Booleans manuais'
    bl_options={'REGISTER','UNDO'}

    @classmethod
    def poll(cls,c):
        return c.mode=='OBJECT' and c.object and c.object.type=='MESH' and editable(c.object) and not is_part(c.object)

    def execute(self,c):
        o=c.object
        if o.get(IGNORE):del o[IGNORE]
        else:o[IGNORE]=True
        reconcile(c.scene,c.view_layer)
        return {'FINISHED'}

class FZMNC_PT_panel(bpy.types.Panel):
    bl_label='Recorte do Shower Niche'
    bl_idname='FZMNC_PT_panel'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='FZM Niche'

    def draw(self,c):
        ui=self.layout
        o=root_for(c.active_object)
        if matching_instance(c.active_object):
            ui.label(text='Este nicho é uma instância.',icon='INFO')
            ui.operator('fzm_niche_cut.realize',text='Tornar editável e ligar recorte',icon='MOD_BOOLEAN').start_cut=True
            ui.operator('fzm_niche_cut.realize',text='Só tornar nicho editável').start_cut=False
        elif o is not None:
            active=bool(o.get(ACTIVE))
            if cutter_for(o) is None:
                ui.label(text='Falta o cortador neste nicho.',icon='ERROR')
                ui.operator('fzm_niche_cut.recover',icon='FILE_BLEND')
            if active or cutter_for(o) is not None:
                ui.operator('fzm_niche_cut.toggle',text='Desligar recorte automático' if active else 'Ligar recorte automático',
                            icon='CHECKBOX_HLT' if active else 'CHECKBOX_DEHLT')
        else:
            ui.label(text='Selecione o objeto Shower Niche.')
            if FZMNC_OT_ignore.poll(c):
                ui.operator('fzm_niche_cut.ignore',text='Permitir cortes nesta malha' if c.object.get(IGNORE) else 'Proteger esta malha')
        ui.operator('fzm_niche_cut.refresh',icon='FILE_REFRESH')
        count,skipped=LAST.get(c.scene.name,(0,0))
        ui.label(text=f'{count} corte(s) na cena.')
        if skipped:ui.label(text='Há candidatos sem malha sólida.',icon='INFO')

CLASSES=(FZMNC_OT_realize,FZMNC_OT_recover,FZMNC_OT_toggle,FZMNC_OT_refresh,FZMNC_OT_ignore,FZMNC_PT_panel)
HOOKS=((bpy.app.handlers.depsgraph_update_post,changed),(bpy.app.handlers.load_post,on_load),
       (bpy.app.handlers.undo_post,on_load),(bpy.app.handlers.redo_post,on_load))

def _initial_scan():
    # Enabling/installing the extension runs register() with Blender's
    # restricted context. Only access scene data after registration finishes.
    if not hasattr(bpy.data,'scenes') or not hasattr(bpy.context,'scene'):
        return .15
    on_load(None)
    return None

def register():
    for c in CLASSES:bpy.utils.register_class(c)
    for h,f in HOOKS:
        if f not in h:h.append(f)
    if hasattr(bpy.data,'scenes') and hasattr(bpy.context,'scene'):
        on_load(None)
    elif not bpy.app.timers.is_registered(_initial_scan):
        bpy.app.timers.register(_initial_scan,first_interval=.10)

def unregister():
    global DIRTY
    for h,f in HOOKS:
        if f in h:h.remove(f)
    for fn in (_tick,_initial_scan):
        if bpy.app.timers.is_registered(fn):bpy.app.timers.unregister(fn)
    DIRTY=False
    TRACKING.clear()
    LAST.clear()
    for c in reversed(CLASSES):bpy.utils.unregister_class(c)
