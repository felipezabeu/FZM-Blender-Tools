import bpy

from ..operators import door_units
from . import menus


def draw_object_mode_right_click_menu(self, context):
    obj = context.object
    menu_id = obj.get("MENU_ID") if obj else None
    layout = self.layout
    if door_units.cage_for(obj):
        # Show door commands in the first menu, regardless of which generated
        # part was selected. Keep the blue viewport button pose-only.
        column = layout.column()
        column.operator_context = 'INVOKE_AREA'
        column.label(text="Door Commands")
        menus.draw_door_context_actions(column, context)
        layout.separator()
    elif menu_id and hasattr(bpy.types, menu_id):
        column = layout.column()
        column.operator_context = 'INVOKE_AREA'
        column.menu(menu_id)
        layout.separator()


def register():
    bpy.types.VIEW3D_MT_object_context_menu.prepend(draw_object_mode_right_click_menu)


def unregister():
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_object_mode_right_click_menu)
