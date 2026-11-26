"""Independent baseboard and casing sections scaled by the user's dimensions.

Positions run from floor to top for baseboards, and from the opening to the
outside for casing. The second coordinate is projection from the wall.
"""

REVISION = 3

LEGACY_BASEBOARD_PROFILES = {
    'FLAT': ((0, 0), (1, 0), (1, 1), (0, 1)),
    'COLONIAL': ((0, 0), (1, 0), (1, 0.35), (0.86, 0.35), (0.75, 0.48),
                 (0.66, 0.7), (0.55, 0.88), (0.42, 1), (0.2, 1), (0, 0.68)),
    'STEP_BEVEL': ((0, 0), (1, 0), (1, 0.35), (0.78, 0.35), (0.78, 0.55),
                   (0.6, 0.55), (0.42, 1), (0, 1)),
}

def _section(front, back=((0., 0.), (1., 0.))):
    # Front points run in increasing position; traverse back in reverse to
    # close the section without crossing. Preserve the backing corner at zero.
    return (*back, *reversed(front))


BASEBOARD_PROFILES = {
    'FLAT': LEGACY_BASEBOARD_PROFILES['FLAT'],
    # Traced from the supplied end view: tall flat lower face, small heel and
    # bead, recessed ogee, then a small bead and a eased upper lip.
    'COLONIAL': _section((
        (0.,1.), (.405,1.), (.429,.973), (.446,.92), (.468,.828),
        (.485,.946), (.505,.978), (.528,.958), (.551,.883), (.575,.79),
        (.606,.68), (.636,.589), (.674,.526), (.706,.539), (.736,.61),
        (.763,.71), (.792,.79), (.817,.835), (.851,.835), (.863,.878),
        (.884,.85), (.901,.792), (.927,.778), (.942,.704), (.975,.667),
        (.99,.635), (1.,.562),
    )),
    # Tall flat face, sharp step and a single long upper bevel. Light relief
    # on the back is visible in the sample; it doesn't change the face.
    'STEP_BEVEL': _section(
        ((0.,1.), (.748,1.), (.748,.87), (1.,.30)),
        ((0.,0.), (.412,0.), (.412,.12), (.60,.12), (.60,0.), (1.,0.)),
    ),
}


CASING_PROFILES = {
    'FLAT': LEGACY_BASEBOARD_PROFILES['FLAT'],
    # The show face from jamb to outside: narrow flat lip, clean planar bevel
    # and broad flat high face. The same orientation is used on both jambs.
    'STEP_BEVEL': _section(((0.,.25), (.065,.25), (.34,1.), (1.,1.))),
    # Small inner rounded bead, broad curved sweep, then the flat outside
    # about two fifths of the width, as in the supplied mitered corner.
    'COLONIAL': _section((
        (0.,.22), (.02,.305), (.044,.382), (.064,.419), (.085,.425),
        (.105,.415), (.133,.372), (.149,.364), (.169,.414), (.196,.491),
        (.23,.55), (.269,.579), (.309,.582), (.349,.609), (.391,.666),
        (.436,.751), (.477,.834), (.514,.898), (.548,.929), (.577,.936),
        (.594,.968), (.610,1.), (.985,1.), (1.,.976),
    )),
}


def baseboard(name, revision):
    return (LEGACY_BASEBOARD_PROFILES if revision < REVISION else BASEBOARD_PROFILES)[name]
