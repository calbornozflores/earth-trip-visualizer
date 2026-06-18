# Earth Trip Visualizer

Generate cinematic 9:16 Instagram Stories videos of travel routes on a 3D globe — like Google Earth, but as a video for social media.

## Features

- Input any number of cities with transport mode between each stop
- **City autocomplete** — type a few letters and pick from ~300 world cities
- Smooth globe fly-through with great-circle arc animations (correct for all routes, including cross-Pacific and antimeridian crossings)
- **HD satellite imagery** — ESRI World Imagery tiles at city zoom level; NASA Blue Marble for overview
- **Adaptive city zoom** — camera zooms in closer for nearby cities, wider for distant ones
- **Transport emoji on the arc** — the plane/train/bus/car/ship icon travels along the route as the transition plays (no text, just the icon)
- City pins with country flags and names
- **Configurable timing** — set pause duration per city (⏱) and transition duration per leg (↔) directly in the UI
- Built-in video player with play/pause/seek/download
- Dark, social-media-ready UI

## Requirements

- macOS (also works on Linux/Windows with minor path adjustments)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [ffmpeg](https://ffmpeg.org/) — video encoding

## Setup

```bash
# Install prerequisites
brew install ffmpeg

# Clone and enter the project
git clone https://github.com/calbornozflores/earth-trip-visualizer.git
cd earth-trip-visualizer

# Install Python dependencies
uv sync

# Download Earth texture (~2.4 MB, one-time)
uv run python scripts/download_assets.py

# Launch the app
uv run earth-trip
```

## Usage

1. In the **JOURNEY** panel, start typing a city name — suggestions appear automatically
2. Adjust the **⏱** spinbox to set how long to pause there (default 2 s)
3. Select a transport mode (plane, train, bus, car, ship) and set the **↔** spinbox for the transition duration (default 4.5 s)
4. Add the next city and repeat for all stops (minimum 2 cities)
5. Click **🎬 Generate Video**
6. Watch the progress — rendering takes ~1–3 minutes depending on cities and zoom
7. The video plays automatically when ready
8. Click **⬇ Download** to save the MP4

## Output

- Format: MP4 (H.264)
- Resolution: 1080×1920 (9:16, Instagram Stories / TikTok / Reels)
- Frame rate: 30 fps
- Codec: libx264, CRF 22

## Tech Stack

- **GUI** — PyQt6
- **Globe rendering** — Pure NumPy orthographic projection
- **Globe texture (overview)** — NASA Blue Marble equirectangular texture
- **Satellite imagery (zoomed)** — ESRI World Imagery Web Mercator tiles, reprojected to equirectangular
- **Transport icons** — Twemoji PNG (CC BY 4.0), rendered at the moving arc tip
- **Overlays** — Pillow (PIL)
- **Video encoding** — ffmpeg via subprocess pipe
- **Geocoding** — geopy + Nominatim (no API key needed)
- **Flags** — flagcdn.com (cached locally)

## Cache

On first use the app downloads satellite tiles and transport icons and caches them locally:

| Path | Contents |
|---|---|
| `~/.cache/earth-trip-visualizer/tiles/` | ESRI satellite tiles (JPEG) |
| `~/.cache/earth-trip-visualizer/icons/` | Twemoji transport icons (PNG) |
| `~/.cache/earth-trip-visualizer/flags/` | Country flag images (PNG) |
| `~/.cache/earth-trip-visualizer/geocode.json` | Geocoding results |

All caches are persistent — subsequent runs are fast.
