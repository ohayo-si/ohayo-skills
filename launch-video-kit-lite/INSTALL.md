# Install Launch Video Kit Lite

## Requirements

- Python 3.9 or newer
- Pillow 9 or newer: `python3 -m pip install Pillow`
- ffmpeg with libx264: macOS `brew install ffmpeg` · Ubuntu/Debian `sudo apt install ffmpeg` · Windows `winget install Gyan.FFmpeg`

No Node.js, browser, account, API key or paid service. Fonts (Inter and JetBrains Mono, SIL Open Font License) are bundled in `assets/fonts/`.

## Claude Code

Put this folder at `~/.claude/skills/launch-video-kit-lite/` (or `.claude/skills/launch-video-kit-lite/` inside a project), so that `SKILL.md` sits directly inside it:

```bash
git clone --depth 1 https://github.com/ohayo-si/ohayo-skills
mkdir -p ~/.claude/skills
cp -R ohayo-skills/launch-video-kit-lite ~/.claude/skills/
```

Start a new session and ask, for example:

> Make a 30-second launch video for my app from these screenshots.

## Codex

Copy the folder to `~/.codex/skills/launch-video-kit-lite/` the same way and start a new session.

## Without an agent

```bash
python3 scripts/check_environment.py
python3 scripts/render_video.py examples/seo-release-check/storyboard.json --check
python3 scripts/render_video.py examples/seo-release-check/storyboard.json --preview
python3 scripts/render_video.py examples/seo-release-check/storyboard.json
```

The finished MP4, poster, stills and report appear in `examples/seo-release-check/out/`.

## Tests

```bash
python3 -m unittest discover -s tests
```

The rendering tests are skipped when ffmpeg is not installed.

## Limits

- 2–12 scenes, 5–90 seconds, 24/25/30/60 fps, 1920×1080 only.
- No voice-over, music, captions track or AI-generated footage.
- Render time on a recent laptop: roughly 1–2 seconds of compute per second of video; `--preview` is about 6× faster.
