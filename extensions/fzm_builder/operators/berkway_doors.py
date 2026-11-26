"""Flush Berkway reference: an uninterrupted left stile and fine routed lines."""

# Normalized image coordinates, read from the supplied front-view reference.
STILE_END = .260
ROW_CENTERS = (.153,.320,.490,.660,.827)  # top → bottom
VERTICAL_GROOVE_WIDTH = .0028
HORIZONTAL_GROOVE_WIDTH = .0022
GROOVE_DEPTH = .0014


def build_leaf(a,width,height,thickness):
    """Cut shallow parallel grooves into both faces of one solid white slab."""
    def difference(base, cutters):
        boolean=a.nodes.new('GeometryNodeMeshBoolean')
        boolean.operation='DIFFERENCE'
        boolean.solver='EXACT'
        a.wire(base,boolean.inputs['Mesh 1'])
        a.wire(a.join(*cutters),boolean.inputs['Mesh 2'])
        return boolean.outputs['Mesh']

    # The build guarantees positive realistic leaf sizes before evaluating the
    # assembly. Cross each end of the slab, leaving the uninterrupted stile
    # untouched except at the single transition groove.
    blank=a.box((width,thickness,height),(0,0,0),'white')
    border=a.mul(width,STILE_END-.5)
    overshoot=.010
    right=a.add(a.mul(width,.5),overshoot)
    groove_x=a.mul(a.add(border,right),.5)
    groove_width=a.sub(right,border)
    vertical=[]
    horizontal=[]
    for sign in (-1,1):
        normal=sign*(thickness*.5+(overshoot-GROOVE_DEPTH)*.5)
        cut_depth=overshoot+GROOVE_DEPTH
        vertical.append(a.box((VERTICAL_GROOVE_WIDTH,cut_depth,a.add(height,2*overshoot)),
                              (border,normal,0),'white'))
        for r in ROW_CENTERS:
            z=a.mul(height,.5-r)
            horizontal.append(a.box((groove_width,cut_depth,HORIZONTAL_GROOVE_WIDTH),
                                    (groove_x,normal,z),'white'))
    # Treat the two groove directions separately so no cutter collection
    # self-intersects at the T-junctions. Their depressions share the same
    # floor and meet at the vertical line.
    result=difference(difference(blank,vertical),horizontal)
    finish=a.nodes.new('GeometryNodeSetMaterial')
    finish.inputs['Material'].default_value=a.materials['white']
    a.wire(result,finish.inputs['Geometry'])
    return finish.outputs['Geometry']
