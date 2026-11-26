"""GUI fixture for real-pointer testing. Set FZM_GUI_PROBE_DIR before launching Blender."""
from math import radians
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
import json
import os
import sys

from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Euler, Quaternion, Vector

sys.path.insert(0,str(Path(__file__).resolve().parent))
import smoke_visual_wall_edit as t

bpy=t.bpy
pose=import_module(t.package+'.ui.door_pose')
doors=import_module(t.package+'.operators.doors_windows')
hinged=import_module(t.package+'.operators.hinged_doors')
root=Path(os.environ['FZM_GUI_PROBE_DIR'])
mode='walls'
previous=''
record={}
door_name='GUI Door'


def init():
    bpy.context.preferences.view.show_splash=False
    bpy.context.preferences.filepaths.save_version=0
    layout=bpy.context.window_manager.windows[0].screen
    for area in layout.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.show_gizmo=True
            area.spaces.active.show_region_ui=False
            area.spaces.active.show_region_toolbar=False
    wall,_,_=t.fixture()
    t.active(wall[1].obj)
    with viewport():
        c=bpy.context
        rv=c.space_data.region_3d
        rv.view_rotation=Quaternion((1,0,0,0))
        rv.view_perspective='ORTHO'
        rv.view_distance=7.
        rv.view_location=(2.,1.5,0.)
        c.area.tag_redraw()
    (root/'ready').touch()
    return .25


def viewport():
    win=bpy.context.window_manager.windows[0]
    area=next(a for a in win.screen.areas if a.type=='VIEW_3D')
    region=next(r for r in area.regions if r.type=='WINDOW')
    return bpy.context.temp_override(window=win,area=area,region=region)


def set_view(name):
    global mode
    with viewport():
        c=bpy.context
        rv=c.space_data.region_3d
        if not bpy.data.objects.get(door_name):
            props=doors.home_builder_doors_windows_OT_place_door
            w=bpy.data.objects['A']
            stub=SimpleNamespace(register_placement_object=lambda a:None,create_placement_dimensions=lambda:None)
            for n in ('OBJECT_NAME','BP_FLAG','MENU_ID','WIDTH_PROP_NAME','HEIGHT_PROP_NAME','HAS_SWING',
                      'INITIAL_SWING_INPUTS','TEXT_NAME','TEXT_KIND'):
                setattr(stub,n,getattr(props,n))
            props.create_placed_object(stub,c)
            cage=stub.placed_obj
            cage.obj.name=door_name
            cage.obj.parent=w
            cage.obj.location=(1.1,0.,0.)
            props.cut_wall(stub,w,cage.obj)
            if not hinged.visual_for(cage.obj):
                t.active(cage.obj)
                bpy.ops.home_builder_doors_windows.door_prompts(show_leaf=True)
        cage=bpy.data.objects[door_name]
        t.active(hinged.visual_for(cage))
        bpy.context.view_layer.update()
        geo=t.hb.GeoNodeCage(cage)
        anchor=cage.matrix_world @ Vector((geo.get_input('Dim X')*.5,geo.get_input('Dim Y')*.5,geo.get_input('Dim Z')*.79))
        rotation,distance,projection={
            'ortho': ((70,0,10),7.,'ORTHO'),
            'persp': ((78,0,38),4.,'PERSP'),
            'wide': ((70,0,-30),20.,'PERSP'),
            'close': ((78,0,28),.7,'PERSP'),
            'clipped': ((75,0,28),.002,'PERSP'),
        }[name]
        rv.view_rotation=Euler(tuple(radians(v) for v in rotation),'XYZ').to_quaternion()
        rv.view_perspective=projection
        rv.view_distance=distance
        rv.view_location=anchor
        c.area.tag_redraw()
    mode=name


def tick():
    global previous
    path=root/'command'
    if path.exists():
        name=path.read_text().strip()
        if name and name!=previous:
            previous=name
            set_view(name)
            return .35
    with viewport():
        c=bpy.context
        region, rv=c.region,c.region_data
        def pix(p): return [round(region.x+p[0]),round(c.window.height-region.y-p[1])]
        if mode=='walls':
            ws=[t.hb.GeoNodeWall(bpy.data.objects[n]) for n in 'ABCD']
            a,b,cc,d=ws
            w=b.obj
            lng=b.get_input('Length')
            handles={name:pix(location_3d_to_region_2d(region,rv,w.matrix_world@Vector((x,0,.0254))))
                     for name,x in [('start',0),('move',lng/2),('end',lng)]}
            record={'mode':mode,'handles':handles,'geom':{s.obj.name:t.geometry(s) for s in ws},'active':c.active_object.name if c.active_object else ''}
        else:
            cage=bpy.data.objects[door_name]
            p=pose._anchor(c,cage)
            record={'mode':mode,'anchor':pix(p) if p else None,'open':hinged.options(cage)[2]}
    tmp=root/'state.tmp'
    tmp.write_text(json.dumps(record))
    tmp.replace(root/'state.json')
    return .15


# Separate startup from measurements to let Blender redraw its view matrix.
def go():
    init()
    bpy.app.timers.register(tick,first_interval=.6)


bpy.app.timers.register(go,first_interval=.8)
