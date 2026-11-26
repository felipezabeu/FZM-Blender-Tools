"""Reference-proportioned symmetric molded Six Panel geometry."""

import bpy

# Reference image coordinates normalized down from the actual slab top and
# across the slab face. Bifold is the same face split through the mullion.
ROWS = ((.061, .161), (.211, .513), (.598, .895))
FULL_COLUMNS = ((.148,.434),(.566,.852))
COLUMNS = {
    'FULL': FULL_COLUMNS,
    'HALF_LEFT': tuple((2*a,2*b) for a,b in FULL_COLUMNS[:1]),
    'HALF_RIGHT': tuple((2*a-1,2*b-1) for a,b in FULL_COLUMNS[1:]),
}
TEMPLATE = 'FZM Six Panel | Molded Relief v1'


def scalar_switch(a, condition, no, yes):
    n=a.nodes.new('GeometryNodeSwitch')
    n.input_type='FLOAT'
    for value,key in ((condition,'Switch'),(no,'False'),(yes,'True')):
        a.wire(value,n.inputs[key])
    return n.outputs[0]


def _template(a):
    memo=bpy.data.node_groups.get(TEMPLATE)
    if memo and memo.get('fzm_six_panel_relief')==1:
        return memo
    group=bpy.data.node_groups.new(TEMPLATE,'GeometryNodeTree')
    group['fzm_six_panel_relief']=1
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    for n in ('Panel Width','Panel Height','Thickness'):
        group.interface.new_socket(name=n,in_out='INPUT',socket_type='NodeSocketFloat')
    p=a.__class__(group)
    w,h,t=(p.inputs.outputs[n] for n in ('Panel Width','Panel Height','Thickness'))
    radius=p.calc('MINIMUM',.024,p.calc('MINIMUM',p.mul(w,.19),p.mul(h,.18)))
    half_y=p.mul(t,.5)
    groove=p.sub(half_y,p.calc('MINIMUM',.008,p.mul(t,.25)))
    inset=p.sub(half_y,p.calc('MINIMUM',.0035,p.mul(t,.11)))
    position=p.nodes.new('GeometryNodeInputPosition')
    split=p.nodes.new('ShaderNodeSeparateXYZ')
    p.wire(position.outputs['Position'],split.inputs['Vector'])
    u,v=split.outputs[0],split.outputs[1]
    au,av=p.calc('ABSOLUTE',u),p.calc('ABSOLUTE',v)

    def axis(coord,abs_coord,size):
        outer=p.mul(size,.5)
        middle=p.sub(outer,p.mul(radius,.38))
        inner=p.sub(outer,radius)
        x=scalar_switch(p,p.calc('GREATER_THAN',abs_coord,.4),inner,middle)
        x=scalar_switch(p,p.calc('GREATER_THAN',abs_coord,.8),x,outer)
        return p.mul(x,p.calc('SIGN',coord))

    x=axis(u,au,w); z=axis(v,av,h)
    ring=p.calc('MAXIMUM',au,av)
    y=scalar_switch(p,p.calc('GREATER_THAN',ring,.4),inset,groove)
    y=scalar_switch(p,p.calc('GREATER_THAN',ring,.8),y,half_y)

    def grid(nx,nz,xyz,flip=False):
        node=p.nodes.new('GeometryNodeMeshGrid')
        for name,value in (('Size X',2.),('Size Y',2.),('Vertices X',nx),('Vertices Y',nz)):
            node.inputs[name].default_value=value
        moved=p.nodes.new('GeometryNodeSetPosition')
        p.wire(node.outputs['Mesh'],moved.inputs['Geometry'])
        p.wire(p.vector(xyz),moved.inputs['Position'])
        out=moved.outputs['Geometry']
        if flip:
            f=p.nodes.new('GeometryNodeFlipFaces')
            p.wire(out,f.inputs['Mesh'])
            out=f.outputs['Mesh']
        return out

    # Identical 6-point boundaries: front/back and each side weld into one
    # closed panel without T junctions, independent of scaled slab dimensions.
    z_along_u=axis(u,au,h); depth_along_v=p.mul(v,half_y)
    faces=(grid(6,6,(x,p.mul(y,-1.),z)),grid(6,6,(x,y,z),True),
           grid(6,2,(x,depth_along_v,p.mul(h,-.5)),True),
           grid(6,2,(x,depth_along_v,p.mul(h,.5))),
           grid(6,2,(p.mul(w,-.5),depth_along_v,z_along_u)),
           grid(6,2,(p.mul(w,.5),depth_along_v,z_along_u),True))
    merge=p.nodes.new('GeometryNodeMergeByDistance')
    p.wire(p.join(*faces),merge.inputs['Geometry'])
    merge.inputs['Distance'].default_value=.000001
    p.wire(merge.outputs['Geometry'],p.output.inputs['Geometry'])
    return group


def build_leaf(a,width,height,thickness, variant, inset_material):
    """One full-width molded leaf, or one true half of a bifold face."""
    columns=COLUMNS[variant]
    parts=[]
    def rect(x0,x1,z0,z1):
        if x1-x0<1e-6 or z1-z0<1e-6:
            return
        cx=a.mul(width,(x0+x1)*.5-.5)
        cz=a.mul(height,.5-(z0+z1)*.5)
        parts.append(a.box((a.mul(width,x1-x0),thickness,a.mul(height,z1-z0)),(cx,0,cz),'white'))

    prev=0.
    for x0,x1 in columns:
        rect(prev,x0,0,1);prev=x1
    rect(prev,1,0,1)
    template=_template(a)
    for x0,x1 in columns:
        prev=0.
        for z0,z1 in ROWS:
            rect(x0,x1,prev,z0)
            node=a.nodes.new('GeometryNodeGroup')
            node.node_tree=template
            for n,v in (('Panel Width',a.mul(width,x1-x0)),('Panel Height',a.mul(height,z1-z0)),
                        ('Thickness',thickness)):
                a.wire(v,node.inputs[n])
            material=a.nodes.new('GeometryNodeSetMaterial')
            material.inputs['Material'].default_value=inset_material
            a.wire(node.outputs['Geometry'],material.inputs['Geometry'])
            parts.append(a.transform(material.outputs['Geometry'],(a.mul(width,(x0+x1)*.5-.5),
                         0,a.mul(height,.5-(z0+z1)*.5))))
            prev=z1
        rect(x0,x1,prev,1)
    return a.join(*parts)
