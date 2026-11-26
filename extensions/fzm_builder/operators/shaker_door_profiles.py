"""Photo-proportioned beveled Shaker panel recesses for native leaves."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    stile: float
    top: float
    bottom: float
    divider: float
    rows: tuple[float, ...]  # Fractions of the open height, from top to bottom.

    def openings(self):
        """Each pair is normalized mouth height and center relative to leaf center."""
        remaining = 1. - self.top - self.bottom - (len(self.rows) - 1) * self.divider
        z = .5 - self.top
        result = []
        for fraction in self.rows:
            height = remaining * fraction
            result.append((height, z - .5 * height))
            z -= height + self.divider
        return tuple(result)


# Source reference proportions measured on ONE leaf. Keep the lower rail deeper
# than the top rail, and the upper opening ~1.55x taller on the two-panel door.
BIFOLD_ONE = Profile(.208, .060, .104, 0., (1.,))
BIFOLD_TWO = Profile(.145, .056, .104, .095, (.608, .392))
HINGED_ONE = Profile(.189, .056, .122, 0., (1.,))
HINGED_TWO = Profile(.189, .055, .120, .0865, (.630, .370))
HINGED_FIVE = Profile(.189, .051, .113, .0555, (.2,) * 5)


def _surface(a, geometry, material, selection=None):
    node = a.nodes.new('GeometryNodeSetMaterial')
    a.wire(geometry, node.inputs['Geometry'])
    if selection is not None:
        a.wire(selection, node.inputs['Selection'])
    a.wire(material, node.inputs['Material'])
    return node.outputs['Geometry']


def _component(a, vector):
    node = a.nodes.new('ShaderNodeSeparateXYZ')
    a.wire(vector, node.inputs[0])
    return node.outputs


def _cutter(a, width, height, z, thickness, side, bevel, recess):
    """Build one tapered cutter going from the panel bed to outside the slab."""
    primitive = a.nodes.new('GeometryNodeMeshCube')
    primitive.inputs['Size'].default_value = (1, 1, 1)
    primitive.inputs['Vertices Y'].default_value = 3
    raw = a.nodes.new('GeometryNodeInputPosition')
    x, y, gz = _component(a, raw.outputs['Position'])
    along = a.mul(y, side)
    outside = a.calc('MAXIMUM', along, 0.)
    inside = a.calc('MINIMUM', along, 0.)
    # Three Y rings: the bottom of the recess, the start of the sloping
    # rim 1.2 mm below the face, and an overcut 1.2 mm beyond the face.
    depth = a.add(thickness * .5 - bevel,
                  a.add(a.mul(inside, a.mul(a.sub(recess, bevel), 2.)), a.mul(outside, 4 * bevel)))
    ramp = a.sub(a.mul(a.calc('GREATER_THAN', along, .25), 4 * bevel), 2 * bevel)
    position = (a.mul(x, a.add(width, ramp)),
                a.mul(depth, side),
                a.add(z, a.mul(gz, a.add(height, ramp))))
    reshape = a.nodes.new('GeometryNodeSetPosition')
    a.wire(primitive.outputs['Mesh'], reshape.inputs['Geometry'])
    a.wire(a.vector(position), reshape.inputs['Position'])
    return reshape.outputs['Geometry']


def build_leaf(a, width, height, thickness, profile, blank, inset_material, *, insert_thickness=None):
    """Carve both faces of one watertight door leaf; dimensions are GN fields.

    Only the recess beds get the insert material (a Material or GN socket).
    Optional insert thickness (metres or a GN float socket) changes the depth,
    never the opening silhouette.
    """
    bevel = min(.0012, thickness * .07)
    recess = min(.0055, thickness * .22)
    if insert_thickness is not None:
        maximum = thickness - 2 * bevel - .0001
        if isinstance(insert_thickness, (int, float)):
            if not .001 <= insert_thickness <= maximum:
                raise ValueError('Shaker insert thickness must fit behind both beveled faces.')
            recess = .5 * (thickness - insert_thickness)
        else:
            clamped = a.calc('MINIMUM', a.calc('MAXIMUM', insert_thickness, .001), maximum)
            recess = a.mul(a.sub(thickness, clamped), .5)
    aperture_w = a.mul(width, 1. - 2. * profile.stile)
    apertures = []
    for h, z in profile.openings():
        for side in (-1, 1):
            apertures.append(_cutter(a, aperture_w, a.mul(height, h), a.mul(height, z),
                                     thickness, side, bevel, recess))
    normals = a.nodes.new('GeometryNodeInputNormal')
    face_y = _component(a, normals.outputs['Normal'])[1]
    panel_face = a.calc('GREATER_THAN', a.calc('ABSOLUTE', face_y), .98)
    cutters = _surface(a, a.join(*apertures), a.materials['white'])
    cutters = _surface(a, cutters, inset_material, panel_face)
    carve = a.nodes.new('GeometryNodeMeshBoolean')
    carve.operation = 'DIFFERENCE'
    carve.solver = 'EXACT'
    carve.label = f'Double-sided recessed Shaker ({len(profile.rows)} panels)'
    a.wire(blank, carve.inputs['Mesh 1'])
    a.wire(cutters, carve.inputs['Mesh 2'])
    return carve.outputs['Mesh']
