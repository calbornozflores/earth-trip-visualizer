# Earth Trip Visualizer — Claude Context

## What this project is

A PyQt6 desktop app that takes a list of cities and transport modes, then renders a cinematic 9:16 (1080×1920) Instagram Stories MP4 showing a Google-Earth-style fly-through on a 3D globe. Each city gets a configurable pause (default 2 s) with a glowing pin, country flag, and city name — shown zoomed in from the sky. Transitions animate a great-circle dotted arc; the transport emoji (Twemoji PNG) travels along the arc as it grows. Transition and pause durations are configurable per leg/city.

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
├── main.py                    # QApplication entry, ffmpeg presence check
├── core/
│   ├── renderer.py            # GlobeRenderer — THE core visual engine
│   ├── animator.py            # build_frame_specs() — pure data, no rendering
│   ├── tiles.py               # HD satellite tile fetching + Mercator→equirect reprojection
│   ├── video_builder.py       # ffmpeg pipe encoder
│   ├── geocoder.py            # geocode_city() → CityInfo, Nominatim + cache
│   ├── cache.py               # platformdirs-based JSON/PNG cache
│   └── worker.py              # GenerationWorker(QThread) — runs geocode+render+encode
├── ui/
│   ├── main_window.py         # QMainWindow, dark stylesheet, splitter layout
│   ├── city_panel.py          # Left panel: CityItem list + Generate button
│   ├── city_item.py           # Single city row widget + TransportSelector + QCompleter
│   ├── city_suggestions.py    # Bundled list of ~300 world cities for autocomplete
│   └── player_panel.py        # Right panel: QMediaPlayer + seek/play/download controls
└── utils/
    ├── geo.py              # slerp_path(), haversine_distance()
    └── easing.py           # ease_in_out_cubic(), ease_out_quad(), lerp(), smoothstep()
```

---

## Globe rendering (renderer.py — the most important file)

**No Cartopy, no matplotlib.** The globe is rendered with pure numpy vectorized orthographic projection. At low zoom (overview), it samples the NASA Blue Marble equirectangular texture. At high zoom (city pause or close-in transition), it fetches ESRI World Imagery satellite tiles and reprojects them.

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

`globe_r` is a per-frame value from `FrameSpec.globe_r`. Larger values zoom in.

### Satellite tile rendering (tiles.py)

When `globe_r > _TILE_MIN_R` (≈ 1040 px), `_get_globe_frame` uses ESRI World Imagery tiles instead of Blue Marble:

1. `_zoom_for(globe_r)` → `min(8, int(log2(0.02 * globe_r)))` — z=8 at globe_r≈16 160
2. `get_patch(center_lat, center_lon, globe_r)` — calculates visible lat/lon bounds with 15% margin, fetches/stitches Mercator tiles, reprojects rows to equirectangular via `canvas_arr[merc_pys]` row-remap
3. Tiles cached to disk at `~/.cache/earth-trip-visualizer/tiles/{z}_{x}_{y}.jpg` and in-memory
4. Blue Marble fallback for visible pixels outside the tile patch bounds

### Two-phase rendering per frame

1. **Globe base** (`_get_globe_frame(clon, clat, globe_r)`): numpy projection (Blue Marble or tile patch) → cached by `(round(lon,1), round(lat,1), round(globe_r,-1))`.
2. **PIL compositing**: atmosphere glow (skipped when zoomed) → arc dashes → city glow rings → flag image paste → text labels → transport emoji at arc tip.

### Transport icon on arc

During transitions, `render_frame` computes the arc tip pixel via `geo_to_pixel` and calls `_draw_transport_icon_at(img, key, px)`:
- 80×80 Twemoji PNG pasted at the arc tip, centered
- Soft dark shadow ellipse behind it for legibility
- Icon only — no text, no static badge

Icons are pre-downloaded (all 5 transport types) in `GlobeRenderer.__init__` and cached in `~/.cache/earth-trip-visualizer/icons/`. Source: jsDelivr CDN, Twemoji 14.0.2 (CC BY 4.0).

### Key constants
- `W, H = 1080, 1920` — output dimensions (9:16)
- `CX, CY = 540, 960` — globe center pixel
- `GLOBE_R = 520` — normal full-globe radius in pixels (renderer.py)
- `_TILE_MIN_R = GLOBE_R * 2.0` — threshold to switch Blue Marble → satellite tiles
- `GLOBE_R_NORMAL = 520`, `GLOBE_R_ZOOM_MAX = 20000`, `GLOBE_R_ZOOM_MIN = 3500` — zoom constants (animator.py)
- `FPS = 30` in animator and video_builder

---

## Animation (animator.py)

`build_frame_specs(cities, transports, city_pause_secs=None, transition_secs=None) → list[FrameSpec]` — pure data, no I/O.

### Sequence per video
1. **Intro** (1.5s): fade-in + zoom from full globe to first city
2. **City pause** (configurable, default 2s): zoomed in on city
3. For each leg:
   - **Transition** (configurable, default 4.5s): camera follows the great-circle slerp arc from city_a to city_b (arc tip = camera position — correct for all routes including antimeridian crossings). Zoom driven by geometry: keeps origin/destination in frame as long as visible.
   - **Arrival pause** (configurable): zoomed in on destination, full arc visible

### Camera motion — slerp arc tracking

The camera does NOT lerp lat/lon. It follows `arc_lats[tip_idx]` / `arc_lons[tip_idx]` where `tip_idx = min(int(te * len(arc_lats)), len(arc_lats)-1)`. This is correct for all routes — the arc is computed via `slerp_path()` which uses proper spherical linear interpolation.

### Adaptive city zoom

`_adaptive_city_globe_r(min_dist_km)` log-interpolates between `GLOBE_R_ZOOM_MAX` (20 000, for close cities) and `GLOBE_R_ZOOM_MIN` (3 500, for distant cities), keyed on the shortest adjacent leg distance.

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
    transport_label: str | None  # transport key e.g. "plane", "car"
    fade: float = 1.0         # overall frame brightness (intro)
    globe_r: float = 520.0    # zoom level — GLOBE_R_NORMAL or zoomed or interpolated
```

---

## Video encoding (video_builder.py)

Pipes raw RGB24 frames to ffmpeg stdin → H.264 libx264 MP4, CRF 22, `yuv420p`, `+faststart`.

```python
cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
       "-s", "1080x1920", "-pix_fmt", "rgb24", "-r", "30", "-i", "pipe:0",
       "-vcodec", "libx264", "-preset", "fast", "-crf", "22",
       "-pix_fmt", "yuv420p", "-movflags", "+faststart", output_path]
```

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
`_cities: list[CityItem]` and `_transports: list[TransportSelector]`, always `len(transports) == len(cities) - 1`. `_add_city()` and `_remove_city()` keep them in sync.

Each `CityItem` has:
- `QLineEdit` with `QCompleter` attached (substring match, case-insensitive) against `city_suggestions.CITIES` (~300 world cities)
- `⏱` label + `QDoubleSpinBox#durationSpin` (0.5–10 s, default 2 s) for pause duration

Each `TransportSelector` has:
- `QComboBox` (plane/train/bus/car/ship)
- `↔` label + `QDoubleSpinBox#durationSpin` (1–15 s, default 4.5 s) for transition duration

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
| requests | ≥2.31 | Flag + tile + icon downloads |
| pycountry | ≥23.12 | ISO country code → country name |
| platformdirs | ≥4.2 | Cross-platform cache directory |

**System requirement:** `ffmpeg` on PATH (`brew install ffmpeg`).

---

## Assets & cache

- `src/earth_trip/assets/earth_texture.jpg` — NASA Blue Marble (5400×2700, ~2.4 MB). Downloaded by `scripts/download_assets.py`. **Not committed to git.**
- `~/.cache/earth-trip-visualizer/tiles/{z}_{x}_{y}.jpg` — ESRI World Imagery satellite tiles (fetched on demand)
- `~/.cache/earth-trip-visualizer/icons/{key}.png` — Twemoji transport icons (pre-fetched at renderer init)
- `~/.cache/earth-trip-visualizer/flags/{cc}.png` — Country flag images
- `~/.cache/earth-trip-visualizer/geocode.json` — Geocoding results

---

## Performance

- **~100ms per unique globe position** on Apple Silicon M-series
- Globe cache keyed on `(round(lon,1), round(lat,1), round(globe_r,-1))` — city pause frames cache well
- Tile patch cache keyed on `(z, tx0, tx1, ty0, ty1)` — same zoom level reuses stitched canvas
- Typical 2-city video at defaults: ~300 frames → ~30 seconds render time
- Each additional city leg adds ~135 frames (~14 seconds) at default settings
- ffmpeg encoding adds ~2–5 seconds regardless of length

---

## Known issues / extension points

- **Transport emoji in combo box**: PyQt6 on macOS may render emoji as arrows; display-only issue, doesn't affect video
- **Geocoding failures**: Nominatim can be slow or return unexpected results for small towns — the geocode cache helps on retry
- **Font**: renderer uses system fonts (Helvetica/Arial on macOS); for a specific font, add TTF to `assets/fonts/` and update `_load_font()` in `renderer.py`
- **Adding transports**: add to `TRANSPORT_LABELS` in `animator.py`, `TRANSPORTS` in `city_item.py`, and `_TWEMOJI_HEX` in `renderer.py`
- **Changing video resolution**: change `W, H` in `renderer.py` and `-s` in `video_builder.py` together
- **Tile rate limiting**: ESRI tiles are free with no API key; heavy use may get throttled — tile disk cache mitigates this
