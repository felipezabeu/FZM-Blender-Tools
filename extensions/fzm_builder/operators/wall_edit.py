"""Geometry-preserving edits of Builder wall joints. No constraints are removed."""

from dataclasses import dataclass
from math import atan2, hypot, pi, isfinite

from .. import hb_types

MIN_LENGTH = 0.0254
EPS = 1e-5
START, END = 0, 1


@dataclass
class Segment:
    start: tuple
    end: tuple

    def __getitem__(self, index):
        return (self.start, self.end)[index]

    @property
    def length(self):
        return hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def angle(self):
        return atan2(self.end[1] - self.start[1], self.end[0] - self.start[0])


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


class Graph:
    def __init__(self, geometry, joints):
        self.geometry = geometry
        self.members = {(w, side): {(w, side)} for w in geometry for side in (START, END)}
        for a, b in joints:
            if a not in self.members or b not in self.members or a[0] == b[0]:
                continue
            union = self.members[a] | self.members[b]
            for node in union:
                self.members[node] = union

    def plan(self, wall, mode, dx, dy):
        if mode not in ('START', 'END', 'MOVE') or not (isfinite(dx) and isfinite(dy)):
            raise ValueError('Invalid wall displacement.')
        modes = {'START': (START,), 'END': (END,), 'MOVE': (START, END)}
        desired = {}
        if abs(dx) <= EPS and abs(dy) <= EPS:
            return {}
        for side in modes[mode]:
            p = self.geometry[wall][side]
            q = p[0] + dx, p[1] + dy
            for key in self.members[(wall, side)]:
                if key in desired and distance(desired[key], q) > EPS:
                    raise ValueError('This wall has both ends attached to the same joint.')
                desired[key] = q
        result = {w: Segment(desired.get((w, START), self.geometry[w].start),
                             desired.get((w, END), self.geometry[w].end))
                  for w, _ in desired}
        if any(s.length < MIN_LENGTH for s in result.values()):
            raise ValueError('The edit would collapse a wall or make it shorter than 1 inch.')
        if any(abs((s.angle - self.geometry[w].angle + pi) % (2*pi) - pi) >= pi/2 + EPS
               for w, s in result.items()):
            raise ValueError('The edit would reverse a wall. Move it in smaller steps.')
        return result


@dataclass
class SceneGraph:
    graph: Graph
    walls: dict
    levels: dict
    constraints: dict

    @classmethod
    def read(cls, context):
        context.view_layer.update()
        geometry, models, levels, constraints, links = {}, {}, {}, {}, []
        for obj in context.scene.objects:
            if not obj.get('IS_WALL_BP'):
                continue
            model = hb_types.GeoNodeWall(obj)
            if not model.obj_x or not model.has_input('Length'):
                continue
            a = obj.matrix_world.translation
            b = obj.matrix_world @ type(a)((model.get_input('Length'), 0., 0.))
            geometry[obj] = Segment((a.x, a.y), (b.x, b.y))
            levels[obj] = a.z
            models[obj] = model
        for obj, model in models.items():
            constraints[obj] = []
            for con in obj.constraints:
                if con.mute or con.influence <= EPS:
                    continue
                target = getattr(con, 'target', None)
                prior = target.parent if target else None
                if (con.type == 'COPY_LOCATION' and prior in models
                        and target == models[prior].obj_x and con.influence == 1
                        and con.use_x and con.use_y and con.use_z and not con.use_offset
                        and not (con.invert_x or con.invert_y or con.invert_z)
                        and con.owner_space == 'WORLD' and con.target_space == 'WORLD'
                        and abs(levels[obj] - levels[prior]) <= EPS):
                    constraints[obj].append(con)
                    links.append(((prior, END), (obj, START)))
                else:
                    constraints[obj].append(None)
            # Draw Walls saves this pointer for the final closure without a
            # constraint, to avoid a Blender dependency cycle. Keep that joint.
            target = model.obj_x.home_builder.connected_object
            if target in models and abs(levels[obj] - levels[target]) <= EPS:
                links.append(((obj, END), (target, START)))
            # New Draw Walls start-to-start snaps persist an explicit identity.
            start_peer = obj.get('FZM_WALL_START_PEER')
            if start_peer in models and abs(levels[obj] - levels[start_peer]) <= EPS:
                links.append(((obj, START), (start_peer, START)))
        return cls(Graph(geometry, links), models, levels, constraints)

    def checked_plan(self, obj, mode, dx, dy):
        plan = self.graph.plan(obj, mode, dx, dy)
        for wall, segment in plan.items():
            if (wall.library or wall.override_library or wall.parent or any(c is None for c in self.constraints[wall])
                    or len(self.constraints[wall]) > 1
                    or wall.rotation_mode != 'XYZ' or abs(wall.rotation_euler.x) > EPS
                    or abs(wall.rotation_euler.y) > EPS or any(abs(v - 1) > EPS for v in wall.scale)
                    or any(abs(v) > EPS for v in wall.delta_location)
                    or any(abs(v) > EPS for v in wall.delta_rotation_euler)
                    or any(abs(v - 1) > EPS for v in wall.delta_scale)
                    or (wall.animation_data and (wall.animation_data.action or len(wall.animation_data.drivers)))):
                raise ValueError(f'{wall.name}: linked, animated, or has unsupported transforms or constraints.')
            # Door/window offsets remain physical distances from the host start.
            # Never allow the wall to get shorter than an opening it already hosts.
            if segment.length < self.graph.geometry[wall].length - EPS:
                for item in wall.children:
                    if not (item.get('IS_ENTRY_DOOR_BP') or item.get('IS_WINDOW_BP')):
                        continue
                    cage = hb_types.GeoNodeCage(item)
                    if not cage.has_input('Dim X'):
                        continue
                    x, width = item.location.x, cage.get_input('Dim X')
                    if max(x, x + width) > segment.length + EPS:
                        raise ValueError(f'{wall.name}: shortening would cut through {item.name}. Move the opening first.')
        return plan

    def commit(self, context, plan):
        if not plan:
            return
        from .floor_outline import legacy_before_wall_edit, save_legacy_bindings
        # Record an exact older room perimeter before it moves. This never
        # regenerates floor geometry, which remains an explicit separate command.
        bindings = legacy_before_wall_edit(context, plan)
        angles = {}
        for key in [(wall, side) for wall in plan for side in (START, END)]:
            nodes = self.graph.members[key]
            if len(nodes) == 2:
                before = next((w for w, side in nodes if side == END), None)
                after = next((w for w, side in nodes if side == START), None)
                if before is not None and after is not None:
                    incoming = (plan.get(before) or self.graph.geometry[before]).angle
                    outgoing = (plan.get(after) or self.graph.geometry[after]).angle
                    turn = (outgoing - incoming + pi) % (2*pi) - pi
                    angles[(before, END)] = -turn / 2
                    angles[(after, START)] = turn / 2
            elif len(nodes) > 2:
                for wall, side in nodes:
                    if not wall.library and not wall.override_library:
                        angles[(wall, side)] = 0.0
        snapshots = {obj: (obj.location.copy(), obj.rotation_euler.z, self.walls[obj].get_input('Length'))
                     for obj in plan}
        previous = {}
        try:
            for obj, segment in plan.items():
                obj.location.x, obj.location.y = segment.start
                obj.rotation_euler.z = segment.angle
                self.walls[obj].set_input('Length', segment.length)
                obj.update_tag()
            for (obj, side), angle in angles.items():
                socket = 'Left Angle' if side == START else 'Right Angle'
                if not obj.library and not obj.override_library and self.walls[obj].has_input(socket):
                    previous[(obj, socket)] = self.walls[obj].get_input(socket)
                    self.walls[obj].set_input(socket, angle)
            context.view_layer.update()
            for obj, segment in plan.items():
                start = obj.matrix_world.translation
                end = obj.matrix_world @ type(start)((segment.length, 0., 0.))
                if distance(start, segment.start) > EPS * 8 or distance(end, segment.end) > EPS * 8:
                    raise ValueError(f'{obj.name}: its loaded connections prevent the requested edit.')
        except (RuntimeError, ValueError, KeyError, TypeError, AttributeError):
            for obj, (loc, angle, length) in snapshots.items():
                obj.location, obj.rotation_euler.z = loc, angle
                self.walls[obj].set_input('Length', length)
                obj.update_tag()
            for (obj, socket), value in previous.items():
                self.walls[obj].set_input(socket, value)
            context.view_layer.update()
            raise
        save_legacy_bindings(bindings)
