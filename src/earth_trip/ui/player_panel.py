from __future__ import annotations

import shutil
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QSlider, QVBoxLayout, QWidget, QFrame,
)


def _ms_to_str(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


class PlayerPanel(QWidget):
    """Right panel: video display + controls."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: str | None = None
        self._seeking = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Video display
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #000;")
        self.video_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.video_widget, 1)

        # Placeholder label (shown when no video loaded)
        self._placeholder = QLabel("Add cities and click\n🎬  Generate Video")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholder")
        self._placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._placeholder)
        self.video_widget.hide()

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #1e293b;")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Controls bar
        ctrl = QWidget()
        ctrl.setObjectName("controlBar")
        ctrl.setFixedHeight(72)
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(16, 8, 16, 8)
        ctrl_layout.setSpacing(6)

        # Seek slider
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setEnabled(False)
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        ctrl_layout.addWidget(self.seek_slider)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.rewind_btn = QPushButton("⏮")
        self.rewind_btn.setObjectName("ctrlBtn")
        self.rewind_btn.setFixedSize(36, 36)
        self.rewind_btn.setEnabled(False)
        self.rewind_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rewind_btn.clicked.connect(self._rewind)
        btn_row.addWidget(self.rewind_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedSize(40, 36)
        self.play_btn.setEnabled(False)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(self._toggle_play)
        btn_row.addWidget(self.play_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")
        btn_row.addWidget(self.time_label)

        btn_row.addStretch(1)

        self.download_btn = QPushButton("⬇  Download")
        self.download_btn.setObjectName("downloadBtn")
        self.download_btn.setMinimumHeight(36)
        self.download_btn.setEnabled(False)
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self._download)
        btn_row.addWidget(self.download_btn)

        ctrl_layout.addLayout(btn_row)
        layout.addWidget(ctrl)

        # Media player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)

    # ── Public API ─────────────────────────────────────────────────────────

    def load_video(self, path: str) -> None:
        self._current_path = path
        self.player.setSource(QUrl.fromLocalFile(path))
        self._placeholder.hide()
        self.video_widget.show()
        self.play_btn.setEnabled(True)
        self.rewind_btn.setEnabled(True)
        self.seek_slider.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.player.play()

    def show_placeholder(self, text: str) -> None:
        self._placeholder.setText(text)
        self.video_widget.hide()
        self._placeholder.show()

    # ── Slots ──────────────────────────────────────────────────────────────

    def _toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _rewind(self) -> None:
        self.player.setPosition(max(0, self.player.position() - 10_000))

    def _on_slider_pressed(self) -> None:
        self._seeking = True

    def _on_slider_released(self) -> None:
        self._seeking = False
        self.player.setPosition(self.seek_slider.value())

    def _on_slider_moved(self, value: int) -> None:
        self.time_label.setText(f"{_ms_to_str(value)} / {_ms_to_str(self.player.duration())}")

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("⏸")
        else:
            self.play_btn.setText("▶")

    def _on_position_changed(self, pos: int) -> None:
        if not self._seeking:
            self.seek_slider.setValue(pos)
        self.time_label.setText(
            f"{_ms_to_str(pos)} / {_ms_to_str(self.player.duration())}"
        )

    def _on_duration_changed(self, dur: int) -> None:
        self.seek_slider.setRange(0, dur)

    def _download(self) -> None:
        if not self._current_path:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Video", "earth_trip.mp4", "MP4 Video (*.mp4)"
        )
        if path:
            shutil.copy2(self._current_path, path)
