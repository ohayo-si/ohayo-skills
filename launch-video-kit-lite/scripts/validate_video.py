"""Check a rendered MP4 against what the storyboard promised.

Usage: python3 scripts/validate_video.py STORYBOARD.json VIDEO.mp4 [--stills DIR]
Exit codes: 0 pass, 1 problems found, 2 cannot run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw, ImageStat  # noqa: E402

import lvk  # noqa: E402


def probe(video: Path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(video)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f'ffprobe could not read {video.name}: {result.stderr.strip()[:200]}')
    return json.loads(result.stdout)


def moov_first(video: Path):
    """True when the moov atom precedes mdat (plays before fully downloaded)."""
    with video.open('rb') as fh:
        offset = 0
        size = video.stat().st_size
        while offset < size:
            fh.seek(offset)
            header = fh.read(16)
            if len(header) < 8:
                return False
            length = int.from_bytes(header[:4], 'big')
            kind = header[4:8]
            if length == 1:
                length = int.from_bytes(header[8:16], 'big')
            if kind == b'moov':
                return True
            if kind == b'mdat' or length < 8:
                return False
            offset += length
    return False


def still(video: Path, t: float, out: Path):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.3f}', '-i', str(video), '-frames:v', '1', str(out)],
                   check=True, capture_output=True, timeout=60)
    return out


def contact_sheet(paths, out: Path, columns=3):
    images = [Image.open(p).convert('RGB') for p in paths]
    w = 480
    h = int(images[0].height * w / images[0].width)
    rows = (len(images) + columns - 1) // columns
    gap = 16
    sheet = Image.new('RGB', (columns * w + (columns + 1) * gap, rows * (h + 34) + (rows + 1) * gap), (20, 20, 24))
    draw = ImageDraw.Draw(sheet)
    for i, im in enumerate(images):
        x = gap + (i % columns) * (w + gap)
        y = gap + (i // columns) * (h + 34 + gap)
        sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        draw.text((x, y + h + 8), f'scene {i + 1}', fill=(200, 200, 210))
    sheet.save(out)
    return out


def validate(board: lvk.Storyboard, video: Path, stills_dir: Path | None = None):
    problems, facts = [], {}
    if not video.exists():
        return [f'{video} does not exist'], facts
    info = probe(video)
    streams = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
    if len(streams) != 1:
        return ['expected exactly one video stream'], facts
    v = streams[0]
    num, den = (int(x) for x in v.get('avg_frame_rate', '0/1').split('/'))
    fps = num / den if den else 0
    duration = float(info.get('format', {}).get('duration', 0))
    facts.update({'codec': v.get('codec_name'), 'pix_fmt': v.get('pix_fmt'), 'width': v.get('width'), 'height': v.get('height'),
                  'fps': round(fps, 3), 'duration': round(duration, 3), 'bytes': video.stat().st_size,
                  'audio_streams': sum(1 for s in info['streams'] if s.get('codec_type') == 'audio'), 'faststart': moov_first(video)})
    if facts['codec'] != 'h264':
        problems.append(f'codec is {facts["codec"]}; expected h264 for widest playback')
    if facts['pix_fmt'] != 'yuv420p':
        problems.append(f'pixel format is {facts["pix_fmt"]}; expected yuv420p (other formats fail on some phones and sites)')
    if (facts['width'], facts['height']) != (board.width, board.height):
        problems.append(f'size is {facts["width"]}×{facts["height"]}; storyboard expects {board.width}×{board.height}')
    if abs(fps - board.fps) > 0.01:
        problems.append(f'frame rate is {fps:.2f}; storyboard expects {board.fps}')
    if abs(duration - board.duration) > 1.5 / board.fps + 0.05:
        problems.append(f'duration is {duration:.2f}s; storyboard expects {board.duration:.2f}s')
    if not facts['faststart']:
        problems.append('moov atom is after the media data; re-encode with -movflags +faststart so it starts playing immediately')
    if facts['bytes'] > 100 * 1024 * 1024:
        problems.append('file is over 100 MB; too large for most upload forms')
    stills = []
    if stills_dir is not None:
        stills_dir.mkdir(parents=True, exist_ok=True)
        for i, t in enumerate(lvk.scene_midpoints(board), start=1):
            path = still(video, min(t, max(0.0, duration - 0.05)), stills_dir / f'scene-{i:02d}.png')
            stat = ImageStat.Stat(Image.open(path).convert('L'))
            if stat.stddev[0] < 6:
                problems.append(f'scene {i} still at {t:.2f}s is nearly blank')
            stills.append(path)
        facts['contact_sheet'] = str(contact_sheet(stills, stills_dir / 'contact-sheet.png'))
        facts['stills'] = [str(p) for p in stills]
    return problems, facts


def main():
    parser = argparse.ArgumentParser(description='Validate a rendered launch video against its storyboard.')
    parser.add_argument('storyboard')
    parser.add_argument('video')
    parser.add_argument('--stills', help='directory for per-scene stills and a contact sheet')
    parser.add_argument('--preview', action='store_true', help='the video was rendered with --preview')
    args = parser.parse_args()
    if not shutil.which('ffprobe') or not shutil.which('ffmpeg'):
        print('ffmpeg/ffprobe not found; run scripts/check_environment.py', file=sys.stderr)
        return 2
    try:
        board = lvk.load(args.storyboard, **(dict(scale=0.5, fps_override=15) if args.preview else {}))
    except lvk.StoryboardError as error:
        print('Storyboard problems:\n- ' + '\n- '.join(error.problems), file=sys.stderr)
        return 2
    problems, facts = validate(board, Path(args.video), Path(args.stills) if args.stills else None)
    print(json.dumps({'pass': not problems, 'problems': problems, 'facts': facts}, indent=2))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
