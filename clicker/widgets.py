"""Custom animated widgets."""

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QWidget,
)


class NoScrollSpinBox(QSpinBox):
    """SpinBox that ignores mouse wheel events."""

    def wheelEvent(self, event) -> None:
        event.ignore()


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
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_glow_color(self, color: QColor) -> None:
        self._glow_color = color
        self._shadow.setColor(color)

    def enterEvent(self, event) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(12)
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
        self._glow_anim.setEndValue(10 if v else 0)
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
        layout.setSpacing(3)

        for v in presets:
            btn = GlowButton(str(v), self)
            btn.setObjectName("preset")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setFixedHeight(28)
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


class MacroEntryWidget(QWidget):
    """Single macro entry row: [#num] [key] [delay ms] [delete]."""

    delete_clicked = Signal(int)
    delay_changed = Signal(int, int)  # (index, delay_ms)

    def __init__(self, index: int, key_name: str, delay_ms: int = 1,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self._num_label = QLabel(f"#{index + 1}")
        self._num_label.setObjectName("dim")
        self._num_label.setFixedWidth(28)
        layout.addWidget(self._num_label)

        self._key_label = QLabel(key_name)
        self._key_label.setObjectName("macroKey")
        self._key_label.setFixedWidth(60)
        self._key_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._key_label)

        self._delay_spin = NoScrollSpinBox()
        self._delay_spin.setRange(1, 99999)
        self._delay_spin.setValue(delay_ms)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.setFixedHeight(26)
        self._delay_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._delay_spin.valueChanged.connect(self._on_delay)
        layout.addWidget(self._delay_spin)

        del_btn = GlowButton("✕", self)
        del_btn.setObjectName("macroDelBtn")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setFixedSize(26, 26)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._index))
        self._del_btn = del_btn
        layout.addWidget(del_btn)

    def _on_delay(self, v: int) -> None:
        self.delay_changed.emit(self._index, v)

    def set_index(self, i: int) -> None:
        self._index = i
        self._num_label.setText(f"#{i + 1}")

    def get_delay(self) -> int:
        return self._delay_spin.value()

    def get_key_name(self) -> str:
        return self._key_label.text()


class ToastNotification(QLabel):
    """Animated toast that fades in and out within parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(36)
        self.hide()

        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

    def show_message(self, text: str, duration: int = 1800) -> None:
        self.setText(text)
        pw = self.parent().width()
        w = min(220, pw - 40)
        self.setFixedWidth(w)
        self.move((pw - w) // 2, self.parent().height() - 55)
        self.show()
        self.raise_()

        self._fade_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in.start()

        QTimer.singleShot(duration, self._fade_out)

    def _fade_out(self) -> None:
        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_out.setDuration(400)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.InCubic)
        self._anim_out.finished.connect(self.hide)
        self._anim_out.start()
