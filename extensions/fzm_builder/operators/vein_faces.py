"""FZM directional porcelain, generated 3 x 3 slab atlas, revision 2.

Inputs: integer tile column/row plus the normalized UVs of the same tile.
Every tile samples one whole cell out of an unrotated atlas, not an
overlapping crop of a single reference tile. The caller masks grout.
"""
from pathlib import Path
import bpy
VARIANTS = {
    "05": ("Branco com veio cinza 05",),
    "06": ("Branco com veio cinza 06",),
    "07": ("Branco com veio cinza 07",),
}
ATLAS_SIDE = 3
# ~2.5 px on each side, keeping the texture filter inside the chosen cell.
CELL_INSET = 0.002

def porcelain_color(tree, image_dir, code, col, row, u, v, at=(0, 0)):
    code=str(code).zfill(2)
    title=VARIANTS[code][-1]
    def wire(src,dst):
        if isinstance(src,(int,float)):
            dst.default_value=src
        else:
            tree.links.new(src,dst)
    def make(kind,x,y,label):
        n=tree.nodes.new(kind); n.location=(at[0]+x,at[1]+y); n.label=label
        return n
    def calc(operation,sources,x,y,label):
        n=make('ShaderNodeMath',x,y,label); n.operation=operation
        for a,b in zip(sources,n.inputs):wire(a,b)
        return n.outputs[0]
    tile=make('ShaderNodeCombineXYZ',0,0,'Endereço fixo da peça: coluna e fiada')
    for src,dst in zip((col,row,67.11),tile.inputs):wire(src,dst)
    noise=make('ShaderNodeTexWhiteNoise',190,0,'Sorteio estável de uma das nove faces')
    noise.noise_dimensions='3D'
    wire(tile.outputs['Vector'],noise.inputs['Vector'])
    rnd=calc('MINIMUM',(noise.outputs['Value'],0.999999),370,0,'Intervalo estável 0–1')
    idx=calc('FLOOR',(calc('MULTIPLY',(rnd,float(ATLAS_SIDE**2)),550,0,'Nove faces por acabamento'),),
             720,0,'Índice da face (0–8)')
    sel_u=calc('FLOORED_MODULO',(idx,float(ATLAS_SIDE)),900,0,'Coluna da face no slab')
    sel_v=calc('FLOOR',(calc('DIVIDE',(idx,float(ATLAS_SIDE)),900,-170,'Linha no atlas'),),
               1070,-170,'Fiada da face no slab')
    def axis(f,cell,y,label):
        norm=calc('MAXIMUM',(0.,calc('MINIMUM',(f,1.),1080,y,'Limite superior '+label)),1260,y,'Face normalizada '+label)
        start=calc('MULTIPLY_ADD',(cell,1./ATLAS_SIDE,CELL_INSET),1260,y-120,'Origem da face '+label)
        return calc('MULTIPLY_ADD',(norm,1./ATLAS_SIDE-2*CELL_INSET,start),1450,y,'Sem girar nem espelhar '+label)
    vec=make('ShaderNodeCombineXYZ',1640,0,'UV da face inteira • porcelanato '+code)
    wire(axis(u,sel_u,0,'U'),vec.inputs[0])
    wire(axis(v,sel_v,-310,'V'),vec.inputs[1])
    tex=make('ShaderNodeTexImage',1830,0,title+' • nove faces geradas')
    tex.extension='EXTEND'; tex.interpolation='Linear'
    image_name='FZM | Porcelain slab '+code+' • r2'
    image=bpy.data.images.get(image_name)
    if image is None:
        image=bpy.data.images.load(str((Path(image_dir)/(code+'.webp')).resolve()),check_existing=False)
        image.name=image_name
        image.pack()
    tex.image=image
    wire(vec.outputs['Vector'],tex.inputs['Vector'])
    return tex.outputs['Color']
