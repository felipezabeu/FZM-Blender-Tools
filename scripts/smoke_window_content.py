"""Blender smoke: legacy openings, optional window assembly, live resize and reload."""
from importlib import import_module
from math import radians
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

from mathutils import Vector

base = run_path(str(Path(__file__).with_name('smoke_native_doors.py')))
bpy, hb, doors, active, wall, build, near, volume = (
    base[n] for n in ('bpy', 'hb_types', 'doors', 'active', 'wall', 'build_fixture', 'near', 'volume'))
wc = import_module(base['package']+'.operators.window_content')
prompts = bpy.ops.home_builder_doors_windows.window_prompts
placement = bpy.ops.home_builder_doors_windows.place_window
delete = bpy.ops.home_builder_doors_windows.delete_door_window


def bounds(vertices):
    return tuple(tuple(fn(v[i] for v in vertices) for i in range(3)) for fn in (min, max))


def parts(obj, cage):
    mesh = base['evaluated_mesh'](obj)
    assert len(mesh.vertices) == 40 and len(mesh.polygons) == 30
    assert obj.parent == cage and obj['MENU_ID'] == 'HOME_BUILDER_MT_window_commands'
    assert not obj.hide_render and cage.hide_render
    assert obj.lock_location[:] == (True, True, True)
    glass_vertices, frame_vertices = [], []
    for p in mesh.polygons:
        mat = mesh.materials[p.material_index]
        role = mat.get('fzm_window_3d_material')
        assert role in {'glass', 'frame'}
        if role == 'glass':
            glass_vertices.extend(mesh.vertices[i].co for i in p.vertices)
            bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
            assert 0 < bsdf.inputs['Alpha'].default_value < 1
        else:
            frame_vertices.extend(mesh.vertices[i].co for i in p.vertices)
    assert len(glass_vertices) == 24 and len(frame_vertices) == 96
    g0, g1 = bounds(glass_vertices)
    f0, f1 = bounds(frame_vertices)
    w, d, h = (hb.GeoNodeCage(cage).get_input(k) for k in ('Dim X', 'Dim Y', 'Dim Z'))
    for i, dim in enumerate((w,d,h)):
        assert 0 <= f0[i] < g0[i] < g1[i] < f1[i] <= dim+1e-6
        near((g0[i]+g1[i])*.5, dim*.5)
        near((f0[i]+f1[i])*.5, dim*.5)
    near((obj.matrix_world.translation-cage.matrix_world.translation).length, 0.)
    assert wc.visual_for(cage) == obj and wc.cage_for(obj) == cage
    return f0, f1


def test(tmp):
    for old in list(bpy.context.scene.objects):
        bpy.data.objects.remove(old, do_unlink=True)
    assert placement.get_rna_type().properties['add_frame'].default is False
    scene = bpy.context.scene
    props = scene.home_builder
    props.show_entry_door_and_window_cages = True
    props.window_width = 1.12
    props.window_height = .88
    props.window_height_from_floor = 1.0
    a = wall(length=8., thickness=.142, height=3.)
    a.rotation_euler.z = radians(31)
    a.location.x, a.location.y = (1.3, 2.1)
    capacity = volume(a)
    cls = doors.home_builder_doors_windows_OT_place_window

    # A fixture created with no new property simulates an ordinary legacy cage.
    old = build(cls, a, .7)
    old.name = 'Legacy opening'
    old.location.z = props.window_height_from_floor
    initial = volume(a)
    near(capacity-initial, 1.12*.88*.142)
    assert not wc.visual_for(old) and wc.VISUAL not in old
    assert old.display_type == 'TEXTURED' and old.show_in_front
    file = tmp/'legacy.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(file))
    bpy.ops.wm.open_mainfile(filepath=str(file))
    old = bpy.data.objects['Legacy opening']
    a = old.parent
    props = bpy.context.scene.home_builder
    assert not wc.visual_for(old)
    near(volume(a), initial)

    # Both placement paths use the existing wall cutter.
    opened = build(cls, a, 3., add_frame=False)
    opened.name = 'New empty'
    opened.location.z = .7
    frame = build(cls, a, 5.4, add_frame=True)
    frame.name = 'New framed'
    frame.location.z = 1.1
    full = volume(a)
    near(capacity-full, 3*1.12*.88*.142)
    cut = tuple(m.object for m in a.modifiers if m.type == 'BOOLEAN')
    assert cut == (old, opened, frame)
    assert not wc.visual_for(opened)
    pane = wc.visual_for(frame)
    b = parts(pane, frame)
    assert frame.display_type == 'WIRE' and not frame.show_in_front

    # Selecting the glass child supports the same prompts and deletion as the cage.
    active(pane)
    assert prompts.poll() and delete.poll()
    assert prompts(show_frame=False)=={'FINISHED'}
    assert not wc.visual_for(frame) and bpy.context.object == frame
    assert frame.display_type == 'TEXTURED' and frame.show_in_front
    near(volume(a),full)
    assert prompts(show_frame=True)=={'FINISHED'}
    pane = wc.visual_for(frame)
    assert parts(pane, frame)==b

    # Updates to size and placement must drive physical geometry AND
    # cutter volume, but must not affect neighboring open cages.
    active(pane)
    assert prompts(window_width=1.63,window_height=1.07,height_from_floor=.91,offset=5.25)=={'FINISHED'}
    near(frame.location.x,5.25)
    near(frame.location.z,.91)
    assert parts(pane,frame) != b
    near(capacity-volume(a),(2*1.12*.88+1.63*1.07)*.142)
    assert wc.visual_for(frame)==pane and not wc.visual_for(old) and not wc.visual_for(opened)
    saved_dimensions=(1.63,1.07)
    cage = hb.GeoNodeCage(frame)
    for key, target in zip(('Dim X','Dim Z'),saved_dimensions): near(cage.get_input(key),target)

    # Cage visibility preference must not put a solid cube in front of glass.
    props.show_entry_door_and_window_cages = False
    assert opened.display_type == frame.display_type == 'WIRE'
    props.show_entry_door_and_window_cages = True
    assert opened.display_type == 'TEXTURED' and frame.display_type == 'WIRE'
    assert not frame.show_in_front
    props.show_entry_door_and_window_cages = False
    assert prompts(show_frame=False)=={'FINISHED'}
    assert frame.display_type == 'WIRE' and not frame.show_in_front
    assert prompts(show_frame=True)=={'FINISHED'}
    pane=wc.visual_for(frame)
    assert parts(pane,frame)

    # Depth is still authoritative on the existing cutter, not the child's own
    # transform; model shrinks without crossing either wall face.
    cage.set_input('Dim Y',.06)
    p0,p1=parts(pane,frame)
    near(p0[1],.06*(1-.88)*.5)
    near(p1[1],.06*(1+.88)*.5)
    cage.set_input('Dim Y',.142)
    assert tuple(m.object for m in a.modifiers if m.type == 'BOOLEAN')==cut

    # Convert legacy in place with the original cutter; decline migration on another.
    active(old)
    assert prompts(show_frame=True)=={'FINISHED'}
    assert parts(wc.visual_for(old),old)
    assert not wc.visual_for(opened)
    stable=volume(a)
    file=tmp/'populated.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(file))
    bpy.ops.wm.open_mainfile(filepath=str(file))
    old, opened, frame=(bpy.data.objects[n] for n in ('Legacy opening','New empty','New framed'))
    pane=wc.visual_for(frame)
    assert parts(pane,frame) and parts(wc.visual_for(old),old)
    assert not wc.visual_for(opened)
    a=frame.parent
    near(volume(a),stable)
    active(pane)
    assert prompts(window_height=1.13)=={'FINISHED'}
    assert parts(pane,frame)
    n_frame,n_pane=frame.name,pane.name
    assert delete(object_type='WINDOW')=={'FINISHED'}
    assert n_frame not in bpy.data.objects and n_pane not in bpy.data.objects
    assert tuple(m.object for m in a.modifiers if m.type=='BOOLEAN')==(old,opened)
    near(capacity-volume(a),2*1.12*.88*.142)
    print('PASS legacy empty reload; opening-only and framed placement; optional update; separate cutters; '
          'rotated wall; resized glass and frame; global cage visibility; save/reopen; deletion from glass')


with TemporaryDirectory() as d:
    test(Path(d))
