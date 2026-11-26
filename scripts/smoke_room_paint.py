"""Blender headless room-side Paint: real doors, divided floors, palette and render."""
from importlib import import_module
from math import radians
from pathlib import Path
from tempfile import TemporaryDirectory
import os, shutil, struct, sys

import addon_utils
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = os.environ.get('FZM_TEST_PACKAGE', 'fzm_builder')
if PACKAGE == 'fzm_builder':
    sys.path.insert(0, str(ROOT / 'extensions'))
    addon_utils.enable(PACKAGE, default_set=True, persistent=True)
hb = import_module(PACKAGE+'.hb_types')
divider = import_module(PACKAGE+'.operators.floor_divider')
room = import_module(PACKAGE+'.operators.room_paint')
FINISH = import_module(PACKAGE+'.operators.finishes')
B = (1.15, 2.0, 0)
R = radians(31.0)


def active(obj, *others):
    for selected in bpy.context.selected_objects:
        selected.select_set(False)
    for o in (obj, *others):
        o.select_set(True)
    bpy.context.view_layer.objects.active = obj


def wall(name='Shared wall', z=0.):
    wall = hb.GeoNodeWall()
    wall.create(name)
    wall.obj.location = (B[0], B[1], z)
    wall.obj.rotation_euler.z = R
    for name, value in [('Length',6.),('Height',2.6),('Thickness',.20)]:
        wall.set_input(name,value)
    bpy.context.view_layer.update()
    return wall


def floor(name, coords):
    old=bpy.data.meshes.new('Blank')
    mesh=divider.make_slab(name,[Vector(v) for v in coords],0,-.012,old,0)
    bpy.data.meshes.remove(old)
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    obj['IS_FLOOR_BP']=True
    obj.location=B
    obj.rotation_euler.z=R
    bpy.context.view_layer.update()
    return obj


def edge_cutter(wall):
    # Through-wall opening formed by the same continuous wall mesh and a
    # Builder entry cage, not a spare mask hiding the doorway.
    cage=hb.GeoNodeCage();cage.create('Door opening')
    cage.obj['IS_ENTRY_DOOR_BP']=True
    cage.obj.parent=wall.obj;cage.obj.location=(2.62,-.01,-.01)
    for key, value in [('Dim X',.73),('Dim Y',.22),('Dim Z',2.10)]:
        cage.set_input(key,value)
    mod=wall.obj.modifiers.new('Entry opening','BOOLEAN')
    mod.object=cage.obj;mod.operation='DIFFERENCE';mod.solver='EXACT'
    cage.obj.hide_render=True
    bpy.context.view_layer.update()
    return cage.obj


def read(w):
    return w.get_input('Right Edge'),w.get_input('Left Edge')


def geometry(w):
    o=w.obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return len(o.data.vertices),len(o.data.polygons)


def fixture_palette(tmp):
    if PACKAGE == 'fzm_builder':
        # Source-tree tests do not have an extension repository or user path.
        FINISH.imported_palettes_path = lambda create=False: tmp/'unused-imports'
    gui=bpy.context.preferences.addons[PACKAGE].preferences
    share=tmp/'room-colors'
    folder=share/'Paletas'/'Benjamin Moore'
    folder.mkdir(parents=True)
    label='OC-65 Test Blue\0'.encode('utf-16-be')
    body=struct.pack('>H',len(label)//2)+label+struct.pack('>4s3fH',b'RGB ',.06,.10,.90,2)
    (folder/'Room test.ase').write_bytes(struct.pack('>4sHHIHI',b'ASEF',1,0,1,1,len(body))+body)
    gui.asset_libraries.add().library_path=str(share)


def check_spans(w, ada, ben, cy):
    a,b=read(w)
    expected_a=[(ada.name,0.,3.),(ben.name,3.,6.)]
    expected_b=[(cy.name,0.,6.)]
    for material, expected in [(a,expected_a),(b,expected_b)]:
        values=sorted((r.floor.name,round(r.start,5),round(r.end,5)) for r in room.get_regions(material))
        assert values==sorted(expected),(w.obj.name,values,expected)
    assert room.get_regions(b)[0].material['fzm_paint_code']=='OC-65'


def color_probe(tmp,w,side):
    sc=bpy.context.scene
    sc.world=bpy.data.worlds.new('Room test')
    sc.world.use_nodes=True
    bg=sc.world.node_tree.nodes['Background'];bg.inputs[0].default_value=(.06,.06,.06,1.)
    bg.inputs[1].default_value=.35
    sc.render.engine='CYCLES';sc.cycles.samples=8
    sc.render.resolution_x=640;sc.render.resolution_y=300
    sc.render.resolution_percentage=100;sc.view_settings.view_transform='Standard'
    sc.render.image_settings.file_format='PNG'
    matrix=w.obj.matrix_world
    camdata=bpy.data.cameras.new('Probe Camera')
    camera=bpy.data.objects.new(camdata.name,camdata);sc.collection.objects.link(camera)
    camdata.type='ORTHO';camdata.ortho_scale=6.4;sc.camera=camera
    camera.location=matrix@Vector((3.,8.*side,1.3))
    target=matrix@Vector((3.,.1,1.3))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    d=bpy.data.lights.new('Room Key','AREA');d.energy=560;d.size=4.0
    light=bpy.data.objects.new(d.name,d);sc.collection.objects.link(light)
    light.location=matrix@Vector((3.,2.2*side,3.15))
    light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=str(tmp/f'room-shader-{side}.png')
    bpy.ops.render.render(write_still=True)
    proof=os.getenv('FZM_ROOM_PAINT_PREVIEW')
    if proof:
        shutil.copyfile(sc.render.filepath,Path(proof)/f'painted-side-{side}.png')
    img=bpy.data.images.load(sc.render.filepath,check_existing=False)
    pixels=tuple(img.pixels)
    def sample(x,z):
        y=.20 if side>0 else 0
        q=world_to_camera_view(sc,camera,matrix@Vector((x,y,z)))
        px,py=int(q.x*640),int(q.y*300)
        i=(py*640+px)*4
        return pixels[i:i+3]
    if side>0:
        # Sample on both sides of the divider both below and above the opening.
        for x,z,i in [(1.4,1.20,0),(4.6,1.20,1),(2.90,2.38,0),(3.10,2.38,1)]:
            c=sample(x,z)
            assert c[i]>max(c[j] for j in range(3) if j!=i)+.25,(x,z,c)
    else:
        for x,z in [(1.5,1.3),(4.5,1.3),(2.93,2.39),(3.07,2.39)]:
            c=sample(x,z)
            assert c[2]>max(c[:2])+.25,(x,z,c)
    # Opening straddles the divider; through-render remains background, not painted.
    c=sample(2.95,1.38)
    assert max(c)<.26,c
    bpy.data.images.remove(img)
    bpy.data.objects.remove(camera,do_unlink=True)
    bpy.data.objects.remove(light,do_unlink=True)


def test(tmp):
    for ob in list(bpy.context.scene.objects):
        bpy.data.objects.remove(ob,do_unlink=True)
    shared=wall();upper=wall('Upper floor, outside the selection',3.0)
    door=edge_cutter(shared)
    before_geometry=geometry(shared)
    assert bpy.ops.fzm_builder.wall_paint(scope='DEFAULT',hex_color='#CCC1B6')=={'FINISHED'}
    before_default=bpy.context.scene.home_builder.wall_material
    north=floor('Room A',[(0,0),(6,0),(6,3),(0,3)])
    south=floor('Room C',[(0,-2.),(6,-2.),(6,0),(0,0)])
    active(north)
    assert bpy.ops.fzm_builder.floor_divider(first=(3,0),second=(3,3))=={'FINISHED'}
    east=bpy.context.view_layer.objects.active
    # Divide Floor preserves the original object on one side. Name the sides
    # by geometry, not by which object is original.
    west,east=sorted((north,east),key=lambda fl:min(v.co.x for v in fl.data.vertices))
    west.name='Temp West';east.name='Room B';west.name='Room A'
    active(west,east)
    before_materials=set(bpy.data.materials)
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',hex_color='#DF1410')=={'CANCELLED'}
    assert set(bpy.data.materials)==before_materials
    active(west)
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',hex_color='#DF1410')=={'FINISHED'}
    assert shared.get_input('Left Edge')==before_default
    active(east)
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',hex_color='#169627')=={'FINISHED'}
    fixture_palette(tmp)
    active(south)
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',input_mode='PALETTE',paint_code='OC65')=={'FINISHED'}
    check_spans(shared,west,east,south)
    assert all(shared.get_input(s)==before_default for s in ('Inside Face','Outside Face','Top Surface','Bottom Surface'))
    assert all(upper.get_input(s)==before_default for s in upper.material_inputs(upper.obj))
    assert bpy.context.scene.home_builder.wall_material==before_default
    assert geometry(shared)==before_geometry
    assert list(shared.obj.modifiers)[-1].object==door

    color_probe(tmp,shared,1)
    color_probe(tmp,shared,-1)

    active(south)
    assert bpy.ops.fzm_builder.wall_paint(scope='DEFAULT',hex_color='#332211')=={'FINISHED'}
    after_default=bpy.context.scene.home_builder.wall_material
    assert after_default!=before_default
    check_spans(shared,west,east,south)
    assert all(room.base_material(mat)==after_default for mat in read(shared))
    assert shared.get_input('Top Surface')==after_default
    active(west)
    assert bpy.ops.fzm_builder.wall_paint(scope='RESET_ROOM')=={'FINISHED'}
    assert [r.floor for r in room.get_regions(read(shared)[0])]==[east]
    assert [r.floor for r in room.get_regions(read(shared)[1])]==[south]
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',hex_color='#DF1410')=={'FINISHED'}
    check_spans(shared,west,east,south)
    assert geometry(shared)==before_geometry

    # Move the real opening. Paint remains on the actual remaining wall mesh.
    door.location.x=3.7
    bpy.context.view_layer.update()
    def hit(x,z):
        o=shared.obj
        return o.ray_cast(Vector((x,1,z)),Vector((0,-1,0)),depsgraph=bpy.context.evaluated_depsgraph_get())[0]
    assert hit(2.95,1.38) and not hit(3.95,1.38)
    door.location.x=2.62
    bpy.context.view_layer.update()
    assert not hit(2.95,1.38)
    path=tmp/'painted-rooms.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    shared=hb.GeoNodeWall(bpy.data.objects['Shared wall'])
    floors={o.name:o for o in bpy.context.scene.objects if o.get('IS_FLOOR_BP')}
    check_spans(shared,floors['Room A'],floors['Room B'],floors['Room C'])
    color_probe(tmp,shared,1)
    assert bpy.ops.fzm_builder.wall_paint(scope='ALL',hex_color='#7F9081')=={'FINISHED'}
    new_global=bpy.context.scene.home_builder.wall_material
    assert all(shared.get_input(socket)==new_global for socket in shared.material_inputs(shared.obj))
    assert geometry(shared)==before_geometry
    active(shared.obj)
    assert bpy.ops.fzm_builder.wall_paint(scope='SELECTED',hex_color='#9090A0')=={'FINISHED'}
    selected=shared.get_input('Left Edge')
    assert bpy.ops.fzm_builder.wall_paint(scope='DEFAULT',hex_color='#123456')=={'FINISHED'}
    assert shared.get_input('Left Edge')==selected
    assert bpy.ops.fzm_builder.wall_paint(scope='RESET')=={'FINISHED'}
    assert shared.get_input('Left Edge')==bpy.context.scene.home_builder.wall_material
    # A fresh scene may not have an assigned base finish, and room reset must
    # restore the empty native slots rather than force a new material on them.
    bpy.context.scene.home_builder.wall_material=None
    shared.apply_material(shared.obj,None)
    active(floors['Room B'])
    assert bpy.ops.fzm_builder.wall_paint(scope='ROOM',hex_color='#EE2244')=={'FINISHED'}
    assert room.base_material(shared.get_input('Right Edge')) is None
    assert bpy.ops.fzm_builder.wall_paint(scope='RESET_ROOM')=={'FINISHED'}
    assert shared.get_input('Right Edge') is None
    print('PASS rendered room-side paints on a rotated physical wall, divided spans, opposite colors, palette, open door (and moving it), old global scopes, reset one room, save/reopen')


if __name__=='__main__':
    with TemporaryDirectory(prefix='fzm-roompaint-') as d:
        test(Path(d))
