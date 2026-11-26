"""Automatic baseboards must meet on the long side of a miter."""
from importlib import import_module
import math
import bpy
from mathutils import Vector

C=bpy.context
pkg=next(k for k in C.preferences.addons.keys() if k.endswith('.fzm_builder'))
types=import_module(pkg+'.hb_types')
finish=import_module(pkg+'.operators.finishes')

def wall(name,start,end,a,b,thickness=.1143):
    w=types.GeoNodeWall()
    w.create(name)
    for k,v in (('Length',math.dist(start,end)),('Thickness',thickness),('Height',2.5),
                ('Left Angle',a),('Right Angle',b)):
        w.set_input(k,v)
    w.obj.location=(*start,0.)
    w.obj.rotation_euler.z=math.atan2(end[1]-start[1],end[0]-start[0])
    return w.obj

th=.1143
wall('Wide north wall',(0.,0.),(4.,0.),0,0,.1524)
wall('Reentrant vertical',(2.,0.),(2.,-2.),0,math.pi/4)
wall('Reentrant horizontal',(2.,-2.),(0.,-2.),-math.pi/4,0.)
wall('East',(4.,0.),(4.,-4.),0,0)
wall('South',(4.,-4.),(0.,-4.),0,0)
wall('West lower',(0.,-4.),(0.,-2.),0,0)
mesh=bpy.data.meshes.new('Room slab')
corner=Vector((2.+th,-2.-th))
mesh.from_pydata([(corner.x,0,0.),(*corner,0.),(0.,corner.y,0.),
                  (0.,-4.,0.),(4.,-4.,0.),(4.,0.,0.)],[],[(0,1,2,3,4,5)])
mesh.update()
floor=bpy.data.objects.new('Floor',mesh); C.collection.objects.link(floor)
floor['IS_FLOOR_BP']=True
bpy.ops.object.select_all(action='DESELECT')
floor.select_set(True); C.view_layer.objects.active=floor
C.view_layer.update()
for style in ('FLAT','COLONIAL','STEP_BEVEL'):
    assert bpy.ops.fzm_builder.room_baseboards(wall_source='AUTO',profile=style,height=.10,thickness=.018)=={'FINISHED'}
    trim,=[o for o in floor.children if o.get(finish.BASEBOARD)]
    for up,out in finish.trim_profiles.BASEBOARD_PROFILES[style]:
        target=Vector((corner.x+out*.018,corner.y-out*.018,up*.10))
        assert sum((v.co-target).length<5e-5 for v in trim.data.vertices)>=2,(style,target)
print('PASS: automatic outside miter joins both true wall faces, for all three trim profiles.')
