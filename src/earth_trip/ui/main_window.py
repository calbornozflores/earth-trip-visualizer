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
from earth_trip.core.worker import GenerationWorker

_ASSETS = Path(__file__).parent.parent / "assets"
_TEXTURE = _ASSETS / "earth_texture.jpg"

_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0a0a0f;
    color: #e2e8f0;
    font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif;
    font-size: 14px;
}

/* Panel title */
QLabel#panelTitle {
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 2px;
    color: #64748b;
}

/* Placeholder */
QLabel#placeholder {
    font-size: 18px;
    color: #334155;
    background: #0a0a0f;
}

/* City input */
QLineEdit#cityInput {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 8px 14px;
    color: #e2e8f0;
    font-size: 15px;
}
QLineEdit#cityInput:focus {
    border-color: #4f9cf9;
    background-color: #1a2540;
}
QLineEdit#cityInput::placeholder {
    color: #475569;
}

/* Remove button */
QPushButton#removeBtn {
    background: transparent;
    border: none;
    color: #475569;
    font-size: 14px;
    border-radius: 6px;
}
QPushButton#removeBtn:hover {
    color: #f87171;
    background: rgba(248,113,113,0.1);
}

/* Transport dropdown */
QComboBox#transportCombo {
    background-color: #151c2e;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 6px 12px;
    color: #94a3b8;
    font-size: 13px;
}
QComboBox#transportCombo::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 24px;
    border: none;
}
QComboBox QAbstractItemView {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    color: #e2e8f0;
    selection-background-color: #2d4a7a;
}

/* Add stop button */
QPushButton#addBtn {
    background-color: transparent;
    border: 1px dashed #334155;
    border-radius: 10px;
    padding: 10px;
    color: #64748b;
    font-size: 14px;
}
QPushButton#addBtn:hover {
    border-color: #4f9cf9;
    color: #4f9cf9;
    background: rgba(79,156,249,0.06);
}

/* Generate button */
QPushButton#generateBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:1 #8b5cf6);
    border: none;
    border-radius: 12px;
    color: white;
    font-size: 16px;
    font-weight: bold;
    padding: 14px;
}
QPushButton#generateBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #60a5fa, stop:1 #a78bfa);
}
QPushButton#generateBtn:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #2563eb, stop:1 #7c3aed);
}

/* Control bar */
QWidget#controlBar {
    background: #0d1117;
    border-top: 1px solid #1e293b;
}

/* Seek slider */
QSlider#seekSlider::groove:horizontal {
    height: 4px;
    background: #1e293b;
    border-radius: 2px;
}
QSlider#seekSlider::handle:horizontal {
    background: #4f9cf9;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider#seekSlider::sub-page:horizontal {
    background: #4f9cf9;
    border-radius: 2px;
}

/* Control buttons */
QPushButton#ctrlBtn, QPushButton#playBtn {
    background: #1e293b;
    border: none;
    border-radius: 8px;
    color: #94a3b8;
    font-size: 16px;
}
QPushButton#ctrlBtn:hover, QPushButton#playBtn:hover {
    background: #2d3f5c;
    color: #e2e8f0;
}
QPushButton#ctrlBtn:disabled, QPushButton#playBtn:disabled {
    color: #334155;
}

/* Time label */
QLabel#timeLabel {
    color: #64748b;
    font-size: 13px;
    min-width: 100px;
}

/* Download button */
QPushButton#downloadBtn {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    color: #94a3b8;
    padding: 0 16px;
    font-size: 13px;
}
QPushButton#downloadBtn:hover {
    border-color: #4f9cf9;
    color: #4f9cf9;
}
QPushButton#downloadBtn:disabled {
    color: #334155;
    border-color: #1e293b;
}

/* Scrollbar */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Earth Trip Visualizer")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setStyleSheet(_STYLESHEET)
        self._worker: GenerationWorker | None = None
        self._progress_dlg: QProgressDialog | None = None
        self._build()

    def _build(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1e293b; }")

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

    def _on_generate(self, city_names: list[str], transports: list[str]) -> None:
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

        self._worker = GenerationWorker(city_names, transports, _TEXTURE)
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
