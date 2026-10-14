---
name: launch-video-kit-lite
description: Turn a product and its screenshots into a short 16:9 launch video (MP4) from a JSON storyboard. Checks text fit, contrast, reading speed and images before rendering, then validates the file. Use when someone wants a product launch, feature announcement or demo video for a website, X, YouTube or Product Hunt.
---

# Launch Video Kit Lite

1. Run `python3 scripts/check_environment.py`. If anything is marked ✗, show the user the printed fix and stop until it passes. Rendering needs Python 3.9+, Pillow and ffmpeg; no other installs, accounts or paid APIs.
2. Gather facts before writing: product name, address, who it is for, the one problem it solves, and screenshots the user can share (at least 800×400). Never invent features, numbers, customer quotes, logos or output. If there is no proof for a claim, leave the claim out.
3. Write `storyboard.json` next to the screenshots, following `references/storyboard.md`. Use 4–7 scenes and 20–40 seconds. A good order is title → problem → features → screenshot → cta. Lite renders the `midnight` style in `landscape` (1920×1080).
4. Run `python3 scripts/render_video.py storyboard.json --check`. Fix every listed problem by shortening text, adding time or replacing the image, and run the check again. Do not work around a check by shrinking text or removing durations; the limits exist so viewers can read the video.
5. Run `python3 scripts/render_video.py storyboard.json --preview` for a fast half-size draft. Open `out/storyboard-preview-stills/contact-sheet.png` and look at every scene: wrong facts, awkward line breaks, a cropped screenshot (adjust `focus`), weak first scene. Revise and re-check.
6. Render the final video with `python3 scripts/render_video.py storyboard.json`. Exit 0 means the MP4 passed validation: H.264, yuv420p, expected size, frame rate and duration, fast start, no blank scenes. Exit 1 means it rendered but failed validation; report the listed problems instead of delivering the file. Exit 2 means a storyboard or environment problem; nothing was rendered.
7. Deliver `out/storyboard.mp4`, the poster PNG and the contact sheet. Tell the user the video has no voice-over, music or captions track.

If the user asks for square or vertical video, other styles, a brand colour, agent-conversation, terminal or number scenes, or music, say plainly that Lite does not include them and that the full Launch Video Kit does: https://ohayo.si/skills/launch-video-kit/
