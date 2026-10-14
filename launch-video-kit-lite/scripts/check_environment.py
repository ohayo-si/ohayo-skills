"""Check everything Launch Video Kit needs, and say how to fix what is missing.

Usage: python3 scripts/check_environment.py
Exit codes: 0 ready, 2 something is missing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ['InterDisplay-Bold.ttf', 'Inter-SemiBold.ttf', 'Inter-Regular.ttf', 'JetBrainsMono-Medium.ttf']


def checks():
    results = []
    ok = sys.version_info >= (3, 9)
    results.append(('Python 3.9+', ok, f'found {sys.version.split()[0]}', 'Install Python 3.9 or newer from python.org or your package manager.'))
    try:
        import PIL
        major = int(PIL.__version__.split('.')[0])
        results.append(('Pillow 9+', major >= 9, f'found {PIL.__version__}', 'Run: python3 -m pip install --upgrade Pillow'))
    except ImportError:
        results.append(('Pillow 9+', False, 'not installed', 'Run: python3 -m pip install Pillow'))
    for tool in ('ffmpeg', 'ffprobe'):
        path = shutil.which(tool)
        results.append((tool, bool(path), path or 'not on PATH',
                        'macOS: brew install ffmpeg · Ubuntu/Debian: sudo apt install ffmpeg · Windows: winget install Gyan.FFmpeg'))
    if shutil.which('ffmpeg'):
        out = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True, timeout=30).stdout
        results.append(('H.264 encoder (libx264)', 'libx264' in out, 'available' if 'libx264' in out else 'missing',
                        'Install a full ffmpeg build that includes libx264 (the package-manager builds above do).'))
    missing = [f for f in FONTS if not (ROOT / 'assets' / 'fonts' / f).exists()]
    results.append(('Bundled fonts', not missing, 'all present' if not missing else 'missing ' + ', '.join(missing),
                    'Re-extract the Launch Video Kit package; fonts live in assets/fonts/.'))
    return results


def main():
    results = checks()
    for name, ok, detail, fix in results:
        print(f'{"✓" if ok else "✗"} {name}: {detail}')
        if not ok:
            print(f'    fix: {fix}')
    ready = all(ok for _, ok, _, _ in results)
    print('Ready to render.' if ready else 'Not ready: fix the items marked ✗ and run this check again.')
    return 0 if ready else 2


if __name__ == '__main__':
    sys.exit(main())
