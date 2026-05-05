"""Main application window."""

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .engine import BindListener, ClickEngine
from .themes import DARK, LIGHT, build_stylesheet
from .widgets import AnimatedToggle, CpsPresetBar, GlowButton, ModeTabBar


class ClickerWindow(QWidget):
    """Main clicker window."""

    def __init__(self) -> None:
        super().__init__()
        self._theme = DARK
        self._is_dark = True
        self._hidden = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(370)

        self._drag_pos = None

        self._engine = ClickEngine()
        self._bind_listener = BindListener()
        self._hold_mode = True  # True = hold, False = toggle
        self._toggle_active = False

        self._build_ui()
        self._apply_theme()
        self._connect_signals()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self._container = QFrame()
        self._container.setObjectName("container")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)
        root.addWidget(self._container)

        main = QVBoxLayout(self._container)
        main.setContentsMargins(18, 14, 18, 18)
        main.setSpacing(12)

        # title bar
        main.addLayout(self._build_title_bar())

        # separator
        main.addWidget(self._sep())

        # mode tabs
        self._mode_tabs = ModeTabBar(["Smooth", "Insta", "Mixed"])
        main.addWidget(self._mode_tabs)

        # CPS input
        main.addLayout(self._build_cps_input())

        # preset bar
        self._presets = CpsPresetBar([100, 200, 300, 400, 500])
        main.addWidget(self._presets)

        # mixed range (hidden by default)
        self._mixed_card = self._build_mixed_card()
        main.addWidget(self._mixed_card)
        self._mixed_card.setVisible(False)

        # separator
        main.addWidget(self._sep())

        # live CPS
        main.addLayout(self._build_cps_display())

        # separator
        main.addWidget(self._sep())

        # bind row
        main.addLayout(self._build_bind_row())

        # mode row (hold / toggle)
        main.addLayout(self._build_mode_row())

        # hide bind row
        main.addLayout(self._build_hide_row())

        # separator
        main.addWidget(self._sep())

        # only roblox
        main.addLayout(self._build_roblox_row())

        main.addStretch()

    def _build_title_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self._theme_btn = GlowButton("Light", self)
        self._theme_btn.setObjectName("themeBtn")
        self._theme_btn.setToolTip("Toggle theme")
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self._theme_btn)

        row.addStretch()

        minimize_btn = GlowButton("─", self)
        minimize_btn.setObjectName("iconBtn")
        minimize_btn.setCursor(Qt.PointingHandCursor)
        minimize_btn.clicked.connect(self.showMinimized)
        row.addWidget(minimize_btn)

        close_btn = GlowButton("✕", self)
        close_btn.setObjectName("closeBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self._quit)
        row.addWidget(close_btn)

        return row

    def _build_cps_input(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("CPS")
        lbl.setObjectName("sec")
        row.addWidget(lbl)

        self._cps_spin = QSpinBox()
        self._cps_spin.setRange(1, 99999)
        self._cps_spin.setValue(10)
        self._cps_spin.setFixedHeight(32)
        self._cps_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self._cps_spin)

        return row

    def _build_mixed_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        lbl_min = QLabel("Min")
        lbl_min.setObjectName("sec")
        layout.addWidget(lbl_min)

        self._min_spin = QSpinBox()
        self._min_spin.setRange(1, 99999)
        self._min_spin.setValue(8)
        self._min_spin.setFixedHeight(30)
        self._min_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._min_spin)

        lbl_max = QLabel("Max")
        lbl_max.setObjectName("sec")
        layout.addWidget(lbl_max)

        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, 99999)
        self._max_spin.setValue(15)
        self._max_spin.setFixedHeight(30)
        self._max_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._max_spin)

        return card

    def _build_cps_display(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)

        lbl = QLabel("LIVE CPS")
        lbl.setObjectName("dim")
        lbl.setAlignment(Qt.AlignCenter)
        col.addWidget(lbl)

        self._cps_label = QLabel("0")
        self._cps_label.setObjectName("cpsLive")
        self._cps_label.setAlignment(Qt.AlignCenter)

        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(20)
        glow.setColor(QColor(92, 111, 255, 80))
        glow.setOffset(0, 0)
        self._cps_label.setGraphicsEffect(glow)
        self._cps_glow = glow

        col.addWidget(self._cps_label)

        return col

    def _build_bind_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Bind")
        lbl.setObjectName("sec")
        lbl.setFixedWidth(36)
        row.addWidget(lbl)

        self._bind_btn = GlowButton("Set Bind", self)
        self._bind_btn.setObjectName("primary")
        self._bind_btn.setCursor(Qt.PointingHandCursor)
        self._bind_btn.setFixedHeight(30)
        self._bind_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self._bind_btn)

        self._bind_display = QLabel("—")
        self._bind_display.setObjectName("sec")
        self._bind_display.setAlignment(Qt.AlignCenter)
        self._bind_display.setFixedWidth(60)
        row.addWidget(self._bind_display)

        return row

    def _build_mode_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Mode")
        lbl.setObjectName("sec")
        lbl.setFixedWidth(36)
        row.addWidget(lbl)

        self._hold_btn = GlowButton("Hold", self)
        self._hold_btn.setObjectName("modeTabActive")
        self._hold_btn.setCursor(Qt.PointingHandCursor)
        self._hold_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hold_btn.setFixedHeight(30)
        row.addWidget(self._hold_btn)

        self._toggle_btn = GlowButton("Toggle", self)
        self._toggle_btn.setObjectName("modeTab")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._toggle_btn.setFixedHeight(30)
        row.addWidget(self._toggle_btn)

        return row

    def _build_hide_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Hide")
        lbl.setObjectName("sec")
        lbl.setFixedWidth(36)
        row.addWidget(lbl)

        self._hide_btn = GlowButton("Set Bind", self)
        self._hide_btn.setCursor(Qt.PointingHandCursor)
        self._hide_btn.setFixedHeight(30)
        self._hide_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(self._hide_btn)

        self._hide_display = QLabel("—")
        self._hide_display.setObjectName("sec")
        self._hide_display.setAlignment(Qt.AlignCenter)
        self._hide_display.setFixedWidth(60)
        row.addWidget(self._hide_display)

        return row

    def _build_roblox_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("Only Roblox")
        lbl.setObjectName("sec")
        row.addWidget(lbl)

        row.addStretch()

        self._roblox_toggle = AnimatedToggle()
        row.addWidget(self._roblox_toggle)

        return row

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setObjectName("separator")
        s.setFrameShape(QFrame.HLine)
        s.setFixedHeight(1)
        return s

    # ── Signals ──────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._theme_btn.clicked.connect(self._toggle_theme)

        self._mode_tabs.mode_changed.connect(self._on_mode_changed)

        self._cps_spin.valueChanged.connect(self._on_cps_changed)
        self._min_spin.valueChanged.connect(self._on_range_changed)
        self._max_spin.valueChanged.connect(self._on_range_changed)
        self._presets.preset_selected.connect(self._on_preset)

        self._bind_btn.clicked.connect(lambda: self._start_bind("click"))
        self._hide_btn.clicked.connect(lambda: self._start_bind("hide"))

        self._hold_btn.clicked.connect(lambda: self._set_hold_mode(True))
        self._toggle_btn.clicked.connect(lambda: self._set_hold_mode(False))

        self._roblox_toggle.toggled.connect(self._engine.set_only_roblox)

        self._bind_listener.bind_set.connect(self._on_bind_set)
        self._bind_listener.bind_pressed.connect(self._on_bind_pressed)
        self._bind_listener.bind_released.connect(self._on_bind_released)
        self._bind_listener.hide_pressed.connect(self._on_hide_toggle)

        self._engine.cps_update.connect(self._on_cps_update)
        self._engine.status_changed.connect(self._on_status_changed)

    # ── Callbacks ────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self._theme = DARK if self._is_dark else LIGHT
        self._theme_btn.setText("Light" if self._is_dark else "Dark")
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(build_stylesheet(t))
        self._roblox_toggle.set_colors(t["toggle_on"], t["toggle_off"], t["primary_glow"])
        self._cps_glow.setColor(QColor(t["primary"]))

        for btn in (self._bind_btn, self._hide_btn):
            btn.set_glow_color(QColor(t["primary"]))

        for w in self.findChildren(GlowButton):
            w.set_glow_color(QColor(t["primary"]))

    def _on_mode_changed(self, mode: str) -> None:
        mode_lower = mode.lower()
        self._engine.set_mode(mode_lower)

        show_mixed = mode_lower == "mixed"
        if show_mixed != self._mixed_card.isVisible():
            self._mixed_card.setVisible(show_mixed)
            QTimer.singleShot(0, self.adjustSize)

    def _on_cps_changed(self, v: int) -> None:
        self._engine.set_cps(float(v))
        self._presets.clear_active()

    def _on_range_changed(self) -> None:
        self._engine.set_cps_range(
            float(self._min_spin.value()),
            float(self._max_spin.value()),
        )

    def _on_preset(self, v: int) -> None:
        self._cps_spin.setValue(v)
        self._engine.set_cps(float(v))

    def _start_bind(self, target: str) -> None:
        if target == "click":
            self._bind_btn.setText("...")
        else:
            self._hide_btn.setText("...")
        self._bind_listener.start_listening(target)

    def _on_bind_set(self, name: str, meta: object) -> None:
        _, _, target = meta
        if target == "click":
            self._bind_btn.setText("Set Bind")
            self._bind_display.setText(name)
        else:
            self._hide_btn.setText("Set Bind")
            self._hide_display.setText(name)

    def _set_hold_mode(self, hold: bool) -> None:
        self._hold_mode = hold
        if hold:
            self._hold_btn.setObjectName("modeTabActive")
            self._toggle_btn.setObjectName("modeTab")
        else:
            self._hold_btn.setObjectName("modeTab")
            self._toggle_btn.setObjectName("modeTabActive")
        for btn in (self._hold_btn, self._toggle_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if not hold:
            self._toggle_active = False
            self._engine.stop()

    def _on_bind_pressed(self) -> None:
        if self._hold_mode:
            self._engine.start()
        else:
            self._toggle_active = not self._toggle_active
            if self._toggle_active:
                self._engine.start()
            else:
                self._engine.stop()

    def _on_bind_released(self) -> None:
        if self._hold_mode:
            self._engine.stop()

    def _on_hide_toggle(self) -> None:
        if self._hidden:
            self._animate_show()
        else:
            self._animate_hide()

    def _on_cps_update(self, cps: float) -> None:
        self._cps_label.setText(f"{cps:.0f}")

    def _on_status_changed(self, active: bool) -> None:
        color = self._theme["success"] if active else self._theme["primary"]
        self._cps_glow.setColor(QColor(color))

    # ── Show / hide animations ───────────────────────────────────

    def _animate_show(self) -> None:
        self._hidden = False
        self.show()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.show()
        self.activateWindow()
        self.raise_()

        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._show_anim = anim
        anim.start()

    def _animate_hide(self) -> None:
        self._hidden = True
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(self.hide)
        self._hide_anim = anim
        anim.start()

    # ── Drag support ─────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    # ── Cleanup ──────────────────────────────────────────────────

    def _quit(self) -> None:
        self._engine.shutdown()
        self._bind_listener.shutdown()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self._engine.shutdown()
        self._bind_listener.shutdown()
        super().closeEvent(event)
