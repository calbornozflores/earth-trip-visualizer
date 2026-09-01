"""Shared UI design tokens.

Values mirror the personal-projects design standard in
``personal/DESIGN_SYSTEM.md`` (reference implementation: poke-dojo).
``TEXT_DIM``/``TEXT_DIMMER`` are project-local extensions for tertiary/
disabled text — the shared standard only defines two text tiers.
"""

from __future__ import annotations

BG = "#0f0f1a"
SURFACE = "#1a1a2e"
SURFACE2 = "#16213e"
BORDER = "#2a2a4a"

ACCENT = "#6c63ff"
ACCENT_HOVER = "#8b85ff"
ACCENT_GRADIENT_END = "#a78bfa"

RED = "#ef4444"
RED_TINT_BG = "rgba(239, 68, 68, 0.1)"

TEXT = "#e2e8f0"
TEXT_MUTED = "#94a3b8"
TEXT_DIM = "#64748b"
TEXT_DIMMER = "#475569"

RADIUS = 12
RADIUS_SM = 8

FONT_FAMILY = "'Segoe UI', -apple-system, system-ui, sans-serif"

ACCENT_GRADIENT = (
    f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_GRADIENT_END})"
)
ACCENT_GRADIENT_HOVER = (
    f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_HOVER}, stop:1 {ACCENT_GRADIENT_END})"
)


def build_stylesheet() -> str:
    """The app-wide QSS, built from the tokens above."""
    return f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: {FONT_FAMILY};
    font-size: 14px;
}}

/* Panel title */
QLabel#panelTitle {{
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 2px;
    color: {TEXT_DIM};
}}

/* Placeholder */
QLabel#placeholder {{
    font-size: 18px;
    color: {BORDER};
    background: {BG};
}}

/* City input */
QLineEdit#cityInput {{
    background-color: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    color: {TEXT};
    font-size: 15px;
}}
QLineEdit#cityInput:focus {{
    border-color: {ACCENT};
    background-color: {SURFACE};
}}
QLineEdit#cityInput::placeholder {{
    color: {TEXT_DIMMER};
}}

/* Remove button */
QPushButton#removeBtn {{
    background: transparent;
    border: none;
    color: {TEXT_DIMMER};
    font-size: 14px;
    border-radius: 6px;
}}
QPushButton#removeBtn:hover {{
    color: {RED};
    background: {RED_TINT_BG};
}}

/* Duration spinboxes */
QDoubleSpinBox#durationSpin {{
    background-color: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 6px;
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QDoubleSpinBox#durationSpin:focus {{
    border-color: {ACCENT};
    color: {TEXT};
}}
QDoubleSpinBox#durationSpin::up-button,
QDoubleSpinBox#durationSpin::down-button {{
    width: 14px;
    border: none;
    background: transparent;
    color: {TEXT_DIM};
}}

/* Transport dropdown */
QComboBox#transportCombo {{
    background-color: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 12px;
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QComboBox#transportCombo::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 24px;
    border: none;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT};
    selection-background-color: {ACCENT};
}}

/* Add stop button */
QPushButton#addBtn {{
    background-color: transparent;
    border: 1px dashed {BORDER};
    border-radius: 10px;
    padding: 10px;
    color: {TEXT_DIM};
    font-size: 14px;
}}
QPushButton#addBtn:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
    background: rgba(108, 99, 255, 0.08);
}}

/* Generate button */
QPushButton#generateBtn {{
    background: {ACCENT_GRADIENT};
    border: none;
    border-radius: 12px;
    color: white;
    font-size: 16px;
    font-weight: bold;
    padding: 14px;
}}
QPushButton#generateBtn:hover {{
    background: {ACCENT_GRADIENT_HOVER};
}}
QPushButton#generateBtn:pressed {{
    background: {ACCENT_GRADIENT};
}}

/* Control bar */
QWidget#controlBar {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
}}

/* Seek slider */
QSlider#seekSlider::groove:horizontal {{
    height: 4px;
    background: {SURFACE2};
    border-radius: 2px;
}}
QSlider#seekSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider#seekSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* Control buttons */
QPushButton#ctrlBtn, QPushButton#playBtn {{
    background: {SURFACE2};
    border: none;
    border-radius: 8px;
    color: {TEXT_MUTED};
    font-size: 16px;
}}
QPushButton#ctrlBtn:hover, QPushButton#playBtn:hover {{
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton#ctrlBtn:disabled, QPushButton#playBtn:disabled {{
    color: {BORDER};
}}

/* Time label */
QLabel#timeLabel {{
    color: {TEXT_DIM};
    font-size: 13px;
    min-width: 100px;
}}

/* Download button */
QPushButton#downloadBtn {{
    background: {SURFACE2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT_MUTED};
    padding: 0 16px;
    font-size: 13px;
}}
QPushButton#downloadBtn:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}
QPushButton#downloadBtn:disabled {{
    color: {BORDER};
    border-color: {BORDER};
}}

/* Scrollbar */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""
