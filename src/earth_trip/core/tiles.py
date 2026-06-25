"""
Satellite tile fetching + equirectangular reprojection.

Downloads Web Mercator tiles from ESRI World Imagery (free, no API key),
caches to disk, stitches into a canvas, then reprojects to equirectangular
so the existing orthographic renderer can sample it directly.
"""
from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from platformdirs import user_cache_dir

_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
_TILE_PX = 256

_CACHE_DIR = Path(user_cache_dir("earth-trip-visualizer")) / "tiles"

# In-memory caches — survive for the duration of the process
_TILE_MEM: dict[tuple[int, int, int], Image.Image] = {}
_PATCH_MEM: dict[tuple, tuple] = {}  # key → (patch_arr, lat_min, lat_max, lon_min, lon_max)


# ── Tile math ────────────────────────────────────────────────────────────────

def _zoom_for(globe_r: float) -> int:
    """Web Mercator zoom level whose pixel resolution matches the given globe_r."""
    z = int(math.log2(max(1.0, 0.02 * globe_r)))
    return max(0, min(14, z))  # cap at z=14 to keep tile counts sane


def _lon_to_tx(lon: float, n: int) -> float:
    return (lon + 180.0) / 360.0 * n


def _lat_to_ty(lat: float, n: int) -> float:
    lr = math.radians(max(-85.051129, min(85.051129, lat)))
    return n * (1 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2


def _lat_to_ty_arr(lats: np.ndarray, n: int) -> np.ndarray:
    lr = np.radians(np.clip(lats, -85.051129, 85.051129))
    return n * (1 - np.log(np.tan(lr) + 1.0 / np.cos(lr)) / math.pi) / 2


def _ty_to_lat(ty: float, n: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2.0 * ty / n))))


# ── Tile fetching ────────────────────────────────────────────────────────────

def _get_tile(z: int, x: int, y: int) -> Image.Image | None:
    key = (z, x, y)
    if key in _TILE_MEM:
        return _TILE_MEM[key]

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{z}_{x}_{y}.jpg"

    if path.exists():
        try:
            img = Image.open(path).convert("RGB")
            _TILE_MEM[key] = img
            return img
        except Exception:
            path.unlink(missing_ok=True)

    try:
        r = requests.get(
            _TILE_URL.format(z=z, x=x, y=y),
            timeout=10,
            headers={"User-Agent": "earth-trip-visualizer/1.0"},
        )
        if r.status_code == 200:
            path.write_bytes(r.content)
            img = Image.open(BytesIO(r.content)).convert("RGB")
            _TILE_MEM[key] = img
            return img
    except Exception:
        pass
    return None


# ── Patch assembly ────────────────────────────────────────────────────────────

def get_patch(
    center_lat: float,
    center_lon: float,
    globe_r: float,
    half_w: float = 540.0,
    half_h: float = 960.0,
) -> tuple[np.ndarray, float, float, float, float] | None:
    """
    Return (patch, lat_min, lat_max, lon_min, lon_max) as an equirectangular
    numpy array covering the visible area, or None if tiles are unavailable.

    The patch can be sampled by the orthographic inverse-projection directly:
        px = (lon - lon_min) / (lon_max - lon_min) * patch_w
        py = (lat_max - lat) / (lat_max - lat_min) * patch_h
    """
    z = _zoom_for(globe_r)
    n = 2 ** z

    # Angular extents of the visible area (with 20% margin).
    # At high latitudes the orthographic projection maps screen-x to a larger longitude
    # range than asin(half_w/globe_r) suggests — correct for cos(lat).
    lat_half = min(85.0, math.degrees(math.asin(min(half_h / globe_r, 1.0)))) * 1.20
    lon_half_base = math.degrees(math.asin(min(half_w / globe_r, 1.0)))
    cos_lat = max(math.cos(math.radians(center_lat)), 0.35)  # cap correction at ~70° lat
    lon_half = min(180.0, lon_half_base / cos_lat) * 1.20

    lat_min_req = max(-85.0, center_lat - lat_half)
    lat_max_req = min(85.0, center_lat + lat_half)
    lon_min_req = center_lon - lon_half
    lon_max_req = center_lon + lon_half

    # Tile index range (north = small ty in TMS)
    tx0 = max(0, int(_lon_to_tx(lon_min_req, n)))
    tx1 = min(n - 1, int(_lon_to_tx(lon_max_req, n)))
    ty0 = max(0, int(_lat_to_ty(lat_max_req, n)))
    ty1 = min(n - 1, int(_lat_to_ty(lat_min_req, n)))

    patch_key = (z, tx0, tx1, ty0, ty1)
    if patch_key in _PATCH_MEM:
        return _PATCH_MEM[patch_key]

    # Stitch tiles into a Web-Mercator canvas
    cols = tx1 - tx0 + 1
    rows = ty1 - ty0 + 1
    canvas = Image.new("RGB", (cols * _TILE_PX, rows * _TILE_PX))

    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = _get_tile(z, tx, ty)
            if tile is None:
                print(f"[tiles] ({z},{tx},{ty}) unavailable — falling back to Blue Marble")
                return None  # fall back to Blue Marble
            canvas.paste(tile, ((tx - tx0) * _TILE_PX, (ty - ty0) * _TILE_PX))

    canvas_arr = np.asarray(canvas)
    h_px, w_px = canvas_arr.shape[:2]

    # Geographic bounds of the stitched canvas
    c_lat_max = _ty_to_lat(ty0, n)       # north edge
    c_lat_min = _ty_to_lat(ty1 + 1, n)  # south edge
    c_lon_min = tx0 / n * 360.0 - 180.0
    c_lon_max = (tx1 + 1) / n * 360.0 - 180.0

    # Reproject Mercator → equirectangular by remapping rows.
    # Each equirectangular row corresponds to a constant latitude;
    # find its row in the Mercator canvas and copy it.
    # Longitude (x) is linear in both projections — no column remapping needed.
    eq_lats = np.linspace(c_lat_max, c_lat_min, h_px)
    merc_ys = _lat_to_ty_arr(eq_lats, n)
    merc_pys = np.clip(
        ((merc_ys - ty0) * _TILE_PX).astype(np.int32), 0, h_px - 1
    )
    equirect = canvas_arr[merc_pys]  # (h_px, w_px, 3)

    result = (equirect, c_lat_min, c_lat_max, c_lon_min, c_lon_max)
    _PATCH_MEM[patch_key] = result
    return result
