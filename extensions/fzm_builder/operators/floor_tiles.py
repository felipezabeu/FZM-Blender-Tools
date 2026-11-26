"""Tile layout controls for a Floor region, independent of its base finish."""
from dataclasses import asdict

import bpy

from .tile_shader import (
    FLOOR_PATTERNS, TileSpec, base_material, dispose_if_unused, tile_material, validate,
)

LAYOUT = "FZM_FLOOR_TILE_LAYOUT"


def get_spec(floor):
    saved = floor.get(LAYOUT)
    if not saved:
        return None
    return TileSpec(pattern=saved['pattern'], width=saved['width'], height=saved['height'],
        grout=saved['grout'], angle=saved['angle'], offset_u=saved['offset_u'],
        offset_v=saved['offset_v'], color=tuple(saved['color']))


def floor_surface_indices(obj):
    if not obj.data.vertices:
        raise ValueError("Select a generated floor with geometry.")
    top = max(v.co.z for v in obj.data.vertices)
    indices = {poly.material_index for poly in obj.data.polygons if all(
        abs(obj.data.vertices[i].co.z - top) <= 1e-5 for i in poly.vertices
    )}
    if not indices:
        raise ValueError("This floor has no horizontal surface.")
    return sorted(indices)


def assign_slots(obj, replacements):
    previous = [obj.material_slots[index].material for index in replacements
                if index < len(obj.material_slots)]
    if obj.data.users > 1:
        obj.data = obj.data.copy()
    for index, material in replacements.items():
        if index >= len(obj.material_slots):
            if material is None:
                continue
            obj.data.materials.append(material)
        slot = obj.material_slots[index]
        slot.link = 'OBJECT'
        slot.material = material
    for mat_name in {m.name for m in previous if m}:
        dispose_if_unused(bpy.data.materials.get(mat_name))


def apply_floor_base_finish(obj, finish):
    """Replace only finish, rebuilding its tile shader if this region has one."""
    indexes = floor_surface_indices(obj)
    settings = get_spec(obj)
    material = tile_material(finish, settings) if settings else finish
    assign_slots(obj, {index: material for index in indexes})


def apply_layout(floor, spec):
    indices = floor_surface_indices(floor)
    if spec:
        validate(spec)
        if 'UVMap' not in floor.data.uv_layers:
            raise ValueError("This floor needs the generated metric UVMap for tiles.")
    replacements, new = {}, {}
    try:
        for index in indices:
            current = floor.material_slots[index].material if index < len(floor.material_slots) else None
            base = base_material(current)
            if spec is None:
                if current != base:
                    replacements[index] = base
            else:
                if base not in new:
                    new[base] = tile_material(base, spec)
                replacements[index] = new[base]
        assign_slots(floor, replacements)
        if spec:
            floor[LAYOUT] = asdict(spec)
        elif LAYOUT in floor:
            del floor[LAYOUT]
    except Exception:
        for mat in new.values():
            dispose_if_unused(mat)
        raise


class FZM_OT_floor_tile_layout(bpy.types.Operator):
    bl_idname = 'fzm_builder.floor_tile_layout'
    bl_label = 'Floor Tile Layout'
    bl_description = 'Set tile size, grout and layout on the active floor without replacing its finish'
    bl_options = {'UNDO'}

    pattern: bpy.props.EnumProperty(name='Layout', items=FLOOR_PATTERNS, default='STACK')
    tile_width: bpy.props.FloatProperty(name='Tile Width', unit='LENGTH', min=.01, max=10., default=.6096)
    tile_height: bpy.props.FloatProperty(name='Tile Length', unit='LENGTH', min=.01, max=10., default=.3048)
    grout: bpy.props.FloatProperty(name='Grout Width', unit='LENGTH', min=0., max=.10, default=.003)
    angle: bpy.props.FloatProperty(name='Rotation', unit='ROTATION', subtype='ANGLE')
    offset_u: bpy.props.FloatProperty(name='Shift Along Tile X', unit='LENGTH')
    offset_v: bpy.props.FloatProperty(name='Shift Along Tile Y', unit='LENGTH')
    grout_color: bpy.props.FloatVectorProperty(name='Grout Color', size=4, min=0., max=1.,
        subtype='COLOR', default=(.24, .23, .21, 1.))

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH' and bool(obj.get('IS_FLOOR_BP'))

    def invoke(self, context, event):
        spec = get_spec(context.active_object) or TileSpec()
        self.pattern, self.tile_width, self.tile_height = spec.pattern, spec.width, spec.height
        self.grout, self.angle = spec.grout, spec.angle
        self.offset_u, self.offset_v, self.grout_color = spec.offset_u, spec.offset_v, spec.color
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'pattern')
        if self.pattern != 'NONE':
            for name in ('tile_width', 'tile_height', 'grout', 'angle', 'offset_u', 'offset_v', 'grout_color'):
                layout.prop(self, name)
            layout.label(text='This changes joints, not the selected Floor Finish.')
            layout.label(text='View in Material Preview or Rendered mode.')

    def execute(self, context):
        spec = None if self.pattern == 'NONE' else TileSpec(
            self.pattern, self.tile_width, self.tile_height, self.grout, self.angle,
            self.offset_u, self.offset_v, tuple(self.grout_color))
        try:
            apply_layout(context.active_object, spec)
        except (ValueError, RuntimeError) as err:
            self.report({'WARNING'}, str(err))
            return {'CANCELLED'}
        return {'FINISHED'}
