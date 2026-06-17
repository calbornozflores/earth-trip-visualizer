from __future__ import annotations

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QFrame, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from earth_trip.ui.city_item import CityItem, TransportSelector


class CityPanel(QWidget):
    """Left panel: journey builder."""

    generate_requested = pyqtSignal(list, list)  # city_names, transport_keys

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cities: list[CityItem] = []
        self._transports: list[TransportSelector] = []
        self._build()
        self._add_city("Paris, France")
        self._add_city("Tokyo, Japan")

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 24, 20, 20)
        outer.setSpacing(0)

        # Header
        title = QLabel("JOURNEY")
        title.setObjectName("panelTitle")
        outer.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #334155; margin: 12px 0 16px 0;")
        sep.setFixedHeight(1)
        outer.addWidget(sep)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)

        scroll.setWidget(self._list_widget)
        outer.addWidget(scroll, 1)

        # Add stop button
        add_btn = QPushButton("＋  Add Stop")
        add_btn.setObjectName("addBtn")
        add_btn.setMinimumHeight(44)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(lambda: self._add_city())
        outer.addSpacing(12)
        outer.addWidget(add_btn)

        # Generate button
        gen_btn = QPushButton("🎬  Generate Video")
        gen_btn.setObjectName("generateBtn")
        gen_btn.setMinimumHeight(52)
        gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gen_btn.clicked.connect(self._on_generate)
        outer.addSpacing(8)
        outer.addWidget(gen_btn)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _add_city(self, name: str = "") -> None:
        stretch = self._list_layout.takeAt(self._list_layout.count() - 1)

        if self._cities:
            ts = TransportSelector()
            self._transports.append(ts)
            self._list_layout.addWidget(ts)

        item = CityItem()
        if name:
            item.set_city_name(name)
        item.remove_requested.connect(self._remove_city)
        self._cities.append(item)
        self._list_layout.addWidget(item)

        self._list_layout.addStretch(stretch.spacerItem().expandingDirections() if stretch and stretch.spacerItem() else 1)

    def _remove_city(self, item: CityItem) -> None:
        if len(self._cities) <= 2:
            QMessageBox.information(self, "Minimum stops", "You need at least 2 cities.")
            return

        idx = self._cities.index(item)

        if idx > 0:
            ts = self._transports[idx - 1]
            self._transports.remove(ts)
            self._list_layout.removeWidget(ts)
            ts.deleteLater()
        elif self._transports:
            ts = self._transports[0]
            self._transports.remove(ts)
            self._list_layout.removeWidget(ts)
            ts.deleteLater()

        self._cities.remove(item)
        self._list_layout.removeWidget(item)
        item.deleteLater()

    def _on_generate(self) -> None:
        names = [c.city_name() for c in self._cities]
        empty = [i + 1 for i, n in enumerate(names) if not n]
        if empty:
            QMessageBox.warning(
                self, "Missing cities",
                f"Please fill in city {'#' + ', #'.join(str(e) for e in empty)}.",
            )
            return
        transport_keys = [t.transport_key() for t in self._transports]
        self.generate_requested.emit(names, transport_keys)
