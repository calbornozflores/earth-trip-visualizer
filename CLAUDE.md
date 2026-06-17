# Earth Trip Visualizer — Claude Context

## What this project is

A PyQt6 desktop app that takes a list of cities and transport modes, then renders a cinematic 9:16 (1080×1920) Instagram Stories MP4 showing a Google-Earth-style fly-through on a 3D globe. Each city gets a configurable pause (default 2 s) with a glowing pin, country flag, and city name — shown zoomed in from the sky (~1700 km view). Transitions animate a great-circle dotted arc with a transport badge; transition duration is also configurable per leg (default 4.5 s).

GitHub: https://github.com/calbornozflores/earth-trip-visualizer

---

## Running

```bash
# One-time setup
brew install ffmpeg
uv sync
uv run python scripts/download_assets.py   # downloads NASA Blue Marble (~2.4 MB)

# Launch
uv run earth-trip
```

The app opens immediately. Pre-filled with Paris → Tokyo via Plane. Click **Generate Video** to produce a video.

---

## Architecture

```
src/earth_trip/
├── main.py                 # QApplication entry, ffmpeg presence check
├── core/
│   ├── renderer.py         # GlobeRenderer — THE core visual engine
│   ├── animator.py         # build_frame_specs() — pure data, no rendering
│   ├── video_builder.py    # ffmpeg pipe encoder
│   ├── geocoder.py         # geocode_city() → CityInfo, Nominatim + cache
│   ├── cache.py            # platformdirs-based JSON/PNG cache
│   └── worker.py           # GenerationWorker(QThread) — runs geocode+render+encode
├── ui/
│   ├── main_window.py      # QMainWindow, dark stylesheet, splitter layout
│   ├── city_panel.py       # Left panel: CityItem list + Generate button
│   ├── city_item.py        # Single city row widget + TransportSelector
│   └── player_panel.py     # Right panel: QMediaPlayer + seek/play/download controls
└── utils/
    ├── geo.py              # slerp_path(), great_circle_midpoint(), haversine_distance()
    └── easing.py           # ease_in_out_cubic(), ease_out_quad(), lerp(), smoothstep()
```

---

## Globe rendering (renderer.py — the most important file)

**No Cartopy, no matplotlib.** The globe is rendered with pure numpy vectorized orthographic projection against the NASA Blue Marble equirectangular texture. ~100ms/frame on Apple Silicon.

### Projection math

Camera basis vectors for a viewer at `(clon, clat)`:
```python
ex = [-sin(clon), cos(clon), 0]                              # screen-right
ey = [-sin(clat)*cos(clon), -sin(clat)*sin(clon), cos(clat)] # screen-up
ez = [cos(clat)*cos(clon),  cos(clat)*sin(clon),  sin(clat)] # toward viewer
```

**Inverse projection** (pixel → Earth texture sample, vectorized over all 1080×1920 pixels):
1. Normalize pixel offset from center by `globe_r` → `(sx, sy)`
2. Visibility: `sx² + sy² ≤ 1`; compute `sz = sqrt(1 - sx² - sy²)`
3. World 3D: `(x3, y3, z3) = sx·ex + sy·ey + sz·ez`
4. `lat = arcsin(z3)`, `lon = arctan2(y3, x3)`
5. Sample equirectangular texture: `src_x = (lon+π)/(2π) * src_w`

**Forward projection** (`geo_to_pixel`) — geographic coords → pixel:
1. Convert `(lat, lon)` to 3D Cartesian `p`
2. `depth = dot(p, ez)` — if negative, point is on far hemisphere → return None
3. `px = CX + dot(p, ex) * globe_r`, `py = CY - dot(p, ey) * globe_r`

`globe_r` is a per-frame value from `FrameSpec.globe_r`. Larger values zoom in (fewer degrees visible). `GLOBE_R = 520` is the normal full-globe constant; `GLOBE_R_ZOOMED = 4000` is the city-pause zoom level.

### Two-phase rendering per frame

1. **Globe base** (`_get_globe_frame(clon, clat, globe_r)`): numpy projection → cached by `(round(lon,1), round(lat,1), round(globe_r,-1))`. Globe mask is also cached per `globe_r` via `_get_globe_mask()`.
2. **PIL compositing**: atmosphere glow RGBA overlay (skipped when zoomed) → arc dashes → city glow rings → flag image paste → text labels → transport badge pill.

### Key constants
- `W, H = 1080, 1920` — output dimensions (9:16)
- `CX, CY = 540, 960` — globe center pixel
- `GLOBE_R = 520` — normal full-globe radius in pixels (renderer.py)
- `GLOBE_R_NORMAL = 520`, `GLOBE_R_ZOOMED = 4000`, `ZOOM_RATIO = 0.15` — zoom constants (animator.py)
- `FPS = 30` in animator and video_builder

---

## Animation (animator.py)

`build_frame_specs(cities, transports, city_pause_secs=None, transition_secs=None) → list[FrameSpec]` — pure data, no I/O. Duration lists are per-city and per-leg; fall back to `CITY_PAUSE_SEC`/`TRANSITION_SEC` constants if None.

### Sequence per video
1. **Intro** (1.5s): fade-in + zoom in from full globe (`GLOBE_R_NORMAL`) to city level (`GLOBE_R_ZOOMED`), `ease_in_out_cubic`
2. **City pause** (configurable, default 2s): zoomed-in frame centred on city (`globe_r = GLOBE_R_ZOOMED`)
3. For each leg:
   - **Transition** (configurable, default 4.5s): first 15% zooms out to full globe, camera pans through great-circle midpoint with arc growth (`ease_in_out_cubic`), last 15% zooms into destination
   - **Arrival pause** (configurable): zoomed in on destination, full arc visible

### FrameSpec fields
```python
@dataclass
class FrameSpec:
    central_lon: float        # camera position
    central_lat: float
    cities_visible: list[CityVisible]   # (city, opacity 0-1)
    arc_lats: np.ndarray | None
    arc_lons: np.ndarray | None
    arc_progress: float       # 0-1 fraction of arc to draw
    transport_label: str | None  # e.g. "✈  Plane"
    fade: float = 1.0         # overall frame brightness (intro)
    globe_r: float = 520.0    # zoom level — GLOBE_R_NORMAL or GLOBE_R_ZOOMED or interpolated
```

---

## Video encoding (video_builder.py)

Pipes raw RGB24 frames to ffmpeg stdin → H.264 libx264 MP4, CRF 22, `yuv420p`, `+faststart`. Requires ffmpeg on PATH.

```python
cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
       "-s", "1080x1920", "-pix_fmt", "rgb24", "-r", "30", "-i", "pipe:0",
       "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
       "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]
```

Frame shape must be `(1920, 1080, 3)` uint8 RGB.

---

## Geocoding (geocoder.py)

Uses `geopy.geocoders.Nominatim` (no API key). Rate-limited to 1.1 req/sec. Results cached to `~/.cache/earth-trip-visualizer/geocode.json`. Country flags cached to `~/.cache/earth-trip-visualizer/flags/{cc}.png` from `flagcdn.com/48x32/{cc}.png`.

`CityInfo` dataclass: `name, display_name, lat, lon, country_code (ISO α-2), country_name`

---

## UI (PyQt6)

### Critical PyQt6 rules (already learned the hard way)
- Use `pyqtSignal`, **never** `Signal` (that's PySide6)
- **Do not use `@pyqtSlot` decorators** — they break on `qint64` media signals from `QMediaPlayer`. Plain methods connected via `.connect()` work fine.
- All enum paths must be fully qualified: `Qt.AlignmentFlag.AlignCenter`, `QSizePolicy.Policy.Expanding`, `QMediaPlayer.PlaybackState.PlayingState`
- `addStretch(n)` takes an `int`, not a Qt enum value

### Layout
- `QMainWindow` → `QSplitter(Horizontal)` → `[CityPanel(320px) | PlayerPanel]`
- Dark theme via single `_STYLESHEET` string in `main_window.py`
- All colours: bg `#0a0a0f`, accent `#4f9cf9`, purple `#8b5cf6`, text `#e2e8f0`, card `#1e293b`

### City panel structure
`_cities: list[CityItem]` and `_transports: list[TransportSelector]`, always `len(transports) == len(cities) - 1`. `_add_city()` and `_remove_city()` keep them in sync. Scroll area keeps items top-aligned via a trailing `addStretch(1)` that gets moved on every add.

Each `CityItem` has a `⏱` label + `QDoubleSpinBox#durationSpin` (0.5–10 s, default 2 s) for pause duration. Each `TransportSelector` has a `↔` label + `QDoubleSpinBox#durationSpin` (1–15 s, default 4.5 s) for transition duration. Both use object name `"durationSpin"` and are styled in `_STYLESHEET`.

### Generation flow
`CityPanel.generate_requested(names, transport_keys, city_pause_secs, transition_secs)` → `MainWindow._on_generate` → creates `GenerationWorker(QThread)` → modal `QProgressDialog` → on `finished(path)` → `PlayerPanel.load_video(path)` → `QMediaPlayer` auto-plays.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| PyQt6 | ≥6.6 | GUI + video player |
| numpy | ≥1.26 | Globe projection, frame math |
| pillow | ≥10.2 | Frame compositing (PIL) |
| geopy | ≥2.4 | City geocoding (Nominatim) |
| requests | ≥2.31 | Flag image downloads |
| pycountry | ≥23.12 | ISO country code → country name |
| platformdirs | ≥4.2 | Cross-platform cache directory |

**System requirement:** `ffmpeg` on PATH (`brew install ffmpeg`).

---

## Assets

- `src/earth_trip/assets/earth_texture.jpg` — NASA Blue Marble (5400×2700, ~2.4 MB). Downloaded by `scripts/download_assets.py`. **Not committed to git.**
- Country flags are fetched on first render and cached in `platformdirs` cache dir, not in the repo.
- No icon files — transport labels are Unicode text badges rendered in PIL.

---

## Performance

- **~100ms per unique globe position** on Apple Silicon M-series
- Globe cache keyed on `(round(lon,1), round(lat,1), round(globe_r,-1))` — city pause frames (all at `GLOBE_R_ZOOMED`) still cache well
- Typical 2-city video at defaults: ~300 frames → ~30 seconds render time
- Each additional city leg adds ~135 frames (~14 seconds) at default transition duration
- ffmpeg encoding adds ~2–5 seconds regardless of length

---

## Known issues / extension points

- **Transport emoji rendering**: PyQt6 on macOS may render emoji in the transport combo as arrows; this is a system font issue, display-only, doesn't affect output video
- **Geocoding failures**: Nominatim can be slow or return unexpected results for small towns — the geocode cache helps on retry
- **Font**: renderer uses system fonts (Helvetica/Arial on macOS); for a specific font, add a TTF to `assets/fonts/` and update `_load_font()` in `renderer.py`
- **Adding transports**: add entries to `TRANSPORT_LABELS` in `animator.py` and `TRANSPORTS` list in `city_item.py`
- **Changing video resolution**: change `W, H` in `renderer.py` and `-s` in `video_builder.py` together
