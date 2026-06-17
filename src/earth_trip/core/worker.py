from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from earth_trip.core.geocoder import geocode_city, CityInfo
from earth_trip.core.animator import build_frame_specs
from earth_trip.core.renderer import GlobeRenderer
from earth_trip.core.video_builder import build_video


class GenerationWorker(QThread):
    progress = pyqtSignal(int, str)   # percent, message
    finished = pyqtSignal(str)        # output file path
    error = pyqtSignal(str)

    def __init__(
        self,
        city_names: list[str],
        transports: list[str],
        earth_texture_path: Path,
        city_pause_secs: list[float] | None = None,
        transition_secs: list[float] | None = None,
    ) -> None:
        super().__init__()
        self._city_names = city_names
        self._transports = transports
        self._earth_texture = earth_texture_path
        self._city_pause_secs = city_pause_secs
        self._transition_secs = transition_secs
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            # Phase 1: Geocode cities (0–25%)
            cities: list[CityInfo] = []
            n = len(self._city_names)
            for i, name in enumerate(self._city_names):
                if self._cancelled:
                    return
                pct = int(i / n * 25)
                self.progress.emit(pct, f"Geocoding {name} ({i + 1}/{n})…")
                info = geocode_city(name)
                if info is None:
                    self.error.emit(f'City not found: "{name}"')
                    return
                cities.append(info)

            # Phase 2: Build frame specs (25–30%)
            self.progress.emit(25, "Planning animation…")
            specs = build_frame_specs(cities, self._transports, self._city_pause_secs, self._transition_secs)
            total = len(specs)

            # Phase 3: Render + encode (30–100%)
            renderer = GlobeRenderer(self._earth_texture)
            out_path = Path(tempfile.mkdtemp()) / "earth_trip.mp4"

            def frame_gen():
                for i, spec in enumerate(specs):
                    if self._cancelled:
                        return
                    yield renderer.render_frame(spec)

            rendered = [0]

            def on_frame(idx: int) -> None:
                rendered[0] += 1
                pct = 30 + int(rendered[0] / total * 70)
                if rendered[0] % 5 == 0 or rendered[0] == total:
                    self.progress.emit(pct, f"Rendering frame {rendered[0]}/{total}…")

            result = build_video(frame_gen(), out_path, on_frame=on_frame)
            self.progress.emit(100, "Done!")
            self.finished.emit(str(result))

        except Exception as exc:
            self.error.emit(str(exc))
