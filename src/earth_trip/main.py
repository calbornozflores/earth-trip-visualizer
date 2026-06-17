import sys
import shutil

from PyQt6.QtWidgets import QApplication, QMessageBox

from earth_trip.ui.main_window import MainWindow


def main() -> None:
    if not shutil.which("ffmpeg"):
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "ffmpeg not found",
            "ffmpeg is required for video generation.\n\nInstall it with:\n  brew install ffmpeg",
        )
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Earth Trip Visualizer")
    app.setOrganizationName("calbornozflores")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
