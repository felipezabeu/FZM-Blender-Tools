"""Blender operator, menu bindings and viewport gizmo projection checks.

The screen UI recorder in this headless script runs the actual GizmoGroup
callbacks and invokes their bound Blender operator. It does not emulate a
physical mouse or test GPU drawing.
"""
from importlib import import_module
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from mathutils import Matrix,Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d

x=run_path(str(Path(__file__).with_name('smoke_native_doors.py')))
bpy,hb,nd,doors,active,wall,build,new,near,stats,volume=(x[k] for k in
    ('bpy','hb_types','nd','doors','active','wall','build_fixture','new','near','stats','volume'))
pkg=x['package']
hd=import_module(pkg+'.operators.hinged_doors')
pose=import_module(pkg+'.ui.door_pose')
menus=import_module(pkg+'.ui.menus')


class BoundButtons:
    def new(self, kind):
        assert kind == 'GIZMO_GT_button_2d'
        btn=SimpleNamespace(properties=SimpleNamespace(),matrix_basis=Matrix.Identity(4))
        def bind(op):
            btn.command=op
        btn.target_set_operator=bind
        return btn


class MenuRecorder:
    def __init__(self): self.ops=[]
    def operator(self,idname,**kwargs):
        self.ops.append((idname,kwargs))
        return SimpleNamespace()
    def separator(self): pass


class Canvas:
    def __init__(self,bpy_context):
        self.original=bpy_context
        self.region=SimpleNamespace(x=10,y=20,width=800,height=550,type='WINDOW')
        self.region_data=SimpleNamespace(perspective_matrix=Matrix.Diagonal((.10,.10,.1,1.)))
        self.area=SimpleNamespace(regions=[self.region])
        self.preferences=SimpleNamespace(system=SimpleNamespace(ui_scale=1.))
    def __getattr__(self,attr):
        return getattr(self.original,attr)


def click(button):
    assert not button.hide,button
    app,operator=button.command.split('.')
    return getattr(getattr(bpy.ops,app),operator)()


def menu_state(context):
    layout=MenuRecorder()
    menus.HOME_BUILDER_MT_door_commands.draw(SimpleNamespace(layout=layout),context)
    return [(idname,p['text']) for idname,p in layout.ops if idname==pose.TOGGLE]


def test(tmp):
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o,do_unlink=True)
    w=wall(length=22)
    a=build(doors.home_builder_doors_windows_OT_place_door,w,.60)
    b=build(doors.home_builder_doors_windows_OT_place_double_door,w,2.4)
    plain=build(doors.home_builder_doors_windows_OT_place_open_door,w,4.6)
    sliding,s,ok,_ = new(w,'BYPASS',6.5,w=1.36,style='MIRROR')
    assert ok
    bifold,f,ok,_ = new(w,'BIFOLD',9.2,w=.91,style='SHAKER_2',right=True)
    assert ok
    pocket,p,ok,_ = new(w,'POCKET',13.5,w=.9,style='SIX_PANEL',right=True)
    assert ok
    for obj,n in ((a,'Fixture Single'),(b,'Fixture Double'),(plain,'Fixture Plain'),
                  (sliding,'Fixture Sliding'),(bifold,'Fixture Bifold'),(pocket,'Fixture Pocket')):
        obj.name=n
    ca,cb=hd.visual_for(a),hd.visual_for(b)
    assert ca and cb
    g=pose.FZM_GGT_door_pose
    helper=SimpleNamespace(gizmos=BoundButtons())
    canvas=Canvas(bpy.context)
    g.setup(helper,canvas)
    assert g.bl_space_type=='VIEW_3D' and g.bl_region_type=='WINDOW'
    assert helper.open_button.properties.icon=='PLAY'
    assert helper.close_button.properties.icon=='LOOP_BACK'
    icon_rna=bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon']
    assert all(k in icon_rna.enum_items for k in ('PLAY','LOOP_BACK'))
    cuts=[(m.name,m.object) for m in w.modifiers if m.type=='BOOLEAN']
    v=volume(w)
    switch=bpy.ops.fzm_builder.toggle_door_pose

    for obj,button_location in ((ca,0),(b,0),(plain,1),(w,1)):
        active(obj)
        g.draw_prepare(helper,canvas)
        assert helper.open_button.hide==bool(button_location)
        assert helper.close_button.hide
        assert g.poll(canvas)==(button_location==0)
        assert menu_state(bpy.context)==([] if button_location else [(pose.TOGGLE,'Open Door')])
        assert hd.options(a)==(True,'FLAT',0.)
        assert hd.options(b)==(True,'FLAT',0.)
        assert pose.LAST_OPEN not in a and pose.LAST_OPEN not in b
    assert not switch.poll()

    active(ca)
    active_pos = pose._anchor(canvas,a)
    assert active_pos and active_pos[0]>400 and active_pos[1]>290
    g.draw_prepare(helper,canvas)
    assert tuple(helper.open_button.matrix_basis.translation)==(*active_pos,0.)
    assert click(helper.open_button)=={'FINISHED'}
    _,closed_lo,closed_hi,_=stats(cb)
    _,open_lo,open_hi,_=stats(ca)
    assert (closed_hi[1]-closed_lo[1])<.06 and (open_hi[1]-open_lo[1])>.65
    assert hd.options(a)==(True,'FLAT',1.) and hd.options(b)==(True,'FLAT',0.)
    g.draw_prepare(helper,canvas)
    assert helper.open_button.hide and not helper.close_button.hide
    assert tuple(helper.close_button.matrix_basis.translation)==(*active_pos,0.)
    assert menu_state(bpy.context)==[(pose.TOGGLE,'Close Door')]
    assert click(helper.close_button)=={'FINISHED'}
    assert hd.options(a)==(True,'FLAT',0.) and a[pose.LAST_OPEN]==1.
    assert volume(w)==v

    for i,(c,vis,is_native,style,amount) in enumerate((
        (a,ca,False,'SHAKER_5',.37),(b,cb,False,'SHAKER_2',.61),
        (sliding,s,True,'MIRROR',.36),(bifold,f,True,'SHAKER_2',.62),
        (pocket,p,True,'SIX_PANEL',.84))):
        # Each real door kind uses the exact existing size/style/pose controls.
        if is_native:
            _,_,right=nd.get_options(vis)
            nd.set_options(vis,style,amount,right)
        else:
            active(vis)
            assert bpy.ops.home_builder_doors_windows.door_prompts(leaf_style=style,opening_amount=amount)=={'FINISHED'}
        active(vis if i%2 else c)
        mod=vis.modifiers[vis.home_builder.mod_name]
        group=mod.node_group
        # Track the door geometrically without clipping its projected position.
        def camera_center():
            canvas.region_data.perspective_matrix=Matrix(((.18,0,0,-c.location.x*.18),
                (0,0,.50,-.25),(0,.1,0,0),(0,0,0,1)))
        camera_center()
        g.draw_prepare(helper,canvas)
        assert helper.open_button.hide and not helper.close_button.hide
        assert click(helper.close_button)=={'FINISHED'}
        assert menu_state(bpy.context)==[(pose.TOGGLE,'Open Door')]
        current=lambda: nd.get_options(vis)[1] if is_native else hd.options(c)[2]
        near(current(),0.)
        g.draw_prepare(helper,canvas)
        assert click(helper.open_button)=={'FINISHED'}
        near(current(),amount)
        assert (nd.get_options(vis)[0] if is_native else hd.options(c)[1])==style
        assert vis.modifiers[vis.home_builder.mod_name].node_group==group
        assert (not is_native) or nd.get_options(vis)[2]==right
        assert c[pose.LAST_OPEN]>0.

    active(a)
    bpy.context.view_layer.update()
    canvas.region_data.perspective_matrix=Matrix(((.18,0,0,-5.),
        (0,0,.5,0),(0,.1,0,0),(0,0,0,1)))
    g.draw_prepare(helper,canvas)
    assert helper.open_button.hide and helper.close_button.hide
    assert menu_state(bpy.context)==[(pose.TOGGLE,'Close Door')] # remains usable via context menu
    ca.hide_set(True)
    assert not switch.poll()
    ca.hide_set(False)
    a.select_set(False)
    assert not switch.poll() and menu_state(bpy.context)==[]
    select_target=hd.swing_for(a).obj
    active(select_target)
    assert not switch.poll()
    active(b)
    assert bpy.ops.home_builder_doors_windows.door_prompts(show_leaf=False)=={'FINISHED'}
    assert not switch.poll() and menu_state(bpy.context)==[]
    assert plain.get(pose.LAST_OPEN) is None
    assert [(m.name,m.object) for m in w.modifiers if m.type=='BOOLEAN']==cuts
    assert volume(w)==v

    active(p)
    assert switch()=={'FINISHED'}  # persists last-open fraction while closed
    point=tmp/'viewport-poses.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(point))
    bpy.ops.wm.open_mainfile(filepath=str(point))
    cage=bpy.data.objects['Fixture Pocket']
    visual=nd.visual_for(cage)
    assert nd.get_options(visual)[0]=='SIX_PANEL'
    near(nd.get_options(visual)[1],0.)
    active(visual)
    assert switch()=={'FINISHED'}
    near(nd.get_options(visual)[1],.84)
    print('PASS viewport gizmo setup/draw/click command wiring, dynamic Door Commands fallback, passive selection, all 5 poses, preserved style/hand/dimensions/Boolean, offscreen and hidden checks, saved remembered pose')


with TemporaryDirectory() as d:
    test(Path(d))
