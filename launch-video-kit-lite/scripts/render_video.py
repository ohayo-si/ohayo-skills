"""Render a launch video from a JSON storyboard.

Usage:
  python3 scripts/render_video.py STORYBOARD.json --check          # checks only, no rendering
  python3 scripts/render_video.py STORYBOARD.json --preview        # fast half-size, 15 fps draft
  python3 scripts/render_video.py STORYBOARD.json [--out DIR]

Nothing is rendered until every storyboard check passes. After rendering, the MP4 is
validated (codec, size, frame rate, duration, fast start, non-blank stills) and a
contact sheet with one still per scene is written next to it.
Exit codes: 0 pass, 1 rendered but validation failed, 2 storyboard or environment problem.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lvk  # noqa: E402
from validate_video import validate  # noqa: E402


def encode(board, renderer, target: Path, music: Path | None = None):
    tmp = target.with_suffix('.partial.mp4')
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{board.width}x{board.height}',
           '-r', str(board.fps), '-i', '-']
    cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(board.frame_count):
            proc.stdin.write(renderer.frame(i / board.fps).tobytes())
            if i % (board.fps * 2) == 0:
                print(f'  frame {i}/{board.frame_count}', end='\r', flush=True)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors='replace')
    if proc.wait() != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f'ffmpeg failed: {err.strip()[:400]}')
    tmp.replace(target)


def main():
    parser = argparse.ArgumentParser(description='Render a launch video from a JSON storyboard.')
    parser.add_argument('storyboard')
    parser.add_argument('--out', help='output directory (default: out/ next to the storyboard)')
    parser.add_argument('--check', action='store_true', help='run storyboard checks only')
    parser.add_argument('--preview', action='store_true', help='half-size 15 fps draft for quick review')
    args = parser.parse_args()

    options = dict(scale=0.5, fps_override=15) if args.preview else {}
    try:
        board = lvk.load(args.storyboard, **options)
    except lvk.StoryboardError as error:
        print('Storyboard problems (nothing rendered):\n- ' + '\n- '.join(error.problems), file=sys.stderr)
        return 2
    for warning in board.warnings:
        print(f'warning: {warning}')
    summary = f'{len(board.scenes)} scenes, {board.duration:.1f}s, {board.width}×{board.height} @ {board.fps} fps, style {board.style_name}'
    if args.check:
        print(f'Storyboard OK: {summary}')
        return 0
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        print('ffmpeg/ffprobe not found; run scripts/check_environment.py', file=sys.stderr)
        return 2
    music = None

    source = Path(args.storyboard)
    out_dir = Path(args.out) if args.out else source.parent / 'out'
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem + ('-preview' if args.preview else '')
    video = out_dir / f'{stem}.mp4'
    print(f'Rendering {summary}')
    started = time.time()
    renderer = lvk.Renderer(board)
    encode(board, renderer, video, music)
    poster = out_dir / f'{stem}-poster.png'
    renderer.frame(lvk.scene_midpoints(board)[0]).save(poster)
    problems, facts = validate(board, video, out_dir / f'{stem}-stills')
    report = {'storyboard': str(source), 'video': str(video), 'poster': str(poster), 'summary': summary,
              'render_seconds': round(time.time() - started, 1), 'warnings': board.warnings,
              'pass': not problems, 'problems': problems, 'facts': facts}
    (out_dir / f'{stem}-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(' ' * 40, end='\r')
    print(f'{"PASS" if not problems else "FAIL"} {video} ({facts.get("bytes", 0) / 1e6:.1f} MB, {report["render_seconds"]}s)')
    for problem in problems:
        print(f'- {problem}')
    print(f'Contact sheet: {facts.get("contact_sheet")}')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
