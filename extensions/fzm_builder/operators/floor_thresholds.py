"""Physical wall-face outline with shared door-threshold steps.

Public API: floor-local directed datum edges and result; all computations that
choose a physical plane use world space. No mutation of scene, walls or doors.
"""
from dataclasses import dataclass
from math import isfinite

from mathutils import Vector

from .. import hb_types
from . import hinged_doors as hd, hinged_kinematics as kin

EPS = .00002
JOINT = .01
LEVEL = .002
PLANE = .002


@dataclass
class _Line:
    wall: object
    a: Vector
    b: Vector
    tangent: Vector
    inward: Vector
    thickness: Vector

    @property
    def shift(self):
        """Wall datum is one face, with the other at local +Y Thickness."""
        return self.inward*max(0.,self.thickness.dot(self.inward))

    def x(self,point):
        return (point-self.a).dot(self.tangent)

    def point(self,x):
        return self.a + self.shift + x*self.tangent


def _vertices(matrix, leading, end):
    return (matrix @ Vector((*leading,0.))).xy,(matrix @ Vector((*end,0.))).xy


def _finite(values):
    return all(isinstance(v,(int,float)) and isfinite(v) for v in values)


def _wall_data(wall):
    if (not wall or wall.type!='MESH' or not wall.get('IS_WALL_BP')
            or wall.get('IS_FAKE_WALL') or wall.get('WALL_TYPE')=='Fake'):
        return None
    params=hb_types.GeoNodeWall(wall)
    if not all(params.has_input(k) for k in ('Length','Thickness')):
        return None
    length,depth=(params.get_input(k) for k in ('Length','Thickness'))
    if not _finite((length,depth)) or min(length,depth)<=EPS:
        return None
    geom=wall.matrix_world
    origin=geom.translation
    along=geom.to_3x3()@Vector((length,0.,0.))
    thickness=geom.to_3x3()@Vector((0.,depth,0.))
    if (not _finite((*origin,*along,*thickness)) or abs(along.z)>LEVEL or abs(thickness.z)>LEVEL
            or min(along.xy.length,thickness.xy.length)<=EPS
            or abs(along.xy.normalized().dot(thickness.xy))>EPS):
        return None
    return origin,origin+along,thickness.xy


def _cuts(line,scene):
    for mod in line.modifiers:
        if (mod.type!='BOOLEAN' or mod.operation!='DIFFERENCE' or not mod.show_viewport
                or mod.operand_type!='OBJECT'):
            continue
        obj=mod.object
        if (obj and obj.type=='MESH' and obj.parent==line and obj.get('IS_ENTRY_DOOR_BP')
                and obj.name in scene.objects):
            yield obj


def _closed_plane(door,depth):
    # Pocket and Bifold center on the wall; Bypass takes the midpoint between
    # its two closed tracks. The bare Opening/legacy plan-only door also has no
    # slab to offset from midpoint. Never look at the current Open Amount.
    if hd.visual_for(door) and (swing:=hd.swing_for(door)):
        return kin.closed_leaf_y(depth,swing.get_input('Swing Inside'))
    return depth*.5


def _opening(line,door,level):
    cage=hb_types.GeoNodeCage(door)
    if not all(cage.has_input(k) for k in ('Dim X','Dim Y','Dim Z')):
        return None
    width,depth,height=(cage.get_input(k) for k in ('Dim X','Dim Y','Dim Z'))
    if not _finite((width,depth,height)) or min(width,depth,height)<=EPS:
        return None
    transform=door.matrix_world
    start,end=transform.translation,transform@Vector((width,0.,0.))
    far=transform@Vector((0.,depth,0.))
    top=transform@Vector((0.,0.,height))
    normal=line.inward
    # Ignore an aperture that is raised, slanted, moved off its host or no
    # longer cuts through both actual faces (e.g. a stale manually edited cage).
    if (not _finite((*start,*end,*far,*top)) or abs(start.z-level)>LEVEL
            or abs(end.z-start.z)>LEVEL or abs(far.z-start.z)>LEVEL or top.z<=level+LEVEL
            or (top.xy-start.xy).length>PLANE or abs((end.xy-start.xy).dot(normal))>PLANE
            or abs((far.xy-start.xy).dot(line.tangent))>PLANE):
        return None
    physical=sorted((0.,line.thickness.dot(normal)))
    measured=sorted(((start.xy-line.a).dot(normal),(far.xy-line.a).dot(normal)))
    if any(abs(x-y)>PLANE for x,y in zip(physical,measured)):
        return None
    y=_closed_plane(door,depth)
    if not 0. <= y <= depth:
        # Too thin to place the closed leaf center somewhere in the wall.
        return None
    left=transform@Vector((0.,y,0.))
    right=transform@Vector((width,y,0.))
    one,two=sorted((left.xy,right.xy),key=line.x)
    lo,hi=(line.x(p) for p in (one,two))
    if hi-lo<=EPS:
        return None
    closed_normal=(one-line.a).dot(normal)
    if not (physical[0]-EPS<=closed_normal<=physical[1]+EPS):
        return None
    return lo,hi,one,two


def _intersect(a,d,b,e):
    crossing=d.cross(e)
    if abs(crossing)<=EPS:
        return None
    return a+d*((b-a).cross(e)/crossing)


def _physical_joint(first,second):
    junction=(first.b+second.a)*.5
    a,b=first.a+first.shift,second.a+second.shift
    d,e=first.tangent,second.tangent
    p=_intersect(a,d,b,e)
    if p is not None:
        if (p-junction).length>max(.15,8*max(first.thickness.length,second.thickness.length)):
            raise ValueError('A wall corner is too acute to resolve the physical floor edge safely.')
        return p,p
    if d.dot(e)<0.:
        raise ValueError('The physical floor boundary turns back along one wall.')
    # Straight neighbors can have different wall thicknesses. In that case
    # preserve the short physical step rather than extending parallel lines.
    p=a+d*((junction-a).dot(d))
    q=b+e*((junction-b).dot(e))
    return p,q


def _safe_jamb_span(line, walls, *, partial=False):
    """Corner keep-out using all incident physical walls from either room side.

    A corner-spanning opening is unsafe to extend *on either side*: use the
    same projected obstruction interval regardless of logical ring winding.
    """
    first=0.
    last=line.x(line.b)
    for w,data in walls:
        if w==line.wall:
            continue
        a,b,thickness=data
        if (b.xy-a.xy).length<=EPS:
            continue
        d=(b.xy-a.xy).normalized()
        for corner,leading in ((line.a,True),(line.b,False)):
            if min((corner-a.xy).length,(corner-b.xy).length)>JOINT:
                if not partial:
                    continue
                # Logical T/X nodes on a long wall may be mid-edge, or the
                # real branch ends at the host's offset face. Use the actual
                # footprint plus their wall thickness, not only endpoints.
                rel = corner-a.xy
                v = rel.cross(d)
                far = thickness.cross(d)
                axis = rel.dot(d)
                reach = line.thickness.length+JOINT
                if not (min(0.,far)-JOINT<=v<=max(0.,far)+JOINT
                        and -reach<=axis<=(b.xy-a.xy).length+reach):
                    continue
            for pos in (line.a,line.a+line.thickness):
                for other in (a.xy,a.xy+thickness):
                    point=_intersect(pos,line.tangent,other,d)
                    if point is None:
                        continue
                    extent=line.x(point)
                    if leading:
                        first=max(first,extent)
                    else:
                        last=min(last,extent)
    return first,last


def _unambiguous(openings):
    """Remove all intervals participating in an overlap/touching cluster."""
    result=[]
    groups=[]
    upper=None
    for obj,entry in sorted(openings,key=lambda row:row[1][:2]):
        lo,hi,*_=entry
        if upper is None or lo>upper+EPS:
            if groups:
                result.append(groups)
            groups=[(obj,entry)]
            upper=hi
        else:
            groups.append((obj,entry))
            upper=max(upper,hi)
    if groups:
        result.append(groups)
    return [group[0] for group in result if len(group)==1]


def physical_floor_ring(edges, floor_matrix, level, scene, *, interior=True, warnings=None, partial=False):
    """Return floor-local XY from ordered (wall, datum start XY, datum end XY).

    ``level`` is the world Z of the slab top. A normal room ring uses
    ``interior=True``; a room bordering the outside of a cutout ring uses False.
    For a ring with no safe real door openings the original datum is returned.
    An opening that crosses a corner or another opening is not partially drawn.
    The caller must check the returned ring for intersections before committing.
    """
    edges=[(w,Vector(a).to_2d(),Vector(b).to_2d()) for w,a,b in edges]
    datum=[a.copy() for _,a,_ in edges]
    if len(edges)<3:
        raise ValueError('At least three physical wall edges are required.')
    doors=[list(dict.fromkeys(_cuts(w,scene))) for w,_,_ in edges]
    if not partial and not any(doors):
        return datum
    world=[_vertices(floor_matrix,a,b) for _,a,b in edges]
    reference=world[0][0]
    space=sum((a-reference).cross(world[(i+1)%len(world)][0]-reference) for i,(a,_) in enumerate(world))
    if abs(space)<=EPS:
        raise ValueError('The floor datum does not enclose enough area.')
    sign=1 if (space>0)==interior else -1
    lines=[]
    for (wall,_,_),(a,b) in zip(edges,world):
        data=_wall_data(wall)
        if not data or (b-a).length<=EPS:
            raise ValueError('A physical wall face could not be resolved for this floor.')
        p,q,depth=data
        same=min(max((a-p.xy).length,(b-q.xy).length),max((a-q.xy).length,(b-p.xy).length))
        if partial:
            axis=(q.xy-p.xy).normalized()
            # A T junction may lie slightly beyond a partition's short end:
            # that endpoint was placed against the thick host's actual face.
            same=max(abs((v-p.xy).cross(axis)) for v in (a,b))
        if same>JOINT or abs(p.z-level)>LEVEL:
            raise ValueError('A floor edge is not aligned to its physical host wall.')
        d=(b-a).normalized()
        lines.append(_Line(wall,a,b,d,Vector((-d.y,d.x))*sign,depth))
    candidates=[[(door,item) for door in group if (item:=_opening(line,door,level))]
                for line,group in zip(lines,doors)]
    if not partial and not any(candidates):
        return datum
    nearby=[]
    for obj in scene.objects:
        if (data:=_wall_data(obj)) and abs(data[0].z-level)<=LEVEL:
            nearby.append((obj,data))
    accepted=[]
    for line,cases in zip(lines,candidates):
        if not cases:
            accepted.append([])
            continue
        protected=_safe_jamb_span(line,nearby,partial=partial)
        good=[]
        clear=_unambiguous(cases)
        if warnings is not None and len(clear)!=len(cases):
            warnings.append(f'{line.wall.name}: overlapping door cuts could not extend the floor.')
        for obj,item in clear:
            lo,hi,*_=item
            if partial and (hi<=EPS or lo>=line.x(line.b)-EPS):
                # A shared long wall may own doors in an adjacent region.
                continue
            if lo<=protected[0]+EPS or hi>=protected[1]-EPS:
                if warnings is not None:
                    warnings.append(f'{obj.name}: opening touches a wall corner; threshold not built.')
                continue
            good.append((obj,item))
        accepted.append(good)
    if not partial and not any(accepted):
        return datum
    joins=[_physical_joint(p,c) for p,c in zip(lines[-1:]+lines[:-1],lines)]
    result=[]
    def append(p):
        if not result or (p-result[-1]).length>EPS:
            result.append(p)
    for i,line in enumerate(lines):
        start,end=joins[i][1],joins[(i+1)%len(lines)][0]
        lo,hi=line.x(start),line.x(end)
        if hi-lo<=EPS:
            raise ValueError('The physical wall faces consume one floor edge.')
        append(start)
        for obj,(door_lo,door_hi,near,far) in accepted[i]:
            if door_lo<=lo+EPS or door_hi>=hi-EPS:
                raise ValueError(f'{obj.name}: the full threshold would cross a mitered wall corner.')
            append(line.point(door_lo))
            append(near);append(far)
            append(line.point(door_hi))
        append(end)
    if (result[0]-result[-1]).length<=EPS:
        result.pop()
    new_area=sum((a-reference).cross(b-reference) for a,b in zip(result,result[1:]+result[:1]))
    if new_area*space<=EPS*EPS:
        raise ValueError('The physical wall faces no longer enclose the same floor region.')
    inverse=floor_matrix.inverted()
    return [(inverse@Vector((*p,level))).xy for p in result]
