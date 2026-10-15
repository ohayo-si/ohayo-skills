"""Lite behaviour. Run: python3 -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import check_email  # noqa: E402


def offline(name):
    raw = json.loads((ROOT / 'examples' / name).read_text())
    return check_email.Resolver(None, {k: v for k, v in raw.items() if k != '_comment'})


def codes(result):
    return [f['code'] for f in result['findings']]


class Lite(unittest.TestCase):
    def test_clean_example(self):
        result = check_email.run('example.com', offline('clean-records.json'))
        self.assertEqual(result['findings'], [])
        self.assertEqual(result['fixes'], [])

    def test_broken_example(self):
        result = check_email.run('example.org', offline('broken-records.json'))
        blockers = [f['code'] for f in result['findings'] if f['severity'] == 'blocker']
        self.assertEqual(sorted(blockers), ['mx-unresolved', 'spf-multiple'])
        self.assertIn('dmarc-monitor-only', codes(result))
        self.assertIn('spf-ptr', codes(result))

    def test_spf_and_dmarc_rules(self):
        cases = {('v=spf1 +all', 'v=DMARC1; p=reject; rua=mailto:d@example.com'): 'spf-pass-all',
                 ('v=spf1 -all', 'p=reject; v=DMARC1'): 'dmarc-syntax',
                 ('v=spf1 -all', 'v=DMARC1; p=maybe'): 'dmarc-syntax',
                 ('v=spf1 ip4:300.0.0.1 -all', 'v=DMARC1; p=none'): 'spf-syntax'}
        for (spf, dmarc), code in cases.items():
            with self.subTest(spf=spf, dmarc=dmarc):
                dns = check_email.Resolver(None, {'example.com TXT': [spf], '_dmarc.example.com TXT': [dmarc]})
                self.assertIn(code, codes(check_email.run('example.com', dns)))

    def test_full_version_options_absent(self):
        with self.assertRaises(SystemExit):
            check_email.main(['example.com', '--eml', 'x.eml'])
        with self.assertRaises(SystemExit):
            check_email.main(['example.com', '--provider', 'google'])

    def test_report_points_to_full_version(self):
        text = check_email.markdown(check_email.run('example.com', offline('clean-records.json')))
        self.assertIn('https://ohayo.si/skills/email-deliverability-check/', text)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = str(Path(tmp) / 'r.md')
            self.assertEqual(check_email.main(['example.com', '--records', str(ROOT / 'examples/clean-records.json'), '--output', out]), 0)
            self.assertEqual(check_email.main(['example.org', '--records', str(ROOT / 'examples/broken-records.json'), '--output', out]), 1)
            self.assertEqual(check_email.main(['bad domain', '--records', str(ROOT / 'examples/clean-records.json')]), 2)


if __name__ == '__main__':
    unittest.main()
