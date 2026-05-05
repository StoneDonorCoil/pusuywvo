#!/usr/bin/env python3
"""Entry point for the clicker application."""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from clicker.window import ClickerWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    window = ClickerWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
