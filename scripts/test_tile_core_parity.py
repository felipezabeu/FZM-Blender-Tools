"""Assert Builder/standalone source parity and geometry vs sampled grout parity."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import random

from sync_tile_core import work


def load(path):
    spec=spec_from_file_location('tile_geometry',path)
    module=module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__=='__main__':
    work(True)
    repo=Path(__file__).resolve().parents[1]
    existing=load(repo/'extensions'/'fzm_tile_panels'/'tile_geometry.py')
    rng=random.Random(20261124)
    count=0
    # Cover both axes, row phases before zero, grout zero, actual cuts at panel
    # edges, offset-course resets, and huge phases without iterating huge grids.
    for pattern in existing.PATTERN_CYCLES:
        for direction in ('HORIZONTAL','VERTICAL'):
            for offset_x,offset_y,grout in ((0,0,0),(1.4,-.6,.125),(-9000,9200,.4)):
                w,h=40.25,37.85
                result=existing.generate_panel(w,h,pattern=pattern,orientation=direction,
                    grout=grout,offset_x=offset_x,offset_y=offset_y)
                assert result['tile_count'] and result['faces']
                assert result['tile_count']==len(result['tile_bounds'])
                tw,th=result['tile_width'],result['tile_height']
                for x0,y0,x1,y1 in result['tile_bounds']:
                    assert 0<=x0<x1<=w and 0<=y0<y1<=h
                for _ in range(240):
                    x,y=rng.uniform(0,w),rng.uniform(0,h)
                    derived=not any(x0<=x<x1 and y0<=y<y1 for x0,y0,x1,y1 in result['tile_bounds'])
                    assert derived==existing.tile_sample(x,y,tw,th,grout,pattern,offset_x,offset_y)[-1]
                    count+=1
    print(f'PASS standalone/Builder vendored source and geometry-to-shader reference across {count} samples')
