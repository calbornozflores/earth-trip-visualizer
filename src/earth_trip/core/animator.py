import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from earth_trip.core.geocoder import CityInfo
from earth_trip.utils.geo import slerp_path, haversine_distance
from earth_trip.utils.easing import ease_in_out_cubic, ease_out_quad, lerp

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

# Distance scale for adaptive zoom
_D_MIN_KM = 100.0     # ≤ this → GLOBE_R_ZOOM_MAX
_D_MAX_KM = 10000.0   # ≥ this → GLOBE_R_ZOOM_MIN

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


def _compute_city_globe_rs(cities: list[CityInfo]) -> list[float]:
    result = []
    for i, city in enumerate(cities):
        dists = []
        if i > 0:
            dists.append(haversine_distance(cities[i - 1].lat, cities[i - 1].lon, city.lat, city.lon))
        if i < len(cities) - 1:
            dists.append(haversine_distance(city.lat, city.lon, cities[i + 1].lat, cities[i + 1].lon))
        min_dist = min(dists) if dists else 5000.0
        result.append(_adaptive_city_globe_r(min_dist))
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
    city_b: CityInfo,
    arc_lats: np.ndarray,
    arc_lons: np.ndarray,
    arc_progress: float,
    cam_lat: float,
    cam_lon: float,
    cap: float,
) -> float:
    """
    Globe radius for one transition frame.

    First half  (arc_progress ≤ 0.5): fit city_a (arc start) + arc tip.
    Second half (arc_progress > 0.5): fit arc tip + city_b (destination).

    At arc_progress = 0 and 1, tip ≈ camera ≈ city endpoint → no geometry
    constraint → globe_r = cap, seamlessly matching the city pause zoom.
    """
    tip_idx = min(int(arc_progress * len(arc_lats)), len(arc_lats) - 1)
    s_tip = _proj_normalized(float(arc_lats[tip_idx]), float(arc_lons[tip_idx]), cam_lon, cam_lat)

    if arc_progress <= 0.5:
        s_anchor = _proj_normalized(city_a.lat, city_a.lon, cam_lon, cam_lat)
    else:
        s_anchor = _proj_normalized(city_b.lat, city_b.lon, cam_lon, cam_lat)

    return _globe_r_to_fit(s_anchor, s_tip, cap=cap)


# ── Frame builders ─────────────────────────────────────────────────────────

def _pause_frames(
    city: CityInfo,
    n: int,
    arc_lats=None,
    arc_lons=None,
    arc_progress: float = 0.0,
    globe_r: float = float(GLOBE_R_ZOOM_MIN),
) -> list[FrameSpec]:
    return [
        FrameSpec(
            central_lon=city.lon,
            central_lat=city.lat,
            cities_visible=[CityVisible(city, 1.0)],
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
            globe_r=lerp(float(GLOBE_R_NORMAL), city_globe_rs[0], zoom_t),
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
        city_b_gr = city_globe_rs[idx + 1]
        total = transition_n(idx)

        for i in range(total):
            t = i / max(total - 1, 1)
            te = ease_in_out_cubic(t)

            # Camera follows the arc tip — correct for all routes including antimeridian
            tip_idx = min(int(te * len(arc_lats)), len(arc_lats) - 1)
            cam_lat = float(arc_lats[tip_idx])
            cam_lon = float(arc_lons[tip_idx])

            # Zoom cap lerps between city zoom levels so endpoints are seamless
            cap = lerp(city_a_gr, city_b_gr, t)

            # Geometry-driven zoom: minimum to keep drawn arc visible
            globe_r = _transition_globe_r(
                city_a, city_b, arc_lats, arc_lons, te, cam_lat, cam_lon, cap=cap,
            )

            # Opacity: city_b fades in over second half
            b_opacity = ease_out_quad(max(0.0, (t - 0.3) / 0.7))

            frames.append(FrameSpec(
                central_lon=cam_lon,
                central_lat=cam_lat,
                cities_visible=[
                    CityVisible(city_a, 1.0),
                    CityVisible(city_b, b_opacity),
                ],
                arc_lats=arc_lats,
                arc_lons=arc_lons,
                arc_progress=te,
                transport_label=label,
                globe_r=globe_r,
            ))

        # Arrival pause (zoomed in on destination)
        frames.extend(_pause_frames(
            city_b, city_pause_n(idx + 1),
            arc_lats=arc_lats, arc_lons=arc_lons, arc_progress=1.0,
            globe_r=city_b_gr,
        ))

    return frames
