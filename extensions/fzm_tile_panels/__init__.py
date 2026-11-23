"""FZM Tile Panels - Blender 4.3+ / 5.1 extension.

Procedural finish panels with true tile/grout surface geometry.
All dimensions in inches. No internet, no paid services, no external dependencies.
"""
bl_info = {
    "name": "FZM Tile Panels",
    "author": "FZM Renovations",
    "version": (1, 0, 0),
    "blender": (4, 3, 0),
    "location": "3D View > Sidebar (N) > FZM Tile",
    "description": "Editable tile finish panels with grout, patterns and supplier images",
    "category": "Mesh",
}

import os

import bpy
from bpy.props import (
    BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
    IntProperty, PointerProperty, StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

from .tile_geometry import INCH, PRESETS, TooManyTiles, generate_panel


TILE_TYPES = [(k, k.replace("x", " × ") + '"', "") for k in PRESETS]
TILE_TYPES.append(("CUSTOM", "Custom Size", "Enter your own tile dimensions"))
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".exr")


def new_material(name, color, roughness=0.55, image_path=None):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color[:3], 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color[:3], 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        if image_path:
            image = bpy.data.images.load(image_path, check_existing=True)
            try:
                image.pack()  # make future .blend / asset portability easier
            except Exception:
                pass
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.image = image
            tex.label = "Tile face photo"
            tex.location = (-420, 180)
            mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def image_paths(settings):
    if settings.texture_source == "IMAGE":
        filepath = bpy.path.abspath(settings.tile_image)
        if not filepath or not os.path.isfile(filepath):
            raise ValueError("Choose an existing image file for this tile")
        return [filepath]
    if settings.texture_source == "FOLDER":
        folder = bpy.path.abspath(settings.tile_folder)
        if not folder or not os.path.isdir(folder):
            raise ValueError("Choose an existing folder containing tile-face images")
        imgs = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if f.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(folder, f))
        )
        if not imgs:
            raise ValueError("The folder has no JPG/PNG/WEBP tile-face images")
        return imgs[:16]  # avoid high material counts
    return []


class FZM_Tile_Settings(PropertyGroup):
    active: BoolProperty(name="FZM Tile Panel", default=False)
    surface: EnumProperty(
        name="Type", items=[
            ("WALL", "Wall", "Panel in X/Z, facing -Y, bottom-left origin"),
            ("FLOOR", "Floor", "Panel in X/Y, facing +Z, corner origin"),
        ], default="WALL")
    width: FloatProperty(name="Panel Width", default=60, min=1, max=5000, precision=2, description="Inches")
    height: FloatProperty(name="Panel Height / Length", default=96, min=1, max=5000, precision=2, description="Inches")
    thickness: FloatProperty(name="Finish Thickness", default=0.5, min=0.08, max=6, precision=3, description="Total panel thickness in inches")
    tile_preset: EnumProperty(name="Tile Size", items=TILE_TYPES, default="12x24")
    tile_a: FloatProperty(name="Dimension A", default=12, min=0.5, max=300, precision=2, description="Tile dimension in inches")
    tile_b: FloatProperty(name="Dimension B", default=24, min=0.5, max=300, precision=2, description="Tile dimension in inches")
    direction: EnumProperty(
        name="Tile Orientation", items=[
            ("HORIZONTAL", "Horizontal", "Longest side across wall/floor width"),
            ("VERTICAL", "Vertical", "Longest side in height/length direction"),
        ], default="HORIZONTAL")
    pattern: EnumProperty(
        name="Layout", items=[
            ("STACK", "Aligned", "Stack bond"),
            ("HALF", "Offset 50%", "Running bond with half tile offset"),
            ("THIRD", "Offset 33%", "Running bond with one third offset"),
        ], default="STACK")
    grout_width: FloatProperty(name="Grout Width", default=0.125, min=0, max=1, precision=3, description="Inches")
    grout_color: FloatVectorProperty(name="Grout Color", subtype="COLOR", size=3, min=0, max=1, default=(0.60, 0.59, 0.57))
    tile_color: FloatVectorProperty(name="Tile Color", subtype="COLOR", size=3, min=0, max=1, default=(0.84, 0.84, 0.81))
    roughness: FloatProperty(name="Tile Roughness", default=0.27, min=0, max=1, precision=2)
    offset_x: FloatProperty(name="Shift X", default=0, min=-10000, max=10000, precision=2, description="Move tile grid horizontally in inches")
    offset_y: FloatProperty(name="Shift Y", default=0, min=-10000, max=10000, precision=2, description="Move tile grid vertically/in depth in inches")
    relief: FloatProperty(name="Joint Relief", default=0.035, min=0.001, max=0.25, precision=3, description="Inches of visual tile height above the grout bed")
    texture_source: EnumProperty(
        name="Tile Appearance", items=[
            ("COLOR", "Solid Color", "Use the tile color picker"),
            ("IMAGE", "Image", "A cropped photo of one tile face"),
            ("FOLDER", "Image Folder", "Randomly apply photos from same product"),
        ], default="COLOR")
    tile_image: StringProperty(name="Tile Image", subtype="FILE_PATH", default="")
    tile_folder: StringProperty(name="Faces Folder", subtype="DIR_PATH", default="")


class FZM_OT_create_tile_panel(Operator):
    bl_idname = "fzm.create_tile_panel"
    bl_label = "Create Tile Panel"
    bl_description = "Create one editable tile panel mesh with grout and tile-face materials"
    bl_options = {"REGISTER", "UNDO"}

    surface: EnumProperty(items=[("WALL", "Wall", ""), ("FLOOR", "Floor", "")], default="WALL")

    def execute(self, context):
        if context.mode != 'OBJECT':
            self.report({'ERROR'}, "Switch to Object Mode first")
            return {'CANCELLED'}
        name = "Wall_Tile_Panel" if self.surface == "WALL" else "Floor_Tile_Panel"
        mesh = bpy.data.meshes.new(name + "_Mesh")
        obj = bpy.data.objects.new(name, mesh)
        context.collection.objects.link(obj)
        for other in context.selected_objects:
            other.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        # Start near current cursor; new panel is still freely movable/rotatable.
        obj.location = context.scene.cursor.location.copy()
        p = obj.fzm_tile_panel
        p.active = True
        p.surface = self.surface
        if self.surface == "FLOOR":
            p.height = 60
            p.tile_preset = "24x24"
            p.tile_a, p.tile_b = PRESETS["24x24"]
        return bpy.ops.fzm.update_tile_panel()


class FZM_OT_apply_tile_preset(Operator):
    bl_idname = "fzm.apply_tile_preset"
    bl_label = "Apply Tile Size"
    bl_description = "Copy the selected standard tile dimensions to the editable dimensions"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = context.object
        return o is not None and o.type == 'MESH' and o.fzm_tile_panel.active

    def execute(self, context):
        p = context.object.fzm_tile_panel
        if p.tile_preset in PRESETS:
            p.tile_a, p.tile_b = PRESETS[p.tile_preset]
        return bpy.ops.fzm.update_tile_panel()


class FZM_OT_update_tile_panel(Operator):
    bl_idname = "fzm.update_tile_panel"
    bl_label = "Update Panel"
    bl_description = "Rebuild only the selected panel from its saved dimensions, layout and texture settings"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        o = context.object
        return o is not None and o.type == 'MESH' and o.fzm_tile_panel.active and context.mode == 'OBJECT'

    def execute(self, context):
        obj = context.object
        p = obj.fzm_tile_panel
        if p.relief >= p.thickness:
            self.report({'ERROR'}, "Joint relief must be smaller than panel thickness")
            return {'CANCELLED'}
        try:
            files = image_paths(p)
            model = generate_panel(
                panel_width=p.width, panel_height=p.height, thickness=p.thickness,
                tile_a=p.tile_a, tile_b=p.tile_b,
                orientation=p.direction, pattern=p.pattern,
                grout=p.grout_width, offset_x=p.offset_x, offset_y=p.offset_y,
                surface=p.surface, tile_relief=p.relief,
                material_count=max(1, len(files)),
            )
        except (ValueError, OSError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}

        # Build new geometry first; do not destroy existing model on failure.
        mesh = bpy.data.meshes.new(obj.name + "_Geometry")
        try:
            mesh.from_pydata(model["vertices"], [], model["faces"])
            mesh.update()
            layer = mesh.uv_layers.new(name="Tile Faces UV")
            for polygon, material_id, uvcoords in zip(mesh.polygons, model["material_indices"], model["uvs"]):
                polygon.material_index = material_id
                for idx, uv in zip(polygon.loop_indices, uvcoords):
                    layer.data[idx].uv = uv

            grout = new_material(obj.name + " | Grout", p.grout_color, roughness=0.85)
            mesh.materials.append(grout)
            if files:
                for i, file in enumerate(files, start=1):
                    mesh.materials.append(new_material(obj.name + f" | Tile Face {i:02d}", p.tile_color, roughness=p.roughness, image_path=file))
            else:
                mesh.materials.append(new_material(obj.name + " | Tile", p.tile_color, roughness=p.roughness))
        except Exception as exc:
            bpy.data.meshes.remove(mesh)
            self.report({'ERROR'}, "Could not build panel: " + str(exc))
            return {'CANCELLED'}

        old_mesh = obj.data
        obj.data = mesh
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
        obj["Tile_Count"] = model["tile_count"]
        obj["Tile_Size_Inches"] = f'{model["tile_width"]:g} x {model["tile_height"]:g}'
        obj["Panel_Dimensions_Inches"] = f'{p.width:g} x {p.height:g} x {p.thickness:g}'
        obj["FZM_Tile_Generator"] = "1.0"
        self.report({'INFO'}, f'Panel updated: {model["tile_count"]} tile pieces')
        return {'FINISHED'}


class FZM_OT_pack_tile_images(Operator):
    bl_idname = "fzm.pack_tile_images"
    bl_label = "Pack All Images"
    bl_description = "Embed all loaded images into the .blend for asset portability"

    def execute(self, context):
        count = 0
        for image in bpy.data.images:
            if image.source == 'FILE':
                try:
                    if not image.packed_file:
                        image.pack()
                        count += 1
                except Exception:
                    continue
        self.report({'INFO'}, f"Packed {count} image(s). Save the .blend afterward")
        return {'FINISHED'}


class FZM_PT_tile_panels(Panel):
    bl_label = "FZM Tile Panels"
    bl_idname = "FZM_PT_tile_panels"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'FZM Tile'

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        op = row.operator("fzm.create_tile_panel", text="New Wall", icon="MESH_PLANE")
        op.surface = "WALL"
        op = row.operator("fzm.create_tile_panel", text="New Floor", icon="MESH_GRID")
        op.surface = "FLOOR"
        obj = context.object
        if not obj or obj.type != 'MESH' or not obj.fzm_tile_panel.active:
            layout.label(text="Select a FZM tile panel to edit", icon="INFO")
            return
        p = obj.fzm_tile_panel
        layout.separator()
        layout.label(text=obj.name, icon="MESH_CUBE")
        box = layout.box()
        box.label(text="Panel geometry (inches)")
        box.prop(p, "surface")
        box.prop(p, "width")
        box.prop(p, "height", text="Height" if p.surface == 'WALL' else "Length")
        box.prop(p, "thickness")

        box = layout.box()
        box.label(text="Tile size and pagination")
        row = box.row(align=True)
        row.prop(p, "tile_preset", text="Size")
        row.operator("fzm.apply_tile_preset", text="Use", icon="CHECKMARK")
        row = box.row(align=True)
        row.prop(p, "tile_a", text='A (in)')
        row.prop(p, "tile_b", text='B (in)')
        box.prop(p, "direction")
        box.prop(p, "pattern")
        row = box.row(align=True)
        row.prop(p, "offset_x")
        row.prop(p, "offset_y")

        box = layout.box()
        box.label(text="Tile appearance")
        box.prop(p, "texture_source")
        if p.texture_source == 'IMAGE':
            box.prop(p, "tile_image")
        elif p.texture_source == 'FOLDER':
            box.prop(p, "tile_folder")
            box.label(text="Up to 16 tile-face images")
        else:
            box.prop(p, "tile_color")
        box.prop(p, "roughness")

        box = layout.box()
        box.label(text="Grout")
        box.prop(p, "grout_width")
        box.prop(p, "grout_color")
        box.prop(p, "relief")

        layout.operator("fzm.update_tile_panel", text="UPDATE PANEL", icon="FILE_REFRESH")
        layout.operator("fzm.pack_tile_images", text="Pack Images", icon="PACKAGE")
        if "Tile_Count" in obj:
            layout.label(text=f'Tiles: {obj["Tile_Count"]}')
        layout.label(text="Origin: back lower-left corner", icon="PIVOT_CURSOR")


CLASSES = (
    FZM_Tile_Settings,
    FZM_OT_create_tile_panel,
    FZM_OT_apply_tile_preset,
    FZM_OT_update_tile_panel,
    FZM_OT_pack_tile_images,
    FZM_PT_tile_panels,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Object.fzm_tile_panel = PointerProperty(type=FZM_Tile_Settings)


def unregister():
    del bpy.types.Object.fzm_tile_panel
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()