"""Drive probe_visual_wall_gui.py using actual XTest mouse events and screenshots."""
from pathlib import Path
import json
import math
import os
import subprocess as sp
import sys
import time

from PIL import Image

root=Path(sys.argv[1])
xd=os.environ.get('FZM_XDOTOOL','xdotool')

def wait(predicate, msg, seconds=25):
    until=time.monotonic()+seconds
    value=None
    while time.monotonic()<until:
        try:
            value=json.loads((root/'state.json').read_text())
            if predicate(value):return value
        except (OSError,json.JSONDecodeError):
            pass
        time.sleep(.14)
    raise AssertionError((msg,value))

def close(a,b,eps=.02):
    return math.dist(a,b)<eps

def drag(start,dx,dy):
    x,y=start
    sp.run([xd,'mousemove',str(x),str(y)],check=True)
    time.sleep(.3)
    sp.run([xd,'mousedown','1'],check=True)
    time.sleep(.25)
    for i in range(1,9):
        sp.run([xd,'mousemove',str(x+round(dx*i/8)),str(y+round(dy*i/8))],check=True)
        time.sleep(.035)
    time.sleep(.25)
    if not (root/'wall-during.png').exists():
        sp.run(['import','-window','root',str(root/'wall-during.png')],check=True)
    sp.run([xd,'mouseup','1'],check=True)

before=wait(lambda v:v.get('active')=='B','wall fixture')
print('Wall source',before,flush=True)
for line in sp.check_output(['xwininfo','-root','-tree'],text=True).splitlines()[-12:]:
    print(line,flush=True)
sp.run(['import','-window','root',str(root/'wall-start.png')],check=True)
ids=sp.check_output([xd,'search','--onlyvisible','--name','Blender'],text=True).split()
if ids: sp.run([xd,'windowfocus',ids[-1]],check=True)
sp.run([xd,'key','Escape'],check=True)
time.sleep(.6)
sp.run([xd,'key','Escape'],check=True)
time.sleep(.55)
drag(before['handles']['move'],82,0)
moved=wait(lambda v:v['geom']['B'][0][0]>4.2,'real wall body drag')
for a,b in zip('ABCD','BCDA'): assert close(moved['geom'][a][1],moved['geom'][b][0])
assert close(before['geom']['A'][0],moved['geom']['A'][0])
print('Whole-wall drag',moved,flush=True)
drag(moved['handles']['end'],20,-49)
second=wait(lambda v:v['geom']['B'][1][1]>moved['geom']['B'][1][1]+.15,'real shared-end drag')
for a,b in zip('ABCD','BCDA'): assert close(second['geom'][a][1],second['geom'][b][0])
assert close(second['geom']['B'][0],moved['geom']['B'][0])
sp.run([xd,'key','ctrl+z'],check=True)
undo=wait(lambda v:close(v['geom']['B'][1],moved['geom']['B'][1]),'one undo restores shared end')
print('PASS real wall body drag, connected endpoint drag, closed contour and undo',flush=True)

def blue_box(label,xy):
    p=root/f'{label}.png'
    sp.run(['import','-window','root',str(p)],check=True)
    im=Image.open(p).convert('RGB')
    x,y=xy
    pixels={(X,Y) for Y in range(y-30,y+31) for X in range(x-30,x+31)
            if (lambda c:c[2]>c[0]+27 and c[1]>c[0]+12 and c[2]>c[1]+8)(im.getpixel((X,Y)))}
    assert pixels,label
    lo=(min(v[0] for v in pixels),min(v[1] for v in pixels))
    hi=(max(v[0] for v in pixels),max(v[1] for v in pixels))
    out=(hi[0]-lo[0]+1,hi[1]-lo[1]+1)
    assert all(22<=i<=47 for i in out),(label,out)
    return out

d=[]
for label in ('ortho','persp','wide','close'):
    (root/'command').write_text(label)
    s=wait(lambda v:v['mode']==label and v.get('anchor'),f'visible icon {label}')
    sp.run([xd,'mousemove','30','30'],check=True)
    time.sleep(.3)
    d.append(blue_box(label,s['anchor']))
    for val in (1.,0.):
        sp.run([xd,'mousemove',*map(str,s['anchor']),'click','1'],check=True)
        wait(lambda v:v['mode']==label and abs(v['open']-val)<.02,f'click {label} {val}')
    print(label, d[-1], flush=True)
assert max(v[0] for v in d)-min(v[0] for v in d)<=5,d
assert max(v[1] for v in d)-min(v[1] for v in d)<=5,d
(root/'command').write_text('clipped')
wait(lambda v:v['mode']=='clipped' and v.get('anchor') is None,'near-plane hides button')
print('PASS real door click, orbit/zoom fixed-size visual bound and near-clip hiding',flush=True)
