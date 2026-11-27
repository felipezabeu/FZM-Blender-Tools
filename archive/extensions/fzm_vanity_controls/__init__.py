"""FZM Vanity Controls 1.2.1 — Blender 5.1+.
Non-destructive finish picker for the FZM Vanity Master 30.
Geometric changes are made in the master asset, not in the finish controls.
"""
bl_info = {
    "name": "FZM Vanity Controls",
    "author": "FZM Renovations",
    "version": (1, 2, 1),
    "blender": (5, 1, 0),
    "location": "3D View > Sidebar (N) > FZM Vanity",
    "description": "Vanity base, countertop, hardware and splash controls",
    "category": "3D View",
}

import bpy
from bpy.props import BoolProperty, EnumProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

CTRL_PREFIX = "Vanity_30_Controller"
ROLES = ("Vanity_Base", "Vanity_Top", "Undermount_Sink", "Backsplash_4in", "Sidesplash_Left", "Sidesplash_Right")


def _part_name(ob):
    return ob.get("FZM_Role") or next((r for r in ROLES if ob.name.startswith(r)), "")


def _find_controller(obj):
    if obj is None:
        return None
    cursor = obj
    while cursor:
        if cursor.name.startswith(CTRL_PREFIX):
            return cursor
        cursor = cursor.parent
    for collection in obj.users_collection:
        for item in collection.objects:
            if item.name.startswith(CTRL_PREFIX):
                return item
    return None


def _parts(ctrl):
    return {_part_name(o): o for o in ctrl.children_recursive if _part_name(o) in ROLES}


def _srgb(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _rgb(hexval):
    vals = [int(hexval[i:i+2], 16) / 255.0 for i in (1, 3, 5)]
    return tuple(_srgb(v) for v in vals)


def _flat_material(name, color, metallic=0.0, roughness=0.43):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_fake_user = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if not bsdf:
        bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    rgb = _rgb(color)
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    m.diffuse_color = (*rgb, 1.0)
    return m


def _marble_material(name, base_hex, vein_hex, band_scale, roughness=.26):
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_fake_user = True
    tree = m.node_tree
    n = tree.nodes
    l = tree.links
    bsdf = next(v for v in n if v.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Metallic'].default_value = 0.0
    bsdf.inputs['Roughness'].default_value = roughness
    uv = n.new('ShaderNodeTexCoord'); uv.location = (-830, 100)
    noise = n.new('ShaderNodeTexNoise'); noise.location = (-620, -130)
    noise.inputs['Scale'].default_value = 4.5
    noise.inputs['Detail'].default_value = 5.0
    noise.inputs['Roughness'].default_value = 0.7
    l.new(uv.outputs['Generated'], noise.inputs['Vector'])
    wave = n.new('ShaderNodeTexWave'); wave.location = (-350, 110)
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'DIAGONAL'
    wave.inputs['Scale'].default_value = band_scale
    wave.inputs['Distortion'].default_value = 3.5
    wave.inputs['Detail'].default_value = 3.0
    l.new(noise.outputs['Color'], wave.inputs['Vector'])
    ramp = n.new('ShaderNodeValToRGB'); ramp.location = (-120, 110)
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[-1])
    entries = [
        (0.00, base_hex),
        (0.44, base_hex),
        (0.490, vein_hex),
        (0.535, base_hex),
        (1.00, base_hex),
    ]
    for i, (pos, color) in enumerate(entries):
        element = ramp.color_ramp.elements[0] if i == 0 else ramp.color_ramp.elements.new(pos)
        element.position = pos
        element.color = (*_rgb(color), 1.0)
    l.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    l.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    return m




def _wood_material(name):
    """Light natural oak look; procedural approximation, not a supplier texture."""
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_fake_user = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    shader.inputs['Roughness'].default_value = .56
    coords = nodes.new('ShaderNodeTexCoord'); coords.location = (-720, 40)
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = (1.0, .70, .65); mapping.location = (-510, 40)
    links.new(coords.outputs['Generated'], mapping.inputs[0])
    wave = nodes.new('ShaderNodeTexWave'); wave.location = (-290, 40)
    wave.wave_type = 'BANDS'; wave.bands_direction = 'X'
    wave.inputs['Scale'].default_value = 18.0
    wave.inputs['Distortion'].default_value = 1.9
    wave.inputs['Detail'].default_value = 3.0
    links.new(mapping.outputs['Vector'], wave.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB'); ramp.location = (-70, 40)
    # Golden wood grain: pale oak with moderately darker narrow fibers.
    colors = [(0.0, '#BD9360'), (.20, '#D0A873'), (.45, '#E1BB85'),
              (.75, '#E9C897'), (1.0, '#D8B27E')]
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[-1])
    for i, (pos, col) in enumerate(colors):
        element = ramp.color_ramp.elements[0] if i == 0 else ramp.color_ramp.elements.new(pos)
        element.position = pos
        element.color = (*_rgb(col), 1.0)
    links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
    mat.diffuse_color = (*_rgb('#DAB887'), 1.0)
    return mat


def _bold_marble_material(name):
    """White veined stone inspired by user's reference; procedural, non-seamless exact match."""
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.use_fake_user = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    shader.inputs['Roughness'].default_value = .21
    tex = nodes.new('ShaderNodeTexCoord'); tex.location = (-900, 80)
    noise = nodes.new('ShaderNodeTexNoise'); noise.location = (-660, -160)
    noise.inputs['Scale'].default_value = 3.8
    noise.inputs['Detail'].default_value = 5.5
    noise.inputs['Roughness'].default_value = .72
    links.new(tex.outputs['Generated'], noise.inputs['Vector'])
    warp = nodes.new('ShaderNodeVectorMath'); warp.operation = 'MULTIPLY_ADD'
    warp.location = (-450, 40)
    warp.inputs[1].default_value = (.36, .43, .32)
    links.new(noise.outputs['Color'], warp.inputs[0])
    links.new(tex.outputs['Generated'], warp.inputs[2])
    wave = nodes.new('ShaderNodeTexWave'); wave.location = (-220, 40)
    wave.wave_type = 'BANDS'; wave.bands_direction = 'DIAGONAL'
    wave.inputs['Scale'].default_value = 2.6
    wave.inputs['Distortion'].default_value = 5.2
    wave.inputs['Detail'].default_value = 5.0
    links.new(warp.outputs['Vector'], wave.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB'); ramp.location = (10, 40)
    colors = [(0.0, '#F6F5F3'), (.40, '#F3F2F1'), (.455, '#C0BEC0'),
              (.490, '#777679'), (.505, '#6F6C70'), (.535, '#D7D5D5'),
              (.60, '#F5F4F2'), (1.0, '#F7F6F5')]
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[-1])
    for i, (pos, col) in enumerate(colors):
        e = ramp.color_ramp.elements[0] if i == 0 else ramp.color_ramp.elements.new(pos)
        e.position = pos
        e.color = (*_rgb(col), 1.0)
    links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
    mat.diffuse_color = (*_rgb('#F5F4F2'), 1.0)
    return mat


def _preset_material(group, code):
    key = f"FZM_Vanity_12_{group}_{code}"
    if group == 'base':
        if code == 'OAK':
            return _wood_material(key)
        return _flat_material(key, {
            'WHITE': '#E7E7E4', 'GRAY': '#777B80', 'BLUE': '#344760',
        }[code], .01, .49)
    if group == 'hardware':
        color, metal, rough = {
            'BLACK': ('#27292C', .68, .48),
            'CHROME': ('#C7CCD1', .95, .15),
            'GOLD': ('#CAA365', .85, .30),
        }[code]
        return _flat_material(key, color, metal, rough)
    if group == 'top':
        if code == 'CALACATTA':
            return _bold_marble_material(key)
        return _flat_material(key, {
            'WHITE': '#F3F2EF', 'CHARCOAL': '#414449', 'CONCRETE': '#A5A7A5',
        }[code], 0, .30)
    raise ValueError((group, code))


def _unique_mesh(ob):
    if ob.data and ob.data.users > 1:
        ob.data = ob.data.copy()


def _assign_material_by_role(ob, group, material):
    """Only alter relevant material slots, preserving seam, sink and drain."""
    if ob is None or ob.type != 'MESH':
        return
    _unique_mesh(ob)
    if group == 'top':
        for slot in range(len(ob.data.materials)):
            ob.data.materials[slot] = material
        return
    for index, old in enumerate(ob.data.materials):
        oldname = old.name.lower() if old else ''
        is_metal = ('metal_' in oldname or 'hardware' in oldname or 'chrome' in oldname)
        is_shadow = ('seam' in oldname or 'shadow' in oldname)
        if group == 'hardware' and is_metal:
            ob.data.materials[index] = material
        if group == 'base' and not (is_metal or is_shadow):
            ob.data.materials[index] = material


def _visible(ob, state):
    if ob is None:
        return
    ob.hide_render = not state
    try:
        ob.hide_set(not state)
    except RuntimeError:
        ob.hide_viewport = not state


def _update_finish(self, context):
    ctrl = self.id_data
    if ctrl is None or not ctrl.name.startswith(CTRL_PREFIX):
        return
    parts = _parts(ctrl)
    if not parts:
        return
    _assign_material_by_role(parts.get('Vanity_Base'), 'base', _preset_material('base', self.base_color))
    _assign_material_by_role(parts.get('Vanity_Base'), 'hardware', _preset_material('hardware', self.hardware_color))
    mat = _preset_material('top', self.top_finish)
    for role in ('Vanity_Top', 'Backsplash_4in', 'Sidesplash_Left', 'Sidesplash_Right'):
        _assign_material_by_role(parts.get(role), 'top', mat)


def _update_splashes(self, context):
    ctrl = self.id_data
    if ctrl is None or not ctrl.name.startswith(CTRL_PREFIX):
        return
    parts = _parts(ctrl)
    for role, show in [('Backsplash_4in', self.back_splash),
                       ('Sidesplash_Left', self.left_splash),
                       ('Sidesplash_Right', self.right_splash)]:
        _visible(parts.get(role), show)


class FZM_VanitySettings(PropertyGroup):
    base_color: EnumProperty(
        name="Gabinete", description="Acabamento do gabinete",
        items=[('WHITE', "Branco", ""), ('GRAY', "Cinza medio", ""),
               ('BLUE', "Azul marinho", ""), ('OAK', "Carvalho claro", "Madeira clara visual (nao produto exato)")],
        default='WHITE', update=_update_finish)
    top_finish: EnumProperty(
        name="Tampo", description="Acabamento visual do top (não é produto de fornecedor)",
        items=[('WHITE', "Quartz Branco", "", 0),
               ('CALACATTA', "Branco veios marcados", "Estilo da referencia; procedural, nao pedra exata", 2),
               ('CHARCOAL', "Quartz Escuro", "", 3),
               ('CONCRETE', "Concreto Cinza", "", 4)],
        default='WHITE', update=_update_finish)
    hardware_color: EnumProperty(
        name="Puxadores", description="Cor dos puxadores da base",
        items=[('BLACK', "Matte Black", ""), ('CHROME', "Chrome", ""), ('GOLD', "Brushed Gold", "")],
        default='BLACK', update=_update_finish)
    back_splash: BoolProperty(name="Backsplash 4″", default=True, update=_update_splashes)
    left_splash: BoolProperty(name="Lateral esquerda", default=False, update=_update_splashes)
    right_splash: BoolProperty(name="Lateral direita", default=False, update=_update_splashes)


class FZM_OT_apply_vanity_preset(Operator):
    bl_idname = "fzm.apply_vanity_preset"
    bl_label = "Aplicar acabamentos"
    bl_description = "Aplica os acabamentos escolhidos à vanity selecionada"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _find_controller(context.active_object) is not None

    def execute(self, context):
        ctrl = _find_controller(context.active_object)
        if ctrl is None:
            return {'CANCELLED'}
        s = ctrl.fzm_vanity_settings
        _update_finish(s, context)
        _update_splashes(s, context)
        self.report({'INFO'}, "Acabamentos aplicados nesta vanity")
        return {'FINISHED'}


class FZM_PT_vanity_controls(Panel):
    bl_label = "FZM Vanity — Acabamentos"
    bl_idname = "FZM_PT_vanity_controls"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'FZM Vanity'

    def draw(self, context):
        layout = self.layout
        ctrl = _find_controller(context.active_object)
        if ctrl is None:
            layout.label(text="Selecione uma peça da vanity", icon='INFO')
            layout.label(text="(ou Vanity_30_Controller)")
            layout.label(text="Append, não Instance")
            return
        layout.label(text="Vanity selecionada:")
        layout.label(text=ctrl.name, icon='OUTLINER_OB_EMPTY')
        s = ctrl.fzm_vanity_settings
        col = layout.column(align=True)
        col.prop(s, 'base_color')
        col.prop(s, 'top_finish')
        col.prop(s, 'hardware_color')
        col.separator()
        col.label(text="Splashes")
        col.prop(s, 'back_splash')
        col.prop(s, 'left_splash')
        col.prop(s, 'right_splash')
        layout.separator()
        layout.operator('fzm.apply_vanity_preset', icon='MATERIAL')
        layout.separator()
        layout.label(text="Apenas esta vanity é modificada.", icon='INFO')
        layout.label(text="Modelo visual; confira medidas.")


classes = (
    FZM_VanitySettings,
    FZM_OT_apply_vanity_preset,
    FZM_PT_vanity_controls,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.fzm_vanity_settings = PointerProperty(type=FZM_VanitySettings)


def unregister():
    del bpy.types.Object.fzm_vanity_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()