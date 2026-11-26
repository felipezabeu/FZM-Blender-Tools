"""Numeric visual snap search. Never mutates wall geometry or its link graph."""
from dataclasses import dataclass
from math import hypot, isfinite

EPS = 1e-6
PIXELS = 17.
END_BIAS = 4.


@dataclass(frozen=True)
class Guide:
    name: str
    start: tuple
    end: tuple


@dataclass(frozen=True)
class Hit:
    kind: str
    guide: Guide
    reference: str
    point: tuple
    offset: tuple
    pixels: float


def _on_edge(p,a,b,axis):
    dx,dy=b[0]-a[0],b[1]-a[1]
    if axis=='FREE':
        squared=dx*dx+dy*dy
        if squared<EPS*EPS:
            return None
        t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/squared
    else:
        locked=1 if axis=='X' else 0
        moving=1-locked
        span=b[locked]-a[locked]
        if abs(span)<=EPS:
            if abs(p[locked]-a[locked])>EPS:
                return None
            free_span=b[moving]-a[moving]
            if abs(free_span)<=EPS:
                return None
            # Already on the same geometric line; the clamp below gives
            # the nearest end if the pointer lies beyond the segment.
            t=(p[moving]-a[moving])/free_span
            t=min(1.,max(0.,t))
        else:
            t=(p[locked]-a[locked])/span
    if t < -EPS or t > 1.+EPS:
        return None
    t=min(1.,max(0.,t))
    pt=(a[0]+t*dx,a[1]+t*dy)
    if axis!='FREE' and abs(pt[locked]-p[locked])>EPS:
        return None
    return pt


def candidates(anchors, offset, guides, axis, project, pixel_radius=PIXELS):
    """Rank wall snaps by pixel correction, then stable tie-breakers.

    Anchors are ``(label, (x,y))``; whole-wall anchors share one translation.
    ``project`` converts XY to screen XY or None. In locked mode only targets
    on that exact X/Y trajectory are eligible. A corner receives a small
    screen-pixel preference over an adjacent edge, not unconditional capture.
    """
    if axis not in ('FREE','X','Y') or not all(isfinite(x) for x in offset):
        return []
    found=[]
    for index,(name,anchor) in enumerate(anchors):
        p=(anchor[0]+offset[0],anchor[1]+offset[1])
        pp=project(p)
        if pp is None:
            continue
        for guide in guides:
            a,b=guide.start,guide.end
            targets=[('CORNER',a),('CORNER',b)]
            if (closest:=_on_edge(p,a,b,axis)) is not None:
                targets.append(('EDGE',closest))
            for kind,target in targets:
                dx,dy=target[0]-anchor[0],target[1]-anchor[1]
                if axis=='X':
                    if abs(dy)>EPS:continue
                    dy=0.
                if axis=='Y':
                    if abs(dx)>EPS:continue
                    dx=0.
                screen=project(target)
                if screen is None:
                    continue
                distance=hypot(screen[0]-pp[0],screen[1]-pp[1])
                if distance<=pixel_radius:
                    hit=Hit(kind,guide,name,target,(dx,dy),distance)
                    rank=(distance-(END_BIAS if kind=='CORNER' else 0.),distance,index,guide.name,
                          target[0],target[1])
                    found.append((rank,hit))
    unique={}
    for _,hit in sorted(found,key=lambda pair:pair[0]):
        key=tuple(round(x,7) for x in hit.offset)
        unique.setdefault(key,hit)
    return list(unique.values())


@dataclass(frozen=True)
class SquareGuide:
    name: str
    joint: tuple
    first: tuple
    neighbor: tuple
    moves_joint: bool
    moves_first: bool
    moves_neighbor: bool


@dataclass(frozen=True)
class SquareHit:
    guide: SquareGuide
    offset: tuple
    pixels: float


def _plus(a,b,s=1.):
    return a[0]+b[0]*s,a[1]+b[1]*s


def _dot(a,b):
    return a[0]*b[0]+a[1]*b[1]


def _equation(g):
    """(u + kt) dot (v + lt) = A|t|² + B*t.x + C*t.y + D."""
    u,v=_plus(g.first,g.joint,-1.),_plus(g.neighbor,g.joint,-1.)
    k,l=int(g.moves_first)-int(g.moves_joint),int(g.moves_neighbor)-int(g.moves_joint)
    return k*l, (k*v[0]+l*u[0],k*v[1]+l*u[1]), _dot(u,v)


def _solutions(g,raw,axis):
    from math import sqrt
    strength,normal,constant=_equation(g)
    if axis in ('X','Y'):
        coordinate=0 if axis=='X' else 1
        term=normal[coordinate]
        if strength:
            disc=term*term-4.*strength*constant
            if disc < -EPS:
                return ()
            r=sqrt(max(0.,disc))
            possible=((-term+r)/(2.*strength),(-term-r)/(2.*strength))
        elif abs(term)>EPS:
            possible=(-constant/term,)
        else:
            return ()
        return tuple((a,0.) if coordinate==0 else (0.,a) for a in possible)
    if strength:
        center=tuple(-x/(2.*strength) for x in normal)
        radius_sq=_dot(center,center)-constant/strength
        away=_plus(raw,center,-1.)
        length=hypot(*away)
        if radius_sq < -EPS or not length>EPS:
            return ()
        return (_plus(center,away,sqrt(max(0.,radius_sq))/length),)
    length_sq=_dot(normal,normal)
    if length_sq<=EPS*EPS:
        return ()
    return (_plus(raw,normal,-(_dot(normal,raw)+constant)/length_sq),)


def square_geometry(guide,offset):
    joint=_plus(guide.joint,offset,float(guide.moves_joint))
    a=_plus(guide.first,offset,float(guide.moves_first))
    b=_plus(guide.neighbor,offset,float(guide.moves_neighbor))
    u,v=_plus(a,joint,-1.),_plus(b,joint,-1.)
    l1,l2=hypot(*u),hypot(*v)
    if min(l1,l2)<.0254:
        return None
    return joint,(u[0]/l1,u[1]/l1),(v[0]/l2,v[1]/l2),min(l1,l2)


def square_candidates(guides,reference,offset,axis,project,pixel_radius=PIXELS):
    """Nearest exact 90° on a connected joint, measuring correction in screen pixels."""
    p=project(_plus(reference,offset))
    if p is None:
        return []
    result=[]
    for g in guides:
        for t in _solutions(g,offset,axis):
            q=project(_plus(reference,t))
            data=square_geometry(g,t)
            if q is None or data is None or abs(_dot(data[1],data[2]))>EPS:
                continue
            distance=hypot(q[0]-p[0],q[1]-p[1])
            if distance<=pixel_radius:
                result.append(SquareHit(g,t,distance))
    return sorted(result,key=lambda hit:(hit.pixels,hit.guide.name,hit.offset))


def square_markers(guides,offset):
    """Return visually 90-degree corners even if the user disables square snap."""
    result=[]
    for guide in guides:
        data=square_geometry(guide,offset)
        if data and abs(_dot(data[1],data[2]))<=.007:  # ~0.4° on either side of 90°.
            result.append(data)
    return result
