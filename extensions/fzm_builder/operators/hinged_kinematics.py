"""Common geometric conventions for the 3D hinged leaf and its plan symbol."""

from math import pi

JAMB_GAP = .004
PAIR_CENTER_GAP = .005
LEAF_THICKNESS = .034925
SWING_ANGLE = pi / 2


def select_scalar(a, condition, no, yes):
    node = a.nodes.new('GeometryNodeSwitch')
    node.input_type = 'FLOAT'
    for value, name in ((condition, 'Switch'), (no, 'False'), (yes, 'True')):
        a.wire(value, node.inputs[name])
    return node.outputs[0]


def leaf_width(a, opening, double):
    clear = a.sub(opening, 2 * JAMB_GAP)
    paired = a.mul(a.sub(opening, 2 * JAMB_GAP + PAIR_CENTER_GAP), .5)
    return select_scalar(a, double, clear, paired)


def hinge_y_and_direction(a, depth, inside):
    """Inside: pivot at 0 toward -Y; outside: at +depth toward +Y."""
    return select_scalar(a, inside, depth, 0.), select_scalar(a, inside, 1., -1.)


def closed_leaf_y(depth, inside):
    """Local center plane of the parked slab, independent of current pose."""
    return LEAF_THICKNESS/2 if inside else depth-LEAF_THICKNESS/2


def hinge_x(a, opening, low):
    """A low-X jamb opens toward +X along the closed opening."""
    return JAMB_GAP if low else a.sub(opening, JAMB_GAP)
