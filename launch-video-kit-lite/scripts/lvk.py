"""Launch Video Kit engine: storyboard checks, layout and frame rendering.

Pure Python + Pillow. Frames are piped to ffmpeg by render_video.py.
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'assets' / 'fonts'
FONT_FILES = {
    'display': 'InterDisplay-Bold.ttf',
    'medium': 'Inter-SemiBold.ttf',
    'body': 'Inter-Regular.ttf',
    'mono': 'JetBrainsMono-Medium.ttf',
}

FORMATS = {
    'landscape': (1920, 1080),
}

STYLES = {
    'midnight': {
        'bg_top': '#0b0b10', 'bg_bottom': '#17131f', 'text': '#f4f4f6', 'muted': '#a7a7b3',
        'accent': '#ff6a3d', 'card': '#191922', 'card_line': '#2a2a36', 'glow': 0.22,
    },
}

SCENE_FIELDS = {
    'title': ({'title'}, {'subtitle', 'eyebrow'}),
    'statement': ({'text'}, {'eyebrow'}),
    'features': ({'items'}, {'title'}),
    'screenshot': ({'image'}, {'caption', 'focus'}),
    'cta': ({'title'}, {'url', 'note'}),
}

MAX_WORDS_PER_SECOND = 3.0
ENTER = 0.6
EXIT = 0.35
MIN_SCENE, MAX_SCENE = 1.5, 10.0
MIN_TOTAL, MAX_TOTAL = 5.0, 90.0
FULL_KIT = ''
FULL_KIT = ' (the full kit adds more: https://ohayo.si/skills/launch-video-kit/)'


class StoryboardError(Exception):
    def __init__(self, problems):
        super().__init__('; '.join(problems))
        self.problems = problems


# ---------- small helpers ----------

def hex_rgb(value: str):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError(f'invalid colour {value!r}; use #rrggbb')
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def luminance(rgb):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def words(text: str) -> int:
    return len(re.findall(r"[\w'’%$.,/-]+", text or ''))


_font_cache: dict = {}


def font(kind: str, size: int):
    key = (kind, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS / FONT_FILES[kind]), size)
    return _font_cache[key]


def wrap(text: str, fnt, width: int):
    """Greedy word wrap by measured width. Returns lines, or None if a single word is wider than width."""
    lines, current = [], ''
    for word in text.split():
        trial = f'{current} {word}'.strip()
        if fnt.getlength(trial) <= width:
            current = trial
            continue
        if not current or fnt.getlength(word) > width:
            return None
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def balance(text: str, fnt, width: int, lines):
    """Narrowest width that keeps the same line count, so the last line is not a lone word."""
    lo, hi, best = int(width * 0.5), width, lines
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = wrap(text, fnt, mid)
        if trial is not None and len(trial) <= len(lines):
            best, hi = trial, mid - 1
        else:
            lo = mid + 1
    return best


def fit(text: str, kind: str, base: int, minimum: int, width: int, max_lines: int):
    """Largest font size (base→minimum) whose wrapped text fits width and max_lines."""
    size = base
    while size >= minimum:
        fnt = font(kind, size)
        lines = wrap(text, fnt, width)
        if lines is not None and len(lines) <= max_lines:
            return size, (balance(text, fnt, width, lines) if len(lines) > 1 else lines)
        size -= 2
    return None


# ---------- storyboard ----------

@dataclass
class Scene:
    index: int
    type: str
    data: dict
    duration: float
    start: float = 0.0
    layout: dict = field(default_factory=dict)


@dataclass
class Storyboard:
    name: str
    url: str
    style: dict
    style_name: str
    format: str
    width: int
    height: int
    fps: int
    scenes: list
    base_dir: Path
    warnings: list

    @property
    def duration(self):
        return sum(s.duration for s in self.scenes)

    @property
    def frame_count(self):
        return round(self.duration * self.fps)


def scene_text(scene_type, data):
    parts = []
    for key in ('title', 'subtitle', 'text', 'label', 'caption', 'note', 'command', 'prompt'):  # eyebrows are glanced, not read
        if isinstance(data.get(key), str):
            parts.append(data[key])
    if scene_type == 'features':
        parts += [i for i in data.get('items', []) if isinstance(i, str)]
    return ' '.join(parts)


def default_duration(scene_type, data):
    if scene_type == 'screenshot':
        return 4.0
    return round(clamp(ENTER + EXIT + words(scene_text(scene_type, data)) / 2.8 + 0.6, 2.5, MAX_SCENE), 2)


def load(path, scale: float = 1.0, fps_override: int | None = None) -> Storyboard:
    """Read and check a storyboard. Raises StoryboardError listing every problem found."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise StoryboardError([f'cannot read storyboard: {error}'])
    problems, warnings = [], []
    if not isinstance(raw, dict):
        raise StoryboardError(['storyboard must be a JSON object'])
    if raw.get('version') != 1:
        problems.append('version must be 1')
    product = raw.get('product') if isinstance(raw.get('product'), dict) else {}
    name = product.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 40:
        problems.append('product.name is required (1–40 characters)')
        name = 'Product'
    url = product.get('url', '')
    if not isinstance(url, str) or len(url) > 60:
        problems.append('product.url must be a string up to 60 characters')
        url = ''
    style_name = raw.get('style', 'midnight')
    if style_name not in STYLES:
        problems.append(f'style must be one of {", ".join(STYLES)}' + FULL_KIT)
        style_name = 'midnight'
    style = {k: (hex_rgb(v) if isinstance(v, str) else v) for k, v in STYLES[style_name].items()}
    if 'accent' in raw:
        problems.append('accent: custom colours need the full kit: https://ohayo.si/skills/launch-video-kit/')
    fmt = raw.get('format', 'landscape')
    if fmt not in FORMATS:
        problems.append(f'format must be one of {", ".join(FORMATS)}' + FULL_KIT)
        fmt = 'landscape'
    fps = raw.get('fps', 30)
    if fps not in (24, 25, 30, 60):
        problems.append('fps must be 24, 25, 30 or 60')
        fps = 30
    if fps_override:
        fps = fps_override
    width, height = FORMATS[fmt]
    width, height = int(round(width * scale / 2) * 2), int(round(height * scale / 2) * 2)

    # colour contrast is a property of the style + accent
    mid_bg = tuple((a + b) // 2 for a, b in zip(style['bg_top'], style['bg_bottom']))
    for label, colour, need in (('text', style['text'], 4.5), ('muted text', style['muted'], 4.5), ('accent', style['accent'], 3.0)):
        ratio = contrast(colour, mid_bg)
        if ratio < need:
            problems.append(f'{label} colour contrast {ratio:.1f}:1 against the background is below {need}:1; choose a {"lighter" if luminance(mid_bg) < 0.2 else "darker"} accent')
    on_accent = pick_on_accent(style['accent'])
    if contrast(on_accent, style['accent']) < 4.5:
        problems.append('accent is too mid-tone for readable button text; choose a lighter or darker accent')

    scenes_raw = raw.get('scenes')
    if not isinstance(scenes_raw, list) or not 2 <= len(scenes_raw) <= 12:
        problems.append('scenes must be a list of 2–12 scenes')
        scenes_raw = scenes_raw if isinstance(scenes_raw, list) else []
    scenes = []
    for i, item in enumerate(scenes_raw[:12], start=1):
        where = f'scene {i}'
        if not isinstance(item, dict) or item.get('type') not in SCENE_FIELDS:
            problems.append(f'{where}: type must be one of {", ".join(SCENE_FIELDS)}' + FULL_KIT)
            continue
        kind = item['type']
        required, optional = SCENE_FIELDS[kind]
        data = {k: v for k, v in item.items() if k not in ('type', 'duration')}
        unknown = set(data) - required - optional
        if unknown:
            problems.append(f'{where} ({kind}): unknown field(s) {", ".join(sorted(unknown))}')
        missing = [k for k in sorted(required) if k not in data]
        if missing:
            problems.append(f'{where} ({kind}): missing {", ".join(missing)}')
            continue
        problems += check_fields(where, kind, data, path.parent)
        duration = item.get('duration', default_duration(kind, data))
        if not isinstance(duration, (int, float)) or not MIN_SCENE <= duration <= MAX_SCENE:
            problems.append(f'{where} ({kind}): duration must be {MIN_SCENE}–{MAX_SCENE} seconds')
            continue
        count = words(scene_text(kind, data))
        readable = max(0.5, duration - ENTER - EXIT)
        if kind == 'screenshot':
            pass  # the image carries the scene; captions are short
        elif count / readable > MAX_WORDS_PER_SECOND:
            need = math.ceil((count / MAX_WORDS_PER_SECOND + ENTER + EXIT) * 2) / 2
            problems.append(f'{where} ({kind}): {count} words in {duration}s is too fast to read; use at least {need}s or cut words')
        scenes.append(Scene(i, kind, data, float(duration)))

    board = Storyboard(name, url, style, style_name, fmt, width, height, fps, scenes, path.parent, warnings)
    if scenes and not problems:
        total = board.duration
        if not MIN_TOTAL <= total <= MAX_TOTAL:
            problems.append(f'total duration {total:.1f}s must be {MIN_TOTAL:.0f}–{MAX_TOTAL:.0f}s')
        if scenes[-1].type != 'cta':
            warnings.append('last scene is not a cta; viewers will not see where to go')
        start = 0.0
        for scene in scenes:
            scene.start = start
            start += scene.duration
            try:
                scene.layout = layout(board, scene)
            except StoryboardError as error:
                problems += error.problems
    if problems:
        raise StoryboardError(problems)
    return board


def check_fields(where, kind, data, base_dir):
    problems = []
    def text(key, limit, required=True):
        value = data.get(key)
        if value is None and not required:
            return
        if not isinstance(value, str) or not value.strip():
            problems.append(f'{where} ({kind}): {key} must be non-empty text')
        elif len(value) > limit:
            problems.append(f'{where} ({kind}): {key} is {len(value)} characters; keep it under {limit}')
    if kind == 'title':
        text('title', 80); text('subtitle', 140, False); text('eyebrow', 40, False)
    elif kind == 'statement':
        text('text', 140); text('eyebrow', 40, False)
    elif kind == 'features':
        text('title', 60, False)
        items = data.get('items')
        if not isinstance(items, list) or not 2 <= len(items) <= 4 or not all(isinstance(i, str) and i.strip() and len(i) <= 90 for i in items):
            problems.append(f'{where} (features): items must be 2–4 texts of up to 90 characters')
    elif kind == 'screenshot':
        text('caption', 90, False)
        image = data.get('image')
        if not isinstance(image, str):
            problems.append(f'{where} (screenshot): image must be a file path')
        else:
            file = (base_dir / image).resolve()
            try:
                with Image.open(file) as im:
                    w, h = im.size
                if w < 800 or h < 400:
                    problems.append(f'{where} (screenshot): {image} is {w}×{h}; use at least 800×400 so it stays sharp')
            except (OSError, ValueError):
                problems.append(f'{where} (screenshot): cannot open image {image}')
        focus = data.get('focus')
        if focus is not None and not (isinstance(focus, list) and len(focus) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in focus)):
            problems.append(f'{where} (screenshot): focus must be [x, y] with values 0–1')
    elif kind == 'cta':
        text('title', 60); text('url', 50, False); text('note', 90, False)
    return problems


def pick_on_accent(accent):
    dark, light = (12, 12, 16), (255, 255, 255)
    return dark if contrast(dark, accent) >= contrast(light, accent) else light


# ---------- layout ----------

def frame_box(board):
    """Content box with social-safe margins (vertical keeps clear of platform UI)."""
    w, h = board.width, board.height
    mx = int(w * 0.08)
    my = int(h * 0.10)
    return mx, my, w - mx, h - my


def layout(board, scene):
    """Font sizes and wrapped lines for a scene; raises StoryboardError when text cannot fit."""
    u = min(board.width, board.height) / 1080
    x0, y0, x1, y1 = frame_box(board)
    cw = x1 - x0
    d = scene.data
    where = f'scene {scene.index} ({scene.type})'
    problems = []
    out = {}

    def need(key, text, kind, base, minimum, width, lines):
        result = fit(text, kind, int(base * u), int(minimum * u), width, lines)
        if result is None:
            problems.append(f'{where}: {key} does not fit in {lines} line(s) at the minimum readable size; shorten it')
            return None
        out[key] = result
        return result

    big = 1.0 if board.format == 'landscape' else 0.82
    if scene.type == 'title':
        if d.get('eyebrow'): need('eyebrow', d['eyebrow'], 'medium', 34, 26, cw, 1)
        need('title', d['title'], 'display', 128 * big, 72 * big, cw, 3)
        if d.get('subtitle'): need('subtitle', d['subtitle'], 'body', 46, 32, int(cw * 0.9), 3)
    elif scene.type == 'statement':
        if d.get('eyebrow'): need('eyebrow', d['eyebrow'], 'medium', 34, 26, cw, 1)
        need('text', d['text'], 'display', 100 * big, 58 * big, cw, 4)
    elif scene.type == 'features':
        if d.get('title'): need('title', d['title'], 'display', 72 * big, 48 * big, cw, 2)
        n = len(d['items'])
        row = board.format == 'landscape'
        gap = int(28 * u)
        card_w = (cw - gap * (n - 1)) // n if row else cw
        out['cards'] = []
        for i, item in enumerate(d['items']):
            r = fit(item, 'medium', int((40 if row else 50) * u), int((28 if row else 34) * u), card_w - int(64 * u), 4 if row else 2)
            if r is None:
                problems.append(f'{where}: item {i + 1} does not fit its card; shorten it')
            out['cards'].append(r)
        out['row'] = row
        out['card_w'] = card_w
        out['gap'] = gap
    elif scene.type == 'screenshot':
        if d.get('caption'): need('caption', d['caption'], 'medium', 46, 32, cw, 2)
    elif scene.type == 'cta':
        need('title', d['title'], 'display', 112 * big, 64 * big, cw, 2)
        if d.get('url'): need('url', d['url'], 'medium', 50, 34, int(cw * 0.8), 1)
        if d.get('note'): need('note', d['note'], 'body', 38, 28, cw, 2)
    if problems:
        raise StoryboardError(problems)
    return out


# ---------- rendering ----------

def text_block(lines, fnt, colour, line_gap=1.12, align='left', width=None):
    asc, desc = fnt.getmetrics()
    lh = int((asc + desc) * line_gap)
    w = width or int(max(fnt.getlength(l) for l in lines)) + 4
    img = Image.new('RGBA', (w, lh * len(lines) + desc), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        x = 0 if align == 'left' else (w - fnt.getlength(line)) / 2
        draw.text((x, i * lh), line, font=fnt, fill=colour)
    return img


def rounded(size, radius, fill, outline=None, width=1, shadow=0, shadow_alpha=110):
    """Antialiased rounded rectangle (2× supersampled), with optional soft shadow."""
    w, h = size
    pad = shadow * 2
    big = Image.new('RGBA', ((w + pad * 2) * 2, (h + pad * 2) * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    box = (pad * 2, pad * 2, (pad + w) * 2 - 1, (pad + h) * 2 - 1)
    d.rounded_rectangle(box, radius * 2, fill=fill, outline=outline, width=width * 2)
    img = big.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
    if shadow:
        sh = Image.new('RGBA', img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad, pad + shadow // 2, pad + w, pad + h + shadow // 2), radius, fill=(0, 0, 0, shadow_alpha))
        sh = sh.filter(ImageFilter.GaussianBlur(shadow))
        sh.alpha_composite(img)
        img = sh
    return img, pad


def with_opacity(img, opacity):
    if opacity >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel('A').point(lambda a: int(a * opacity)))
    return out


def place(frame, layer, x, y, opacity=1.0):
    """Alpha-composite a layer at (x, y), clipping to the frame."""
    if opacity <= 0.001:
        return
    x, y = int(round(x)), int(round(y))
    left, top = max(0, -x), max(0, -y)
    right = min(layer.width, frame.width - x)
    bottom = min(layer.height, frame.height - y)
    if right <= left or bottom <= top:
        return
    part = layer.crop((left, top, right, bottom)) if (left or top or right < layer.width or bottom < layer.height) else layer
    frame.alpha_composite(with_opacity(part, opacity), (x + left, y + top))


class Renderer:
    def __init__(self, board: Storyboard):
        self.b = board
        self.s = board.style
        self.u = min(board.width, board.height) / 1080
        self.on_accent = pick_on_accent(self.s['accent'])
        self._background()
        self.layers = [self._prepare(scene) for scene in board.scenes]

    # background: vertical gradient + slow drifting accent glow
    def _background(self):
        w, h = self.b.width, self.b.height
        top, bottom = self.s['bg_top'], self.s['bg_bottom']
        grad = Image.new('RGB', (1, h))
        for y in range(h):
            p = y / max(1, h - 1)
            grad.putpixel((0, y), tuple(int(a + (b - a) * p) for a, b in zip(top, bottom)))
        self.base = grad.resize((w, h)).convert('RGBA')
        r = int(max(w, h) * 0.5)
        size = 256  # draw at quarter size and upscale: soft glow, no hard canvas edge, no banding blocks
        glow = Image.new('L', (size, size), 0)
        ImageDraw.Draw(glow).ellipse((size * 0.22, size * 0.22, size * 0.78, size * 0.78), fill=int(255 * self.s['glow']))
        glow = glow.filter(ImageFilter.GaussianBlur(size * 0.1)).resize((r * 2, r * 2), Image.BICUBIC)
        self.glow = Image.new('RGBA', glow.size, self.s['accent'] + (0,))
        self.glow.putalpha(glow)

        # fixed fine grain dithers 8-bit gradients so H.264 does not show banding blocks
        noise = Image.frombytes('L', (w, h), random.Random(1080).randbytes(w * h)).point(lambda v: 255 if v > 127 else 0)
        self.grain = noise.convert('RGBA')
        self.grain.putalpha(5)

    def background(self, t):
        frame = self.base.copy()
        w, h = self.b.width, self.b.height
        cx = w * (0.72 + 0.10 * math.sin(t * 0.35))
        cy = h * (0.25 + 0.08 * math.cos(t * 0.27))
        place(frame, self.glow, cx - self.glow.width / 2, cy - self.glow.height / 2)
        frame.alpha_composite(self.grain)
        return frame

    def _prepare(self, scene):
        """Pre-render static layers for a scene: list of (image, x, y, delay, kind)."""
        b, s, u, L, d = self.b, self.s, self.u, scene.layout, scene.data
        x0, y0, x1, y1 = frame_box(b)
        cw, chh = x1 - x0, y1 - y0
        items = []
        def stack(blocks, gap):
            total = sum(img.height for img, *_ in blocks) + gap * (len(blocks) - 1)
            y = y0 + (chh - total) / 2
            for img, x, delay in blocks:
                items.append({'img': img, 'x': x, 'y': y, 'delay': delay})
                y += img.height + gap
        if scene.type in ('title', 'statement'):
            blocks = []
            if 'eyebrow' in L:
                size, lines = L['eyebrow']; blocks.append((text_block(lines, font('medium', size), s['accent']), x0, 0.0))
            key = 'title' if scene.type == 'title' else 'text'
            size, lines = L[key]; blocks.append((text_block(lines, font('display', size), s['text'], 1.04), x0, 0.08))
            if 'subtitle' in L:
                size, lines = L['subtitle']; blocks.append((text_block(lines, font('body', size), s['muted'], 1.25), x0, 0.22))
            stack(blocks, int(30 * u))
        elif scene.type == 'features':
            blocks = []
            if 'title' in L:
                size, lines = L['title']; blocks.append((text_block(lines, font('display', size), s['text'], 1.04), x0, 0.0))
            pad = int(32 * u)
            cards = []
            for i, (size, lines) in enumerate(L['cards']):
                body = text_block(lines, font('medium', size), s['text'], 1.2)
                num = text_block([f'0{i + 1}'], font('mono', int(30 * u)), s['accent'])
                inner_h = num.height + int(18 * u) + body.height
                cards.append((num, body, inner_h))
            card_h = max(c[2] for c in cards) + pad * 2
            imgs = []
            for num, body, _ in cards:
                card, off = rounded((L['card_w'], card_h), int(22 * u), s['card'] + (255,), s['card_line'] + (255,), max(1, int(2 * u)), shadow=int(18 * u))
                card.alpha_composite(num, (off + pad, off + pad))
                card.alpha_composite(body, (off + pad, off + pad + num.height + int(18 * u)))
                imgs.append((card, off))
            title_h = blocks[0][0].height + int(44 * u) if blocks else 0
            if L['row']:
                total_h = title_h + card_h
            else:
                total_h = title_h + card_h * len(imgs) + L['gap'] * (len(imgs) - 1)
            y = y0 + (chh - total_h) / 2
            if blocks:
                items.append({'img': blocks[0][0], 'x': x0, 'y': y, 'delay': 0.0}); y += title_h
            for i, (card, off) in enumerate(imgs):
                if L['row']:
                    cx, cy = x0 + i * (L['card_w'] + L['gap']), y
                else:
                    cx, cy = x0, y + i * (card_h + L['gap'])
                items.append({'img': card, 'x': cx - off, 'y': cy - off, 'delay': 0.18 + 0.16 * i})
        elif scene.type == 'screenshot':
            caption = None
            if 'caption' in L:
                size, lines = L['caption']; caption = text_block(lines, font('medium', size), s['text'], 1.2)
            # screenshots may use most of the safe area
            grow = int(min(x0, y0) * 0.5)
            x0, y0, cw, chh = x0 - grow, y0 - grow, cw + grow * 2, chh + grow * 2
            avail_h = chh - (caption.height + int(36 * u) if caption else 0)
            bar = int(44 * u)
            with Image.open((b.base_dir / d['image']).resolve()) as im:
                shot = im.convert('RGB')
            ratio = shot.width / shot.height
            win_w = min(cw, int((avail_h - bar) * ratio))
            view_h = int(win_w / ratio)
            win_h = view_h + bar
            frame_img, off = rounded((win_w, win_h), int(18 * u), s['card'] + (255,), s['card_line'] + (255,), max(1, int(2 * u)), shadow=int(30 * u), shadow_alpha=150)
            dots = ImageDraw.Draw(frame_img)
            for k, colour in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
                cx = off + int(26 * u) + k * int(22 * u); cy = off + bar // 2
                rr = int(6.5 * u)
                dots.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=colour)
            total = win_h + (caption.height + int(36 * u) if caption else 0)
            top = y0 + (chh - total) / 2
            left = x0 + (cw - win_w) / 2
            if caption:
                items.append({'img': caption, 'x': x0 + (cw - caption.width) / 2, 'y': top, 'delay': 0.15})
                top += caption.height + int(36 * u)
            items.append({'img': frame_img, 'x': left - off, 'y': top - off, 'delay': 0.0,
                          'shot': shot.resize((int(win_w * 1.08), int(view_h * 1.08)), Image.LANCZOS),
                          'view': (off + 1, off + bar, win_w - 2, view_h - 1), 'focus': d.get('focus', [0.5, 0.35])})
        elif scene.type == 'cta':
            blocks = []
            size, lines = L['title']; title = text_block(lines, font('display', size), s['text'], 1.04, 'center', cw)
            blocks.append((title, x0, 0.0))
            if 'url' in L:
                size, lines = L['url']; f = font('medium', size)
                tw = int(f.getlength(lines[0])); ph, pv = int(40 * u), int(22 * u)
                asc, desc = f.getmetrics()
                pill, off = rounded((tw + ph * 2, asc + desc + pv * 2), (asc + desc + pv * 2) // 2, s['accent'] + (255,), shadow=int(20 * u), shadow_alpha=90)
                ImageDraw.Draw(pill).text((off + ph, off + pv), lines[0], font=f, fill=self.on_accent)
                blocks.append((pill, x0 + (cw - pill.width) / 2, 0.2))
            if 'note' in L:
                size, lines = L['note']; blocks.append((text_block(lines, font('body', size), s['muted'], 1.25, 'center', cw), x0, 0.32))
            stack(blocks, int(40 * u))
        return items

    def frame(self, t):
        frame = self.background(t)
        b = self.b
        for scene, items in zip(b.scenes, self.layers):
            local = t - scene.start
            if local < 0 or local >= scene.duration:
                continue
            last = scene is b.scenes[-1]
            out = 1.0 if last else clamp((scene.duration - local) / EXIT)
            for it in items:
                p = ease_out((local - it['delay']) / ENTER)
                opacity = p * out
                dy = (1 - p) * 46 * self.u
                if 'shot' in it:
                    self._shot(frame, it, local, scene.duration, opacity, dy)
                else:
                    place(frame, it['img'], it['x'], it['y'] + dy, opacity)
        return frame.convert('RGB')

    def _shot(self, frame, it, local, duration, opacity, dy):
        win = it['img'].copy()
        vx, vy, vw, vh = it['view']
        shot = it['shot']
        p = ease_in_out(local / duration)
        zoom = 1.0 + 0.06 * p
        sw, sh = int(vw * zoom), int(vh * zoom)
        scaled = shot.resize((sw, sh), Image.BILINEAR)
        fx, fy = it['focus']
        cx = clamp(fx * sw - vw / 2, 0, sw - vw)
        cy = clamp(fy * sh - vh / 2, 0, sh - vh)
        crop = scaled.crop((int(cx), int(cy), int(cx) + vw, int(cy) + vh))
        win.paste(crop, (vx, vy))
        place(frame, win, it['x'], it['y'] + dy, opacity)

def scene_midpoints(board):
    """Time inside each scene where all its elements are fully visible."""
    points = []
    for scene in board.scenes:
        settle = min(scene.duration - EXIT - 0.05, ENTER + 0.9 + (0.6 if scene.type in ('terminal', 'agent') else 0))
        points.append(round(scene.start + max(0.0, settle), 3))
    return points
