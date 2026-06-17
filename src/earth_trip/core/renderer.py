"""
Globe renderer: pure-numpy orthographic projection + Pillow compositing.
No matplotlib/Cartopy — ~50-100ms per unique globe position on ARM64.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from earth_trip.core.animator import FrameSpec, CityVisible
from earth_trip.core.geocoder import CityInfo
from earth_trip.core import cache as _cache_mod

W, H = 1080, 1920
CX, CY = W // 2, H // 2
GLOBE_R = 520  # globe radius in pixels (normal full-globe view)


# ── Font helpers ────────────────────────────────────────────────────────────

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int):
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = _load_font(size)
    return _FONT_CACHE[size]


# ── Orthographic projection math ────────────────────────────────────────────

def _camera_basis(clon_deg: float, clat_deg: float):
    clon = math.radians(clon_deg)
    clat = math.radians(clat_deg)
    ex = np.array([-math.sin(clon), math.cos(clon), 0.0])
    ey = np.array([
        -math.sin(clat) * math.cos(clon),
        -math.sin(clat) * math.sin(clon),
        math.cos(clat),
    ])
    ez = np.array([
        math.cos(clat) * math.cos(clon),
        math.cos(clat) * math.sin(clon),
        math.sin(clat),
    ])
    return ex, ey, ez


def geo_to_pixel(
    lat_deg: float, lon_deg: float,
    clon_deg: float, clat_deg: float,
    globe_r: float = GLOBE_R,
) -> tuple[int, int] | None:
    """Forward orthographic projection. Returns None if on far hemisphere."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    ex, ey, ez = _camera_basis(clon_deg, clat_deg)
    p = np.array([
        math.cos(lat) * math.cos(lon),
        math.cos(lat) * math.sin(lon),
        math.sin(lat),
    ])
    depth = float(np.dot(p, ez))
    if depth < 0:
        return None
    sx = float(np.dot(p, ex))
    sy = float(np.dot(p, ey))
    px = int(CX + sx * globe_r)
    py = int(CY - sy * globe_r)
    return (px, py)


def _project_globe(
    earth: np.ndarray, clon_deg: float, clat_deg: float, globe_r: float = GLOBE_R
) -> np.ndarray:
    """Vectorized inverse orthographic projection: pixel → Earth texture sample."""
    ex, ey, ez = _camera_basis(clon_deg, clat_deg)

    x_idx = np.arange(W, dtype=np.float32)
    y_idx = np.arange(H, dtype=np.float32)
    X, Y = np.meshgrid(x_idx, y_idx)

    sx = (X - CX) / globe_r
    sy = (CY - Y) / globe_r
    r2 = sx * sx + sy * sy
    visible = r2 <= 1.0
    sz = np.where(visible, np.sqrt(np.clip(1.0 - r2, 0.0, 1.0)), 0.0)

    # World 3-D coordinates
    x3 = sx * ex[0] + sy * ey[0] + sz * ez[0]
    y3 = sx * ex[1] + sy * ey[1] + sz * ez[1]
    z3 = sx * ex[2] + sy * ey[2] + sz * ez[2]

    lat = np.arcsin(np.clip(z3, -1.0, 1.0))
    lon = np.arctan2(y3, x3)

    src_h, src_w = earth.shape[:2]
    src_x = ((lon + math.pi) / (2 * math.pi) * src_w).astype(np.int32) % src_w
    src_y = np.clip(
        ((math.pi / 2 - lat) / math.pi * src_h).astype(np.int32), 0, src_h - 1
    )

    result = np.zeros((H, W, 3), dtype=np.uint8)
    result[visible] = earth[src_y[visible], src_x[visible]]
    return result


# ── GlobeRenderer ────────────────────────────────────────────────────────────

class GlobeRenderer:
    def __init__(self, earth_texture_path: Path):
        self.earth = np.array(Image.open(earth_texture_path).convert("RGB"))
        self._star_base: np.ndarray = self._make_star_field()
        self._atmo: Image.Image = self._make_atmosphere()
        self._globe_cache: dict[tuple, np.ndarray] = {}
        self._mask_cache: dict[int, np.ndarray] = {}
        self._flag_cache: dict[str, Image.Image | None] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    def render_frame(self, spec: FrameSpec) -> np.ndarray:
        globe_r = spec.globe_r
        frame = self._get_globe_frame(spec.central_lon, spec.central_lat, globe_r).copy()

        img = Image.fromarray(frame).convert("RGBA")

        # Atmosphere only visible at normal (unzoomed) globe radius
        if globe_r <= GLOBE_R * 1.5:
            img.alpha_composite(self._atmo)

        self._draw_arc(img, spec)
        for cv in spec.cities_visible:
            self._draw_city(img, cv, spec.central_lon, spec.central_lat, globe_r)
        if spec.transport_label:
            self._draw_transport_badge(img, spec.transport_label)

        rgb = np.asarray(img.convert("RGB"))
        if spec.fade < 1.0:
            rgb = (rgb * spec.fade).astype(np.uint8)
        return rgb

    # ── Globe base ─────────────────────────────────────────────────────────

    def _get_globe_mask(self, globe_r: float) -> np.ndarray:
        key = round(globe_r, -1)
        if key not in self._mask_cache:
            y_idx = np.arange(H, dtype=np.float32)
            x_idx = np.arange(W, dtype=np.float32)
            X, Y = np.meshgrid(x_idx, y_idx)
            self._mask_cache[key] = ((X - CX) ** 2 + (Y - CY) ** 2) <= key ** 2
        return self._mask_cache[key]

    def _get_globe_frame(self, clon: float, clat: float, globe_r: float) -> np.ndarray:
        key = (round(clon, 1), round(clat, 1), round(globe_r, -1))
        if key not in self._globe_cache:
            projected = _project_globe(self.earth, clon, clat, globe_r)
            base = self._star_base.copy()
            mask = self._get_globe_mask(globe_r)
            base[mask] = projected[mask]
            self._globe_cache[key] = base
        return self._globe_cache[key]

    def _make_star_field(self) -> np.ndarray:
        img = Image.new("RGB", (W, H), (10, 8, 18))
        draw = ImageDraw.Draw(img)
        rng = np.random.RandomState(42)
        n = 900
        xs = rng.randint(0, W, n)
        ys = rng.randint(0, H, n)
        brights = rng.uniform(0.3, 1.0, n)
        sizes = rng.choice([1, 1, 1, 2, 2, 3], n, p=[0.50, 0.20, 0.15, 0.10, 0.04, 0.01])
        for x, y, b, s in zip(xs, ys, brights, sizes):
            r = int(210 + b * 45)
            g = int(210 + b * 45)
            bv = int(225 + b * 30)
            col = (r, g, bv)
            if s == 1:
                draw.point((int(x), int(y)), fill=col)
            else:
                draw.ellipse([int(x) - s // 2, int(y) - s // 2,
                              int(x) + s // 2, int(y) + s // 2], fill=col)
        return np.asarray(img)

    def _make_atmosphere(self) -> Image.Image:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for dr in range(40, 0, -1):
            r = GLOBE_R + dr
            alpha = int(80 * (1 - dr / 40) ** 2)
            col = (80, 160, 255, alpha)
            draw.ellipse([CX - r, CY - r, CX + r, CY + r], outline=col, width=1)
        # Extra bright rim
        for dr in range(4, 0, -1):
            r = GLOBE_R + dr
            alpha = int(120 * (1 - dr / 4))
            draw.ellipse([CX - r, CY - r, CX + r, CY + r],
                         outline=(140, 200, 255, alpha), width=1)
        return img

    # ── Overlays ───────────────────────────────────────────────────────────

    def _draw_arc(self, img: Image.Image, spec: FrameSpec) -> None:
        if spec.arc_lats is None or spec.arc_progress <= 0:
            return

        globe_r = spec.globe_r
        n = max(2, int(spec.arc_progress * len(spec.arc_lats)))
        pts: list[tuple[int, int]] = []
        for i in range(n):
            pt = geo_to_pixel(
                float(spec.arc_lats[i]), float(spec.arc_lons[i]),
                spec.central_lon, spec.central_lat,
                globe_r,
            )
            if pt:
                pts.append(pt)

        if len(pts) < 2:
            return

        draw = ImageDraw.Draw(img)
        step = max(1, len(pts) // 80)
        for i in range(0, len(pts) - step, step * 2):
            j = min(i + step, len(pts) - 1)
            draw.line([pts[i], pts[j]], fill=(255, 220, 80, 200), width=3)

        tip = pts[-1]
        for r, a in [(10, 60), (6, 120), (3, 220)]:
            draw.ellipse(
                [tip[0] - r, tip[1] - r, tip[0] + r, tip[1] + r],
                fill=(255, 220, 80, a),
            )

    def _draw_city(
        self,
        img: Image.Image,
        cv: CityVisible,
        clon: float,
        clat: float,
        globe_r: float,
    ) -> None:
        pt = geo_to_pixel(cv.city.lat, cv.city.lon, clon, clat, globe_r)
        if pt is None:
            return

        px, py = pt
        alpha = int(cv.opacity * 255)
        draw = ImageDraw.Draw(img)

        # Glow rings
        for r, a_frac in [(22, 0.25), (15, 0.45), (9, 0.70), (5, 1.0)]:
            a = int(alpha * a_frac)
            draw.ellipse(
                [px - r, py - r, px + r, py + r],
                fill=(100, 180, 255, a),
            )
        # White centre
        draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 255, 255, alpha))

        # Flag
        flag = self._get_flag(cv.city.country_code)
        label_x = px + 16
        label_y = py - 20

        if flag and cv.opacity > 0.2:
            flag_a = flag.copy()
            if cv.opacity < 1.0:
                flag_a.putalpha(
                    Image.fromarray(
                        (np.asarray(flag_a.split()[3]) * cv.opacity).astype(np.uint8)
                    )
                )
            img.paste(flag_a, (label_x, label_y), flag_a)
            label_x += flag.width + 8

        # City name
        city_text = cv.city.display_name or cv.city.name
        country_text = cv.city.country_name
        fn_big = _font(28)
        fn_small = _font(20)

        # Shadow
        draw.text((label_x + 1, label_y + 1), city_text, font=fn_big, fill=(0, 0, 0, int(alpha * 0.6)))
        draw.text((label_x, label_y), city_text, font=fn_big, fill=(255, 255, 255, alpha))
        draw.text(
            (label_x + 1, label_y + 34),
            country_text,
            font=fn_small,
            fill=(180, 210, 255, int(alpha * 0.85)),
        )

    def _draw_transport_badge(self, img: Image.Image, label: str) -> None:
        draw = ImageDraw.Draw(img)
        fn = _font(34)
        bbox = draw.textbbox((0, 0), label, font=fn)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x, pad_y = 28, 14
        bw = tw + pad_x * 2
        bh = th + pad_y * 2
        bx = (W - bw) // 2
        by = 80

        # Pill background
        pill = Image.new("RGBA", (bw + 4, bh + 4), (0, 0, 0, 0))
        pd = ImageDraw.Draw(pill)
        pd.rounded_rectangle([0, 0, bw + 3, bh + 3], radius=bh // 2,
                              fill=(20, 30, 60, 200))
        pd.rounded_rectangle([0, 0, bw + 3, bh + 3], radius=bh // 2,
                              outline=(79, 156, 249, 160), width=2)
        img.alpha_composite(pill, (bx - 2, by - 2))
        draw.text(
            (bx + pad_x - bbox[0], by + pad_y - bbox[1]),
            label,
            font=fn,
            fill=(230, 240, 255, 230),
        )

    # ── Flag fetching ──────────────────────────────────────────────────────

    def _get_flag(self, country_code: str) -> Image.Image | None:
        if not country_code:
            return None
        cc = country_code.lower()
        if cc in self._flag_cache:
            return self._flag_cache[cc]

        cached_path = _cache_mod.get_flag_path(cc)
        if cached_path:
            try:
                img = Image.open(cached_path).convert("RGBA").resize((48, 32), Image.LANCZOS)
                self._flag_cache[cc] = img
                return img
            except Exception:
                pass

        # Download from flagcdn.com
        try:
            url = f"https://flagcdn.com/48x32/{cc}.png"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                _cache_mod.save_flag(cc, resp.content)
                img = Image.open(_cache_mod.get_flag_path(cc)).convert("RGBA").resize((48, 32), Image.LANCZOS)
                self._flag_cache[cc] = img
                return img
        except Exception:
            pass

        self._flag_cache[cc] = None
        return None
