from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QMainWindow, QMessageBox, QProgressDialog,
    QSplitter, QWidget,
)

from earth_trip.ui.city_panel import CityPanel
from earth_trip.ui.player_panel import PlayerPanel
from earth_trip.ui import theme
from earth_trip.core.worker import GenerationWorker

_ASSETS = Path(__file__).parent.parent / "assets"
_TEXTURE = _ASSETS / "earth_texture.jpg"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Earth Trip Visualizer")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(theme.build_stylesheet())
        self._worker: GenerationWorker | None = None
        self._progress_dlg: QProgressDialog | None = None
        self._build()

    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {theme.BORDER}; }}")

        self.city_panel = CityPanel()
        self.city_panel.setMinimumWidth(320)
        self.city_panel.setMaximumWidth(400)
        splitter.addWidget(self.city_panel)

        self.player_panel = PlayerPanel()
        splitter.addWidget(self.player_panel)

        splitter.setSizes([340, 940])
        self.setCentralWidget(splitter)

        self.city_panel.generate_requested.connect(self._on_generate)

        if not _TEXTURE.exists():
            self.player_panel.show_placeholder(
                "Earth texture missing.\nRun: uv run python scripts/download_assets.py"
            )

    def _on_generate(self, city_names: list[str], transports: list[str], city_pause_secs: list[float], transition_secs: list[float]) -> None:
        if not _TEXTURE.exists():
            QMessageBox.critical(
                self, "Missing texture",
                "Earth texture not found.\n\nRun: uv run python scripts/download_assets.py",
            )
            return

        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()

        self._progress_dlg = QProgressDialog("Preparing…", "Cancel", 0, 100, self)
        self._progress_dlg.setWindowTitle("Generating video")
        self._progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dlg.setMinimumDuration(0)
        self._progress_dlg.setValue(0)

        self._worker = GenerationWorker(city_names, transports, _TEXTURE, city_pause_secs, transition_secs)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._progress_dlg.canceled.connect(self._worker.cancel)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str) -> None:
        if self._progress_dlg:
            self._progress_dlg.setValue(pct)
            self._progress_dlg.setLabelText(msg)

    def _on_finished(self, path: str) -> None:
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None
        self.player_panel.load_video(path)

    def _on_error(self, msg: str) -> None:
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None
        QMessageBox.critical(self, "Error", msg)
