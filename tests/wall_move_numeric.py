"""Pure parser/axis regression checks: python3 tests/wall_move_numeric.py."""
from importlib.util import module_from_spec, spec_from_file_location
from math import isclose
from pathlib import Path
from types import SimpleNamespace
import unittest

path = Path(__file__).resolve().parents[1] / 'extensions/fzm_builder/operators/wall_move_input.py'
spec = spec_from_file_location('wall_move_input', path)
units = module_from_spec(spec)
spec.loader.exec_module(units)


def setting(system, unit='ADAPTIVE', scale=1.):
    return SimpleNamespace(system=system,length_unit=unit,scale_length=scale)


class WallDistanceTests(unittest.TestCase):
    def test_scene_bare_numbers(self):
        pairs = [
            (setting('IMPERIAL','INCHES'), '5', .127),
            (setting('IMPERIAL','INCHES',.5), '5', .254),
            (setting('IMPERIAL','ADAPTIVE'), '5', .127),
            (setting('IMPERIAL','FEET'), '5', 1.524),
            (setting('METRIC','METERS'), '1', 1.),
            (setting('METRIC','METERS',.25), '1', 4.),
            (setting('METRIC','MILLIMETERS',.01), '5.5', .55),
            (setting('METRIC','CENTIMETERS'), '2,5', .025),
            (setting('NONE','ADAPTIVE',.0254), '5', 5.),
        ]
        for s,text,wanted in pairs:
            with self.subTest(s=s,text=text):
                self.assertTrue(isclose(units.distance_to_world(text,s),wanted))

    def test_explicit_measurements(self):
        s = setting('METRIC','METERS')
        for text,wanted in [('5"',.127),('5in',.127),('5 inches',.127),('5 polegadas',.127),
                            ('5″',.127),('127 mm',.127),('0.127 m',.127),('5 1/2"',.1397),
                            ("5' 6\"",1.6764),("-5'6\"", -1.6764),('1/2"',.0127),
                            ('-5"',-.127),('.5m',.5),('+5in',.127),("5'",1.524)]:
            with self.subTest(text=text):
                self.assertTrue(isclose(units.distance_to_world(text,s),wanted))
        self.assertTrue(isclose(units.distance_to_world('5"',setting('METRIC','METERS',.01)),12.7))

    def test_incomplete_or_invalid(self):
        for text in ('','5 i','5 2','5 cats','5/0','NaN','Inf','1e9','.' ,'5"'*60):
            with self.subTest(text=text), self.assertRaises(ValueError):
                units.distance_to_world(text,setting('IMPERIAL','INCHES'))
        with self.assertRaises(ValueError):
            units.distance_to_world('5',setting('METRIC','METERS',0.))

    def test_mouse_aim_and_axis(self):
        self.assertEqual(units.offset_for_distance(.127,(-2.,1.),'X'),(-.127,0.))
        self.assertEqual(units.offset_for_distance(.127,(-2.,1.),'Y'),(0.,.127))
        self.assertEqual(units.offset_for_distance(-.127,(-2.,1.),'X'),(.127,0.))
        self.assertEqual(units.offset_for_distance(5.,(3.,4.),'FREE'),(3.,4.))
        self.assertIsNone(units.offset_for_distance(.127,(0.,3.),'X'))
        self.assertIsNone(units.offset_for_distance(.127,(0.,0.),'FREE'))


if __name__ == '__main__':
    unittest.main()
