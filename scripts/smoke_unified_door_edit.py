"""Shared edit dispatch through the actual Builder UI callbacks and Blender operator."""
from importlib import import_module
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

fx=run_path(str(Path(__file__).with_name('smoke_native_doors.py')))
bpy,hb,nd,doors,active,wall,build,new,near,volume=(fx[k] for k in
    ('bpy','hb_types','nd','doors','active','wall','build_fixture','new','near','volume'))
pkg=fx['package']
hd=import_module(pkg+'.operators.hinged_doors')
menus=import_module(pkg+'.ui.menus')
sidebar=import_module(pkg+'.ui.view3d_sidebar')
fin=import_module(pkg+'.operators.finishes')
edit=bpy.ops.fzm_builder.edit_door


class Layout:
    def __init__(self):
        self.ops=[]
        self.props=[]
        self.labels=[]
    def operator(self,op,**settings):
        self.ops.append((op,settings))
        return SimpleNamespace()
    def prop(self,obj,prop,**settings):
        self.props.append(prop)
    def label(self,text,**settings):
        self.labels.append(text)
    def separator(self): pass
    def row(self,**kw): return self
    def column(self,**kw): return self
    def box(self,**kw): return self


def draw_ui(cage, expected, hidden=()):
    contract=doors.FZM_OT_edit_door
    assert edit.poll()
    for widget in (menus.HOME_BUILDER_MT_door_commands,sidebar.HOME_BUILDER_PT_room_layout_doors_windows):
        l=Layout()
        widget.draw(SimpleNamespace(layout=l),bpy.context)
        entries=[k for k,_ in l.ops]
        assert entries.count('fzm_builder.edit_door')==1
        assert 'fzm_builder.door_casing' in entries
        assert 'fzm_builder.edit_native_door' not in entries and 'home_builder_doors_windows.door_prompts' not in entries

    # Call the same invoke and draw implementations Blender installs. Stub only
    # the window manager popup callback and UILayout, unavailable in background.
    dialog=SimpleNamespace(layout=Layout())
    calls=[]
    wm=SimpleNamespace(invoke_props_dialog=lambda self,**kwargs:
                       (calls.append((self,kwargs)) or {'RUNNING_MODAL'}))
    ctx=SimpleNamespace(object=bpy.context.object,window_manager=wm)
    out=contract.invoke(dialog,ctx,None)
    assert out=={'RUNNING_MODAL'} and calls==[(dialog,{'width':390})]
    state=hb.GeoNodeCage(cage)
    near(dialog.width,state.get_input('Dim X'))
    near(dialog.height,state.get_input('Dim Z'))
    near(dialog.offset,cage.location.x)
    contract.draw(dialog,ctx)
    assert dialog.layout.props[:3]==['width','height','offset']
    assert all(k in dialog.layout.props for k in expected)
    assert not any(k in dialog.layout.props for k in hidden)
    return dialog


def test(tmp):
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o,do_unlink=True)
    w=wall(length=15)
    a=build(doors.home_builder_doors_windows_OT_place_door,w,.5)
    b=build(doors.home_builder_doors_windows_OT_place_double_door,w,2.4)
    op=build(doors.home_builder_doors_windows_OT_place_open_door,w,4.6)
    y,yv,ok,_=new(w,'BYPASS',6.5,w=1.4,style='MIRROR',opening=.43)
    assert ok
    f,fv,ok,_=new(w,'BIFOLD',9.,w=.72,style='SHAKER',right=True)
    assert ok
    p,pv,ok,_=new(w,'POCKET',11.5,w=.85,style='SIX_PANEL',right=True)
    assert ok
    cages={d.name:d for d in (a,b,op,y,f,p)}
    va,vb=hd.visual_for(a),hd.visual_for(b)
    cutters=tuple(m.object for m in w.modifiers if m.type=='BOOLEAN')
    starting_volume=volume(w)

    active(w)
    assert not edit.poll()
    active(va)
    opts=draw_ui(a,('show_leaf','opening_amount','leaf_style','swing_direction','hinge_hand'),('bypass_style','right_hand'))
    assert opts.show_leaf and opts.leaf_style=='FLAT' and opts.opening_amount==0.
    assert edit(leaf_style='SHAKER_5',opening_amount=.31,hinge_hand='RIGHT',swing_direction='OUTSIDE')=={'FINISHED'}
    assert hd.options(a)[:2]==(True,'SHAKER_5')
    near(hd.options(a)[2],.31)
    swing=hd.swing_for(a)
    assert not swing.get_input('Is Left') and not swing.get_input('Swing Inside')
    assert bpy.ops.fzm_builder.toggle_door_pose()=={'FINISHED'} and hd.options(a)[2]==0.
    assert bpy.ops.fzm_builder.toggle_door_pose()=={'FINISHED'}
    near(hd.options(a)[2],.31)
    near(volume(w),starting_volume)

    active(vb)
    draw_ui(b,('show_leaf','opening_amount','leaf_style','swing_direction'),('hinge_hand','right_hand'))
    assert edit(show_leaf=False)=={'FINISHED'}
    active(b)
    draw_ui(b,('show_leaf','swing_direction'),('leaf_style','opening_amount'))
    assert edit(show_leaf=True,leaf_style='SHAKER_2')=={'FINISHED'}
    assert hd.options(b)[:2]==(True,'SHAKER_2')

    active(op)
    draw_ui(op,(),('show_leaf','opening_amount','leaf_style','bypass_style','right_hand','swing_direction','hinge_hand'))
    assert not bpy.ops.fzm_builder.toggle_door_pose.poll()
    assert edit(show_leaf=True)=={'CANCELLED'}
    assert not hd.visual_for(op)

    active(yv)
    opt=draw_ui(y,('bypass_style','opening_amount'),('show_leaf','leaf_style','right_hand','hinge_hand'))
    assert opt.bypass_style=='MIRROR'
    t=y.location.copy(); h=hb.GeoNodeCage(y).get_input('Dim Z')
    assert edit(opening_amount=.75)=={'FINISHED'}
    assert nd.get_options(yv)[0]=='MIRROR'
    near(nd.get_options(yv)[1],.75)
    assert (y.location-t).length<1e-6 and hb.GeoNodeCage(y).get_input('Dim Z')==h
    assert bpy.ops.fzm_builder.door_casing(profile='FLAT')=={'FINISHED'}
    cy=next(o for o in y.children if o.get(fin.CASING))
    assert edit(bypass_style='SHAKER_2')=={'FINISHED'} and cy.parent==y

    for c,v in ((f,fv),(p,pv)):
        active(v)
        initial=draw_ui(c,('leaf_style','opening_amount','right_hand'),('show_leaf','bypass_style','hinge_hand'))
        assert initial.right_hand
        previous=nd.get_options(v)
        assert edit(width=.05,leaf_style='FLAT')=={'CANCELLED'}
        assert nd.get_options(v)==previous
        assert edit(leaf_style='SHAKER_5',right_hand=False)=={'FINISHED'}
        assert nd.get_options(v)==('SHAKER_5',previous[1],False)
    assert tuple(m.object for m in w.modifiers if m.type=='BOOLEAN')==cutters
    near(volume(w),starting_volume)
    active(a)
    initial_width=hb.GeoNodeCage(a).get_input('Dim X')
    assert edit(width=initial_width+.045,offset=.52)=={'FINISHED'}
    near(hb.GeoNodeCage(a).get_input('Dim X'),initial_width+.045)
    near(a.location.x,.52)
    assert len(hd.visual_for(a).evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices)>8

    filename=str(tmp/'unified.blend')
    bpy.ops.wm.save_as_mainfile(filepath=filename)
    bpy.ops.wm.open_mainfile(filepath=filename)
    reopened=bpy.data.objects[next(iter(cages))]
    active(reopened)
    assert draw_ui(reopened,('leaf_style','opening_amount')).leaf_style=='SHAKER_5'
    assert bpy.ops.home_builder_doors_windows.door_prompts(leaf_style='SIX_PANEL')=={'FINISHED'}
    print('PASS unified Edit Door menu/sidebar, loaded appropriate dialog fields for six types, effective edits through Blender, '
          'unaffected other door/Boolean/casing, invalid geometry rejected, persistence, old prompts and viewport pose')


with TemporaryDirectory() as tmp:
    test(Path(tmp))
