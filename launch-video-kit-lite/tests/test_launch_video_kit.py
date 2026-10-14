"""Tests for Launch Video Kit. Run: python3 -m unittest discover -s tests"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from PIL import Image  # noqa: E402

import lvk  # noqa: E402
from validate_video import moov_first, validate  # noqa: E402

HAS_FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def board(scenes, **extra):
    data = {'version': 1, 'product': {'name': 'Acme', 'url': 'acme.test'}, 'style': 'midnight', 'format': 'landscape', 'fps': 30, 'scenes': scenes}
    data.update(extra)
    return data


GOOD = [
    {'type': 'title', 'title': 'Ship it today.', 'subtitle': 'A short subtitle.', 'duration': 3},
    {'type': 'cta', 'title': 'Try it now.', 'url': 'acme.test', 'duration': 3},
]


class StoryboardChecks(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, data, name='board.json'):
        path = self.dir / name
        path.write_text(json.dumps(data))
        return path

    def problems(self, data):
        with self.assertRaises(lvk.StoryboardError) as caught:
            lvk.load(self.write(data))
        return ' | '.join(caught.exception.problems)

    def test_bundled_examples_pass_checks(self):
        for path in sorted((ROOT / 'examples').glob('*/storyboard.json')):
            if path.parent.name == 'broken':
                continue
            with self.subTest(example=path.parent.name):
                self.assertGreaterEqual(len(lvk.load(path).scenes), 2)

    def test_broken_example_reports_every_problem(self):
        with self.assertRaises(lvk.StoryboardError) as caught:
            lvk.load(ROOT / 'examples' / 'broken' / 'storyboard.json')
        expected = (ROOT / 'examples' / 'broken' / 'expected-problems.txt').read_text().strip().splitlines()
        self.assertEqual(['- ' + p for p in caught.exception.problems], expected)

    def test_unknown_scene_type_and_field(self):
        text = self.problems(board([{'type': 'intro', 'title': 'x'}, {**GOOD[1], 'colour': 'red'}]))
        self.assertIn('scene 1: type must be one of', text)
        self.assertIn('unknown field(s) colour', text)

    def test_missing_or_small_screenshot(self):
        Image.new('RGB', (400, 300), 'white').save(self.dir / 'small.png')
        text = self.problems(board([{'type': 'screenshot', 'image': 'nope.png'}, {'type': 'screenshot', 'image': 'small.png'}, GOOD[1]]))
        self.assertIn('cannot open image nope.png', text)
        self.assertIn('small.png is 400×300', text)

    def test_text_that_cannot_fit_is_rejected_before_rendering(self):
        long = 'Supercalifragilisticexpialidocious-' * 2
        text = self.problems(board([{'type': 'title', 'title': long[:79], 'duration': 6}, GOOD[1]]))
        self.assertIn('title does not fit', text)


    def test_reading_speed(self):
        words = 'one two three four five six seven eight nine ten eleven twelve'
        text = self.problems(board([{'type': 'statement', 'text': words, 'duration': 2}, GOOD[1]]))
        self.assertIn('12 words in 2s is too fast to read; use at least 5.0s', text)


    def test_total_duration_bounds(self):
        short = [{'type': 'title', 'title': 'Go.', 'duration': 2}, {'type': 'cta', 'title': 'Now.', 'duration': 2}]
        self.assertIn('total duration 4.0s', self.problems(board(short)))

    def test_defaults_and_warnings(self):
        b = lvk.load(self.write(board([{'type': 'title', 'title': 'Hello world.'}, {'type': 'statement', 'text': 'Ten times faster.'}])))
        self.assertTrue(all(lvk.MIN_SCENE <= s.duration <= lvk.MAX_SCENE for s in b.scenes))
        self.assertIn('last scene is not a cta', ' '.join(b.warnings))


class LayoutAndHelpers(unittest.TestCase):
    def test_contrast_reference_values(self):
        self.assertAlmostEqual(lvk.contrast((0, 0, 0), (255, 255, 255)), 21.0, places=1)
        self.assertAlmostEqual(lvk.contrast((119, 119, 119), (255, 255, 255)), 4.48, places=1)

    def test_balanced_wrap_avoids_a_lone_last_word(self):
        size, lines = lvk.fit('Ship the build. Not the SEO bugs.', 'display', 128, 72, 1536, 3)
        self.assertEqual(len(lines), 2)
        self.assertGreater(len(lines[-1].split()), 1)


    def test_every_style_meets_contrast_rules(self):
        for name, style in lvk.STYLES.items():
            with self.subTest(style=name):
                mid = tuple((a + b) // 2 for a, b in zip(lvk.hex_rgb(style['bg_top']), lvk.hex_rgb(style['bg_bottom'])))
                self.assertGreaterEqual(lvk.contrast(lvk.hex_rgb(style['text']), mid), 4.5)
                self.assertGreaterEqual(lvk.contrast(lvk.hex_rgb(style['muted']), mid), 4.5)
                self.assertGreaterEqual(lvk.contrast(lvk.hex_rgb(style['accent']), mid), 3.0)


@unittest.skipUnless(HAS_FFMPEG, 'ffmpeg not installed')
class RenderAndValidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        Image.new('RGB', (1200, 700), (40, 120, 200)).save(cls.dir / 'shot.png')
        scenes = [
            {'type': 'title', 'eyebrow': 'Acme', 'title': 'Ship it today.', 'duration': 2.5},
            {'type': 'screenshot', 'image': 'shot.png', 'caption': 'The dashboard.', 'duration': 2},
            {'type': 'cta', 'title': 'Try it.', 'url': 'acme.test', 'duration': 2.5},
        ]
        cls.path = cls.dir / 'tiny.json'
        cls.path.write_text(json.dumps(board(scenes)))
        cls.result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'render_video.py'), str(cls.path), '--preview'],
                                    capture_output=True, text=True, timeout=300)
        cls.video = cls.dir / 'out' / 'tiny-preview.mp4'

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def test_render_passes_its_own_validation(self):
        self.assertEqual(self.result.returncode, 0, self.result.stdout + self.result.stderr)
        report = json.loads((self.dir / 'out' / 'tiny-preview-report.json').read_text())
        self.assertTrue(report['pass'])
        self.assertEqual((report['facts']['width'], report['facts']['height']), (960, 540))
        self.assertTrue(report['facts']['faststart'])
        self.assertTrue((self.dir / 'out' / 'tiny-preview-stills' / 'contact-sheet.png').exists())

    def test_validator_catches_a_mismatched_video(self):
        full = lvk.load(self.path)  # expects 1920×1080 @ 30 fps; the file is a 960×540 @ 15 fps preview
        problems, _ = validate(full, self.video)
        text = ' '.join(problems)
        self.assertIn('size is 960×540', text)
        self.assertIn('frame rate is 15.00', text)

    def test_moov_after_mdat_is_detected(self):
        slow = self.dir / 'slow.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(self.video), '-c', 'copy', str(slow)], check=True, timeout=60)
        self.assertTrue(moov_first(self.video))
        self.assertFalse(moov_first(slow))

    def test_check_mode_renders_nothing(self):
        out = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'render_video.py'), str(self.path), '--check'],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0)
        self.assertIn('Storyboard OK: 3 scenes, 7.0s, 1920×1080 @ 30 fps', out.stdout)


if __name__ == '__main__':
    unittest.main()
