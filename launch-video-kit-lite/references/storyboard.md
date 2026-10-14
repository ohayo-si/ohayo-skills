# Storyboard format (version 1, Lite)

A storyboard is one JSON file. Image paths are relative to it.

```json
{
  "version": 1,
  "product": {"name": "Acme", "url": "acme.example"},
  "style": "midnight",
  "format": "landscape",
  "fps": 30,
  "scenes": [
    {"type": "title", "eyebrow": "Acme", "title": "Ship it today.", "subtitle": "One line on who it is for.", "duration": 5}
  ]
}
```

| Field | Values | Default |
| --- | --- | --- |
| `version` | `1` | required |
| `product.name` | 1–40 characters | required |
| `product.url` | up to 60 characters | `""` |
| `style` | `midnight` (dark) | `midnight` |
| `format` | `landscape` 1920×1080 | `landscape` |
| `fps` | 24, 25, 30, 60 | 30 |
| `scenes` | 2–12 scenes, 5–90 seconds in total | required |

Every scene accepts `duration` in seconds (1.5–10). Without it, a duration is computed from the amount of text.

## Scene types

| Type | Required | Optional | Limits |
| --- | --- | --- | --- |
| `title` | `title` | `eyebrow`, `subtitle` | title 80, subtitle 140, eyebrow 40 characters |
| `statement` | `text` | `eyebrow` | text 140 characters, up to 4 lines |
| `features` | `items` | `title` | 2–4 items of up to 90 characters |
| `screenshot` | `image` | `caption`, `focus` | image at least 800×400; `focus` is `[x, y]` from 0 to 1, where the slow zoom heads |
| `cta` | `title` | `url`, `note` | title 60, url 50, note 90 characters |

## Checks before rendering

Rendering starts only when all of these pass. Every problem is listed at once.

- Text fits its area at a readable size. Long text is never shrunk below the minimum; you are asked to shorten it.
- Text, muted text and accent reach WCAG contrast against the background (4.5:1, 4.5:1, 3:1).
- Reading speed: at most 3 words per second of on-screen time (eyebrows not counted).
- Screenshots exist, open, and are at least 800×400.

## Checks after rendering

`render_video.py` validates the MP4 automatically (also available as `scripts/validate_video.py`): H.264 video, yuv420p pixels, the storyboard's size, frame rate and duration, `moov` before `mdat` (fast start), under 100 MB, and a non-blank still from every scene. Stills and a contact sheet are saved for review.

## Output files

| File | Purpose |
| --- | --- |
| `out/NAME.mp4` | the video |
| `out/NAME-poster.png` | first scene, for thumbnails and `<video poster>` |
| `out/NAME-stills/` | one still per scene and `contact-sheet.png` |
| `out/NAME-report.json` | checks, warnings, probe results and render time |

## Full kit

The full [Launch Video Kit](https://ohayo.si/skills/launch-video-kit/) adds `paper` and `signal` styles, a custom `accent`, `square` and `vertical` formats with platform-safe margins, `agent`, `terminal` and `stat` scenes, optional music, a copywriting guide and more examples.
