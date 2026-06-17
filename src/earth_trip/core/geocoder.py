import time
from dataclasses import dataclass

import pycountry
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

from earth_trip.core.cache import load_geocode_cache, save_geocode_cache

_geolocator = Nominatim(user_agent="earth-trip-visualizer/0.1")
_cache: dict | None = None
_MIN_DELAY = 1.1  # Nominatim rate limit: 1 req/sec


@dataclass
class CityInfo:
    name: str
    display_name: str
    lat: float
    lon: float
    country_code: str
    country_name: str


def _get_cache() -> dict:
    global _cache
    if _cache is None:
        _cache = load_geocode_cache()
    return _cache


def _country_name(code: str) -> str:
    try:
        return pycountry.countries.get(alpha_2=code.upper()).name
    except Exception:
        return code


def geocode_city(name: str) -> CityInfo | None:
    cache = _get_cache()
    key = name.strip().lower()

    if key in cache:
        d = cache[key]
        return CityInfo(**d)

    time.sleep(_MIN_DELAY)
    try:
        loc = _geolocator.geocode(name, language="en", addressdetails=True, timeout=10)
    except (GeocoderTimedOut, GeocoderUnavailable):
        return None

    if loc is None:
        return None

    addr = loc.raw.get("address", {})
    cc = addr.get("country_code", "").upper()
    country = _country_name(cc) if cc else addr.get("country", "Unknown")
    city_label = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or name
    )

    info = CityInfo(
        name=city_label,
        display_name=loc.address.split(",")[0],
        lat=float(loc.latitude),
        lon=float(loc.longitude),
        country_code=cc,
        country_name=country,
    )

    cache[key] = {
        "name": info.name,
        "display_name": info.display_name,
        "lat": info.lat,
        "lon": info.lon,
        "country_code": info.country_code,
        "country_name": info.country_name,
    }
    save_geocode_cache(cache)
    return info
