import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from earth_trip.core.geocoder import CityInfo
from earth_trip.utils.geo import slerp_path, haversine_distance
from earth_trip.utils.easing import ease_in_out_cubic, ease_out_quad, lerp, log_lerp

FPS = 30
CITY_PAUSE_SEC = 2.0
TRANSITION_SEC = 4.5
INTRO_SEC = 1.5

GLOBE_R_NORMAL = 520       # full-globe view for intro reveal
GLOBE_R_ZOOM_MAX = 20000   # tightest city pause zoom (very close cities, ~170 km view)
GLOBE_R_ZOOM_MIN = 3500    # widest city pause zoom (very far cities, ~960 km view)

# Screen half-dimensions — must match renderer W=1080, H=1920
_HALF_W = 540.0
_HALF_H = 960.0
_ZOOM_MARGIN = 0.85   # keep arc endpoints 15% from screen edge

# Distance scale for adaptive zoom (fallback when bbox unavailable)
_D_MIN_KM = 100.0     # ≤ this → GLOBE_R_ZOOM_MAX
_D_MAX_KM = 10000.0   # ≥ this → GLOBE_R_ZOOM_MIN

# Bbox-based zoom: city bbox fills this fraction of screen half-width
_BBOX_SCREEN_MARGIN = 1.0        # bbox half-diagonal fills _HALF_W / margin pixels
_BBOX_GLOBE_R_MAX = 300_000      # tightest zoom for very small administrative areas
_BBOX_MAX_DIAGONAL_KM = 200.0    # bboxes larger than this span admin territories, not the urban footprint
_CITY_DEFAULT_GR = 80_000        # fallback for oversized admin bboxes (~107 km view — good for megacities)

TRANSPORT_LABELS = {
    "plane": "plane",
    "train": "train",
    "bus":   "bus",
    "car":   "car",
    "ship":  "ship",
}


@dataclass
class CityVisible:
    city: CityInfo
    opacity: float


@dataclass
class FrameSpec:
    central_lon: float
    central_lat: float
    cities_visible: list[CityVisible]
    arc_lats: Optional[np.ndarray]
    arc_lons: Optional[np.ndarray]
    arc_progress: float          # 0-1, fraction of arc to draw
    transport_label: Optional[str]
    fade: float = 1.0            # overall frame fade (intro)
    globe_r: float = float(GLOBE_R_NORMAL)  # zoom level in pixels


# ── Adaptive zoom helpers ──────────────────────────────────────────────────

def _adaptive_city_globe_r(min_dist_km: float) -> float:
    """
    Globe radius for a city pause based on the shortest adjacent leg distance.
    Logarithmically interpolates between GLOBE_R_ZOOM_MAX (close cities) and
    GLOBE_R_ZOOM_MIN (far cities).
    """
    t = (math.log(max(min_dist_km, _D_MIN_KM)) - math.log(_D_MIN_KM)) / (
        math.log(_D_MAX_KM) - math.log(_D_MIN_KM)
    )
    t = max(0.0, min(1.0, t))
    log_r = math.log(GLOBE_R_ZOOM_MAX) * (1.0 - t) + math.log(GLOBE_R_ZOOM_MIN) * t
    return math.exp(log_r)


def _bbox_diagonal_km(bbox: tuple[float, float, float, float]) -> float:
    south, north, west, east = bbox
    lat_km = (north - south) * 111.32
    lon_km = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
    return math.sqrt(lat_km ** 2 + lon_km ** 2)


def _city_globe_r_from_bbox(diagonal_km: float) -> float:
    # globe_r so the city bbox half-diagonal spans (_HALF_W / _BBOX_SCREEN_MARGIN) pixels
    half_diag = max(diagonal_km / 2.0, 2.0)
    globe_r = (_HALF_W / _BBOX_SCREEN_MARGIN) * 6371.0 / half_diag
    return max(float(GLOBE_R_ZOOM_MIN), min(float(_BBOX_GLOBE_R_MAX), globe_r))


def _compute_city_globe_rs(cities: list[CityInfo]) -> list[float]:
    result = []
    for i, city in enumerate(cities):
        if city.bbox is not None:
            diag = _bbox_diagonal_km(city.bbox)
            if diag <= _BBOX_MAX_DIAGONAL_KM:
                result.append(_city_globe_r_from_bbox(diag))
            else:
                result.append(float(_CITY_DEFAULT_GR))  # admin bbox too large (e.g. Tokyo's island territories)
        else:
            dists = []
            if i > 0:
                dists.append(haversine_distance(cities[i - 1].lat, cities[i - 1].lon, city.lat, city.lon))
            if i < len(cities) - 1:
                dists.append(haversine_distance(city.lat, city.lon, cities[i + 1].lat, cities[i + 1].lon))
            result.append(_adaptive_city_globe_r(min(dists) if dists else 5000.0))
    return result


# ── Orthographic projection helpers (pure math, called per frame) ──────────

def _proj_normalized(
    lat_deg: float, lon_deg: float,
    cam_lon_deg: float, cam_lat_deg: float,
) -> tuple[float, float] | None:
    """Normalized screen coords (independent of globe_r). Returns (sx, sy) or None if behind globe."""
    clon = math.radians(cam_lon_deg)
    clat = math.radians(cam_lat_deg)
    sc, cc = math.sin(clon), math.cos(clon)
    sl, cl = math.sin(clat), math.cos(clat)
    ex = (-sc, cc, 0.0)
    ey = (-sl * cc, -sl * sc, cl)
    ez = (cl * cc, cl * sc, sl)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    px = math.cos(lat) * math.cos(lon)
    py = math.cos(lat) * math.sin(lon)
    pz = math.sin(lat)
    depth = px * ez[0] + py * ez[1] + pz * ez[2]
    if depth <= 0:
        return None
    return (px * ex[0] + py * ex[1] + pz * ex[2],
            px * ey[0] + py * ey[1] + pz * ey[2])


def _globe_r_to_fit(*norm_coords: tuple[float, float] | None, cap: float) -> float:
    """Maximum globe_r that keeps all points on screen, capped at `cap`."""
    limits: list[float] = []
    for coords in norm_coords:
        if coords is None:
            continue
        sx, sy = coords
        if abs(sx) > 1e-6:
            limits.append(_HALF_W / abs(sx))
        if abs(sy) > 1e-6:
            limits.append(_HALF_H / abs(sy))
    if not limits:
        return cap
    return min(min(limits) * _ZOOM_MARGIN, cap)


def _transition_globe_r(
    city_a: CityInfo,
    arc_lats: np.ndarray,
    arc_lons: np.ndarray,
    arc_progress: float,
    cam_lat: float,
    cam_lon: float,
    cap: float,
) -> float:
    """
    Globe radius for one transition frame.

    Always fits city_a (origin) + arc tip in view. The destination is never
    considered during the transition — it is revealed only at the arrival pause.
    """
    tip_idx = min(int(arc_progress * len(arc_lats)), len(arc_lats) - 1)
    s_tip = _proj_normalized(float(arc_lats[tip_idx]), float(arc_lons[tip_idx]), cam_lon, cam_lat)
    s_anchor = _proj_normalized(city_a.lat, city_a.lon, cam_lon, cam_lat)
    return _globe_r_to_fit(s_anchor, s_tip, cap=cap)


# ── Frame builders ─────────────────────────────────────────────────────────

def _pause_frames(
    city: CityInfo,
    n: int,
    arc_lats=None,
    arc_lons=None,
    arc_progress: float = 0.0,
    globe_r: float = float(GLOBE_R_ZOOM_MIN),
    also_visible: list[CityInfo] | None = None,
) -> list[FrameSpec]:
    cities_visible = [CityVisible(city, 1.0)] + [CityVisible(c, 1.0) for c in (also_visible or [])]
    return [
        FrameSpec(
            central_lon=city.lon,
            central_lat=city.lat,
            cities_visible=cities_visible,
            arc_lats=arc_lats,
            arc_lons=arc_lons,
            arc_progress=arc_progress,
            transport_label=None,
            globe_r=globe_r,
        )
        for _ in range(n)
    ]


def build_frame_specs(
    cities: list[CityInfo],
    transports: list[str],
    city_pause_secs: list[float] | None = None,
    transition_secs: list[float] | None = None,
) -> list[FrameSpec]:
    frames: list[FrameSpec] = []

    def city_pause_n(idx: int) -> int:
        sec = city_pause_secs[idx] if city_pause_secs else CITY_PAUSE_SEC
        return max(1, int(sec * FPS))

    def transition_n(idx: int) -> int:
        sec = transition_secs[idx] if transition_secs else TRANSITION_SEC
        return max(2, int(sec * FPS))

    # Per-city adaptive zoom based on adjacent trip distances
    city_globe_rs = _compute_city_globe_rs(cities)

    # ── Intro: fade in + zoom from full globe to first city level ──────────
    intro_n = int(INTRO_SEC * FPS)
    first = cities[0]
    for i in range(intro_n):
        t = i / max(intro_n - 1, 1)
        zoom_t = ease_in_out_cubic(t)
        frames.append(FrameSpec(
            central_lon=first.lon,
            central_lat=first.lat,
            cities_visible=[CityVisible(first, ease_out_quad(t))],
            arc_lats=None, arc_lons=None, arc_progress=0.0,
            transport_label=None,
            fade=ease_out_quad(t),
            globe_r=log_lerp(float(GLOBE_R_NORMAL), city_globe_rs[0], zoom_t),
        ))

    # ── First city pause ────────────────────────────────────────────────────
    frames.extend(_pause_frames(first, city_pause_n(0), globe_r=city_globe_rs[0]))

    # ── Legs ────────────────────────────────────────────────────────────────
    for idx, transport in enumerate(transports):
        city_a = cities[idx]
        city_b = cities[idx + 1]
        label = TRANSPORT_LABELS.get(transport, transport.title())

        arc_lats, arc_lons = slerp_path(city_a.lat, city_a.lon, city_b.lat, city_b.lon, 200)

        city_a_gr = city_globe_rs[idx]
        total = transition_n(idx)

        for i in range(total):
            t = i / max(total - 1, 1)
            te = ease_in_out_cubic(t)

            # Camera follows the arc tip — correct for all routes including antimeridian
            tip_idx = min(int(te * len(arc_lats)), len(arc_lats) - 1)
            cam_lat = float(arc_lats[tip_idx])
            cam_lon = float(arc_lons[tip_idx])

            # Cap at departure city zoom — destination not revealed until arrival
            cap = city_a_gr

            # Geometry-driven zoom: keep origin + arc tip in view (destination hidden)
            globe_r = _transition_globe_r(
                city_a, arc_lats, arc_lons, te, cam_lat, cam_lon, cap=cap,
            )

            frames.append(FrameSpec(
                central_lon=cam_lon,
                central_lat=cam_lat,
                cities_visible=[CityVisible(city_a, 1.0)],
                arc_lats=arc_lats,
                arc_lons=arc_lons,
                arc_progress=te,
                transport_label=label,
                globe_r=globe_r,
            ))

        # Arrival: split city pause into route-overview zoom + urban hold
        s_origin_from_dest = _proj_normalized(city_a.lat, city_a.lon, city_b.lon, city_b.lat)
        arrival_gr = _globe_r_to_fit(s_origin_from_dest, cap=city_a_gr)
        city_b_gr = city_globe_rs[idx + 1]

        n = city_pause_n(idx + 1)
        zoom_n = max(2, min(int(FPS * 1.0), n // 3))  # up to 1s, at most 1/3 of pause
        hold_n = n - zoom_n

        # Zoom from route-overview into destination's urban radius
        for i in range(zoom_n):
            t = ease_in_out_cubic(i / max(zoom_n - 1, 1))
            frames.append(FrameSpec(
                central_lon=city_b.lon,
                central_lat=city_b.lat,
                cities_visible=[CityVisible(city_b, 1.0), CityVisible(city_a, 1.0)],
                arc_lats=arc_lats, arc_lons=arc_lons, arc_progress=1.0,
                transport_label=None,
                globe_r=log_lerp(arrival_gr, city_b_gr, t),
            ))

        # Hold at urban zoom for remainder of city pause
        frames.extend(_pause_frames(
            city_b, hold_n,
            arc_lats=arc_lats, arc_lons=arc_lons, arc_progress=1.0,
            globe_r=city_b_gr,
            also_visible=[city_a],
        ))

    return frames
