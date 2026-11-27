"""Installed extension integration with a native packaged Shower Area asset."""
from importlib import import_module
from math import pi,isclose
from pathlib import Path
import bpy,sys,tempfile
from mathutils import Vector
from mathutils.bvhtree import BVHTree
C=bpy.context
P=Path(__file__).resolve().parent
package=next(x for x in C.preferences.addons.keys() if x.endswith('.fzm_builder'))
hb=import_module(package+'.hb_types')
host=import_module(package+'.operators.shower_niche_host')
F=bpy.ops.fzm_builder
IN=.0254
def wall(name,x,y,angle,L,D=.1143):
 h=hb.GeoNodeWall()
 h.create(name);o=h.obj
 for k,v in [('Length',L),('Thickness',D),('Height',2.7),('Left Angle',0.),('Right Angle',0.)]:h.set_input(k,v)
 o.location=(x,y,0);o.rotation_euler.z=angle;C.view_layer.update()
 return o
def select(*objects):
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 C.view_layer.objects.active=objects[0]
 C.view_layer.update()
def put(a,label,value):
 m=a.modifiers[0];sock=m.node_group.interface.items_tree[label];key=sock.identifier
 if isinstance(value,str):
  was=sock.default_value;sock.default_value=value;tmp=a.modifiers.new('enum','NODES');tmp.node_group=m.node_group
  value=tmp[key];a.modifiers.remove(tmp);sock.default_value=was
 m[key]=value
 a.update_tag();C.view_layer.update()
def hit(o,x,y,z,d):
 C.view_layer.update();e=o.evaluated_get(C.evaluated_depsgraph_get())
 mesh=e.to_mesh()
 v=[e.matrix_world @ t.co for t in mesh.vertices]
 poly=[tuple(p.vertices) for p in mesh.polygons]
 e.to_mesh_clear()
 if not poly:return None
 q,_,_,_=BVHTree.FromPolygons(v,poly).ray_cast(Vector((x,y,z)),Vector(d),7.)
 return q
def cutmods(w):
 return [m for m in w.modifiers if m.type=='BOOLEAN' and m.object and m.object.get(host.MANAGED)]
def close(a,b,tol=2e-5):return abs(a-b)<tol
assert '--' in sys.argv, 'Pass the current Shower Area .blend path after --.'
src=Path(sys.argv[-1]).resolve()
name='Shower Area'
assert bpy.ops.wm.append(directory=str(src/'Object')+'/',filename=name,do_reuse_local_id=False)=={'FINISHED'}
a=C.scene.objects[name]
back=wall('WO Back',0.,0.,0,1.6)
left=wall('WO Left',0.,-0.9144,pi/2,.9144)
unselected=wall('WO Protected nearby',0.,.20,0,1.6)
fixture=bpy.data.objects.new('Decorative object',bpy.data.meshes.new('Decorative object'));C.scene.collection.objects.link(fixture)
put(a,'Ativar nicho 1',True)
z=.04+52*IN
y0=hit(back,.762,-.5,z,(0,1,0))
n0=hit(a,.762,-.5,z,(0,1,0))
assert y0 is not None and close(y0.y,0.) and n0 is not None and n0.y>.055,(y0,n0)
assert not cutmods(back)
select(a,back,fixture)
assert F.cut_shower_niche_host()=={'FINISHED'}
cut,=cutmods(back);helper=cut.object
print('HELPER',helper,helper.hide_get(),len(helper.animation_data.drivers),len(helper.evaluated_get(C.evaluated_depsgraph_get()).data.vertices))
assert helper.hide_render and helper.hide_get()
print('HIT',hit(back,.762,-.5,z,(0,1,0)),hit(back,.762,.4,z,(0,-1,0)),hit(back,.17,-.5,z,(0,1,0)),hit(a,.762,-.5,z,(0,1,0)))
p=hit(back,.762,-.5,z,(0,1,0));assert p is not None and p.y>n0.y-.001,(p,n0)
assert close(hit(back,.762,.4,z,(0,-1,0)).y,.1143)  # exterior face stays.
assert close(hit(back,.17,-.5,z,(0,1,0)).y,0.)  # no other wall section altered.
assert not cutmods(unselected) and not cutmods(left) and not fixture.modifiers
assert F.cut_shower_niche_host()=={'FINISHED'} and len(cutmods(back))==1
# Move through modifier values; former position fills and parameters remain live.
put(a,'Deslocamento 1',12*IN)
assert close(hit(back,.762,-.5,z,(0,1,0)).y,0.)
assert hit(back,.762+12*IN,-.5,z,(0,1,0)).y>.055
put(a,'Deslocamento 1',0.)
put(a,'Ativar nicho 1',False)
assert close(hit(back,.762,-.5,z,(0,1,0)).y,0.)
put(a,'Ativar nicho 1',True)
# Left wall is not touched until selected; then both share one native helper.
put(a,'Ativar nicho 2',True)
assert close(hit(left,.5,-.45,z,(-1,0,0)).x,0.)
select(a,back,left)
assert F.cut_shower_niche_host()=={'FINISHED'}
assert cutmods(left)[0].object==helper
q=hit(left,.5,-.45,z,(-1,0,0));assert q.x<-.055,q
# Switching an enum (Builder helper driver) must retain the right geometry.
put(a,'Tipo do nicho 1','Mármore pré-fabricado • Modamo 15 × 24″')
q=hit(back,.762,-.5,z,(0,1,0));assert q.y>.07,q
# Reopening without autoexec still uses native geometry and all scoped drivers.
C.preferences.filepaths.save_version=0
test_dir=Path(tempfile.mkdtemp(prefix='fzm-shower-host-'))
roundtrip=test_dir/'reopened.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(roundtrip),compress=True)
bpy.ops.wm.open_mainfile(filepath=str(roundtrip),use_scripts=False)
back,left,a=(C.scene.objects[k] for k in ('WO Back','WO Left',name));helper=cutmods(back)[0].object
assert cutmods(left)[0].object==helper and helper.hide_get() and helper.hide_render
q=hit(back,.762,-.5,z,(0,1,0));assert q.y>.07,q
put(a,'Ativar nicho 1',False)
assert close(hit(back,.762,-.5,z,(0,1,0)).y,0.)
select(left);assert F.remove_shower_niche_host()=={'FINISHED'}
assert not cutmods(left) and cutmods(back)[0].object==helper
select(back);assert F.remove_shower_niche_host()=={'FINISHED'}
assert not cutmods(back) and not any(o.get(host.MANAGED) for o in C.scene.objects)
assert not a.hide_get()

# Prepare for Export is destructive, so test it in this disposable scene.
# Use a different offset from the link-time value to detect stale cuts.
put(a,'Ativar nicho 1',True)
put(a,'Deslocamento 1',0.)
select(a,back)
assert F.cut_shower_niche_host()=={'FINISHED'}
put(a,'Deslocamento 1',12*IN)
assert bpy.ops.home_builder.prepare_for_export()=={'FINISHED'}
back=C.scene.objects['WO Back']
assert not any(o.get(host.MANAGED) for o in C.scene.objects)
assert close(hit(back,.762,-.5,z,(0,1,0)).y,0.)
assert hit(back,.762+12*IN,-.5,z,(0,1,0)).y>.055
print('PASS: Live exact cutters on real selected Builder wall(s); two walls, offsets, enums, reopen/autoexec off, no collateral cuts, undoable removal.')
