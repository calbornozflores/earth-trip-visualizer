import json
from pathlib import Path
from platformdirs import user_cache_dir

_CACHE_DIR = Path(user_cache_dir("earth-trip-visualizer"))


def _geocode_file() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "geocode.json"


def _flags_dir() -> Path:
    d = _CACHE_DIR / "flags"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_geocode_cache() -> dict:
    f = _geocode_file()
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return {}
    return {}


def save_geocode_cache(data: dict) -> None:
    _geocode_file().write_text(json.dumps(data, ensure_ascii=False, indent=2))


def get_flag_path(country_code: str) -> Path | None:
    p = _flags_dir() / f"{country_code.lower()}.png"
    return p if p.exists() else None


def save_flag(country_code: str, data: bytes) -> Path:
    p = _flags_dir() / f"{country_code.lower()}.png"
    p.write_bytes(data)
    return p
