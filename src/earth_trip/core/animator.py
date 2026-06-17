from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from earth_trip.core.geocoder import CityInfo
from earth_trip.utils.geo import slerp_path, great_circle_midpoint
from earth_trip.utils.easing import ease_in_out_cubic, ease_out_quad, lerp

FPS = 30
CITY_PAUSE_SEC = 2.0
TRANSITION_SEC = 4.5
INTRO_SEC = 1.5

TRANSPORT_LABELS = {
    "plane": "✈  Plane",
    "train": "🚂  Train",
    "bus": "🚌  Bus",
    "car": "🚗  Car",
    "ship": "⛴  Ship",
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


def _pause_frames(city: CityInfo, n: int, arc_lats=None, arc_lons=None, arc_progress=0.0) -> list[FrameSpec]:
    return [
        FrameSpec(
            central_lon=city.lon,
            central_lat=city.lat,
            cities_visible=[CityVisible(city, 1.0)],
            arc_lats=arc_lats,
            arc_lons=arc_lons,
            arc_progress=arc_progress,
            transport_label=None,
        )
        for _ in range(n)
    ]


def build_frame_specs(cities: list[CityInfo], transports: list[str]) -> list[FrameSpec]:
    frames: list[FrameSpec] = []

    # ── Intro: fade in on first city ───────────────────────────────────────
    intro_n = int(INTRO_SEC * FPS)
    first = cities[0]
    for i in range(intro_n):
        t = i / max(intro_n - 1, 1)
        frames.append(FrameSpec(
            central_lon=first.lon,
            central_lat=first.lat,
            cities_visible=[CityVisible(first, ease_out_quad(t))],
            arc_lats=None, arc_lons=None, arc_progress=0.0,
            transport_label=None,
            fade=ease_out_quad(t),
        ))

    # ── First city pause ───────────────────────────────────────────────────
    frames.extend(_pause_frames(first, int(CITY_PAUSE_SEC * FPS)))

    # ── Legs ───────────────────────────────────────────────────────────────
    for idx, transport in enumerate(transports):
        city_a = cities[idx]
        city_b = cities[idx + 1]
        label = TRANSPORT_LABELS.get(transport, transport.title())

        # Pre-compute great circle path (200 intermediate points)
        arc_lats, arc_lons = slerp_path(city_a.lat, city_a.lon, city_b.lat, city_b.lon, 200)
        mid_lat, mid_lon = great_circle_midpoint(city_a.lat, city_a.lon, city_b.lat, city_b.lon)

        total = int(TRANSITION_SEC * FPS)
        for i in range(total):
            t = i / max(total - 1, 1)
            te = ease_in_out_cubic(t)

            # Camera: move through midpoint
            if t <= 0.5:
                sub = t * 2.0
                cam_lat = lerp(city_a.lat, mid_lat, ease_in_out_cubic(sub))
                cam_lon = lerp(city_a.lon, mid_lon, ease_in_out_cubic(sub))
            else:
                sub = (t - 0.5) * 2.0
                cam_lat = lerp(mid_lat, city_b.lat, ease_in_out_cubic(sub))
                cam_lon = lerp(mid_lon, city_b.lon, ease_in_out_cubic(sub))

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
            ))

        # Arrival pause (keep full arc visible)
        frames.extend(_pause_frames(city_b, int(CITY_PAUSE_SEC * FPS),
                                    arc_lats=arc_lats, arc_lons=arc_lons, arc_progress=1.0))

    return frames
