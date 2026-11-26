"""Optional placement tools local to the 3D Viewport's Object Mode toolbar."""

import bpy


class FZM_WST_interior_wall(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = 'fzm_builder.interior_wall_tool'
    bl_label = 'FZM Interior Wall'
    bl_description = 'Click the viewport to start Draw Walls using Interior defaults'
    bl_icon = 'ops.curve.draw'
    bl_keymap = (
        ('home_builder_walls.draw_walls', {'type': 'LEFTMOUSE', 'value': 'PRESS'},
         {'properties': [('force_interior', True)]}),
    )


class FZM_WST_hinged_door(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = 'fzm_builder.hinged_door_tool'
    bl_label = 'FZM Hinged Door'
    bl_description = 'Click the viewport to start the standard hinged door placement'
    bl_icon = 'ops.mesh.primitive_cube_add_gizmo'
    bl_keymap = (
        ('home_builder_doors_windows.place_door', {'type': 'LEFTMOUSE', 'value': 'PRESS'}, None),
    )


class FZM_WST_window_3d(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = 'fzm_builder.window_3d_tool'
    bl_label = 'FZM 3D Window'
    bl_description = 'Click the viewport to start window placement with a frame and glass'
    bl_icon = 'ops.mesh.primitive_grid_add_gizmo'
    bl_keymap = (
        ('home_builder_doors_windows.place_window', {'type': 'LEFTMOUSE', 'value': 'PRESS'},
         {'properties': [('add_frame', True)]}),
    )


TOOLS = (FZM_WST_interior_wall, FZM_WST_hinged_door, FZM_WST_window_3d)


def register():
    for index, tool in enumerate(TOOLS):
        bpy.utils.register_tool(tool, separator=index == 0)


def unregister():
    for tool in reversed(TOOLS):
        bpy.utils.unregister_tool(tool)
