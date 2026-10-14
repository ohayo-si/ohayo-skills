"""Lite-only behaviour. Run: python3 -m unittest discover -s tests"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import lvk  # noqa: E402

SCENES = [
    {'type': 'title', 'title': 'Ship it today.', 'duration': 3},
    {'type': 'cta', 'title': 'Try it now.', 'duration': 3},
]


class FullKitOptions(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def problems(self, **extra):
        data = {'version': 1, 'product': {'name': 'Acme'}, 'scenes': SCENES, **extra}
        path = self.dir / 'board.json'
        path.write_text(json.dumps(data))
        with self.assertRaises(lvk.StoryboardError) as caught:
            lvk.load(path)
        return ' | '.join(caught.exception.problems)

    def test_lite_renders_one_style_and_format(self):
        self.assertEqual(list(lvk.STYLES), ['midnight'])
        self.assertEqual(list(lvk.FORMATS), ['landscape'])
        self.assertEqual(set(lvk.SCENE_FIELDS), {'title', 'statement', 'features', 'screenshot', 'cta'})

    def test_full_kit_options_are_named_not_silently_ignored(self):
        text = self.problems(style='paper', format='vertical', accent='#2949e0',
                             scenes=[{'type': 'terminal', 'command': 'ls'}, SCENES[1]])
        self.assertIn('style must be one of midnight (the full kit adds more', text)
        self.assertIn('format must be one of landscape (the full kit adds more', text)
        self.assertIn('accent: custom colours need the full kit', text)
        self.assertIn('scene 1: type must be one of', text)


if __name__ == '__main__':
    unittest.main()
