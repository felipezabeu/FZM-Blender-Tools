import bpy
from . import door_pose


class HOME_BUILDER_OT_change_units(bpy.types.Operator):
    bl_idname = "home_builder.change_units"
    bl_label = "Change Units"
    bl_description = "Change the scene unit system"

    unit_system: bpy.props.StringProperty(name="Unit System")
    length_unit: bpy.props.StringProperty(name="Length Unit")

    def execute(self, context):
        context.scene.unit_settings.system = self.unit_system
        context.scene.unit_settings.length_unit = self.length_unit
        return {'FINISHED'}


class HOME_BUILDER_MT_main_menu(bpy.types.Menu):
    bl_label = "FZM Builder"
    bl_idname = "HOME_BUILDER_MT_main_menu"

    def draw(self, context):
        layout = self.layout
        
        # Room operations
        layout.operator("home_builder.create_room", text="New Room", icon='ADD')
        layout.menu("HOME_BUILDER_MT_room_list", text="Switch Room", icon='LOOP_BACK')
        
        layout.separator()
        
        # Layout views submenu
        layout.menu("HOME_BUILDER_MT_layout_views_create", text="Create View", icon='VIEW_ORTHO')
        
        layout.separator()
        
        # Camera
        layout.operator("home_builder.create_camera", text="Create Camera", icon='CAMERA_DATA')
        
        layout.separator()
        
        # Units
        layout.menu("HOME_BUILDER_MT_change_units", text="Change Units", icon='DRIVER_DISTANCE')
        
        layout.separator()
        
        # Settings
        layout.operator("home_builder.set_recommended_settings", 
                       text="Recommended Settings", icon='PREFERENCES')
        layout.operator("home_builder.rendering_settings",
                       text="Rendering Settings", icon='RENDER_STILL')
        
        layout.separator()
        
        # Export
        layout.operator("home_builder.prepare_for_export", icon='EXPORT')


class HOME_BUILDER_MT_wall_commands(bpy.types.Menu):
    bl_label = "Wall Commands"

    def draw(self, context):
        layout = self.layout
        layout.operator("home_builder_walls.wall_prompts", text="Wall Prompts")
        for mode, label in (('MOVE', 'Move Entire Wall'), ('START', 'Move Wall Start'), ('END', 'Move Wall End')):
            layout.operator("fzm_builder.edit_wall", text=label).edit_mode = mode
        layout.separator()
        layout.operator("home_builder_walls.hide_wall", text="Hide Wall", icon='HIDE_ON')
        layout.operator("home_builder_walls.isolate_selected_walls", text="Isolate Selected Walls", icon='ZOOM_SELECTED')
        layout.operator("home_builder_walls.show_all_walls", text="Show All Walls", icon='HIDE_OFF')
        layout.separator()
        layout.operator("fzm_builder.room_baseboards", text="Add/Edit Wall Baseboards",
                        icon="MOD_SOLIDIFY").wall_source = 'WALL_FACES'
        layout.operator("fzm_builder.divide_wall", icon="MOD_BOOLEAN")
        layout.operator("home_builder_walls.draw_wall_cutter", text="Draw Wall Cutter", icon='MOD_BOOLEAN')
        layout.separator()
        layout.operator("hb_frameless.place_snap_line", text="Place Snap Line", icon='SNAP_MIDPOINT')
        layout.operator("hb_frameless.delete_all_snap_lines", text="Delete All Snap Lines", icon='TRASH')
        layout.separator()
        layout.operator("home_builder_walls.delete_wall", text="Delete Wall", icon='X')


class HOME_BUILDER_MT_door_commands(bpy.types.Menu):
    bl_label = "Door Commands"

    def draw(self, context):
        layout = self.layout
        pose_command = door_pose.command_label(context)
        if pose_command:
            layout.operator(door_pose.TOGGLE, text=pose_command,
                            icon='LOOP_BACK' if pose_command == 'Close Door' else 'PLAY')
            layout.separator()
        if bpy.ops.fzm_builder.move_door_along_wall.poll():
            layout.operator("fzm_builder.move_door_along_wall", icon='TRANSFORM_MOVE')
        if bpy.ops.fzm_builder.edit_door.poll():
            layout.operator("fzm_builder.edit_door", icon='PREFERENCES')
        if bpy.ops.home_builder_doors_windows.toggle_double_door.poll():
            layout.operator("home_builder_doors_windows.toggle_double_door")
            layout.operator("home_builder_doors_windows.flip_door_swing")
            if bpy.ops.home_builder_doors_windows.flip_door_hand.poll():
                layout.operator("home_builder_doors_windows.flip_door_hand")
            layout.separator()
        layout.operator("fzm_builder.door_casing")
        layout.separator()
        layout.operator("home_builder_doors_windows.delete_door_window", text="Delete Door").object_type = 'DOOR'


class HOME_BUILDER_MT_window_commands(bpy.types.Menu):
    bl_label = "Window Commands"

    def draw(self, context):
        layout = self.layout
        layout.operator("home_builder_doors_windows.window_prompts", text="Window Prompts")
        layout.separator()
        layout.operator("home_builder_doors_windows.delete_door_window", text="Delete Window").object_type = 'WINDOW'


class HOME_BUILDER_MT_change_units(bpy.types.Menu):
    bl_label = "Change Units"
    bl_idname = "HOME_BUILDER_MT_change_units"

    def draw(self, context):
        layout = self.layout
        unit_settings = context.scene.unit_settings

        units = [
            ("METRIC", "METERS", "Meters"),
            ("METRIC", "CENTIMETERS", "Centimeters"),
            ("METRIC", "MILLIMETERS", "Millimeters"),
            ("IMPERIAL", "FEET", "Feet"),
            ("IMPERIAL", "INCHES", "Inches"),
        ]

        for system, length, label in units:
            is_active = (unit_settings.system == system and unit_settings.length_unit == length)
            icon = 'CHECKMARK' if is_active else 'NONE'
            op = layout.operator("home_builder.change_units", text=label, icon=icon)
            op.unit_system = system
            op.length_unit = length



def draw_home_builder_menu(self, context):
    self.layout.menu("HOME_BUILDER_MT_main_menu")


classes = (
    HOME_BUILDER_OT_change_units,
    HOME_BUILDER_MT_change_units,
    HOME_BUILDER_MT_main_menu,
    HOME_BUILDER_MT_wall_commands,
    HOME_BUILDER_MT_door_commands,
    HOME_BUILDER_MT_window_commands,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(draw_home_builder_menu)


def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(draw_home_builder_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
