# Earth Trip Visualizer

Generate cinematic 9:16 Instagram Stories videos of travel routes on a 3D globe — like Google Earth, but as a video for social media.

## Features

- Input any number of cities with transport mode between each stop
- Smooth globe fly-through with great-circle arc animations
- City pins with country flags and names
- Transport badges (✈ Plane, 🚂 Train, 🚌 Bus, 🚗 Car, ⛴ Ship)
- 2-second pause at each city to read location
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

1. In the **JOURNEY** panel, enter your starting city
2. Select a transport mode and add the next city
3. Repeat for all stops (minimum 2 cities)
4. Click **🎬 Generate Video**
5. Watch the progress — rendering takes ~1–3 minutes depending on cities
6. The video plays automatically when ready
7. Click **⬇ Download** to save the MP4

## Output

- Format: MP4 (H.264)
- Resolution: 1080×1920 (9:16, Instagram Stories)
- Frame rate: 30 fps
- Codec: libx264, CRF 22

## Tech Stack

- **GUI** — PyQt6
- **Globe rendering** — Pure NumPy orthographic projection with NASA Blue Marble texture
- **Overlays** — Pillow (PIL)
- **Video encoding** — ffmpeg via subprocess pipe
- **Geocoding** — geopy + Nominatim (no API key needed)
- **Flags** — flagcdn.com (cached locally)
