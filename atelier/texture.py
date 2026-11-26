"""Procedural floor textures and soft shadows (numpy rasters, placed on vector sheets).

Every colour here is DERIVED from atelier.theme tokens by mixing, so a re-brand in
theme.py re-tints the materials too, and this file holds no colour values.
ACCENT and FLAG are reserved by STANDARDS §1 and are never used for materials.

Textures are generated in plan mm: k = pixels per plan mm, rows run from the top
(plan y max) downwards so they can be placed with imshow(origin="upper").
"""
from __future__ import annotations

import numpy as np
from matplotlib.colors import to_rgb
from PIL import Image, ImageDraw, ImageFilter

from atelier import theme as T


# ------------------------------------------------------------------ colour mixing
def rgb(token) -> np.ndarray:
    return np.array(to_rgb(token))


def mix(a, b, t: float) -> np.ndarray:
    """t = 0 -> a, t = 1 -> b (tokens or rgb arrays)."""
    a = rgb(a) if isinstance(a, str) else a
    b = rgb(b) if isinstance(b, str) else b
    return a * (1 - t) + b * t


# Material palette: mixes of theme tokens only.
def palette():
    return {
        "oak":        mix(T.AMBER, T.PAPER, 0.42),
        "oak_dark":   mix(T.AMBER, T.INK, 0.30),
        "stone":      mix(T.LIGHT, T.MID, 0.45),
        "stone_dark": mix(T.MID, T.GREY, 0.35),
        "marble":     mix(T.PAPER, T.LIGHT, 0.35),
        "vein":       mix(T.GREY, T.INK, 0.15),
        "grout":      mix(T.MID, T.GREY, 0.55),
        "fabric":     mix(T.MID, T.PAPER, 0.35),
        "fabric_dk":  mix(T.MID, T.GREY, 0.35),
        "cushion":    mix(T.LIGHT, T.PAPER, 0.35),
        "linen":      mix(T.PAPER, T.LIGHT, 0.15),
        "throw":      mix(T.GREEN, T.PAPER, 0.55),
        "wood":       mix(T.AMBER, T.INK, 0.18),
        "wood_lt":    mix(T.AMBER, T.PAPER, 0.30),
        "rug":        mix(T.BLUE, T.PAPER, 0.72),
        "rug_border": mix(T.BLUE, T.INK, 0.25),
        "leaf":       mix(T.GREEN, T.INK, 0.10),
        "leaf_lt":    mix(T.GREEN, T.PAPER, 0.30),
        "worktop":    mix(T.LIGHT, T.PAPER, 0.20),
        "joinery":    mix(T.LIGHT, T.AMBER, 0.18),
        "metal":      mix(T.GREY, T.PAPER, 0.35),
        "velvet":     mix(T.GREEN, T.INK, 0.38),
        "velvet_dk":  mix(T.GREEN, T.INK, 0.55),
    }


# Colour NAMES -> theme tokens (designers name colours; no colour values outside theme.py).
# The first base word found sets the tone; modifiers then shift it. Unknown -> None.
TONE_BASE = [
    (("white", "ivory", "bone", "alabaster", "chalk", "snow"), lambda: mix(T.PAPER, T.LIGHT, 0.10)),
    (("cream", "linen", "oat", "ecru", "parchment"), lambda: mix(T.PAPER, T.AMBER, 0.12)),
    (("beige", "sand", "greige", "taupe", "mushroom", "stone", "travertine"), lambda: mix(T.LIGHT, T.AMBER, 0.18)),
    (("marble",), lambda: palette()["marble"]),
    (("grey", "gray", "ash", "concrete", "cement", "smoke", "pewter"), lambda: rgb(T.MID)),
    (("charcoal", "graphite", "black", "ink", "onyx", "espresso"), lambda: mix(T.INK, T.GREY, 0.20)),
    (("oak", "honey", "natural", "teak", "maple", "ash wood"), lambda: palette()["oak"]),
    (("walnut", "smoked", "wenge", "mocha", "chocolate"), lambda: palette()["oak_dark"]),
    (("brass", "bronze", "gold", "champagne", "copper"), lambda: mix(T.AMBER, T.GREY, 0.25)),
    (("terracotta", "rust", "clay", "cognac", "tan", "caramel"), lambda: mix(T.AMBER, T.INK, 0.22)),
    (("sage", "olive", "green", "moss", "emerald", "forest", "eucalyptus"), lambda: mix(T.GREEN, T.PAPER, 0.25)),
    (("blue", "navy", "denim", "indigo", "slate", "teal", "petrol"), lambda: mix(T.BLUE, T.PAPER, 0.25)),
    (("blush", "rose", "pink", "dusty"), lambda: mix(T.AMBER, T.PAPER, 0.62)),
]
TONE_MOD = [(("light", "pale", "soft"), T.PAPER, 0.40), (("dark", "deep", "rich"), T.INK, 0.35),
            (("warm",), T.AMBER, 0.08), (("cool",), T.BLUE, 0.08), (("muted", "dusty"), T.MID, 0.20)]


def named_tone(name):
    """A colour name ("warm oak", "deep olive", "bone") as RGB mixed from theme tokens, or None."""
    words = str(name or "").lower().replace("-", " ").split()
    text = " ".join(words)
    base = next((fn() for keys, fn in TONE_BASE if any(k in words or (" " in k and k in text) for k in keys)), None)
    if base is None:
        return None
    for keys, tok, t in TONE_MOD:
        if any(k in words for k in keys):
            base = mix(base, tok, t)
    return np.clip(base, 0, 1)


def finish_tone(f: dict) -> np.ndarray:
    """One flat tone for a finish (swatch fallback, render base colour). Rules, not per-code colours."""
    pal = palette()
    kind, name = f.get("kind", ""), (f.get("name") or "").lower()
    if f.get("tone") is not None and named_tone(f["tone"]) is not None:
        return named_tone(f["tone"])
    if kind == "paint":
        return mix(T.LIGHT, T.AMBER, 0.12) if "lime" in name else mix(T.PAPER, T.LIGHT, 0.12)
    if kind in ("wood", "veneer"):
        return pal["oak"]
    if kind == "fabric":
        return pal["fabric"]
    if kind == "laminate":
        return pal["joinery"]
    if kind == "metal":
        return pal["metal"]
    if kind == "stone":
        return pal["marble"] if "marble" in name else pal["worktop"] if "quartz" in name else pal["stone"]
    if kind in ("tile",):
        return pal["stone"]
    if kind in ("glass", "mirror"):
        return mix(T.BLUE, T.PAPER, 0.8)
    return mix(T.PAPER, T.LIGHT, 0.3)


def hexc(c) -> str:
    """rgb array -> matplotlib colour string (runtime value, not a literal)."""
    r, g, b = (np.clip(c, 0, 1) * 255).round().astype(int)
    return f"#{r:02x}{g:02x}{b:02x}"


# ------------------------------------------------------------------ noise
def value_noise(h, w, cell_px, rng, octaves=4, persistence=0.5):
    """Fractal value noise in [0, 1], shape (h, w)."""
    out = np.zeros((h, w))
    amp, total = 1.0, 0.0
    cell = max(cell_px, 2)
    for _ in range(octaves):
        gh, gw = int(h / cell) + 2, int(w / cell) + 2
        g = rng.random((gh, gw)).astype(np.float32)
        im = Image.fromarray((g * 255).astype(np.uint8)).resize((int(gw * cell), int(gh * cell)), Image.BICUBIC)
        out += amp * (np.asarray(im, dtype=np.float32)[:h, :w] / 255.0)
        total += amp
        amp *= persistence
        cell = max(cell / 2, 1)
    return out / total


def _grid(bounds, k):
    """Pixel-centre coordinates (plan mm) for a raster covering bounds at k px/mm."""
    x0, y0, x1, y1 = bounds
    w, h = max(int((x1 - x0) * k), 1), max(int((y1 - y0) * k), 1)
    xs = x0 + (np.arange(w) + 0.5) / k
    ys = y1 - (np.arange(h) + 0.5) / k
    X, Y = np.meshgrid(xs, ys)
    return X, Y, h, w


def _rot(X, Y, deg):
    a = np.radians(deg)
    return X * np.cos(a) + Y * np.sin(a), -X * np.sin(a) + Y * np.cos(a)


def _hash(*ints):
    """Deterministic pseudo-random [0,1) per integer key array."""
    v = np.zeros_like(ints[0], dtype=np.int64)
    for i, a in enumerate(ints):
        v = v * 1_000_003 + (a.astype(np.int64) + 7919 * (i + 1))
    v = (v ^ (v >> 13)) * 1274126177
    return ((v ^ (v >> 16)) & 0xFFFFFF) / float(0xFFFFFF)


def _streaks(across, key_a, key_b, warp, freq=0.32):
    """Irregular grain lines running along a plank: a 1-D random profile across the
    plank (per plank), smoothly interpolated and warped by noise."""
    c = across * freq + warp
    c0 = np.floor(c).astype(int)
    f = c - c0
    f = f * f * (3 - 2 * f)
    a = _hash(key_a, key_b, c0)
    b = _hash(key_a, key_b, c0 + 1)
    return a * (1 - f) + b * f


# ------------------------------------------------------------------ materials
def oak_planks(bounds, k, plank_w=190, plank_l=1900, angle=0.0, seed=1):
    P = palette()
    X, Y, h, w = _grid(bounds, k)
    U, V = _rot(X, Y, angle)                      # U along planks
    rng = np.random.default_rng(seed)
    row = np.floor(V / plank_w).astype(int)
    stagger = _hash(row) * plank_l
    idx = np.floor((U + stagger) / plank_l).astype(int)
    tone = _hash(row, idx) - 0.5
    along = (U + stagger) % plank_l
    across = V - row * plank_w
    n = value_noise(h, w, max(4, 260 * k), rng, 3)
    grain = _streaks(across, row, idx, 3.0 * n)
    fine = _streaks(across, row + 7, idx, 1.5 * n, freq=1.1)
    base = P["oak"][None, None, :] + tone[..., None] * 0.08
    img = base * (0.90 + 0.07 * grain[..., None] + 0.03 * fine[..., None]) - 0.025 * n[..., None]
    seam = (across < 1.6 / k + 0.8) | (along < 1.6 / k + 0.8)
    img[seam] = P["oak_dark"]
    return np.clip(img, 0, 1)


def herringbone(bounds, k, plank_w=90, plank_l=450, angle=45.0, seed=2):
    """Classic herringbone: n:1 planks; closed form of the staircase tiling."""
    P = palette()
    X, Y, h, w = _grid(bounds, k)
    U, V = _rot(X, Y, angle)
    n = max(2, round(plank_l / plank_w))
    x, y = U / plank_w, V / plank_w
    fx, fy = np.floor(x).astype(int), np.floor(y).astype(int)
    r = (fx - fy + n) % (2 * n) - n                # [-n, n-1]: >=0 horizontal, <0 vertical
    m = (fx - fy - r) // (2 * n)
    horiz = r >= 0
    k_h = fy
    k_v = fy + r
    key_k = np.where(horiz, k_h, k_v)
    along = np.where(horiz, (x - (k_h + 2 * n * m)) / n, (y - (k_v + 1)) / n)
    across = np.where(horiz, y - fy, x - fx)
    tone = _hash(key_k, m, horiz.astype(int)) - 0.5
    rng = np.random.default_rng(seed)
    nz = value_noise(h, w, max(4, 40 * k), rng, 3)
    grain_mm = across * plank_w
    grain = _streaks(grain_mm, key_k, m * 2 + horiz.astype(int), 2.5 * nz)
    img = P["oak"][None, None, :] + tone[..., None] * 0.10
    img = img * (0.90 + 0.09 * grain[..., None]) - 0.025 * nz[..., None]
    edge = 1.4 / (k * plank_w) + 0.008
    seam = (across < edge) | (along < edge / n * 1.0) | (along > 1 - 1e-3)
    img[seam] = P["oak_dark"]
    return np.clip(img, 0, 1)


def stone_tile(bounds, k, tile=(600, 600), grout=3, angle=0.0, seed=3, origin=(0, 0)):
    P = palette()
    X, Y, h, w = _grid(bounds, k)
    U, V = _rot(X - origin[0], Y - origin[1], angle)
    tx, ty = tile
    ix, iy = np.floor(U / tx).astype(int), np.floor(V / ty).astype(int)
    lu, lv = U - ix * tx, V - iy * ty
    tone = _hash(ix, iy) - 0.5
    rng = np.random.default_rng(seed)
    mott = value_noise(h, w, max(3, 120 * k), rng, 4)
    fine = value_noise(h, w, max(2, 12 * k), rng, 2)
    img = P["stone"][None, None, :] + tone[..., None] * 0.05
    img = img + (mott[..., None] - 0.5) * 0.06 + (fine[..., None] - 0.5) * 0.03
    g = max(grout, 1.2 / k)
    edge = (lu < g) | (lv < g)
    img[edge] = P["grout"]
    return np.clip(img, 0, 1)


def marble(bounds, k, slab=(800, 1600), angle=0.0, seed=4, origin=(0, 0)):
    P = palette()
    X, Y, h, w = _grid(bounds, k)
    U, V = _rot(X - origin[0], Y - origin[1], angle)
    rng = np.random.default_rng(seed)
    turb = value_noise(h, w, max(6, 1400 * k), rng, 5, 0.55)
    turb2 = value_noise(h, w, max(4, 300 * k), rng, 3, 0.5)
    phase = (U * 0.85 + V * 0.53) / 2300.0 + 1.1 * turb + 0.15 * turb2
    main = np.exp(-np.abs(np.sin(phase * np.pi)) * 28)
    phase2 = (U * 0.3 - V * 0.95) / 700.0 + 1.6 * turb2 + 0.7 * turb
    minor = np.exp(-np.abs(np.sin(phase2 * np.pi)) * 70) * 0.25
    vein = np.clip(main + minor, 0, 1)
    cloud = value_noise(h, w, max(6, 500 * k), rng, 4)
    img = P["marble"][None, None, :] + (cloud[..., None] - 0.5) * 0.05
    img = img * (1 - 0.42 * vein[..., None]) + P["vein"][None, None, :] * 0.42 * vein[..., None]
    sx, sy = slab
    lu, lv = U % sx, V % sy
    joint = (lu < 1.0 / k + 0.6) | (lv < 1.0 / k + 0.6)
    img[joint] = img[joint] * 0.94
    return np.clip(img, 0, 1)


def floor_texture(finish: dict, floor: dict, bounds, k, seed=0):
    """Pick the material from finish kind + floor pattern; a named `tone` re-tints it."""
    img = _floor_texture(finish, floor, bounds, k, seed)
    tone = named_tone(finish.get("tone")) if finish.get("tone") else None
    if tone is None:
        return img
    mean = img.reshape(-1, 3).mean(axis=0)
    return np.clip(img * (tone / np.maximum(mean, 1e-3)), 0, 1)


def _floor_texture(finish: dict, floor: dict, bounds, k, seed=0):
    """Pick the material from finish kind + floor pattern (agents/SCHEMA.md enums)."""
    kind = finish.get("kind", "tile")
    pattern = floor.get("pattern", "straight")
    mod = floor.get("module") or [600, 600]
    ang = floor.get("angle", 0)
    if kind in ("wood", "laminate", "veneer"):
        if pattern in ("herringbone", "chevron"):
            return herringbone(bounds, k, mod[0], mod[1], 45 + ang, seed)
        return oak_planks(bounds, k, mod[0], mod[1], ang, seed)
    if kind == "stone" and "marble" in finish.get("name", "").lower():
        return marble(bounds, k, tuple(mod), ang, seed)
    return stone_tile(bounds, k, tuple(mod), 3, ang, seed)


# ------------------------------------------------------------------ soft shadows
def soft_shadow(polys_page, page_w_mm, page_h_mm, dpi=150, offset=(1.0, 1.3), blur_mm=1.5, strength=0.36):
    """RGBA shadow layer for the whole page (light from the top-left).
    polys_page: page-mm polygons, each either a point list or (exterior, [holes])."""
    s = dpi / 25.4
    W, H = int(page_w_mm * s), int(page_h_mm * s)
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    ox, oy = offset
    for item in polys_page:
        ext, holes = item if (len(item) == 2 and isinstance(item[1], list)
                              and (not item[1] or isinstance(item[1][0], list))) else (item, [])
        d.polygon([((x + ox) * s, (y + oy) * s) for x, y in ext], fill=255)
        for h in holes:
            d.polygon([((x + ox) * s, (y + oy) * s) for x, y in h], fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(blur_mm * s))
    a = np.asarray(mask, dtype=np.float32) / 255.0 * strength
    ink = rgb(T.INK)
    out = np.zeros((H, W, 4), dtype=np.float32)
    out[..., :3] = ink
    out[..., 3] = a
    return out
