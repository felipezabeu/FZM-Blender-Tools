"""Original metric tile finishes; no supplier files or external dependencies."""
TILE_FINISHES = {
    'WHITE_GREY_VEINS': ('White with Grey Veins', (.78, .78, .75, 1), (.25, .27, .28, 1), 'VEINS'),
    'GREY_PORCELAIN': ('Grey Porcelain', (.32, .33, .34, 1), (.29, .30, .31, 1), 'PORCELAIN'),
    'WHITE_BEIGE_VEINS': ('White with Beige Veins', (.82, .79, .71, 1), (.44, .34, .24, 1), 'VEINS'),
    'LIGHT_TERRAZZO': ('Light Terrazzo', (.72, .69, .61, 1), (.27, .28, .29, 1), 'TERRAZZO'),
    'WHITE_PORCELAIN': ('White Porcelain', (.84, .83, .80, 1), (.79, .78, .75, 1), 'PORCELAIN'),
    'DARK_GREY_PORCELAIN': ('Dark Grey Porcelain', (.11, .12, .13, 1), (.09, .10, .11, 1), 'PORCELAIN'),
}
FINISH_OPTIONS = (('CUSTOM', 'Custom Color or Photo', 'Use your own color or tile-face photo'), *(
    (key, row[0], 'Built-in procedural tile finish') for key, row in TILE_FINISHES.items()))


def finish_entry(key):
    name, color, accent, texture = TILE_FINISHES[key]
    return {'id': key, 'name': name, 'color': color, 'accent': accent, 'texture': texture}


def attach_tile_finish(material, pbr, data):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    uv = nodes.new('ShaderNodeUVMap')
    uv.uv_map = 'UVMap'
    uv.location = (-690, 100)
    texture = data['texture']
    color, accent = data['color'], data['accent']
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.location = (-110, 120)
    low, high = ramp.color_ramp.elements
    low.color, high.color = accent, color
    pbr.inputs['Roughness'].default_value = .45

    def add(kind, coords):
        node = nodes.new(kind)
        node.location = coords
        return node

    if texture == 'VEINS':
        noise = add('ShaderNodeTexNoise', (-520, -160))
        noise.inputs['Scale'].default_value = 4
        noise.inputs['Detail'].default_value = 2
        links.new(uv.outputs['UV'], noise.inputs['Vector'])
        wave = add('ShaderNodeTexWave', (-300, 200))
        wave.bands_direction = 'DIAGONAL'
        wave.inputs['Scale'].default_value = 1.55
        wave.inputs['Distortion'].default_value = 5
        wave.inputs['Detail'].default_value = 4
        wave.inputs['Detail Scale'].default_value = 2
        links.new(uv.outputs['UV'], wave.inputs['Vector'])
        low.position, high.position = .015, .10
        shoulder = ramp.color_ramp.elements.new(.044)
        shoulder.color = tuple(.68 * a + .32 * b for a, b in zip(color, accent))
        links.new(wave.outputs['Fac'], ramp.inputs[0])
        # Subtle roughness variation softens the cut-thin veins without changing their scale.
        roughness = add('ShaderNodeMapRange', (-110, -160))
        roughness.inputs['To Min'].default_value = .31
        roughness.inputs['To Max'].default_value = .43
        links.new(noise.outputs['Fac'], roughness.inputs['Value'])
        links.new(roughness.outputs[0], pbr.inputs['Roughness'])
    elif texture == 'TERRAZZO':
        chips = add('ShaderNodeTexVoronoi', (-360, 160))
        chips.voronoi_dimensions = '2D'
        chips.inputs['Scale'].default_value = 115
        links.new(uv.outputs['UV'], chips.inputs['Vector'])
        low.position, high.position = .22, .30
        ramp.color_ramp.interpolation = 'CONSTANT'
        tan = ramp.color_ramp.elements.new(.24)
        tan.color = (.49, .38, .27, 1.)
        links.new(chips.outputs['Distance'], ramp.inputs[0])
    else:
        noise = add('ShaderNodeTexNoise', (-380, 120))
        noise.inputs['Scale'].default_value = 91
        noise.inputs['Detail'].default_value = 2
        low.position, high.position = .18, .82
        links.new(uv.outputs['UV'], noise.inputs['Vector'])
        links.new(noise.outputs['Fac'], ramp.inputs[0])
    links.new(ramp.outputs['Color'], pbr.inputs['Base Color'])
