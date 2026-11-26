"""Non-destructive rectangular and partial-depth wall cut support."""
def wall_difference(wall, cutter, name=None):
    """Use the same exact solid subtraction for wall cuts and niche recesses."""
    mod = wall.modifiers.new(name or f"Cut - {cutter.name}", type='BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter
    mod.solver = 'EXACT'
    return mod
