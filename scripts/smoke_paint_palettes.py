"""Exercise paint lookup, shared-library discovery and local import in Blender 5.1.2."""

from importlib import import_module
from pathlib import Path
import struct
from tempfile import TemporaryDirectory

import bpy


def write_palette(path, code, name, rgb):
    label = f'{code} {name}\0'.encode('utf-16-be')
    body = struct.pack('>H', len(label) // 2) + label + struct.pack('>4s3fH', b'RGB ', *rgb, 2)
    path.write_bytes(struct.pack('>4sHHIHI', b'ASEF', 1, 0, 1, 1, len(body)) + body)


def verify(fixture):
    package = 'bl_ext.user_default.fzm_builder'
    types = import_module(f'{package}.hb_types')
    finishes = import_module(f'{package}.operators.finishes')
    preferences = bpy.context.preferences.addons[package].preferences

    shared_root = fixture / 'library'
    directory = shared_root / 'Paletas' / 'Benjamin Moore'
    directory.mkdir(parents=True)
    ase = directory / 'Shared fixture.ase'
    write_palette(ase, 'OC-65', 'Synthetic White', (0.25, 0.5, 0.75))
    (directory / 'Unreadable.ase').write_bytes(b'invalid')
    entry = preferences.asset_libraries.add()
    entry.library_path = str(shared_root)
    catalog = finishes.wall_paint_catalog()
    assert catalog.skipped == ('Unreadable.ase',)
    assert catalog.lookup('OC65') == catalog.lookup('OC-65') == catalog.lookup('Synthetic White')

    wall = types.GeoNodeWall()
    wall.create('Palette fixture wall')
    wall.set_input('Length', 3.0)
    wall.set_input('Height', 2.5)
    wall.set_input('Thickness', 0.15)
    context = bpy.context
    props = context.scene.home_builder

    assert bpy.ops.fzm_builder.wall_paint(input_mode='PALETTE', paint_code='oc65') == {'FINISHED'}
    mat = props.wall_material
    assert mat['fzm_paint_code'] == 'OC-65'
    assert mat['fzm_paint_name'] == 'Synthetic White'
    assert mat['fzm_paint_palette'] == 'Shared fixture'
    assert tuple(mat['fzm_paint_srgb']) == (0.25, 0.5, 0.75)
    assert all(wall.get_input(socket) == mat for socket in wall.material_inputs(wall.obj))
    assert abs(mat.diffuse_color[1] - ((128 / 255 + 0.055) / 1.055) ** 2.4) < 1e-6

    updated = directory / 'New collection.ase'
    write_palette(updated, 'HC-1', 'Synthetic Historic', (0.5, 0.5, 0.5))
    assert finishes.wall_paint_catalog().lookup('HC1').code == 'HC-1'

    write_palette(directory / 'Alternate fixture.ase', 'OC-65', 'Synthetic White', (0.5, 0.5, 0.5))
    catalog = finishes.wall_paint_catalog()
    assert set(catalog.collections('OC65')) == {'Shared fixture', 'Alternate fixture'}
    try:
        catalog.lookup('OC65')
    except ValueError as error:
        assert 'Multiple swatches' in str(error)
    else:
        raise AssertionError('Conflicting colors must request a collection')
    assert bpy.ops.fzm_builder.wall_paint(
        input_mode='PALETTE', paint_code='OC65', paint_collection='Alternate fixture',
    ) == {'FINISHED'}
    assert props.wall_material['fzm_paint_palette'] == 'Alternate fixture'

    local = fixture / 'Local fixture.ase'
    write_palette(local, 'TH-10', 'Synthetic Heritage', (0.75, 0.5, 0.25))
    assert bpy.ops.fzm_builder.import_paint_palette(filepath=str(local)) == {'FINISHED'}
    local.unlink()
    assert (finishes.imported_palettes_path() / 'Local fixture.ase').exists()
    assert bpy.ops.fzm_builder.wall_paint(
        scope='ALL', input_mode='PALETTE', paint_code='TH-10',
    ) == {'FINISHED'}
    assert props.wall_material['fzm_paint_code'] == 'TH-10'

    before = props.wall_material
    try:
        bpy.ops.fzm_builder.wall_paint(input_mode='PALETTE', paint_code='ZZ99999')
    except RuntimeError as error:
        assert 'Swatch not found' in str(error)
    else:
        raise AssertionError('Unknown code should report an error')
    assert props.wall_material == before
    path = fixture / 'materials.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    bpy.ops.wm.open_mainfile(filepath=str(path))
    assert bpy.context.scene.home_builder.wall_material['fzm_paint_code'] == 'TH-10'
    assert bpy.ops.fzm_builder.wall_paint(input_mode='HEX', hex_color='#445566') == {'FINISHED'}
    assert bpy.ops.fzm_builder.wall_paint(input_mode='RGB', rgb_color=(0.2, 0.4, 0.6)) == {'FINISHED'}
    print('PASS shared ASE, code/name lookup, source metadata, refresh, import, persistence and HEX/RGB')


if __name__ == '__main__':
    with TemporaryDirectory(prefix='fzm-paint-') as directory:
        verify(Path(directory))
