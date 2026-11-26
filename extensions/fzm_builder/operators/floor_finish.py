"""Floor appearance on metric UVs, independent of the floor geometry."""
from pathlib import Path
from math import isfinite
import json
import shutil
from uuid import uuid4

import bpy

from .floor_tiles import apply_floor_base_finish, floor_surface_indices, get_spec
from .floor_wood import BOARD_DIMENSIONS, BOARD_LENGTH, BOARD_WIDTH, attach_board_shader
from .tile_shader import base_material


DEFAULTS = (
    {"id": "maple", "name": "Maple (generic)", "color": (.57, .37, .19, 1), "grain": (.27, .14, .064, 1), "wood_boards": True},
    {"id": "hickory", "name": "Hickory (generic)", "color": (.43, .23, .106, 1), "grain": (.11, .045, .016, 1), "wood_boards": True},
    {"id": "grey_wood", "name": "Grey Wood (generic)", "color": (.34, .33, .31, 1), "grain": (.13, .135, .14, 1), "wood_boards": True},
    {"id": "neutral_tile", "name": "Neutral Porcelain (generic)", "color": (.58, .55, .49, 1)},
    {"id": "dark_stone", "name": "Dark Stone (generic)", "color": (.10, .105, .11, 1)},
)
# Blender must retain references to strings returned by dynamic enum callbacks.
_enum_items = {}
_enum_numbers = {}


def catalog_root():
    return Path(bpy.utils.user_resource('CONFIG')) / "fzm_builder_floor_catalog"


def catalog_entries():
    entries = {data["id"]: data for data in DEFAULTS}
    root = catalog_root()
    for folder in sorted(root.glob("*/")):
        try:
            data = json.loads((folder / "preset.json").read_text(encoding="utf-8"))
            if not isinstance(data.get("name"), str) or not data["name"].strip():
                continue
            data["id"] = folder.name
            if "image" in data:
                image_name = data["image"]
                if not isinstance(image_name, str) or Path(image_name).name != image_name:
                    continue
                data["image"] = str(folder / image_name)
            entries[folder.name] = data
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return entries


def list_presets(self, context):
    items = []
    for key, row in catalog_entries().items():
        number = _enum_numbers.setdefault(key, len(_enum_numbers) + 1)
        name = row["name"]
        items.append(_enum_items.setdefault((key, name), (key, name, "", number)))
    return items


def save_preset(name, data):
    if not name.strip():
        raise ValueError("Enter a name for the catalog preset.")
    entry_id = "custom_" + uuid4().hex
    folder = catalog_root() / entry_id
    folder.mkdir(parents=True)
    try:
        saved = dict(data, id=entry_id, name=name.strip())
        if data.get("image"):
            path = Path(data["image"])
            saved["image"] = "surface" + path.suffix.lower()
            shutil.copyfile(path, folder / saved["image"])
        (folder / "preset.json").write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
    except Exception:
        shutil.rmtree(folder)
        raise
    return entry_id


def is_wood_board_preset(data):
    return bool(data and data.get("wood_boards") and data.get("grain") and not data.get("image"))


def create_material(data):
    color = tuple(data.get("color", (1, 1, 1, 1)))
    if len(color) != 4 or not all(isfinite(c) and 0 <= c <= 1 for c in color):
        raise ValueError("Invalid preset color.")
    width, height = float(data.get("width", .6)), float(data.get("height", .6))
    if not all(isfinite(v) and v >= .001 for v in (width, height)):
        raise ValueError("The physical image repeat must be at least 1 mm.")
    board_dims = None
    if is_wood_board_preset(data):
        board_dims = (float(data.get("board_width", BOARD_WIDTH)),
                      float(data.get("board_length", BOARD_LENGTH)))
        if not all(isfinite(v) and .00999999 <= v <= 10. for v in board_dims):
            raise ValueError("Board width and length must be between 10 mm and 10 m.")
    material = bpy.data.materials.new("Floor Finish - " + data["name"])
    image = None
    try:
        material.use_nodes = True
        material.diffuse_color = color
        material["fzm_floor_finish_source"] = data.get("id", "local_image" if data.get("image") else "solid_color")
        material["fzm_floor_finish_name"] = data["name"]
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        pbr = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        pbr.inputs["Roughness"].default_value = .55
        pbr.inputs["Base Color"].default_value = color
        if data.get("image"):
            path = Path(data["image"])
            if not path.is_file():
                raise ValueError("Image not found. Choose a local texture file.")
            image = bpy.data.images.load(str(path), check_existing=False)
            if min(image.size) <= 0:
                raise ValueError("Blender could not decode this image.")
            image.pack()
            uv = nodes.new("ShaderNodeUVMap")
            uv.uv_map = "UVMap"
            scale = nodes.new("ShaderNodeVectorMath")
            scale.operation = 'MULTIPLY'
            scale.label = "Image repeat in metres"
            scale.inputs[1].default_value = (1 / width, 1 / height, 1)
            texture = nodes.new("ShaderNodeTexImage")
            texture.image = image
            texture.extension = 'REPEAT'
            links.new(uv.outputs["UV"], scale.inputs[0])
            links.new(scale.outputs["Vector"], texture.inputs["Vector"])
            links.new(texture.outputs["Color"], pbr.inputs["Base Color"])
            material["fzm_image_repeat_m"] = (width, height)
            material["fzm_image_source_name"] = path.name
        elif data.get("grain"):
            uv = nodes.new("ShaderNodeUVMap")
            uv.uv_map = "UVMap"
            scale = nodes.new("ShaderNodeVectorMath")
            scale.operation = 'MULTIPLY'
            scale.inputs[1].default_value = (3, 110, 1)
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 1
            noise.inputs["Detail"].default_value = 2.5
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = .18
            ramp.color_ramp.elements[0].color = data["grain"]
            ramp.color_ramp.elements[1].position = .85
            ramp.color_ramp.elements[1].color = color
            links.new(uv.outputs["UV"], scale.inputs[0])
            links.new(scale.outputs["Vector"], noise.inputs["Vector"])
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            if board_dims is not None:
                noise.location = (-365, 100)
                ramp.location = (-165, 420)
                joint_color = tuple(channel * .44 for channel in data["grain"][:3]) + (1.,)
                attach_board_shader(material, pbr, uv, scale, ramp.outputs["Color"], *board_dims, joint_color)
                next(n for n in nodes if n.type == 'OUTPUT_MATERIAL').location = (755, 240)
            else:
                links.new(ramp.outputs["Color"], pbr.inputs["Base Color"])
        return material
    except Exception:
        bpy.data.materials.remove(material)
        if image is not None and image.users == 0:
            bpy.data.images.remove(image)
        raise


def apply_finish(obj, material):
    apply_floor_base_finish(obj, material)


class FZM_OT_floor_finish(bpy.types.Operator):
    bl_idname = "fzm_builder.floor_finish"
    bl_label = "Floor Finish"
    bl_description = "Apply a catalog preset, a solid color, or a local texture to the active floor"
    bl_options = {'UNDO'}

    mode: bpy.props.EnumProperty(name="Source", items=(
        ('CATALOG', "Catalog", "Built-in and saved local presets"),
        ('COLOR', "Solid Color", "Apply a custom color"),
        ('IMAGE', "Local Image", "Select a local surface texture without registering it"),
    ))
    preset: bpy.props.EnumProperty(name="Preset", items=list_presets)
    color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR', size=4,
        min=0, max=1, default=(.55, .48, .36, 1))
    filepath: bpy.props.StringProperty(name="Image File", subtype='FILE_PATH')
    width: bpy.props.FloatProperty(name="Repeat Width", default=.6, min=.001, subtype='DISTANCE', unit='LENGTH')
    height: bpy.props.FloatProperty(name="Repeat Height", default=.6, min=.001, subtype='DISTANCE', unit='LENGTH')
    board_width: bpy.props.FloatProperty(name="Board Width", default=BOARD_WIDTH, min=.01, max=10.,
        subtype='DISTANCE', unit='LENGTH', description="Nominal width across the wood boards")
    board_length: bpy.props.FloatProperty(name="Board Length", default=BOARD_LENGTH, min=.01, max=10.,
        subtype='DISTANCE', unit='LENGTH', description="Nominal board length along the grain")
    add_to_catalog: bpy.props.BoolProperty(name="Also Save to Local Catalog")
    preset_name: bpy.props.StringProperty(name="Preset Name")

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return context.mode == 'OBJECT' and obj is not None and obj.type == 'MESH' and bool(obj.get('IS_FLOOR_BP'))

    def invoke(self, context, event):
        obj = context.active_object
        try:
            index = floor_surface_indices(obj)[0]
        except (IndexError, ValueError):
            index = -1
        if 0 <= index < len(obj.material_slots):
            material = base_material(obj.material_slots[index].material)
            source = material.get("fzm_floor_finish_source") if material else None
            row = catalog_entries().get(source)
            if is_wood_board_preset(row):
                if not self.properties.is_property_set("mode"):
                    self.mode = 'CATALOG'
                if not self.properties.is_property_set("preset"):
                    self.preset = source
                if BOARD_DIMENSIONS in material:
                    width, length = material[BOARD_DIMENSIONS]
                    if not self.properties.is_property_set("board_width"):
                        self.board_width = width
                    if not self.properties.is_property_set("board_length"):
                        self.board_length = length
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode")
        if self.mode == 'CATALOG':
            layout.prop(self, "preset")
            row = catalog_entries().get(self.preset or DEFAULTS[0]["id"])
            if is_wood_board_preset(row):
                layout.prop(self, "board_width")
                layout.prop(self, "board_length")
                layout.label(text="View the boards in Material Preview or Rendered mode.")
                if get_spec(context.active_object):
                    layout.label(text="Tile joints are active on this floor.", icon='INFO')
                    layout.label(text="Choose No Tile Layout to show the wood joints.")
        else:
            if self.mode == 'COLOR':
                layout.prop(self, "color")
            else:
                layout.prop(self, "filepath")
                layout.prop(self, "width")
                layout.prop(self, "height")
                layout.label(text="Size of one full image repeat on the floor.")
            layout.prop(self, "add_to_catalog")
            if self.add_to_catalog:
                layout.prop(self, "preset_name")

    def execute(self, context):
        obj = context.active_object
        if not obj.data.vertices or not obj.data.polygons:
            self.report({'WARNING'}, "Select a generated floor with geometry.")
            return {'CANCELLED'}
        material = None
        try:
            if self.mode == 'CATALOG':
                data = catalog_entries().get(self.preset or DEFAULTS[0]["id"])
                if not data:
                    raise ValueError("Catalog preset unavailable.")
                if is_wood_board_preset(data):
                    data = dict(data, board_width=self.board_width, board_length=self.board_length)
            elif self.add_to_catalog and not self.preset_name.strip():
                raise ValueError("Enter a name for the catalog preset.")
            elif self.mode == 'IMAGE':
                path = bpy.path.abspath(self.filepath) if self.filepath else ""
                data = {"name": self.preset_name or Path(path).stem,
                        "image": path, "width": self.width, "height": self.height}
                if not path:
                    raise ValueError("Select a local image file.")
            else:
                data = {"name": self.preset_name or "Solid Color", "color": list(self.color)}
            if (data.get("image") or data.get("grain")) and "UVMap" not in obj.data.uv_layers:
                raise ValueError("This floor needs the generated metric UVMap to use a texture.")
            material = create_material(data)
            apply_finish(obj, material)
        except (ValueError, OSError, RuntimeError, TypeError) as error:
            if material is not None and material.users == 0:
                bpy.data.materials.remove(material)
            self.report({'WARNING'}, str(error))
            return {'CANCELLED'}
        if self.mode != 'CATALOG' and self.add_to_catalog:
            try:
                material["fzm_floor_finish_source"] = save_preset(self.preset_name, data)
            except (ValueError, OSError) as error:
                self.report({'WARNING'}, f"Finish applied, but catalog save failed: {error}")
        return {'FINISHED'}
