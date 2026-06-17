from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget, QFrame,
)


TRANSPORTS = [
    ("✈  Plane", "plane"),
    ("🚂  Train", "train"),
    ("🚌  Bus", "bus"),
    ("🚗  Car", "car"),
    ("⛴  Ship", "ship"),
]


class CityItem(QWidget):
    """One city row: pin icon + text input + remove button."""

    remove_requested = pyqtSignal(object)  # self

    def __init__(self, placeholder: str = "City name…", parent=None) -> None:
        super().__init__(parent)
        self._build()
        self.input.setPlaceholderText(placeholder)

    def _build(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        pin = QLabel("📍")
        pin.setFixedWidth(28)
        row.addWidget(pin)

        self.input = QLineEdit()
        self.input.setMinimumHeight(40)
        self.input.setObjectName("cityInput")
        row.addWidget(self.input, 1)

        rm = QPushButton("✕")
        rm.setFixedSize(32, 32)
        rm.setObjectName("removeBtn")
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(rm)

    def city_name(self) -> str:
        return self.input.text().strip()

    def set_city_name(self, name: str) -> None:
        self.input.setText(name)


class TransportSelector(QWidget):
    """Connector between two city rows showing a transport dropdown."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(28, 4, 40, 4)
        row.setSpacing(8)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(2)
        line.setStyleSheet("background: #334155;")
        row.addWidget(line)

        self.combo = QComboBox()
        self.combo.setObjectName("transportCombo")
        self.combo.setMinimumHeight(36)
        for label, _ in TRANSPORTS:
            self.combo.addItem(label)
        row.addWidget(self.combo, 1)

    def transport_key(self) -> str:
        idx = self.combo.currentIndex()
        return TRANSPORTS[idx][1] if 0 <= idx < len(TRANSPORTS) else "plane"
