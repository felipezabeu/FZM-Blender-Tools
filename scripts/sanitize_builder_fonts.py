"""Replace the two upstream Calibri references with Blender's built-in font."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import bpy


ASSETS = ("GeoNodeDimension.blend", "GeoNodeRectangle.blend")


def replace_calibri(path):
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    calibri = [
        font for font in bpy.data.fonts
        if Path(font.filepath.replace("\\", "/")).name.lower() == "calibri.ttf"
    ]
    if not calibri:
        print(f"Already free of Calibri: {path.name}", flush=True)
        return

    placeholder = bpy.data.curves.new("Built-in font reference", type="FONT")
    builtin = placeholder.font
    for font in calibri:
        font.user_remap(builtin)
        bpy.data.fonts.remove(font)
    bpy.data.curves.remove(placeholder)

    # Stage on the same filesystem and replace the asset only after reopening it.
    with TemporaryDirectory(prefix=".font-replacement-", dir=path.parent) as folder:
        cleaned = Path(folder) / path.name
        assert bpy.ops.wm.save_as_mainfile(filepath=str(cleaned), relative_remap=False) == {"FINISHED"}
        bpy.ops.wm.open_mainfile(filepath=str(cleaned), load_ui=False)
        assert path.stem in bpy.data.node_groups, path
        assert all(font.filepath in {"", "<builtin>"} and not font.packed_file
                   for font in bpy.data.fonts), path
        cleaned.replace(path)
    print(f"Replaced Calibri in {path.name}", flush=True)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    if len(args) != 1:
        raise SystemExit("Pass the extension source directory after --")
    source = Path(args[0]).resolve()
    for asset_name in ASSETS:
        replace_calibri(source / "geometry_nodes" / asset_name)
