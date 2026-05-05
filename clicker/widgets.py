"""Custom animated widgets."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class GlowButton(QPushButton):
    """Button with animated glow on hover."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._glow_color = QColor(92, 111, 255, 120)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(self._glow_color)
        self._shadow.setOffset(0, 0)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_glow_color(self, color: QColor) -> None:
        self._glow_color = color
        self._shadow.setColor(color)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(18)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(0)
        self._anim.start()
        super().leaveEvent(event)


class AnimatedToggle(QWidget):
    """Custom toggle switch with smooth animation."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self._thumb_x = 4.0
        self._track_on = QColor("#5c6fff")
        self._track_off = QColor("#303050")
        self._thumb_color = QColor("#ffffff")
        self.setFixedSize(46, 26)
        self.setCursor(Qt.PointingHandCursor)

        self._pos_anim = QPropertyAnimation(self, b"thumbX")
        self._pos_anim.setDuration(200)
        self._pos_anim.setEasingCurve(QEasingCurve.InOutCubic)

        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setColor(QColor(92, 111, 255, 100))
        self._glow.setOffset(0, 0)
        self.setGraphicsEffect(self._glow)

        self._glow_anim = QPropertyAnimation(self._glow, b"blurRadius")
        self._glow_anim.setDuration(200)

    # --- property for animation ---
    def _get_thumb_x(self) -> float:
        return self._thumb_x

    def _set_thumb_x(self, v: float) -> None:
        self._thumb_x = v
        self.update()

    thumbX = Property(float, _get_thumb_x, _set_thumb_x)

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, v: bool, emit: bool = True) -> None:
        if self._checked == v:
            return
        self._checked = v
        self._pos_anim.stop()
        self._pos_anim.setStartValue(self._thumb_x)
        self._pos_anim.setEndValue(24.0 if v else 4.0)
        self._pos_anim.start()

        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._glow.blurRadius())
        self._glow_anim.setEndValue(14 if v else 0)
        self._glow_anim.start()

        if emit:
            self.toggled.emit(v)

    def set_colors(self, on: str, off: str, glow: str) -> None:
        self._track_on = QColor(on)
        self._track_off = QColor(off)
        self._glow.setColor(QColor(glow))
        self.update()

    def mousePressEvent(self, event) -> None:
        self.set_checked(not self._checked)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self._thumb_x / 24.0 if self._checked else 1.0 - (self._thumb_x - 4.0) / 20.0
        t = max(0.0, min(1.0, (self._thumb_x - 4.0) / 20.0))
        r1, g1, b1 = self._track_off.red(), self._track_off.green(), self._track_off.blue()
        r2, g2, b2 = self._track_on.red(), self._track_on.green(), self._track_on.blue()
        mixed = QColor(
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(mixed))
        p.drawRoundedRect(0, 0, 46, 26, 13, 13)
        p.setBrush(QBrush(self._thumb_color))
        p.drawEllipse(QPointF(self._thumb_x + 9, 13), 8.5, 8.5)
        p.end()

    def sizeHint(self) -> QSize:
        return QSize(46, 26)


class ModeTabBar(QWidget):
    """Tab bar with animated selection."""

    mode_changed = Signal(str)

    def __init__(self, modes: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modes = modes
        self._active = modes[0]
        self._buttons: list[GlowButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for m in modes:
            btn = GlowButton(m, self)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, mode=m: self._select(mode))
            self._buttons.append(btn)
            layout.addWidget(btn)

        self._update_styles()

    def _select(self, mode: str) -> None:
        if mode == self._active:
            return
        self._active = mode
        self._update_styles()
        self.mode_changed.emit(mode)

    def _update_styles(self) -> None:
        for btn in self._buttons:
            if btn.text() == self._active:
                btn.setObjectName("modeTabActive")
            else:
                btn.setObjectName("modeTab")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def current(self) -> str:
        return self._active


class CpsPresetBar(QWidget):
    """Row of CPS preset buttons."""

    preset_selected = Signal(int)

    def __init__(self, presets: list[int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._presets = presets
        self._active: int | None = None
        self._buttons: list[GlowButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for v in presets:
            btn = GlowButton(str(v), self)
            btn.setObjectName("preset")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, val=v: self._select(val))
            self._buttons.append(btn)
            layout.addWidget(btn)

    def _select(self, v: int) -> None:
        self._active = v
        self._update_styles()
        self.preset_selected.emit(v)

    def clear_active(self) -> None:
        self._active = None
        self._update_styles()

    def _update_styles(self) -> None:
        for btn in self._buttons:
            if self._active is not None and btn.text() == str(self._active):
                btn.setObjectName("presetActive")
            else:
                btn.setObjectName("preset")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
