# Launch Video Kit Lite

Turn your product and a few screenshots into a 1920×1080 launch video, from one JSON storyboard. Works as a skill for Claude Code and Codex, or as a plain Python script.

- **Light dependencies.** Python, Pillow and ffmpeg. No Node.js, headless browser, account or paid API.
- **Checks before it renders.** Text that does not fit, low contrast, text too fast to read, missing or blurry screenshots: every problem is listed at once and nothing is rendered until they are fixed.
- **Checks after it renders.** H.264, yuv420p, size, frame rate, duration, fast start and a non-blank still from every scene. A contact sheet lets you review the whole video in one image.

## Quick start

As a skill: copy this folder to `~/.claude/skills/` (Claude Code) or `~/.codex/skills/` (Codex), start a new session and ask for a launch video. See [INSTALL.md](INSTALL.md).

Without an agent:

```bash
python3 -m pip install Pillow          # plus ffmpeg: brew install ffmpeg / sudo apt install ffmpeg
python3 scripts/check_environment.py
python3 scripts/render_video.py examples/seo-release-check/storyboard.json
```

```json
{
  "version": 1,
  "product": {"name": "Acme", "url": "acme.example"},
  "scenes": [
    {"type": "title", "title": "Ship it today.", "subtitle": "One line on who it is for."},
    {"type": "screenshot", "image": "dashboard.png", "caption": "The new dashboard."},
    {"type": "cta", "title": "Try it free.", "url": "acme.example"}
  ]
}
```

Scene types: `title`, `statement`, `features`, `screenshot`, `cta`. Full format in [references/storyboard.md](references/storyboard.md); agent instructions in [SKILL.md](SKILL.md); install for Claude Code and Codex in [INSTALL.md](INSTALL.md).

## Lite and the full kit

| | Lite (this repo, MIT) | [Launch Video Kit](https://ohayo.si/skills/launch-video-kit/) ($4.90) |
| --- | --- | --- |
| Checks before and after rendering | ✓ | ✓ |
| Styles | midnight | midnight, paper, signal, custom brand colour |
| Formats | 16:9 | 16:9, 1:1, 9:16 with platform-safe margins |
| Scenes | title, statement, features, screenshot, cta | adds agent (a typed request to your coding agent and its reply), terminal (typed command and real output) and stat (count-up number) |
| Music | — | optional track with fade-out |
| Guides and examples | 1 example, 1 broken example | copywriting guide, 3 examples in 3 formats, broken example |

## License

Code: MIT. Bundled fonts: SIL Open Font License 1.1 (see `assets/fonts/`). Videos you make are yours.
