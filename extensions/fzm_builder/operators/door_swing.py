"""Geometric plan annotation for the real hinged slab (not its hardware)."""

from . import hinged_kinematics as kin, native_doors as nd
from .. import hb_types

import bpy


LEGACY_GROUP = 'GeoNodeDoorSwing'
GROUP_NAME = 'FZM Door Swing | Seated Leaf v1'
REVISION = 'fzm_door_swing_geometry_version'
# The stroke keeps the stock 0.1-inch tube radius. Lift the entire stroke so
# the bottom is clear of the generated floor's z=0 datum, not half-buried.
LINE_RADIUS = .00254
PLAN_LIFT = .008


def _rectangle(a, width, height, center):
    rect = a.nodes.new('GeometryNodeCurvePrimitiveQuadrilateral')
    rect.mode = 'RECTANGLE'
    a.wire(width, rect.inputs['Width'])
    a.wire(height, rect.inputs['Height'])
    return a.transform(rect.outputs['Curve'], center)


def _annotation_group(old):
    new = next((g for g in bpy.data.node_groups if g.get(REVISION) == 1), None)
    if new is not None:
        return new

    # Preserve the entire interface and its internal socket identifiers so
    # saved modifier properties, controls and Dim X/Y driver FCurves work.
    new = old.copy()
    new.name = GROUP_NAME
    new.use_fake_user = False
    new.nodes.clear()
    new.interface.items_tree['Door Thickness'].hide_in_modifier = True
    a = nd.Assembly(new)

    w, d = (a.inputs.outputs[k] for k in ('Dim X', 'Dim Y'))
    inside, left, double = (a.inputs.outputs[k] for k in ('Swing Inside', 'Is Left', 'Is Double'))
    leaf = kin.leaf_width(a, w, double)
    pivot_y, room_direction = kin.hinge_y_and_direction(a, d, inside)
    t = kin.LEAF_THICKNESS

    # Trace the corner furthest from the hinge pin: local XY=(leaf,-t).
    # Its centerline is the actual free outer corner over the full 90°
    # sweep. The current pose or handle presence never affects this path.
    radius = a.calc('SQRT', a.add(a.mul(leaf, leaf), t * t))
    phase = a.mul(a.calc('ARCTAN2', t, leaf), -1.)
    arc = a.nodes.new('GeometryNodeCurveArc')
    arc.mode = 'RADIUS'
    arc.inputs['Resolution'].default_value = 64
    arc.inputs['Sweep Angle'].default_value = kin.SWING_ANGLE
    a.wire(radius, arc.inputs['Radius'])
    a.wire(phase, arc.inputs['Start Angle'])
    # At full opening the slab's projected outline occupies x:[0,t]
    # and y:[0,leaf] relative to the pin, before reflection to either hand.
    opened_leaf = _rectangle(a, t, leaf, (t * .5, a.mul(leaf, .5), 0.))
    canonical = a.join(arc.outputs['Curve'], opened_leaf)

    def at_jamb(low):
        return a.transform(canonical, (kin.hinge_x(a, w, low), pivot_y, PLAN_LIFT),
                           scale=(1. if low else -1., room_direction, 1.))

    low, high = at_jamb(True), at_jamb(False)
    sectors = a.select(double, a.select(left, low, high), a.join(low, high))
    opening = _rectangle(a, w, d, (a.mul(w, .5), a.mul(d, .5), PLAN_LIFT))
    circle = a.nodes.new('GeometryNodeCurvePrimitiveCircle')
    circle.inputs['Resolution'].default_value = 12
    circle.inputs['Radius'].default_value = LINE_RADIUS
    mesh = a.nodes.new('GeometryNodeCurveToMesh')
    a.wire(circle.outputs['Curve'], mesh.inputs['Profile Curve'])
    a.wire(a.join(opening, sectors), mesh.inputs['Curve'])
    a.wire(mesh.outputs['Mesh'], a.output.inputs['Geometry'])
    new[REVISION] = 1
    return new


def upgrade_annotation(obj):
    """Upgrade a local stock annotation, without changing object transforms."""
    if (obj.type != 'MESH' or obj.library or obj.override_library or not obj.parent
            or not obj.parent.get('IS_ENTRY_DOOR_BP') or obj.parent.get(nd.TYPE_KEY)
            or not (obj.get('FZM_DOOR_SWING') or obj.get('IS_2D_ANNOTATION'))):
        return False
    modifier = obj.modifiers.get(obj.home_builder.mod_name)
    if not modifier or modifier.type != 'NODES' or not modifier.node_group:
        return False
    old = modifier.node_group
    base, sep, suffix = old.name.rpartition('.')
    if old.library or (old.name != LEGACY_GROUP and not (sep and base == LEGACY_GROUP and suffix.isdigit())):
        return False
    required = ('Dim X', 'Dim Y', 'Is Double', 'Is Left', 'Swing Inside', 'Door Thickness')
    if not all((item := old.interface.items_tree.get(name)) and item.identifier == f'Socket_{i}'
               for i, name in enumerate(required, start=2)):
        return False
    # Do not rewrite a non-stock graph intentionally substituted under its name.
    if not all(old.nodes.get(name) for name in ('Curve to Mesh', 'Arc', 'Arc.001', 'Trim Curve')):
        return False
    marker = hb_types.GeoNodeObject(obj)
    settings = {key: marker.get_input(key) for key in ('Is Double', 'Is Left', 'Swing Inside')}
    modifier.node_group = _annotation_group(old)
    for key, state in settings.items():
        marker.set_input(key, state)
    obj.update_tag()
    return True


def upgrade_saved_annotations():
    for obj in bpy.data.objects:
        if obj.get('FZM_DOOR_SWING') or obj.get('IS_2D_ANNOTATION'):
            upgrade_annotation(obj)
