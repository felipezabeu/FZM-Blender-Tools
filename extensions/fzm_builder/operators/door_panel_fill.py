"""Separate optional glass fill for the measured Five Panel Shaker leaf."""

import bpy

KEY = 'FZM_HINGED_3D_PANEL_FILL'
INPUT = 'Frosted Panels'
NAME = 'FZM Five Panel Shaker | Frosted Glass'
MATERIAL_KEY = 'fzm_five_panel_frosted_glass'
ITEMS = (
    ('SOLID', 'Solid', 'Solid door inserts'),
    ('FROSTED', 'Frosted Glass', 'Replace all five inserts with frosted glass'),
)


def panel_fill_for(door):
    return 'FROSTED' if door.get(KEY) == 'FROSTED' else 'SOLID'


def glass_material():
    result = bpy.data.materials.get(NAME)
    if result and result.get(MATERIAL_KEY):
        return result
    result = bpy.data.materials.new(NAME)
    result[MATERIAL_KEY] = True
    result.diffuse_color = (.78, .84, .87, .49)
    result.use_nodes = True
    bsdf = result.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (.86, .92, .94, 1.)
    bsdf.inputs['Metallic'].default_value = 0.
    bsdf.inputs['Roughness'].default_value = .26
    bsdf.inputs['IOR'].default_value = 1.46
    bsdf.inputs['Transmission Weight'].default_value = .92
    return result
