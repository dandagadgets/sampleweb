#!/usr/bin/env python3
"""MC.GOLD promo shorts renderer.

Renders vertical (1080x1920, 30 fps) promo shorts for the MC.GOLD Minecraft
server from the brand assets in ./assets. Backgrounds, pixel-art sprites,
motion, chiptune music and sound effects are all generated in code, so the
videos are royalty-free and can be re-rendered after editing the copy below.

Usage:
    python3 render.py                 # render every short into ./out
    python3 render.py paid            # render one short (paid | leaderboard | pvp)

Needs python3 with numpy + pillow, ffmpeg and curl (fonts download on first run).
"""
import math
import os
import subprocess
import sys
import wave
from functools import lru_cache
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(HERE, "assets")
FONT_DIR = os.path.join(HERE, ".fonts")
OUT_DIR = os.path.join(HERE, "out")

W, H, FPS = 1080, 1920, 30
SR = 44100
BEAT = 0.5  # 120 BPM: every cut and hit lands on the beat grid
CX = W // 2

FONTS = {
    "silk": ("Silkscreen-Bold.ttf",
             "https://fonts.gstatic.com/s/silkscreen/v6/m8JUjfVPf62XiF7kO-i9aAhATms.ttf"),
    "press": ("PressStart2P.ttf",
              "https://fonts.gstatic.com/s/pressstart2p/v16/e3t4euO8T-267oIAQAu6jDQyK0nS.ttf"),
}

# Brand palette, sampled from the MC.GOLD wordmark.
INK = (21, 9, 0)
G_WHITE = (254, 252, 250)
G_PALE = (253, 237, 99)
G_YELLOW = (250, 220, 30)
G_GOLD = (247, 191, 14)
G_DEEP = (170, 85, 0)


# ----------------------------------------------------------------------------
# small helpers

def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, p):
    return a + (b - a) * p


def ease_out_cubic(p):
    return 1 - (1 - clamp(p)) ** 3


def ease_in_cubic(p):
    return clamp(p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return p * p * (3 - 2 * p)


def ease_out_back(p, s=1.9):
    p = clamp(p) - 1
    return 1 + p * p * ((s + 1) * p + s)


def ease_in_back(p, s=1.7):
    p = clamp(p)
    return p * p * ((s + 1) * p - s)


def ease_out_bounce(p):
    p, n, d = clamp(p), 7.5625, 2.75
    if p < 1 / d:
        return n * p * p
    if p < 2 / d:
        p -= 1.5 / d
        return n * p * p + 0.75
    if p < 2.5 / d:
        p -= 2.25 / d
        return n * p * p + 0.9375
    p -= 2.625 / d
    return n * p * p + 0.984375


def beat_pulse(t):
    """1.0 right on each beat, decaying quickly - for music-synced bumps."""
    return math.exp(-(t % BEAT) / 0.12)


def font_path(key):
    name, url = FONTS[key]
    path = os.path.join(FONT_DIR, name)
    if not os.path.exists(path):
        os.makedirs(FONT_DIR, exist_ok=True)
        subprocess.run(["curl", "-fsSL", "-o", path, url], check=True)
    return path


@lru_cache(None)
def font(key):
    # Both fonts are drawn on an 8px grid, so size 8 gives one image pixel per font pixel.
    return ImageFont.truetype(font_path(key), 8)


def shift(m, dy, dx):
    h, w = m.shape[:2]
    out = np.zeros_like(m)
    ys0, ys1 = max(0, -dy), min(h, h - dy)
    xs0, xs1 = max(0, -dx), min(w, w - dx)
    out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] = m[ys0:ys1, xs0:xs1]
    return out


def dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if (dy or dx) and dx * dx + dy * dy <= r * r + 1:
                out |= shift(m, dy, dx)
    return out


def upscale(a, k):
    return Image.fromarray(np.repeat(np.repeat(a, k, 0), k, 1))


def set_alpha(img, alpha):
    img = img.copy()
    img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    return img


def place(canvas, img, cx, cy, scale=1.0, alpha=1.0, rot=0.0, smooth=False):
    """Composite img centred on (cx, cy), clipped to the canvas."""
    if scale <= 0.02 or alpha <= 0.02:
        return
    if abs(scale - 1) > 1e-3:
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                         Image.BILINEAR if smooth else Image.NEAREST)
    if abs(rot) > 0.05:
        img = img.rotate(rot, resample=Image.BICUBIC if smooth else Image.NEAREST, expand=True)
    if alpha < 0.999:
        img = set_alpha(img, alpha)
    x, y = round(cx - img.width / 2), round(cy - img.height / 2)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + img.width), min(H, y + img.height)
    if x1 <= x0 or y1 <= y0:
        return
    if (x0, y0, x1, y1) != (x, y, x + img.width, y + img.height):
        img = img.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    canvas.alpha_composite(img, (x0, y0))


# ----------------------------------------------------------------------------
# pixel text in the MC.GOLD logo style: banded gold fill, extrude, dark outline

TEXT_STYLES = {
    "gold": ([(0.25, G_WHITE), (0.48, G_PALE), (0.70, G_YELLOW), (9, G_GOLD)], G_DEEP),
    "white": ([(0.5, (255, 255, 255)), (9, (222, 218, 238))], (112, 100, 150)),
    "red": ([(0.3, (255, 222, 214)), (0.6, (255, 110, 96)), (9, (232, 56, 48))], (120, 18, 18)),
    "green": ([(0.3, (226, 255, 214)), (0.6, (130, 238, 100)), (9, (70, 204, 70))], (20, 96, 30)),
}
SUB = 6  # sub-pixels per font pixel; outline/extrude widths are measured in these


@lru_cache(None)
def pixel_text(text, cell, style="gold", face="silk", outline=2, extrude=3, shadow=3):
    f = font(face)
    l, t, r, b = f.getbbox(text)
    _, ht, _, hb = f.getbbox("H")
    pad = 3
    im = Image.new("L", (r - l + 2 * pad, b - t + 2 * pad), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((pad - l, pad - t), text, font=f, fill=255)
    m = np.kron(np.array(im) > 127, np.ones((SUB, SUB), bool))
    hh, ww = m.shape
    top, bot = (pad - t + ht) * SUB, (pad - t + hb) * SUB
    bands, deep = TEXT_STYLES[style]
    frac = (np.arange(hh) + 0.5 - top) / max(1, bot - top)
    row_col = np.array([next(c for lim, c in bands if fr < lim) for fr in frac], np.uint8)
    ext = np.zeros_like(m)
    for i in range(1, extrude + 1):
        ext |= shift(m, i, 0)
    ext &= ~m
    ring = dilate(m | ext, outline)
    out = np.zeros((hh, ww, 4), np.uint8)
    if shadow:
        out[shift(ring, shadow, 0) & ~ring] = (0, 0, 0, 110)
    out[ring] = (*INK, 255)
    out[ext] = (*deep, 255)
    out[m, :3] = np.broadcast_to(row_col[:, None, :], (hh, ww, 3))[m]
    out[m, 3] = 255
    img = Image.fromarray(out)
    img = img.crop(img.getbbox())
    s = cell / SUB
    return img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.NEAREST)


def text_fit(text, cell, max_w=940, **kw):
    """pixel_text at `cell`, shrunk if needed so it fits within max_w."""
    w1 = pixel_text(text, SUB, **kw).width
    cell = min(cell, max_w * SUB / w1)
    return pixel_text(text, math.floor(cell * 4) / 4, **kw)


_glow_cache = {}


def glow_for(img, color=(255, 186, 40), radius=34, strength=1.4):
    key = (id(img), color)
    if key not in _glow_cache:
        pad = radius * 2
        a = Image.new("L", (img.width + 2 * pad, img.height + 2 * pad), 0)
        a.paste(img.getchannel("A"), (pad, pad))
        small = a.resize((max(1, a.width // 4), max(1, a.height // 4)), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(radius / 4))
        blur = np.array(small.resize(a.size, Image.BILINEAR), np.float32) * strength
        out = np.zeros((*blur.shape, 4), np.uint8)
        out[..., :3] = color
        out[..., 3] = np.clip(blur, 0, 255)
        _glow_cache[key] = (img, Image.fromarray(out))  # keep img alive so id() stays unique
    return _glow_cache[key][1]


def shine(img, p, width=0.09):
    """Diagonal light sweep across the bright parts of img; p runs 0..1."""
    a = np.array(img, np.float32)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u = (xx + yy * 0.7) / (w + h * 0.7)
    band = np.clip(1 - np.abs(u - (p * 1.4 - 0.2)) / width, 0, 1)
    band *= (a[..., :3].mean(-1) > 90) * 0.9
    a[..., :3] += (255 - a[..., :3]) * band[..., None]
    return Image.fromarray(a.astype(np.uint8))


# ----------------------------------------------------------------------------
# pixel-art sprites (all drawn here, nothing borrowed from the game)

def from_rows(rows, pal):
    a = np.zeros((len(rows), max(map(len, rows)), 4), np.uint8)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                a[y, x] = (*pal[ch], 255)
    return a


def outlined(a, r=1):
    a = np.pad(a, ((r, r), (r, r), (0, 0)))
    m = a[..., 3] > 0
    a[dilate(m, r) & ~m] = (*INK, 255)
    return a


def coin_art():
    s, c = 16, 7.5
    a = np.zeros((s, s, 4), np.uint8)
    for y in range(s):
        for x in range(s):
            dx, dy = x - c, y - c
            r = math.hypot(dx, dy)
            if r > 7.9:
                continue
            k = (dx + dy) / 11
            if r > 6.9:
                col = INK
            elif r > 5.6:
                col = G_PALE if k < -0.25 else G_GOLD if k < 0.35 else G_DEEP
            else:
                col = G_WHITE if k < -0.75 else G_PALE if k < -0.2 else G_YELLOW if k < 0.4 else G_GOLD
            a[y, x] = (*col, 255)
    im = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    f = font("silk")
    l, t, r, b = f.getbbox("$")
    d.text((round(8 - (r - l) / 2 - l), round(8 - (b - t) / 2 - t)), "$", font=f, fill=255)
    a[np.array(im) > 127] = (*G_DEEP, 255)
    return a


def sword_art():
    a = np.zeros((16, 16, 4), np.uint8)

    def put(r, c, col):
        if 0 <= r < 16 and 0 <= c < 16:
            a[r, c] = (*col, 255)

    for i in range(10):  # blade, tip at top right
        put(i, 14 - i, G_YELLOW)
        put(i + 1, 15 - i, G_GOLD)
        put(i, 15 - i, G_WHITE if i < 3 else G_PALE)
    for i in range(-2, 3):  # cross guard
        put(10 + i, 5 + i, G_DEEP)
        put(11 + i, 5 + i, G_GOLD)
    for i in range(3):  # grip
        put(12 + i, 3 - i, (120, 66, 30))
        put(11 + i, 3 - i, (150, 88, 44))
    put(15, 0, G_GOLD)
    put(14, 0, G_PALE)
    return outlined(a)


def head_art(helmet, light, skin):
    rows = [
        "hhhhhhhh",
        "hHHHHHHh",
        "hhhhhhhh",
        "ssssssss",
        "swessews",
        "ssssssss",
        "sssmmsss",
        "ssssssss",
    ]
    dark = tuple(int(v * 0.8) for v in skin)
    return outlined(from_rows(rows, {"h": helmet, "H": light, "s": skin, "w": (255, 255, 255),
                                     "e": (34, 30, 60), "m": dark}))


CURSOR_ROWS = [
    "o...........",
    "oo..........",
    "owo.........",
    "owwo........",
    "owwwo.......",
    "owwwwo......",
    "owwwwwo.....",
    "owwwwwwo....",
    "owwwwwwwo...",
    "owwwwwwwwo..",
    "owwwwwoooo..",
    "owwowwo.....",
    "owo.owwo....",
    "oo..owwo....",
    "o....owwo...",
    ".....owwo...",
    "......oo....",
]
SPARK_ROWS = ["...p...", "...p...", "..pWp..", "ppWWWpp", "..pWp..", "...p...", "...p..."]
ARROW_ROWS = ["...g...", "..ggg..", ".ggggg.", "ggggggg", "..ggg..", "..ggg..", "..ggg.."]


@lru_cache(None)
def sprites():
    return {
        "coin": coin_art(),
        "sword": sword_art(),
        "cursor": from_rows(CURSOR_ROWS, {"o": INK, "w": (255, 255, 255)}),
        "spark": from_rows(SPARK_ROWS, {"p": G_PALE, "W": (255, 255, 255)}),
        "arrow": outlined(from_rows(ARROW_ROWS, {"g": (90, 226, 90)})),
        "head_gold": head_art(G_GOLD, G_PALE, (236, 188, 146)),
        "head_white": head_art((214, 214, 228), (255, 255, 255), (170, 118, 84)),
        "head_purple": head_art((150, 80, 230), (205, 160, 255), (250, 212, 180)),
        "head_red": head_art((218, 52, 52), (255, 134, 122), (124, 84, 62)),
    }


@lru_cache(None)
def sprite(name, k):
    return upscale(sprites()[name], k)


@lru_cache(None)
def coin_img(k, squash_q):
    img = sprite("coin", k)
    q = max(0.18, squash_q / 10)
    return img.resize((max(4, round(img.width * q)), img.height), Image.NEAREST)


# ----------------------------------------------------------------------------
# block textures + the scrolling night-time world behind everything

def block_tex(kind, seed):
    r = np.random.default_rng(seed)

    def pick(pal, p):
        return np.array(pal, np.uint8)[r.choice(len(pal), (16, 16), p=p)]

    dirt = ([(121, 85, 58), (134, 96, 67), (105, 72, 48), (150, 108, 75)], [.4, .3, .2, .1])
    stone = ([(125, 125, 128), (110, 110, 114), (142, 142, 146), (96, 96, 100)], [.4, .25, .2, .15])
    if kind == "dirt":
        return pick(*dirt)
    if kind == "stone":
        return pick(*stone)
    if kind == "grass":
        a = pick(*dirt)
        greens = np.array([(92, 160, 60), (106, 178, 70), (80, 140, 52)], np.uint8)
        for x in range(16):
            depth = 3 + r.integers(0, 3)
            a[:depth, x] = greens[r.integers(0, 3, depth)]
        return a
    if kind == "gold_ore":
        a = pick(*stone)
        for _ in range(4):
            y, x = r.integers(1, 14, 2)
            a[y:y + 2, x:x + 2] = G_YELLOW
            a[y, x] = G_PALE
            a[min(15, y + 2), x:x + 2] = G_DEEP
        return a
    if kind == "gold_block":
        a = pick([G_YELLOW, G_GOLD, (240, 178, 10)], [.3, .5, .2])
        a[0, :], a[:, 0] = G_PALE, G_PALE
        a[-1, :], a[:, -1] = G_DEEP, G_DEEP
        a[1, 1:-1] = G_WHITE
        return a
    if kind == "obsidian":
        return pick([(40, 18, 70), (52, 24, 90), (30, 12, 52), (66, 34, 110)], [.35, .3, .25, .1])
    raise ValueError(kind)


LR_W, LR_H, PX = W // 8, H // 8, 8  # the world is drawn at 135x240 and blown up 8x
RAY_CX, RAY_CY = 67.5, 105.0
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0


class World:
    def __init__(self, duration, seed=11, speed=9.0):
        r = np.random.default_rng(seed)
        self.speed = speed
        yy, xx = np.mgrid[0:LR_H, 0:LR_W].astype(np.float32)
        # banded, dithered night sky
        stops = [(0, (10, 5, 24)), (80, (26, 11, 52)), (150, (54, 20, 90)),
                 (200, (92, 34, 112)), (240, (116, 44, 120))]

        def sky_at(y):
            for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
                if y <= y1:
                    p = (y - y0) / (y1 - y0)
                    return np.array([lerp(a, b, p) for a, b in zip(c0, c1)])
            return np.array(stops[-1][1], float)

        band = 12
        v = yy / band + (BAYER[yy.astype(int) % 4, xx.astype(int) % 4] - 0.5) * 0.9
        idx = np.clip(np.floor(v), 0, LR_H // band)
        self.sky = np.stack([sky_at(i * band + band / 2) for i in range(LR_H // band + 1)])[idx.astype(int)]
        self.sky = self.sky.astype(np.float32)
        dx, dy = xx - RAY_CX, yy - RAY_CY
        rad = np.hypot(dx, dy * 0.85)
        self.ang = np.arctan2(dy, dx)
        self.glow = np.floor(np.exp(-(rad / 46) ** 2) * 6) / 6
        self.ray_fall = np.floor(np.clip(1 - rad / 150, 0, 1) * 5) / 5
        self.vignette = 1 - 0.55 * np.clip((np.hypot(dx / LR_W, dy / LR_H) - 0.42) / 0.5, 0, 1)
        # stars and rising gold motes
        n = 80
        self.stars = (r.integers(0, LR_W, n), r.integers(0, 165, n), r.uniform(1, 4, n),
                      r.uniform(0, 6.3, n), r.random(n) < 0.3)
        m = 26
        self.motes = (r.uniform(0, LR_W, m), r.uniform(0, LR_H, m), r.uniform(3, 9, m), r.uniform(0, 6.3, m))
        # blocky clouds
        self.clouds = []
        for i in range(4):
            cw, ch = r.integers(24, 44), r.integers(5, 9)
            cm = np.zeros((ch + 4, cw), bool)
            for _ in range(5):
                x0, w0 = r.integers(0, cw - 8), r.integers(8, 20)
                y0 = r.integers(0, 4)
                cm[y0:y0 + ch, x0:x0 + w0] = True
            self.clouds.append((np.repeat(np.repeat(cm, PX, 0), PX, 1), r.uniform(-20, LR_W),
                                r.integers(12, 95), r.uniform(1.5, 4)))
        # far + near hills and the block terrain as wide pre-upscaled strips
        span = LR_W + int(speed * duration) + 64
        self.hills = [self._hills(span, r, 150, (44, 20, 78), (60, 30, 100)),
                      self._hills(span, r, 172, (30, 12, 54), (44, 20, 76))]
        self.terrain = self._terrain(span, r)

    @staticmethod
    def _hills(span, r, base, col, top_col):
        h = LR_H - base + 20
        a = np.zeros((h, span, 3), np.uint8)
        m = np.zeros((h, span), bool)
        y = 10
        for x0 in range(0, span, 8):
            y = int(np.clip(y + r.integers(-1, 2) * 4, 0, 26))
            m[y:, x0:x0 + 8] = True
            a[y:, x0:x0 + 8] = col
            a[y, x0:x0 + 8] = top_col
        return (np.repeat(np.repeat(a, PX, 0), PX, 1), np.repeat(np.repeat(m, PX, 0), PX, 1),
                (base - 20) * PX)

    @staticmethod
    def _terrain(span, r):
        top_lr = 184
        h = LR_H - top_lr
        a = np.zeros((h, span, 3), np.uint8)
        m = np.zeros((h, span), bool)
        night = {"grass": (0.62, 0.6, 0.8), "dirt": (0.6, 0.56, 0.76), "stone": (0.62, 0.6, 0.8),
                 "gold_ore": (0.85, 0.8, 0.9), "gold_block": (1.0, 0.95, 0.95)}
        raised = False
        for j in range(span // 16 + 1):
            raised = (r.random() < 0.35) if not raised else (r.random() < 0.6)
            top = 0 if raised else 16
            for by in range(top, h, 16):
                depth = (by - top) // 16
                if depth == 0:
                    kind = "gold_block" if r.random() < 0.07 else "grass"
                elif depth == 1:
                    kind = "dirt"
                else:
                    kind = "gold_ore" if r.random() < 0.3 else "stone"
                tex = block_tex(kind, int(r.integers(1 << 30))) * np.array(night[kind])
                x0 = j * 16
                hh = min(16, h - by)
                ww = min(16, span - x0)
                if ww <= 0:
                    continue
                a[by:by + hh, x0:x0 + ww] = tex[:hh, :ww]
                m[by:by + hh, x0:x0 + ww] = True
        return (np.repeat(np.repeat(a, PX, 0), PX, 1), np.repeat(np.repeat(m, PX, 0), PX, 1),
                top_lr * PX)

    def render(self, t, rays=0.3, glow=0.5, terrain=1.0, dim=0.0):
        lr = self.sky.copy()
        if glow > 0:
            lr += self.glow[..., None] * np.array([150, 92, 18], np.float32) * glow
        if rays > 0:
            on = (np.cos(self.ang * 12 + t * 0.5) > 0.42) * self.ray_fall
            lr += on[..., None] * np.array([120, 80, 22], np.float32) * rays
        sx, sy, sf, sp, big = self.stars
        b = np.clip(0.45 + 0.65 * np.sin(t * sf + sp), 0, 1)
        lr[sy, sx] += (b * 210)[:, None]
        for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            lr[np.clip(sy[big] + oy, 0, LR_H - 1), np.clip(sx[big] + ox, 0, LR_W - 1)] += (b[big] * 90)[:, None]
        mx, my, msp, mph = self.motes
        x = np.clip((mx + 2 * np.sin(t * 0.9 + mph)).astype(int), 0, LR_W - 1)
        y = ((my - t * msp) % LR_H).astype(int)
        lr[y, x] += np.array([180, 130, 20]) * np.clip(0.5 + 0.5 * np.sin(t * 5 + mph), 0, 1)[:, None]
        lr *= self.vignette[..., None] * (1 - dim)
        frame = np.repeat(np.repeat(np.clip(lr, 0, 255).astype(np.uint8), PX, 0), PX, 1)

        for cm, x0, y0, v in self.clouds:
            ch, cw = cm.shape
            x = int(((x0 + t * v) * PX) % (W + cw + 200)) - cw
            y = y0 * PX
            xa, xb = max(0, x), min(W, x + cw)
            if xb > xa:
                reg = frame[y:y + ch, xa:xb]
                mm = cm[:, xa - x:xb - x]
                reg[mm] = (reg[mm] * 0.55 + np.array([62, 34, 104]) * 0.45).astype(np.uint8)

        lift = int((1 - terrain) * 700)
        for (a, m, y0), k in zip(self.hills, (0.25, 0.5)):
            self._blit(frame, a, m, y0 + lift, int(t * self.speed * k * PX))
        a, m, y0 = self.terrain
        self._blit(frame, a, m, y0 + lift, int(t * self.speed * PX))
        return frame

    @staticmethod
    def _blit(frame, a, m, y0, off):
        if y0 >= H:
            return
        h = min(a.shape[0], H - y0)
        reg = frame[y0:y0 + h]
        mm = m[:h, off:off + W]
        reg[mm] = a[:h, off:off + W][mm]


# ----------------------------------------------------------------------------
# brand assets

@lru_cache(None)
def assets():
    def trim(img):
        return img.crop(img.getchannel("A").getbbox())

    def key_out(img, bg, lo=16, hi=50):
        a = np.array(img.convert("RGBA")).astype(np.float32)
        d = np.sqrt(((a[..., :3] - np.array(bg, np.float32)) ** 2).sum(-1))
        a[..., 3] = np.clip((d - lo) / (hi - lo), 0, 1) * 255
        return trim(Image.fromarray(a.astype(np.uint8)))

    def crisp(img, k=4):  # nearest-neighbour blow-up so later smooth scaling keeps hard pixel edges
        return img.resize((img.width * k, img.height * k), Image.NEAREST)

    server = Image.open(os.path.join(ASSET_DIR, "server-list.png")).convert("RGBA")
    # Hide the live player count so the promo never shows a stale "0/3500".
    ImageDraw.Draw(server).rectangle((492, 2, 570, 24), fill=(0, 0, 0, 255))
    server = server.crop((2, 2, server.width - 2, server.height - 1))
    return {
        "trophy": trim(Image.open(os.path.join(ASSET_DIR, "logo-trophy.webp")).convert("RGBA")),
        "wordmark": trim(Image.open(os.path.join(ASSET_DIR, "logo-wordmark.webp")).convert("RGBA")),
        "weekend": key_out(Image.open(os.path.join(ASSET_DIR, "weekend-events.png")), (57, 58, 65)),
        "server": crisp(server),
        "board": crisp(Image.open(os.path.join(ASSET_DIR, "leaderboard.png")).convert("RGBA")),
    }


@lru_cache(None)
def panel(w, h, cell=6, fill=(22, 12, 38, 235)):
    """Pixel UI box with a bevelled gold frame; fill=None leaves the middle see-through."""
    gw, gh = max(10, round(w / cell)), max(10, round(h / cell))
    a = np.zeros((gh, gw, 4), np.uint8)
    a[:, :] = (*INK, 255)
    a[1:-1, 1:-1] = (*G_GOLD, 255)
    a[1, 1:-1] = a[1:-1, 1] = (*G_PALE, 255)
    a[-2, 2:-1] = a[2:-1, -2] = (*G_DEEP, 255)
    a[3:-3, 3:-3] = (*INK, 255)
    a[4:-4, 4:-4] = fill if fill else (0, 0, 0, 0)
    for y, x in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
        a[y, x] = 0
    return upscale(a, cell)


@lru_cache(None)
def tag(text, style="gold", cell=4):
    t = pixel_text(text, cell, style, "press", outline=1, extrude=1, shadow=0)
    p = panel(t.width + 64, t.height + 52, 4).copy()
    p.alpha_composite(t, ((p.width - t.width) // 2, (p.height - t.height) // 2))
    return p


# ----------------------------------------------------------------------------
# timeline elements

class Ctx:
    def __init__(self, canvas, dx, dy):
        self.canvas, self.dx, self.dy = canvas, dx, dy


class El:
    z = 0

    def __init__(self, start, end):
        self.start, self.end = start, end


class Sprite(El):
    def __init__(self, img, x, y, start, end, anim="pop", dur_in=None, out="shrink", dur_out=0.18,
                 glow=False, bob=0, pulse=0.0, shine_at=None, smooth=False, rot=0.0, shake=True):
        super().__init__(start, end)
        self.img, self.x, self.y = img, x, y
        self.anim, self.out, self.dur_out = anim, out, dur_out
        self.dur_in = dur_in or {"slam": 0.14, "drop": 0.75, "swing": 0.4, "pop": 0.28}.get(anim, 0.32)
        self.glow = glow_for(img) if glow else None
        self.bob, self.pulse, self.shine_at = bob, pulse, shine_at
        self.smooth, self.rot, self.shake = smooth, rot, shake

    def land_time(self):
        return self.start + (self.dur_in * (1 / 2.75 if self.anim == "drop" else 1))

    def draw(self, ctx, t):
        lt = t - self.start
        p = lt / self.dur_in
        sc, al, dx, dy, rot = 1.0, 1.0, 0.0, 0.0, self.rot
        a = self.anim
        if a == "pop":
            sc, al = ease_out_back(p, 2.4), clamp(p * 4)
        elif a == "slam":
            sc, al = lerp(2.3, 1, ease_out_cubic(p)), clamp(p * 3)
        elif a == "drop":
            dy = lerp(-(self.y + self.img.height), 0, ease_out_bounce(p))
        elif a == "rise":
            dy, al = lerp(150, 0, ease_out_cubic(p)), clamp(p * 2)
        elif a == "left":
            dx = lerp(-W, 0, ease_out_back(p, 1.2))
        elif a == "right":
            dx = lerp(W, 0, ease_out_back(p, 1.2))
        elif a == "swing":
            rot += lerp(-80, 0, ease_out_back(p, 2.2))
            sc = ease_out_back(p, 1.5)
        elif a == "fade":
            al = clamp(p)
        ot = self.end - t
        if self.out and ot < self.dur_out:
            q = 1 - ot / self.dur_out
            if self.out == "shrink":
                sc *= max(0.0, 1 - ease_in_back(q))
            elif self.out == "fade":
                al *= 1 - q
            elif self.out == "up":
                dy -= ease_in_cubic(q) * H * 0.7
        if self.bob and p >= 1:
            dy += math.sin(2 * math.pi * lt / 1.6) * self.bob
        if self.pulse and p >= 1:
            sc *= 1 + self.pulse * beat_pulse(t)
        img = self.img
        if self.shine_at is not None and 0 <= t - self.shine_at < 0.5:
            img = shine(img, (t - self.shine_at) / 0.5)
        x = self.x + dx + (ctx.dx if self.shake else 0)
        y = self.y + dy + (ctx.dy if self.shake else 0)
        if self.glow is not None and p > 0.3:
            place(ctx.canvas, self.glow, x, y, sc, al * (0.75 + 0.25 * beat_pulse(t)), smooth=True)
        place(ctx.canvas, img, x, y, sc, al, rot, smooth=self.smooth)


class Counter(El):
    """Big number that ticks through values, popping on every change."""

    def __init__(self, steps, y, end, cell, style="gold", glow=True):
        super().__init__(steps[0][0], end)
        self.y = y
        self.steps = [(t, text_fit(s, cell, style=style)) for t, s in steps]
        self.glows = [glow_for(img) for _, img in self.steps] if glow else None

    def draw(self, ctx, t):
        i = max(k for k, (ts, _) in enumerate(self.steps) if ts <= t)
        ts, img = self.steps[i]
        sc = lerp(1.35, 1, ease_out_cubic((t - ts) / 0.12))
        ot = self.end - t
        if ot < 0.18:
            sc *= max(0.0, 1 - ease_in_back(1 - ot / 0.18))
        x, y = CX + ctx.dx, self.y + ctx.dy
        if self.glows:
            place(ctx.canvas, self.glows[i], x, y, sc, 0.8, smooth=True)
        place(ctx.canvas, img, x, y, sc)


class CoinRain(El):
    z = -1

    def __init__(self, start, end, n=34, seed=3):
        super().__init__(start, end)
        r = np.random.default_rng(seed)
        self.coins = [(r.uniform(-30, W + 30), r.uniform(start, end - 1.4), r.uniform(150, 420),
                       int(r.integers(4, 9)), r.uniform(1.2, 2.6), r.uniform(0, 6.3)) for _ in range(n)]

    def draw(self, ctx, t):
        for x, ts, v0, k, f, ph in self.coins:
            dt = t - ts
            if dt < 0:
                continue
            y = -90 + v0 * dt + 0.5 * 1300 * dt * dt
            if y > H + 90:
                continue
            q = int(round(abs(math.cos(2 * math.pi * f * dt + ph)) * 10))
            place(ctx.canvas, coin_img(k, q), x + ctx.dx * 0.3, y, alpha=0.95)


class Burst(El):
    """Coins and sparkles exploding out of a point (behind the text so nothing gets covered)."""
    z = -1

    def __init__(self, t0, x, y, coins=10, sparks=14, seed=7, power=1.0):
        super().__init__(t0, t0 + 1.8)
        r = np.random.default_rng(seed)
        self.x, self.y = x, y
        self.coins = []
        for _ in range(coins):
            a = r.uniform(-math.pi * 0.95, -math.pi * 0.05)
            s = r.uniform(700, 1400) * power
            self.coins.append((math.cos(a) * s, math.sin(a) * s, int(r.integers(5, 9)), r.uniform(1.5, 3)))
        self.sparks = []
        for _ in range(sparks):
            a = r.uniform(0, 2 * math.pi)
            s = r.uniform(250, 650) * power
            self.sparks.append((math.cos(a) * s, math.sin(a) * s, int(r.integers(5, 10))))

    def draw(self, ctx, t):
        dt = t - self.start
        for vx, vy, k in self.sparks:
            if dt > 0.7:
                break
            d = (1 - math.exp(-dt * 4)) / 4
            place(ctx.canvas, sprite("spark", k), self.x + vx * d, self.y + vy * d,
                  scale=1 - dt / 0.8, alpha=1 - dt / 0.7)
        for vx, vy, k, f in self.coins:
            x = self.x + vx * dt
            y = self.y + vy * dt + 0.5 * 2600 * dt * dt
            if y > H + 80:
                continue
            q = int(round(abs(math.cos(2 * math.pi * f * dt)) * 10))
            place(ctx.canvas, coin_img(k, q), x, y)


class Flash(El):
    z = 8

    def __init__(self, t0, dur=0.22, strength=0.75):
        super().__init__(t0, t0 + dur)
        self.dur, self.strength = dur, strength

    def draw(self, ctx, t):
        a = int(255 * self.strength * (1 - (t - self.start) / self.dur))
        ctx.canvas.alpha_composite(Image.new("RGBA", (W, H), (255, 246, 214, a)))


class TileWipe(El):
    """Gold blocks pop in across the screen, the scene swaps underneath, then they pop out."""
    z = 9
    TILE = 128

    def __init__(self, tmid, dur=0.56, seed=5):
        super().__init__(tmid - dur / 2, tmid + dur / 2)
        self.dur = dur
        r = np.random.default_rng(seed)
        cols, rows = math.ceil(W / self.TILE), math.ceil(H / self.TILE)
        self.tiles = []
        for row in range(rows):
            for col in range(cols):
                d = (col + row * 0.55) / (cols - 1 + (rows - 1) * 0.55) * 0.2 + r.uniform(0, 0.05)
                kind = "gold_ore" if r.random() < 0.18 else "gold_block"
                self.tiles.append((col, row, d, kind, int(r.integers(1 << 30))))
        self._tex = {}

    def tex(self, kind, seed, size):
        key = (kind, seed % 6, size)
        if key not in self._tex:
            base = upscale(np.dstack([block_tex(kind, seed % 6), np.full((16, 16), 255, np.uint8)]), 8)
            self._tex[key] = base.resize((size, size), Image.NEAREST)
        return self._tex[key]

    def draw(self, ctx, t):
        u = (t - self.start) / self.dur
        for col, row, d, kind, seed in self.tiles:
            s = ease_out_cubic((u - d) / 0.25) * (1 - ease_in_cubic((u - 0.5 - d) / 0.25))
            size = int(self.TILE * s) // 8 * 8
            if size <= 0:
                continue
            cx, cy = col * self.TILE + self.TILE // 2, row * self.TILE + self.TILE // 2
            ctx.canvas.paste(self.tex(kind, seed, size), (cx - size // 2, cy - size // 2))


class Badge(El):
    """Small "IP: MC.GOLD" chip kept on screen so the IP is always visible."""
    z = 5

    def __init__(self, start, end, y=262):
        super().__init__(start, end)
        self.y = y
        ip = pixel_text("IP: MC.GOLD", 4, "gold", "press", outline=1, extrude=1, shadow=0)
        self.img = panel(ip.width + 70, ip.height + 56, 4).copy()
        self.img.alpha_composite(ip, ((self.img.width - ip.width) // 2, (self.img.height - ip.height) // 2))

    def draw(self, ctx, t):
        p = (t - self.start) / 0.3
        sc = ease_out_back(p) * (1 - ease_in_back(1 - (self.end - t) / 0.2) if self.end - t < 0.2 else 1)
        place(ctx.canvas, self.img, CX, self.y, max(0.0, sc) * (1 + 0.03 * beat_pulse(t)))


class IPBox(El):
    """The call-to-action IP panel with typed-out text and a blinking cursor."""

    def __init__(self, start, end, y, type_at, text="MC.GOLD", step=0.125):
        super().__init__(start, end)
        self.y, self.type_at, self.step = y, type_at, step
        self.box = panel(920, 290, 6)
        self.label = pixel_text("SERVER IP", 4, "white", "press", outline=1, extrude=1, shadow=0)
        # every prefix uses the full text's cell size so letters don't jump while typing
        self.cell = math.floor(min(24, 800 * SUB / pixel_text(text, SUB).width) * 4) / 4
        self.parts = [pixel_text(text[:i], self.cell) if i else None for i in range(len(text) + 1)]
        self.full = self.parts[-1]
        self.n = len(text)
        self.done = type_at + self.n * step

    def draw(self, ctx, t):
        p = (t - self.start) / 0.3
        dy = lerp(160, 0, ease_out_cubic(p))
        al = clamp(p * 2)
        ot = self.end - t
        sc = 1 + 0.025 * beat_pulse(t) if t > self.done else 1.0
        if ot < 0.2:
            sc *= max(0.0, 1 - ease_in_back(1 - ot / 0.2))
        y = self.y + dy + ctx.dy
        x = CX + ctx.dx
        if sc <= 0.02:
            return
        place(ctx.canvas, self.box, x, y, sc, al)
        place(ctx.canvas, self.label, x, y - 82 * sc, sc, al)
        typed = int(clamp((t - self.type_at) / self.step, 0, self.n) + 1e-6)
        left = x - self.full.width / 2 * sc
        ty = y + 32 * sc
        img = self.parts[typed]
        if img is not None:
            place(ctx.canvas, img, left + img.width / 2 * sc, ty, sc, al)
        if self.type_at <= t < self.done:
            cw = (img.width if img is not None else 0) * sc
            bar = Image.new("RGBA", (max(4, round(self.cell * 1.2 * sc)), round(self.cell * 5 * sc)),
                            (*G_PALE, 255))
            place(ctx.canvas, bar, left + cw + bar.width / 2 + 10 * sc, ty, 1.0, al)


class KenBurns(El):
    """Pans/zooms across a screenshot inside a gold frame, with highlight boxes."""

    def __init__(self, img, rect, keys, start, end, k=4, highlights=(), dims=()):
        super().__init__(start, end)
        self.img, self.rect, self.keys, self.k = img, rect, keys, k
        self.highlights, self.dims = highlights, dims
        x0, y0, x1, y1 = rect
        self.frame = panel(x1 - x0 + 48, y1 - y0 + 48, 6, fill=None)

    def cam(self, t):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1:]
        for a, b in zip(ks, ks[1:]):
            if t <= b[0]:
                p = ease_in_out((t - a[0]) / (b[0] - a[0]))
                return tuple(lerp(u, v, p) for u, v in zip(a[1:], b[1:]))
        return ks[-1][1:]

    def to_screen(self, sx, sy, cam):
        cx, cy, z = cam
        x0, y0, x1, y1 = self.rect
        return (x0 + x1) / 2 + (sx - cx) * z, (y0 + y1) / 2 + (sy - cy) * z

    def draw(self, ctx, t):
        x0, y0, x1, y1 = self.rect
        rw, rh = x1 - x0, y1 - y0
        cam = self.cam(t)
        cx, cy, z = cam
        sw, sh = rw / z, rh / z
        k = self.k
        view = self.img.transform((rw, rh), Image.EXTENT,
                                  ((cx - sw / 2) * k, (cy - sh / 2) * k, (cx + sw / 2) * k, (cy + sh / 2) * k),
                                  Image.BILINEAR)
        layer = Image.new("RGBA", (rw + 48, rh + 48), (0, 0, 0, 0))
        layer.paste(view, (24, 24))
        dim = 0.0
        for d0, d1, amt in self.dims:
            if d0 <= t < d1:
                dim = amt * clamp((t - d0) / 0.25)
        if dim:
            shade = Image.new("RGBA", (rw, rh), (8, 4, 16, int(255 * dim)))
            layer.alpha_composite(shade, (24, 24))
        dr = ImageDraw.Draw(layer)
        tags = []
        for h0, h1, box, col, label, below in self.highlights:
            if not h0 <= t < h1:
                continue
            if t - h0 < 0.5 and int((t - h0) / 0.1) % 2 == 1:
                continue
            ax, ay = self.to_screen(box[0], box[1], cam)
            bx, by = self.to_screen(box[2], box[3], cam)
            ax, ay = max(x0 + 6, ax) - x0 + 24, max(y0 + 6, ay) - y0 + 24
            bx, by = min(x1 - 6, bx) - x0 + 24, min(y1 - 6, by) - y0 + 24
            pad = 10
            dr.rectangle((ax - pad - 6, ay - pad - 6, bx + pad + 6, by + pad + 6), outline=INK, width=16)
            dr.rectangle((ax - pad, ay - pad, bx + pad, by + pad), outline=col, width=8)
            if label is not None:
                edge = (by + pad + label.height / 2 + 4) if below else (ay - pad - label.height / 2 + 10)
                tags.append((label, bx + x0 - 24, edge + y0 - 24, h0))
        layer.alpha_composite(self.frame)
        p = (t - self.start) / 0.35
        dy = lerp(260, 0, ease_out_cubic(p))
        al = clamp(p * 2)
        sc = 1.0
        ot = self.end - t
        if ot < 0.22:
            sc = max(0.0, 1 - ease_in_back(1 - ot / 0.22))
        place(ctx.canvas, layer, (x0 + x1) / 2 + ctx.dx, (y0 + y1) / 2 + dy + ctx.dy, sc, al, smooth=True)
        for label, rx, ty, h0 in tags:
            s = ease_out_back((t - h0) / 0.25)
            lx = min(W - 30 - label.width / 2, rx - label.width / 2 + 30)
            place(ctx.canvas, label, lx, ty, s * sc)


class Cursor(El):
    z = 4

    def __init__(self, path, start, end, click_at):
        super().__init__(start, end)
        self.path, self.click_at = path, click_at
        self.img = sprite("cursor", 7)

    def draw(self, ctx, t):
        (t0, ax, ay), (t1, bx, by) = self.path
        p = ease_in_out((t - t0) / (t1 - t0))
        x, y = lerp(ax, bx, p), lerp(ay, by, p)
        sc = 0.85 if 0 <= t - self.click_at < 0.12 else 1.0
        place(ctx.canvas, self.img, x + self.img.width / 2 * sc, y + self.img.height / 2 * sc, sc)


class Selection(El):
    """White Minecraft-style selection outline around the server-list entry."""

    def __init__(self, box, start, end):
        super().__init__(start, end)
        self.box = box

    def draw(self, ctx, t):
        x0, y0, x1, y1 = self.box
        ImageDraw.Draw(ctx.canvas).rectangle((x0 - 8, y0 - 8, x1 + 8, y1 + 8), outline=(255, 255, 255, 255),
                                             width=6)


class EloBar(El):
    def __init__(self, y, start, end):
        super().__init__(start, end)
        self.y = y
        self.box = panel(780, 96, 6)
        self.arrow = sprite("arrow", 8)

    def draw(self, ctx, t):
        p = (t - self.start) / 0.3
        al = clamp(p * 2)
        ot = self.end - t
        sc = max(0.0, 1 - ease_in_back(1 - ot / 0.18)) if ot < 0.18 else 1.0
        if sc <= 0.02:
            return
        layer = self.box.copy()
        fill = lerp(0.08, 0.88, ease_out_cubic((t - self.start - 0.3) / 1.1))
        iw = layer.width - 2 * 30
        fw = int(iw * fill)
        d = ImageDraw.Draw(layer)
        d.rectangle((30, 30, 30 + fw, layer.height - 31), fill=G_GOLD)
        d.rectangle((30, 30, 30 + fw, 41), fill=G_PALE)
        d.rectangle((30, layer.height - 42, 30 + fw, layer.height - 31), fill=G_DEEP)
        place(ctx.canvas, layer, CX + ctx.dx, self.y + ctx.dy, sc, al)
        ax = CX - layer.width / 2 + 30 + fw
        place(ctx.canvas, self.arrow, ax + ctx.dx, self.y - 100 + math.sin(t * 9) * 8 + ctx.dy, sc, al)


# ----------------------------------------------------------------------------
# a short = background keys + elements + sound cues

HOOK_BG = dict(rays=1.0, glow=0.95, terrain=0.0, dim=0.0)
WORLD_BG = dict(rays=0.3, glow=0.5, terrain=1.0, dim=0.0)
HYPE_BG = dict(rays=0.75, glow=0.8, terrain=1.0, dim=0.0)


class Short:
    def __init__(self, name, title, duration):
        self.name, self.title, self.duration = name, title, duration
        self.els, self.sfx, self.shakes, self.bg_keys = [], [], [], []
        self.drops, self.risers = [], []
        self.world = World(duration)

    # -- building
    def add(self, el):
        self.els.append(el)
        return el

    def bg(self, t, params):
        self.bg_keys.append((t, params))

    def cue(self, t, name, **kw):
        self.sfx.append((t, name, kw))

    def shake(self, t, amp):
        self.shakes.append((t, amp))

    def _sprite(self, img, y, start, end, anim, x=CX, sfx=True, **kw):
        el = self.add(Sprite(img, x, y, start, end, anim=anim, **kw))
        if sfx and anim == "slam":
            self.cue(el.land_time() - 0.02, "impact")
            self.shake(el.land_time(), 20)
        elif sfx and anim == "drop":
            self.cue(el.land_time() - 0.02, "impact")
            self.shake(el.land_time(), 26)
        elif sfx and anim in ("pop", "rise", "swing"):
            self.cue(start, "pop" if anim != "swing" else "whoosh", dur=0.3)
        return el

    def text(self, s, y, start, end, cell=18, style="gold", face="silk", anim="pop", max_w=940, **kw):
        if face == "press":
            img = text_fit(s, cell, max_w, style=style, face=face, outline=1, extrude=1, shadow=2)
        else:
            img = text_fit(s, cell, max_w, style=style, face=face)
        return self._sprite(img, y, start, end, anim, **kw)

    def image(self, img, y, start, end, width, anim="pop", **kw):
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        return self._sprite(img, y, start, end, anim, smooth=True, **kw)

    def sprite(self, name, k, x, y, start, end, anim="pop", **kw):
        return self._sprite(sprite(name, k), y, start, end, anim, x=x, **kw)

    def counter(self, steps, y, end, cell, tick="blip", **kw):
        self.add(Counter(steps, y, end, cell, **kw))
        for i, (t, _) in enumerate(steps):
            self.cue(t, tick, semi=i * 2)
        self.cue(steps[-1][0], "impact")
        self.shake(steps[-1][0], 20)

    def burst(self, t, x, y, **kw):
        self.add(Burst(t, x, y, **kw))

    def rain(self, start, end, **kw):
        self.add(CoinRain(start, end, **kw))

    def wipe(self, t):
        self.add(TileWipe(t))
        self.cue(t - 0.28, "whoosh", dur=0.5)

    def drop(self, t):
        """The beat drop: full band comes in, crash + boom, flash, shake."""
        self.drops.append(t)
        self.cue(t, "boom")
        self.add(Flash(t))
        self.shake(t, 28)

    def riser(self, t, dur):
        self.risers.append((t, dur))

    def cta(self, t0, end, subline):
        self.bg(t0, HYPE_BG)
        self.rain(t0 + 0.2, end, n=22, seed=91)
        self.image(assets()["trophy"], 610, t0, end, 560, anim="pop", glow=True, bob=12, out=None)
        self.text("JOIN NOW", 1010, t0 + 0.5, end, cell=22, anim="slam", pulse=0.05, out=None)
        box = self.add(IPBox(t0 + 1.0, end, 1250, type_at=t0 + 1.25))
        self.cue(t0 + 1.0, "pop")
        for i in range(box.n):
            self.cue(box.type_at + i * box.step, "type", semi=i)
        self.cue(box.done, "kaching")
        self.burst(box.done, CX, 1250, coins=12, sparks=16, seed=33)
        self.text(subline, 1475, box.done + 0.4, end, cell=5, style="white", face="press", anim="rise", out=None)

    # -- rendering
    def finish(self):
        self.els.sort(key=lambda e: e.z)
        self.bg_keys.sort(key=lambda k: k[0])
        return self

    def bg_at(self, t):
        """Background params: each key eases in from the previous one over 0.6 s."""
        ks = self.bg_keys
        i = max((j for j, (tk, _) in enumerate(ks) if tk <= t), default=0)
        cur = ks[i][1]
        if i == 0:
            return cur
        p = ease_in_out((t - ks[i][0]) / 0.6)
        return {k: lerp(ks[i - 1][1][k], v, p) for k, v in cur.items()}

    def shake_at(self, t, i):
        r = np.random.default_rng(i)
        dx = dy = 0.0
        for ts, amp in self.shakes:
            d = t - ts
            if 0 <= d < 0.35:
                a = amp * math.exp(-d / 0.08)
                ux, uy = r.uniform(-1, 1, 2)
                dx += ux * a
                dy += uy * a
        return dx, dy

    def frame(self, i):
        t = i / FPS
        arr = self.world.render(t, **self.bg_at(t))
        canvas = Image.fromarray(arr, "RGB").convert("RGBA")
        ctx = Ctx(canvas, *self.shake_at(t, i))
        for el in self.els:
            if el.start <= t < el.end:
                el.draw(ctx, t)
        return canvas.convert("RGB")


# ----------------------------------------------------------------------------
# the three shorts

A_NETWAX = (108, 94, 278, 119)
A_QOCY = (122, 120, 262, 146)
A_YOURS = (18, 388, 318, 412)


def short_paid():
    s = Short("mcgold-short-1-get-paid", "Get paid to play Minecraft", 17.0)
    A = assets()
    s.bg(0, HOOK_BG)
    s.bg(2.0, WORLD_BG)

    # hook
    s.text("GET PAID", 640, 0.0, 1.85, cell=19, anim="slam")
    s.text("TO PLAY", 805, 0.5, 1.85, cell=19, style="white", anim="slam")
    s.text("MINECRAFT?", 975, 1.0, 1.85, cell=17, anim="slam", glow=True)
    s.burst(1.12, CX, 975, seed=2)
    s.cue(1.12, "kaching")
    s.riser(1.0, 1.0)
    s.wipe(2.0)
    s.drop(2.0)

    # the server
    s.text("WELCOME TO", 430, 2.15, 3.9, cell=6, style="white", face="press", anim="pop")
    s.image(A["trophy"], 830, 2.0, 3.9, 600, anim="drop", glow=True, bob=10)
    s.text("WHERE WINNERS GET PAID", 1255, 2.75, 3.9, cell=5, face="press", anim="rise")
    s.add(Badge(2.4, 10.8))

    # events
    s.bg(4.0, HYPE_BG)
    s.image(A["weekend"], 560, 4.0, 6.35, 860, anim="slam")
    s.counter([(4.5, "1"), (4.625, "2"), (4.75, "3"), (4.875, "4"), (5.0, "5+")], 930, 6.35, cell=44)
    s.text("EVENTS", 1160, 5.25, 6.35, cell=18, anim="pop")
    s.text("EVERY SATURDAY", 1295, 5.5, 6.35, cell=12, style="white", anim="pop")

    # $5 per win
    s.bg(6.5, WORLD_BG)
    s.add(Flash(6.5, strength=0.5))
    s.rain(6.5, 11.0, n=36)
    s.text("WIN AN EVENT", 560, 6.5, 8.35, cell=15, style="white", anim="slam")
    s.text("$5", 890, 7.0, 8.35, cell=62, anim="slam", glow=True, shine_at=7.3, pulse=0.04)
    s.cue(7.1, "kaching")
    s.burst(7.12, CX, 890, seed=4)
    s.text("PER WIN!", 1210, 7.5, 8.35, cell=20, anim="pop")

    # $25 in one Saturday
    s.text("WIN 5 EVENTS", 560, 8.5, 10.85, cell=15, style="white", anim="slam")
    s.counter([(9.0, "$5"), (9.25, "$10"), (9.5, "$15"), (9.75, "$20"), (10.0, "$25")], 880, 10.85,
              cell=52, tick="coin")
    s.burst(10.02, CX, 880, seed=6)
    s.text("IN ONE SATURDAY", 1170, 10.0, 10.85, cell=11, anim="pop")
    s.riser(10.0, 1.0)

    s.wipe(11.0)
    s.drop(11.0)
    s.cta(11.0, 17.0, "SEE YOU SATURDAY!")
    return s.finish()


def short_leaderboard():
    s = Short("mcgold-short-2-beat-number-one", "Can you beat #1?", 20.0)
    A = assets()
    s.bg(0, HOOK_BG)
    s.bg(2.0, WORLD_BG)

    s.text("CAN YOU", 640, 0.0, 1.85, cell=20, style="white", anim="slam")
    s.text("BEAT", 800, 0.5, 1.85, cell=20, style="white", anim="slam")
    s.text("#1?", 1030, 1.0, 1.85, cell=50, anim="slam", glow=True)
    s.burst(1.12, CX, 1030, seed=12)
    s.riser(1.0, 1.0)
    s.wipe(2.0)
    s.drop(2.0)

    full = min(840 / 349, 1040 / 432)
    rect = (120, 420, 960, 1460)
    keys = [(2.0, 185, 134, 3.9), (4.0, 185, 140, 4.0), (4.7, 174.5, 216, full), (5.6, 174.5, 216, full),
            (6.3, 174.5, 246.5, 2.8), (8.0, 174.5, 246.5, 2.9)]
    hl = [(2.5, 4.4, A_NETWAX, G_GOLD, tag("#1 - 23 WINS"), False),
          (3.25, 4.4, A_QOCY, G_GOLD, tag("#2 - 20 WINS", "white"), True),
          (6.5, 7.85, A_YOURS, (255, 70, 60), None, False)]
    s.add(KenBurns(A["board"], rect, keys, 2.0, 7.85, highlights=hl, dims=[(6.6, 8.0, 0.62)]))
    s.cue(2.5, "blip", semi=7)
    s.cue(3.25, "blip", semi=4)
    s.cue(4.6, "whoosh", dur=0.5)
    s.cue(6.2, "whoosh", dur=0.5)
    s.cue(6.5, "blip", semi=-5)
    s.text("YOURS: 0?", 960, 6.9, 7.85, cell=26, style="red", anim="slam", glow=True)
    s.add(Badge(2.4, 14.8))

    s.bg(8.0, HYPE_BG)
    s.add(Flash(8.0, strength=0.5))
    s.text("LET'S", 760, 8.0, 9.85, cell=22, style="white", anim="slam")
    s.text("CHANGE", 925, 8.5, 9.85, cell=24, anim="slam")
    s.text("THAT.", 1090, 9.0, 9.85, cell=24, anim="slam", glow=True)

    s.bg(10.0, WORLD_BG)
    s.rain(10.0, 15.0, n=36, seed=21)
    s.text("EVERY EVENT WIN", 560, 10.0, 12.35, cell=14, style="white", anim="slam")
    s.text("= $5", 870, 10.5, 12.35, cell=50, anim="slam", glow=True, shine_at=10.8, pulse=0.04)
    s.cue(10.6, "kaching")
    s.burst(10.62, CX, 870, seed=14)
    s.text("PER WIN!", 1170, 11.0, 12.35, cell=20, anim="pop")

    s.text("5+ EVENTS", 600, 12.5, 14.85, cell=26, anim="slam")
    s.text("EVERY SATURDAY", 770, 13.0, 14.85, cell=13, style="white", anim="pop")
    for i in range(5):
        s.sprite("coin", 9, CX + (i - 2) * 170, 980, 13.25 + i * 0.125, 14.85, anim="pop", bob=8, sfx=False)
        s.cue(13.25 + i * 0.125, "coin", semi=i * 2)
    s.text("WIN THEM ALL = $25+", 1190, 14.0, 14.85, cell=11, anim="pop")
    s.riser(14.0, 1.0)

    s.wipe(15.0)
    s.drop(15.0)
    s.cta(15.0, 20.0, "CLIMB THE LEADERBOARD")
    return s.finish()


def short_pvp():
    s = Short("mcgold-short-3-new-pvp-server", "Looking for a new PvP server?", 20.0)
    A = assets()
    s.bg(0, HOOK_BG)
    s.bg(2.0, WORLD_BG)

    s.text("LOOKING FOR A", 620, 0.0, 1.85, cell=13, style="white", anim="slam")
    s.text("NEW PVP", 800, 0.5, 1.85, cell=26, anim="slam")
    s.text("SERVER?", 990, 1.0, 1.85, cell=26, anim="slam", glow=True)
    s.burst(1.12, CX, 990, seed=31)
    s.riser(1.0, 1.0)
    s.wipe(2.0)
    s.drop(2.0)

    # server list entry + click
    srv = A["server"].resize((1040, round(A["server"].height * 1040 / A["server"].width)), Image.LANCZOS)
    s.text("ADD THIS ONE:", 650, 2.1, 3.9, cell=6, style="white", face="press", anim="pop")
    s.add(Sprite(srv, CX, 860, 2.25, 3.9, anim="right", smooth=True))
    s.cue(2.25, "whoosh", dur=0.35)
    sy0 = 860 - srv.height / 2
    s.add(Selection((CX - srv.width // 2, sy0, CX + srv.width // 2, sy0 + srv.height), 3.15, 3.75))
    s.add(Cursor([(2.6, 900, 1350), (3.1, 470, 880)], 2.6, 3.75, click_at=3.15))
    s.cue(3.15, "select")
    s.text("IP: MC.GOLD", 1090, 3.2, 3.9, cell=7, face="press", anim="pop", sfx=False)
    s.add(Badge(4.0, 13.8))

    # feature 1
    s.bg(4.0, HYPE_BG)
    s.sprite("sword", 17, CX, 740, 4.0, 6.35, anim="swing", bob=8)
    s.cue(4.25, "impact")
    s.shake(4.25, 16)
    s.text("VANILLA PVP", 1080, 4.5, 6.35, cell=20, anim="slam")
    s.text("JUST YOU AND YOUR SWORD", 1225, 5.0, 6.35, cell=5, style="white", face="press", anim="rise")

    # feature 2
    s.bg(6.5, WORLD_BG)
    for i, (name, x) in enumerate([("head_gold", 150), ("head_white", 340), ("head_purple", 740),
                                   ("head_red", 930)]):
        t0 = 6.5 + [0, 0.125, 0.375, 0.5][i]
        s.sprite(name, 18, x, 740, t0, 8.85, anim="pop", bob=10, sfx=False)
        s.cue(t0, "blip", semi=i * 3)
    s.text("VS", 740, 6.75, 8.85, cell=13, style="red", anim="slam", x=CX)
    s.text("2V2 ELO", 990, 7.0, 8.85, cell=24, anim="slam")
    s.text("RANKED DUOS", 1120, 7.5, 8.85, cell=6, style="white", face="press", anim="rise")
    s.add(EloBar(1290, 7.5, 8.85))
    s.cue(7.8, "riser_short")

    # feature 3
    s.bg(9.0, HYPE_BG)
    s.image(A["weekend"], 620, 9.0, 11.35, 860, anim="slam")
    s.text("5+ EVENTS", 930, 9.5, 11.35, cell=24, anim="slam")
    s.text("EVERY SATURDAY", 1090, 10.0, 11.35, cell=12, style="white", anim="pop")

    # $5
    s.bg(11.5, WORLD_BG)
    s.add(Flash(11.5, strength=0.5))
    s.rain(11.5, 14.5, n=34, seed=41)
    s.text("WIN AN EVENT", 560, 11.5, 13.85, cell=15, style="white", anim="slam")
    s.text("$5", 890, 12.0, 13.85, cell=62, anim="slam", glow=True, shine_at=12.3, pulse=0.04)
    s.cue(12.1, "kaching")
    s.burst(12.12, CX, 890, seed=42)
    s.text("PER WIN!", 1210, 12.5, 13.85, cell=20, anim="pop")
    s.riser(13.0, 1.0)

    s.wipe(14.0)
    s.drop(14.0)
    s.cta(14.0, 20.0, "BRING YOUR DUO!")
    return s.finish()


SHORTS = {"paid": short_paid, "leaderboard": short_leaderboard, "pvp": short_pvp}


# ----------------------------------------------------------------------------
# audio: a small chiptune synth

def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


_NOISE = np.random.default_rng(99).uniform(-1, 1, SR * 4)


def noise(n, offset=0):
    return _NOISE[offset:offset + n].copy()


def lowpass(x, n):
    return np.convolve(x, np.ones(n) / n, "same") if n > 1 else x


def env_adsr(n, a=0.004, d=0.08, s=0.5, r=0.03):
    e = np.full(n, s, np.float64)
    na = min(n, int(a * SR))
    nd = min(n - na, int(d * SR))
    e[:na] = np.linspace(0, 1, na, endpoint=False)
    e[na:na + nd] = np.linspace(1, s, nd, endpoint=False)
    nr = min(n, int(r * SR))
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def osc(freq, dur, wave="pulse", duty=0.5, vib=0.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if vib:
        phase = np.cumsum(freq * (1 + vib * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.2, 0, 1))) / SR
    else:
        phase = freq * t
    ph = phase % 1.0
    if wave == "pulse":
        return np.where(ph < duty, 1.0, -1.0) - (2 * duty - 1)
    if wave == "tri":
        return 4 * np.abs(ph - 0.5) - 1
    return np.sin(2 * np.pi * phase)


def tone(m, dur, wave="pulse", duty=0.5, vib=0.0, **env):
    x = osc(midi_hz(m), dur, wave, duty, vib)
    return x * env_adsr(len(x), **env)


def kick():
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    f = 48 + 120 * np.exp(-t / 0.035)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.11)
    x[:220] += noise(220) * np.linspace(0.5, 0, 220)
    return x


def snare():
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    nz = noise(n, 1000)
    nz = nz - lowpass(nz, 6)
    return nz * np.exp(-t / 0.07) * 0.9 + np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05) * 0.5


def hat(long=False):
    n = int((0.25 if long else 0.05) * SR)
    t = np.arange(n) / SR
    nz = np.diff(noise(n + 1, 5000))
    return nz * np.exp(-t / (0.08 if long else 0.012)) * 0.5


def crash():
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    nz = np.diff(noise(n + 1, 20000)) * 0.6 + noise(n, 40000) * 0.25
    return nz * np.exp(-t / 0.55)


def sfx(name, dur=0.5, semi=0):
    if name == "impact":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        f = 30 + 95 * np.exp(-t / 0.06)
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.16)
        return body + lowpass(noise(n, 7000), 10) * np.exp(-t / 0.05) * 1.2
    if name == "boom":
        a, b = sfx("impact"), crash()
        b[:len(a)] += a * 1.2
        return b
    if name == "whoosh":
        n = int(dur * SR)
        t = np.arange(n) / SR
        nz = noise(n, 9000)
        lo = lowpass(nz, 24) - lowpass(nz, 90)
        hi = lowpass(nz, 4) - lowpass(nz, 24)
        p = t / dur
        return (lo * (1 - p) + hi * p * 0.7) * np.sin(np.pi * p) ** 2 * 2.2
    if name in ("riser", "riser_short"):
        dur = dur if name == "riser" else 0.6
        n = int(dur * SR)
        t = np.arange(n) / SR
        p = t / dur
        nz = np.diff(noise(n + 1, 30000)) * p ** 2 * 0.45
        f = 180 * 2 ** (3 * p)
        sweep = np.where((np.cumsum(f) / SR) % 1 < 0.25, 1.0, -1.0) * p ** 1.5 * 0.16
        return nz + sweep
    if name == "coin":
        s = 2 ** (semi / 12)
        a = osc(1047 * s, 0.06) * 0.5
        b = osc(1568 * s, 0.28)
        b *= np.exp(-np.arange(len(b)) / SR / 0.09) * 0.5
        return np.concatenate([a, b])
    if name == "kaching":
        n = int(0.9 * SR)
        t = np.arange(n) / SR
        bell = sum(np.sin(2 * np.pi * f * t) * a for f, a in
                   [(2093, 1), (2637, .7), (3136, .6), (4186, .4), (5274, .25)])
        bell = bell * np.exp(-t / 0.3) * 0.32
        out = np.zeros(n + int(0.08 * SR))
        out[:900] += noise(900, 3000) * np.linspace(0.9, 0, 900)
        out[int(0.08 * SR):] += bell
        out[:n] += bell * 0.6
        return out
    if name == "pop":
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        f = 380 * 3 ** (t / 0.09)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / 0.09) * 0.7
    if name == "type":
        n = int(0.03 * SR)
        t = np.arange(n) / SR
        return (osc(1900 + 300 * math.sin(semi + n), 0.03) * np.exp(-t / 0.006) * 0.35
                + np.diff(noise(n + 1, 11000)) * np.exp(-t / 0.004) * 0.6)
    if name == "blip":
        x = tone(81 + semi, 0.09, duty=0.25, a=0.002, d=0.07, s=0.0, r=0.01)
        return x * 0.45
    if name == "select":
        return np.concatenate([sfx("blip"), sfx("blip", semi=7)])
    raise ValueError(name)


# Am - F - C - G, voiced close together so the arpeggio flows
CHORDS = [(45, [64, 69, 72, 76]), (41, [65, 69, 72, 77]), (48, [64, 67, 72, 76]), (43, [62, 67, 71, 74])]
LEAD = [(0, 76, 1), (1, 76, .5), (1.5, 74, .5), (2, 72, 1), (3, 74, 1),
        (4, 72, 1), (5, 69, 1), (6, 72, .5), (6.5, 74, .5), (7, 76, 1),
        (8, 79, 1), (9, 76, .5), (9.5, 79, .5), (10, 81, 1), (11, 79, 1),
        (12, 74, 1.5), (13.5, 76, .5), (14, 74, 1), (15, 71, 1)]


class Bus:
    def __init__(self, dur):
        n = int((dur + 2) * SR)
        self.l, self.r = np.zeros(n), np.zeros(n)

    def add(self, t, x, vol=1.0, pan=0.0):
        i = int(round(t * SR))
        if i >= len(self.l) or i < 0:
            return
        j = min(len(self.l), i + len(x))
        gl, gr = vol * math.sqrt((1 - pan) / 2) * 1.41, vol * math.sqrt((1 + pan) / 2) * 1.41
        self.l[i:j] += x[:j - i] * gl
        self.r[i:j] += x[:j - i] * gr


def build_audio(short, path):
    dur = short.duration
    drop = short.drops[0]
    music, drums, fx = Bus(dur), Bus(dur), Bus(dur)
    bar = 4 * BEAT
    drop_bar = round(drop / bar)
    for b in range(math.ceil(dur / bar)):
        t0 = b * bar
        bass, arp = CHORDS[(b - drop_bar) % 4]
        phrase_bar = (b - drop_bar) % 4
        for k in range(16):
            t = t0 + k * BEAT / 4
            if t >= dur:
                break
            note = arp[[0, 1, 2, 3, 2, 1][k % 6]]
            pan = 0.35 if k % 2 else -0.35
            if t >= drop:
                music.add(t, tone(note + 12, BEAT / 4 * 0.9, duty=0.125, d=0.06, s=0.25, r=0.02), 0.07, pan)
                music.add(t, tone(note, BEAT / 4 * 0.9, "tri", d=0.08, s=0.3, r=0.02), 0.12, -pan)
            else:
                music.add(t, tone(note, BEAT / 4 * 0.95, "tri", d=0.08, s=0.4, r=0.02), 0.2, pan)
        if t0 + 1e-6 < drop:
            for e in range(8):  # light offbeat hats over the hook
                drums.add(t0 + e * BEAT / 2 + BEAT / 4, hat(), 0.14, 0.3)
            continue
        for e in range(8):
            m = bass + (12 if e % 2 else 0)
            music.add(t0 + e * BEAT / 2, tone(m, BEAT / 2 * 0.9, "tri", d=0.1, s=0.7, r=0.03), 0.34)
            music.add(t0 + e * BEAT / 2, tone(m + 12, BEAT / 2 * 0.8, duty=0.5, d=0.1, s=0.3, r=0.03), 0.05)
        for bt, m, d in LEAD:
            if phrase_bar * 4 <= bt < phrase_bar * 4 + 4:
                music.add(t0 + (bt - phrase_bar * 4) * BEAT,
                          tone(m, d * BEAT * 0.92, duty=0.5, vib=0.006, a=0.005, d=0.1, s=0.6, r=0.04), 0.075)
        for q in range(4):
            t = t0 + q * BEAT
            drums.add(t, kick(), 0.9)
            if q in (1, 3):
                drums.add(t, snare(), 0.45)
            drums.add(t + BEAT / 2, hat(), 0.26, 0.25)
            drums.add(t + BEAT / 4, hat(), 0.1, -0.25)
            drums.add(t + 3 * BEAT / 4, hat(), 0.1, -0.25)
    for t, d in short.risers:
        fx.add(t, sfx("riser", dur=d), 0.5)
    for t, name, kw in short.sfx:
        vol = {"impact": 0.75, "boom": 0.8, "whoosh": 0.45, "kaching": 0.5, "coin": 0.45, "pop": 0.4,
               "type": 0.4, "blip": 0.5, "select": 0.5, "riser_short": 0.45}[name]
        fx.add(t, sfx(name, **kw), vol)

    n = int(dur * SR)
    tt = np.arange(len(music.l)) / SR
    duck = 1 - 0.45 * np.exp(-((tt - drop) % BEAT) / 0.1) * (tt >= drop)
    out = []
    for m, d, f in ((music.l, drums.l, fx.l), (music.r, drums.r, fx.r)):
        x = (m * duck + d * 0.8 + f)[:n]
        fade = int(0.7 * SR)
        x[-fade:] *= np.linspace(1, 0, fade)
        out.append(x)
    x = np.stack(out, 1)
    x = np.tanh(x * 1.1) / np.tanh(1.1)
    x /= max(1e-6, np.abs(x).max()) / 0.95
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((x * 32767).astype("<i2").tobytes())


# ----------------------------------------------------------------------------
# rendering

_worker_short = None


def _init_worker(name):
    global _worker_short
    _worker_short = SHORTS[name]()


def _render_frame(i):
    return _worker_short.frame(i).tobytes()


def render(name, jobs=None):
    short = SHORTS[name]()
    os.makedirs(OUT_DIR, exist_ok=True)
    wav = os.path.join(OUT_DIR, short.name + ".wav")
    mp4 = os.path.join(OUT_DIR, short.name + ".mp4")
    build_audio(short, wav)
    n = int(short.duration * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", wav, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-tune", "animation", "-crf", "18",
           "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.84:level=false,aresample=44100",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", mp4]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(jobs or os.cpu_count(), initializer=_init_worker, initargs=(name,)) as pool:
        for k, buf in enumerate(pool.imap(_render_frame, range(n), chunksize=6)):
            proc.stdin.write(buf)
            if k % 60 == 0:
                print(f"  {short.name}: frame {k}/{n}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    os.remove(wav)
    # cover / thumbnail: the hook with all of its lines on screen
    short.frame(int(1.6 * FPS)).save(os.path.join(OUT_DIR, short.name + "-cover.png"))
    return short, mp4


if __name__ == "__main__":
    for key in FONTS:
        font_path(key)
    names = sys.argv[1:] or list(SHORTS)
    for nm in names:
        print(f"rendering {nm} ...", flush=True)
        _, path = render(nm)
        print(f"  -> {path}")
