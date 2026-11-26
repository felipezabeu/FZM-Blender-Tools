"""Exact drag input, independent of viewport and Builder snap candidates."""
from math import hypot, isfinite
import re

# World distances are expressed in Blender units. Explicit units are physical;
# bare numbers use the configured scene units (imperial adaptive defaults to
# inches, consistent with Builder's other numeric placement tools).
LENGTH_UNITS = {
    'MICROMETERS': 1e-6, 'MILLIMETERS': .001, 'CENTIMETERS': .01,
    'METERS': 1., 'KILOMETERS': 1000.,
    'THOU': .0000254, 'INCHES': .0254, 'FEET': .3048, 'MILES': 1609.344,
}
EXPLICIT = {
    '"': .0254, 'in': .0254, 'inch': .0254, 'inches': .0254,
    'pol': .0254, 'polegada': .0254, 'polegadas': .0254,
    "'": .3048, 'ft': .3048, 'foot': .3048, 'feet': .3048,
    'mm': .001, 'cm': .01, 'm': 1., 'km': 1000.,
}
_UNIT_LABEL = {
    'MICROMETERS': 'µm', 'MILLIMETERS': 'mm', 'CENTIMETERS': 'cm',
    'METERS': 'm', 'KILOMETERS': 'km', 'THOU': 'thou',
    'INCHES': 'in', 'FEET': 'ft', 'MILES': 'mi',
}
_QUOTES = str.maketrans({'′':"'", '’':"'", '‘':"'", '″':'"', '“':'"', '”':'"', ',':'.'})
_DECIMAL = r'(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)'
_MAGNITUDE = rf'(?:[0-9]+\s+[0-9]+\s*/\s*[0-9]+|[0-9]+\s*/\s*[0-9]+|{_DECIMAL})'
_SCALAR = re.compile(rf'(?P<sign>[+-]?)\s*(?P<num>{_MAGNITUDE})\s*(?P<unit>[A-Za-z]+|["\'])?')
_FEET_INCHES = re.compile(rf"(?P<sign>[+-]?)\s*(?P<feet>{_MAGNITUDE})\s*'\s*(?P<inch>{_MAGNITUDE})\s*(?:\"|in(?:ch(?:es)?)?)?", re.I)
MAX_INPUT = 48


def _bare_unit(settings):
    system = settings.system
    if system == 'NONE':
        return 1., 'BU'
    length = settings.length_unit
    if length not in LENGTH_UNITS:
        length = 'INCHES' if system == 'IMPERIAL' else 'METERS'
    return LENGTH_UNITS[length], _UNIT_LABEL[length]


def unit_label(settings):
    return _bare_unit(settings)[1]


def _number(text):
    if '/' not in text:
        return float(text)
    a,b = text.split('/')
    amounts = a.split()
    whole = float(amounts[0]) if len(amounts)==2 else 0.
    return whole + float(amounts[-1])/float(b)


def distance_to_world(text, settings):
    """Parse a complete length or raise a short error suitable for the header."""
    clean = text.strip().lower().translate(_QUOTES)
    if len(clean) > MAX_INPUT:
        raise ValueError('Distance is too long.')
    try:
        if mix := _FEET_INCHES.fullmatch(clean):
            value = .3048*_number(mix['feet']) + .0254*_number(mix['inch'])
            sign = -1 if mix['sign']=='-' else 1
        elif one := _SCALAR.fullmatch(clean):
            value = _number(one['num'])
            sign = -1 if one['sign']=='-' else 1
            if one['unit']:
                value *= EXPLICIT[one['unit']]
            elif settings.system == 'NONE':
                if not isfinite(value):
                    raise ValueError('Distance must be finite.')
                return sign*value
            else:
                value *= _bare_unit(settings)[0]
        else:
            raise ValueError
    except (ValueError, KeyError, ArithmeticError) as error:
        raise ValueError('Enter a distance, e.g. 5", 127 mm or 0.127 m.') from error
    scale = settings.scale_length
    if not (isfinite(scale) and scale > 0.):
        raise ValueError('Scene unit scale must be positive.')
    distance = sign*value/scale
    if not isfinite(distance):
        raise ValueError('Distance must be finite.')
    return distance


def offset_for_distance(distance, raw, axis, *, epsilon=1e-5):
    """Use the unsnapped cursor delta for direction, not its magnitude.

    A negative length reverses the chosen direction. With no useful mouse
    direction we decline to guess which way the user wants to move.
    """
    x,y = raw
    if axis=='X':
        y = 0.
    elif axis=='Y':
        x = 0.
    size = hypot(x,y)
    if size <= epsilon:
        return None
    return distance*x/size, distance*y/size
