from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget, QFrame,
)


TRANSPORTS = [
    ("✈  Plane", "plane"),
    ("🚂  Train", "train"),
    ("🚌  Bus", "bus"),
    ("🚗  Car", "car"),
    ("⛴  Ship", "ship"),
]


def _duration_spin(min_val: float, max_val: float, default: float, step: float = 0.5) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(min_val, max_val)
    spin.setSingleStep(step)
    spin.setValue(default)
    spin.setSuffix(" s")
    spin.setDecimals(1)
    spin.setFixedWidth(72)
    spin.setObjectName("durationSpin")
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return spin


class CityItem(QWidget):
    """One city row: pin icon + text input + pause duration + remove button."""

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

        clock = QLabel("⏱")
        clock.setFixedWidth(18)
        clock.setStyleSheet("color: #64748b; font-size: 13px;")
        clock.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(clock)

        self._pause_spin = _duration_spin(0.5, 10.0, 2.0)
        row.addWidget(self._pause_spin)

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

    def pause_secs(self) -> float:
        return self._pause_spin.value()


class TransportSelector(QWidget):
    """Connector between two city rows: transport dropdown + transition duration."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(28, 4, 0, 4)
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

        arrow = QLabel("↔")
        arrow.setFixedWidth(18)
        arrow.setStyleSheet("color: #64748b; font-size: 13px;")
        arrow.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(arrow)

        self._trans_spin = _duration_spin(1.0, 15.0, 4.5)
        row.addWidget(self._trans_spin)

        # Match right margin of CityItem (remove btn 32px + 8px gap = 40px)
        row.addSpacing(40)

    def transport_key(self) -> str:
        idx = self.combo.currentIndex()
        return TRANSPORTS[idx][1] if 0 <= idx < len(TRANSPORTS) else "plane"

    def transition_secs(self) -> float:
        return self._trans_spin.value()
