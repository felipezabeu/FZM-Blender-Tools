"""Exercise the real Builder niche/bench operator on supported walls and saved files."""
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory

base = run_path(str(Path(__file__).with_name('smoke_shower_area.py')))
bpy, sh, select, parts, buildwall, opening, near, package = (
    base[key] for key in ('bpy','sh','select','parts','buildwall','opening','near','package'))
from importlib import import_module
from mathutils import Vector
sf = import_module(package+'.operators.shower_fixtures')
op = bpy.ops.fzm_builder.shower_fixture


def scene():
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o,do_unlink=True)
    a = buildwall('Left',(0,0,0),(0,2.6,0))
    b = buildwall('Back',(0,2.6,0),(2.4,2.6,0))
    c = buildwall('Right',(2.4,0,0),(2.4,2.6,0))
    w = opening(b,.90,1.56,.48,.45)
    return a,b,c,w


def photo(p,name,px):
    img=bpy.data.images.new(name,width=4,height=4)
    img.pixels=list(px)*16
    img.filepath_raw=str(p); img.file_format='PNG'; img.save()
    bpy.data.images.remove(img)


def hit(obj, xyz, vector=(0,1,0), *, evaluated=False):
    if evaluated:
        obj=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    inv=obj.matrix_world.inverted()
    ok,loc,*_=obj.ray_cast(inv@Vector(xyz),(inv.to_3x3()@Vector(vector)).normalized())
    return (obj.matrix_world@loc) if ok else None


def backpanel(root,b):
    return next(o for o in parts(root) if o.get('fzm_shower_wall')==b)


def tile_photo(material):
    return next(n.image for n in material.node_tree.nodes if n.type=='TEX_IMAGE')


def test(tmp):
    a,b,c,w=scene()
    f, accent = [tmp/x for x in ('tile.png','accent.png')]
    photo(f,'Tile',(.32,.7,.2,1)); photo(accent,'Accent',(.9,.3,.1,1))
    select(a,b,c)
    assert bpy.ops.fzm_builder.shower_area(pattern='HALF',filepath=str(f))=={'FINISHED'}
    root=bpy.context.active_object
    p=backpanel(root,b)
    select(p)
    original=b.modifiers[-1]
    assert original.object==w
    assert op(kind='NICHE',offset=.32,bottom=.92,width=.53,height=.28,depth=.085,
              override=True,filepath=str(accent))=={'FINISHED'}
    n=bpy.context.active_object; nr=n.parent
    assert len(n.data.polygons)==5
    assert len(n.data.materials)==2 and n.data.polygons[2].material_index==1
    assert tile_photo(n.data.materials[0]).packed_file and tile_photo(n.data.materials[1]).packed_file
    bpy.context.view_layer.update()
    p=backpanel(root,b)
    assert not hit(p,(.60,2,.99))
    assert hit(p,(.20,2,.99))
    near(hit(b,(.60,2,.99),evaluated=True).y,2.685)
    near(hit(b,(.60,3,.99),(0,-1,0),evaluated=True).y,2.75)
    near(hit(n,(.60,2,.99)).y,2.6842)
    assert not hit(b,(1.13,2,1.73),evaluated=True)
    assert not hit(p,(1.13,2,1.73))
    old_cutter=sf._modifier(b,nr).object
    assert op(kind='NICHE',offset=.90,bottom=1.6,width=.35,height=.30,depth=.09)=={'CANCELLED'}
    assert op(kind='NICHE',offset=.32,bottom=.92,width=.53,height=.28,depth=.145)=={'CANCELLED'}
    assert sf._modifier(b,nr).object==old_cutter
    assert backpanel(root,b)==p and b.modifiers[1]==original
    assert op(kind='NICHE',offset=.70,bottom=.67,width=.35,height=.51,depth=.055,
              override=True,filepath=str(accent))=={'FINISHED'}
    n=bpy.context.active_object
    bpy.context.view_layer.update()
    p=backpanel(root,b)
    assert hit(p,(.60,2,.99))
    assert not hit(p,(1.05,2,.99))
    near(hit(b,(1.05,2,.99),evaluated=True).y,2.655)
    near(hit(b,(.60,2,.99),evaluated=True).y,2.60)

    select(p)
    assert op(kind='BENCH',anchor='START',width=.69,depth=.40,bottom=0,height=.4572,
              override=True,color=(.7,.3,.25,1.))=={'FINISHED'}
    bench=bpy.context.active_object
    assert len(bench.data.polygons)==6 and bench.data.polygons[1].material_index==1
    assert bench.data.materials[0]==p.data.materials[0] and len(bench.data.materials)==2
    bpy.context.view_layer.update()
    world=[bench.matrix_world@v.co for v in bench.data.vertices]
    near(min(p.z for p in world),0)
    near(max(p.z for p in world),.4572)
    near(max(p.y for p in world),2.5993)
    near(min(p.x for p in world),.0015)
    near(min(p.y for p in world),2.1985)
    assert len([m for m in b.modifiers if m.type=='BOOLEAN'])==2
    select(p)
    assert op(kind='BENCH',anchor='WALL',offset=.2,bottom=0,width=.6,depth=.35,height=.45)=={'CANCELLED'}
    nname,bname,rootname=n.name,bench.name,root.name
    blend=str(tmp/'fixtures.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    f.unlink(); accent.unlink()
    bpy.ops.wm.open_mainfile(filepath=blend)
    root,n,bench=[bpy.data.objects[k] for k in (rootname,nname,bname)]
    b,w=[bpy.data.objects[name] for name in ('Back','Fixture Window Opening')]
    bpy.context.view_layer.update()
    select(n)
    assert op(kind='NICHE',offset=.99,bottom=.66,width=.33,height=.45,depth=.048,
              override=True,filepath=str(accent))=={'FINISHED'}
    n=bpy.context.active_object
    assert tile_photo(n.data.materials[1]).packed_file
    p=backpanel(root,b)
    select(p)
    assert bpy.ops.fzm_builder.shower_area(pattern='THIRD',filepath=str(f))=={'FINISHED'}
    p=backpanel(root,b)
    assert bench.data.materials[0]==p.data.materials[0]==n.data.materials[0]
    assert tile_photo(n.data.materials[0]).packed_file
    assert tile_photo(n.data.materials[1]).packed_file
    accent_group=next(node for node in n.data.materials[1].node_tree.nodes if node.type=='GROUP')
    assert accent_group.inputs['Cycle'].default_value==3
    select(n)
    assert op(kind='NICHE',remove=True)=={'FINISHED'}
    p=backpanel(root,b)
    assert hit(p,(1.25,2.,.98)) and not hit(p,(1.13,2,1.73))
    assert [m.object for m in b.modifiers if m.type=='BOOLEAN']==[w]
    select(bench)
    assert op(kind='BENCH',remove=True)=={'FINISHED'}
    assert not sf.fixtures_for_area(bpy.context,root)
    select(p)
    assert op(kind='NICHE',offset=.34,bottom=.90,width=.40,height=.45,depth=.064)=={'FINISHED'}
    select(backpanel(root,b))
    assert bpy.ops.fzm_builder.shower_area(remove=True)=={'FINISHED'}
    assert not any(o.get(sf.FIXTURE) or o.get(sf.CUTTER) or o.get(sf.VISUAL) for o in bpy.context.scene.objects)
    assert [m.object for m in b.modifiers if m.type=='BOOLEAN']==[w]
    select(bpy.data.objects['Left'],b,bpy.data.objects['Right'])
    assert bpy.ops.fzm_builder.shower_area()=={'FINISHED'}
    root=bpy.context.active_object
    select(backpanel(root,b))
    assert op(kind='BENCH',full_width=True,depth=.36)=={'FINISHED'}
    bench=bpy.context.active_object
    bpy.context.view_layer.update()
    world=[bench.matrix_world@v.co for v in bench.data.vertices]
    near(min(v.x for v in world),.0015)
    near(max(v.x for v in world),2.2485)
    near(min(v.z for v in world),0.)
    near(max(v.z for v in world),.4572)
    farwall=bpy.data.objects['Right']
    for orientation, expected_w, expected_h in (('VERTICAL',.352425,.555625),('HORIZONTAL',.555625,.352425)):
        select(backpanel(root,b))
        assert op(kind='NICHE',niche_style='MARBLE_K',orientation=orientation,offset=.50,bottom=.78)=={'FINISHED'}
        n=bpy.context.active_object
        assert len(n.data.polygons)==13
        assert all(f.material_index==1 for f in n.data.polygons)
        assert n.data.materials[1].get('fzm_shower_prefab_material')
        bpy.context.view_layer.update()
        world=[n.matrix_world@v.co for v in n.data.vertices]
        near(max(v.x for v in world)-min(v.x for v in world),expected_w)
        near(max(v.z for v in world)-min(v.z for v in world),expected_h)
        width=n.parent[sf.FIXTURE_OPTIONS]['width']
        near(width,expected_w-.048)
        near(hit(b,(.50+width*.5,2.,.99),evaluated=True).y,2.675)
        # The visible front ring faces the room; check normals in world space.
        assert all((n.matrix_world.to_3x3()@face.normal).y<-.9 for face in list(n.data.polygons)[5:9])
        assert op(kind='NICHE',niche_style='MARBLE_K',orientation=orientation,offset=.5,bottom=.78,
                  width=expected_w,depth=.08)=={'CANCELLED'}
        assert op(kind='NICHE',remove=True)=={'FINISHED'}
    # A rotated real wall still yield a masked, blind niche.
    select(backpanel(root,farwall))
    assert op(kind='NICHE',offset=.35,bottom=.85,width=.55,height=.26,depth=.065)=={'FINISHED'}
    n=bpy.context.active_object
    bpy.context.view_layer.update()
    assert n.parent.parent == farwall
    assert op(kind='NICHE',remove=True)=={'FINISHED'}
    a=buildwall('Narrow Left',(0,5,0),(0,7.2,0))
    b=buildwall('Narrow Back',(0,7.2,0),(1.,7.2,0))
    c=buildwall('Narrow Right',(1.,5,0),(1.,7.2,0))
    select(a,b,c)
    assert bpy.ops.fzm_builder.shower_area()=={'FINISHED'}
    select(backpanel(bpy.context.active_object,c))
    assert op(kind='BENCH',anchor='WALL',offset=.30,width=.55,depth=1.5)=={'CANCELLED'}
    print('PASS shower fixtures: recess and wall skin, clip, move/resize, bounds, existing cut, corner bench, packed finishes, reopen, remove')


with TemporaryDirectory() as d:
    test(Path(d))
