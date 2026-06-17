#!/usr/bin/env python3
"""Download required assets for Earth Trip Visualizer."""
import sys
import urllib.request
from pathlib import Path

ASSETS = Path(__file__).parent.parent / "src" / "earth_trip" / "assets"
TEXTURE_URL = (
    "https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/"
    "world.topo.bathy.200412.3x5400x2700.jpg"
)
TEXTURE_PATH = ASSETS / "earth_texture.jpg"


def download(url: str, dest: Path, label: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  ✓  {label} already exists ({dest.stat().st_size // 1024} KB)")
        return

    print(f"  ↓  Downloading {label}…", end="", flush=True)

    def reporthook(block, block_size, total):
        if total > 0:
            pct = min(100, int(block * block_size / total * 100))
            print(f"\r  ↓  Downloading {label}… {pct}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, dest, reporthook=reporthook)
        print(f"\r  ✓  {label} saved ({dest.stat().st_size // 1024} KB)")
    except Exception as e:
        print(f"\n  ✗  Failed to download {label}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("Earth Trip Visualizer — Asset Downloader")
    print("─" * 45)
    download(TEXTURE_URL, TEXTURE_PATH, "NASA Blue Marble Earth texture")
    print("\nAll assets ready. Run the app with:\n  uv run earth-trip\n")
