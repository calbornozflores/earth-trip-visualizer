import math
import numpy as np


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two lat/lon points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _to_cart(lat_deg: float, lon_deg: float) -> np.ndarray:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    return np.array([
        math.cos(lat) * math.cos(lon),
        math.cos(lat) * math.sin(lon),
        math.sin(lat),
    ])


def _from_cart(v: np.ndarray) -> tuple[float, float]:
    lat = math.degrees(math.asin(float(np.clip(v[2], -1, 1))))
    lon = math.degrees(math.atan2(float(v[1]), float(v[0])))
    return lat, lon


def slerp_path(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    n: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (lats, lons) arrays of n evenly-spaced points along the great circle."""
    v1 = _to_cart(lat1, lon1)
    v2 = _to_cart(lat2, lon2)

    dot = float(np.clip(np.dot(v1, v2), -1.0, 1.0))
    omega = math.acos(dot)

    lats = np.empty(n)
    lons = np.empty(n)

    if omega < 1e-10:
        lats[:] = lat1
        lons[:] = lon1
        return lats, lons

    ts = np.linspace(0.0, 1.0, n)
    for i, t in enumerate(ts):
        v = (math.sin((1 - t) * omega) * v1 + math.sin(t * omega) * v2) / math.sin(omega)
        lats[i], lons[i] = _from_cart(v)

    return lats, lons


def great_circle_midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float]:
    """Midpoint along the great circle."""
    v1 = _to_cart(lat1, lon1)
    v2 = _to_cart(lat2, lon2)
    mid = v1 + v2
    norm = np.linalg.norm(mid)
    if norm < 1e-10:
        return 0.0, 0.0
    mid /= norm
    return _from_cart(mid)
