"""Main application window."""

import os

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QMovie,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .engine import BindListener, ClickEngine, MacroEngine
from .music import MusicPlayer
from .themes import ALL_THEMES, DARK, build_stylesheet
from .widgets import (
    AnimatedToggle,
    CpsPresetBar,
    GlowButton,
    MacroEntryWidget,
    ModeTabBar,
    NoScrollSpinBox,
    ToastNotification,
)


class BackgroundFrame(QFrame):
    """Container frame with optional custom background image/GIF."""

    def __init__(self) -> None:
        super().__init__()
        self._bg_pixmap: QPixmap | None = None
        self._bg_movie: QMovie | None = None
        self._overlay_alpha = 140

    def set_background(self, path: str) -> None:
        self.clear_background()
        if path.lower().endswith(".gif"):
            self._bg_movie = QMovie(path)
            self._bg_movie.frameChanged.connect(self.update)
            self._bg_movie.start()
        else:
            self._bg_pixmap = QPixmap(path)
        self.update()

    def clear_background(self) -> None:
        if self._bg_movie:
            self._bg_movie.stop()
            self._bg_movie.deleteLater()
        self._bg_movie = None
        self._bg_pixmap = None
        self.update()

    @property
    def has_background(self) -> bool:
        return self._bg_pixmap is not None or self._bg_movie is not None

    def paintEvent(self, event) -> None:
        if self._bg_pixmap or self._bg_movie:
            p = QPainter(self)
            p.setRenderHint(QPainter.SmoothPixmapTransform)

            if self._bg_movie:
                pixmap = self._bg_movie.currentPixmap()
            else:
                pixmap = self._bg_pixmap

            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.size(),
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                x = (self.width() - scaled.width()) // 2
                y = (self.height() - scaled.height()) // 2

                p.setClipRoundedRect(self.rect(), 12, 12)
                p.drawPixmap(x, y, scaled)
                p.fillRect(self.rect(), QColor(0, 0, 0, self._overlay_alpha))

            p.end()

        super().paintEvent(event)


class ClickerWindow(QWidget):
    """Main clicker window."""

    def __init__(self) -> None:
        super().__init__()
        self._theme_idx = 0
        self._theme = ALL_THEMES[0]
        self._hidden = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(370)

        self._drag_pos = None

        self._engine = ClickEngine()
        self._macro_engine = MacroEngine()
        self._music_player = MusicPlayer()
        self._bind_listener = BindListener()
        self._hold_mode = True
        self._toggle_active = False
        self._macro_hold_mode = True
        self._macro_toggle_active = False

        self._macro_data: list[tuple] = []

        self._build_ui()
        self._apply_theme()
        self._connect_signals()
        self._set_window_icon()

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)

        self._container = BackgroundFrame()
        self._container.setObjectName("container")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)
        root.addWidget(self._container)

        main = QVBoxLayout(self._container)
        main.setContentsMargins(18, 14, 18, 18)
        main.setSpacing(10)

        main.addLayout(self._build_title_bar())
        main.addWidget(self._sep())

        self._page_tabs = ModeTabBar(["Clicker", "Macros", "Music"])
        main.addWidget(self._page_tabs)

        self._stack = QStackedWidget()
        main.addWidget(self._stack)

        self._clicker_page = QWidget()
        self._build_clicker_page()
        self._stack.addWidget(self._clicker_page)

        self._macros_page = QWidget()
        self._build_macros_page()
        self._stack.addWidget(self._macros_page)

        self._music_page = QWidget()
        self._build_music_page()
        self._stack.addWidget(self._music_page)

        main.addStretch()

        self._toast = ToastNotification(self._container)

    def _build_title_bar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        # theme selector button
        self._theme_btn = GlowButton("Dark", self)
        self._theme_btn.setObjectName("themeBtn")
        self._theme_btn.setToolTip("Choose theme")
        self._theme_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self._theme_btn)

        # discord author button
        self._discord_btn = GlowButton("  123.456.789.100", self)
        self._discord_btn.setObjectName("discordBtn")
        self._discord_btn.setCursor(Qt.PointingHandCursor)
        self._discord_btn.setToolTip("Copy Discord")
        row.addWidget(self._discord_btn)

        # background button
        self._bg_btn = GlowButton("BG", self)
        self._bg_btn.setObjectName("themeBtn")
        self._bg_btn.setCursor(Qt.PointingHandCursor)
        self._bg_btn.setToolTip("Custom background")
        row.addWidget(self._bg_btn)

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

    # ── Clicker page ─────────────────────────────────────────────

    def _build_clicker_page(self) -> None:
        lay = QVBoxLayout(self._clicker_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._mode_tabs = ModeTabBar(["Smooth", "Insta", "Mixed"])
        lay.addWidget(self._mode_tabs)

        self._cps_widget = QWidget()
        cps_lay = QVBoxLayout(self._cps_widget)
        cps_lay.setContentsMargins(0, 0, 0, 0)
        cps_lay.setSpacing(8)
        cps_lay.addLayout(self._build_cps_input())
        self._presets = CpsPresetBar([100, 200, 300, 400, 500])
        cps_lay.addWidget(self._presets)
        lay.addWidget(self._cps_widget)

        self._mixed_card = self._build_mixed_card()
        lay.addWidget(self._mixed_card)
        self._mixed_card.setVisible(False)

        lay.addWidget(self._sep())

        self._target_label = QLabel("Target: 10 CPS")
        self._target_label.setObjectName("targetCps")
        self._target_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._target_label)

        lay.addLayout(self._build_cps_display())
        lay.addWidget(self._sep())
        lay.addLayout(self._build_bind_row())
        lay.addLayout(self._build_mode_row())
        lay.addLayout(self._build_hide_row())
        lay.addWidget(self._sep())
        lay.addLayout(self._build_roblox_row())

    def _build_cps_input(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel("CPS")
        lbl.setObjectName("sec")
        row.addWidget(lbl)

        self._cps_spin = NoScrollSpinBox()
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

        self._min_spin = NoScrollSpinBox()
        self._min_spin.setRange(1, 99999)
        self._min_spin.setValue(8)
        self._min_spin.setFixedHeight(30)
        self._min_spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._min_spin)

        lbl_max = QLabel("Max")
        lbl_max.setObjectName("sec")
        layout.addWidget(lbl_max)

        self._max_spin = NoScrollSpinBox()
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
        self._bind_display.setFixedWidth(50)
        row.addWidget(self._bind_display)

        self._bind_clear_btn = GlowButton("✕", self)
        self._bind_clear_btn.setObjectName("clearBindBtn")
        self._bind_clear_btn.setCursor(Qt.PointingHandCursor)
        self._bind_clear_btn.setFixedSize(22, 22)
        self._bind_clear_btn.setVisible(False)
        row.addWidget(self._bind_clear_btn)

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
        self._hide_display.setFixedWidth(50)
        row.addWidget(self._hide_display)

        self._hide_clear_btn = GlowButton("✕", self)
        self._hide_clear_btn.setObjectName("clearBindBtn")
        self._hide_clear_btn.setCursor(Qt.PointingHandCursor)
        self._hide_clear_btn.setFixedSize(22, 22)
        self._hide_clear_btn.setVisible(False)
        row.addWidget(self._hide_clear_btn)

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

    # ── Macros page ──────────────────────────────────────────────

    def _build_macros_page(self) -> None:
        lay = QVBoxLayout(self._macros_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self._macro_count_label = QLabel("Macros: 0")
        self._macro_count_label.setObjectName("macroCount")
        self._macro_count_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._macro_count_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(180)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._macro_list_widget = QWidget()
        self._macro_list_layout = QVBoxLayout(self._macro_list_widget)
        self._macro_list_layout.setContentsMargins(0, 0, 0, 0)
        self._macro_list_layout.setSpacing(2)
        self._macro_list_layout.addStretch()

        scroll.setWidget(self._macro_list_widget)
        lay.addWidget(scroll)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._macro_add_btn = GlowButton("+ Add Key", self)
        self._macro_add_btn.setObjectName("macroAddBtn")
        self._macro_add_btn.setCursor(Qt.PointingHandCursor)
        self._macro_add_btn.setFixedHeight(28)
        self._macro_add_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_row.addWidget(self._macro_add_btn)

        self._macro_copy_btn = GlowButton("Copy Last", self)
        self._macro_copy_btn.setObjectName("macroAddBtn")
        self._macro_copy_btn.setCursor(Qt.PointingHandCursor)
        self._macro_copy_btn.setFixedHeight(28)
        self._macro_copy_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_row.addWidget(self._macro_copy_btn)

        lay.addLayout(btn_row)
        lay.addWidget(self._sep())

        macro_bind_row = QHBoxLayout()
        macro_bind_row.setSpacing(8)

        lbl = QLabel("Bind")
        lbl.setObjectName("sec")
        lbl.setFixedWidth(36)
        macro_bind_row.addWidget(lbl)

        self._macro_bind_btn = GlowButton("Set Bind", self)
        self._macro_bind_btn.setObjectName("primary")
        self._macro_bind_btn.setCursor(Qt.PointingHandCursor)
        self._macro_bind_btn.setFixedHeight(30)
        self._macro_bind_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        macro_bind_row.addWidget(self._macro_bind_btn)

        self._macro_bind_display = QLabel("—")
        self._macro_bind_display.setObjectName("sec")
        self._macro_bind_display.setAlignment(Qt.AlignCenter)
        self._macro_bind_display.setFixedWidth(60)
        macro_bind_row.addWidget(self._macro_bind_display)

        lay.addLayout(macro_bind_row)

        macro_mode_row = QHBoxLayout()
        macro_mode_row.setSpacing(8)

        lbl2 = QLabel("Mode")
        lbl2.setObjectName("sec")
        lbl2.setFixedWidth(36)
        macro_mode_row.addWidget(lbl2)

        self._macro_hold_btn = GlowButton("Hold", self)
        self._macro_hold_btn.setObjectName("modeTabActive")
        self._macro_hold_btn.setCursor(Qt.PointingHandCursor)
        self._macro_hold_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._macro_hold_btn.setFixedHeight(30)
        macro_mode_row.addWidget(self._macro_hold_btn)

        self._macro_toggle_btn = GlowButton("Toggle", self)
        self._macro_toggle_btn.setObjectName("modeTab")
        self._macro_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._macro_toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._macro_toggle_btn.setFixedHeight(30)
        macro_mode_row.addWidget(self._macro_toggle_btn)

        lay.addLayout(macro_mode_row)

    # ── Music page ───────────────────────────────────────────────

    def _build_music_page(self) -> None:
        lay = QVBoxLayout(self._music_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # URL input row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)

        from PySide6.QtWidgets import QLineEdit
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Paste URL (YouTube, SoundCloud...)")
        self._url_input.setFixedHeight(30)
        url_row.addWidget(self._url_input)

        self._url_load_btn = GlowButton("Load", self)
        self._url_load_btn.setObjectName("primary")
        self._url_load_btn.setCursor(Qt.PointingHandCursor)
        self._url_load_btn.setFixedHeight(30)
        self._url_load_btn.setFixedWidth(55)
        url_row.addWidget(self._url_load_btn)

        lay.addLayout(url_row)

        # file load button
        self._file_load_btn = GlowButton("Load File (mp3, wav, ogg, flac...)", self)
        self._file_load_btn.setObjectName("macroAddBtn")
        self._file_load_btn.setCursor(Qt.PointingHandCursor)
        self._file_load_btn.setFixedHeight(28)
        lay.addWidget(self._file_load_btn)

        lay.addWidget(self._sep())

        # now playing
        self._track_label = QLabel("No track loaded")
        self._track_label.setObjectName("sec")
        self._track_label.setAlignment(Qt.AlignCenter)
        self._track_label.setWordWrap(True)
        self._track_label.setFixedHeight(32)
        lay.addWidget(self._track_label)

        # progress slider
        self._progress_slider = QSlider(Qt.Horizontal)
        self._progress_slider.setRange(0, 0)
        self._progress_slider.setFixedHeight(16)
        lay.addWidget(self._progress_slider)

        # time labels
        time_row = QHBoxLayout()
        self._time_current = QLabel("0:00")
        self._time_current.setObjectName("dim")
        time_row.addWidget(self._time_current)
        time_row.addStretch()
        self._time_total = QLabel("0:00")
        self._time_total.setObjectName("dim")
        time_row.addWidget(self._time_total)
        lay.addLayout(time_row)

        # controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self._play_btn = GlowButton("▶", self)
        self._play_btn.setObjectName("primary")
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setFixedSize(36, 36)
        ctrl_row.addWidget(self._play_btn)

        self._stop_btn = GlowButton("■", self)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFixedSize(36, 36)
        ctrl_row.addWidget(self._stop_btn)

        ctrl_row.addSpacing(8)

        vol_lbl = QLabel("Vol")
        vol_lbl.setObjectName("dim")
        ctrl_row.addWidget(vol_lbl)

        self._volume_slider = QSlider(Qt.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(50)
        self._volume_slider.setFixedHeight(16)
        ctrl_row.addWidget(self._volume_slider)

        lay.addLayout(ctrl_row)

        # supported sites info
        info = QLabel(
            "YouTube, SoundCloud, Twitch, Vimeo, Bandcamp, "
            "Dailymotion, Twitter/X, Reddit + 1000+"
        )
        info.setObjectName("dim")
        info.setWordWrap(True)
        info.setAlignment(Qt.AlignCenter)
        lay.addWidget(info)

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _sep() -> QFrame:
        s = QFrame()
        s.setObjectName("separator")
        s.setFrameShape(QFrame.HLine)
        s.setFixedHeight(1)
        return s

    @staticmethod
    def _format_time(ms: int) -> str:
        s = ms // 1000
        m = s // 60
        return f"{m}:{s % 60:02d}"

    def _set_window_icon(self) -> None:
        px = QPixmap(32, 32)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#5c6fff"))
        p.drawEllipse(2, 2, 28, 28)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(10, 10, 12, 12)
        p.setBrush(QColor("#5c6fff"))
        p.drawEllipse(13, 13, 6, 6)
        p.end()
        self.setWindowIcon(QIcon(px))

    # ── Signals ──────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self._theme_btn.clicked.connect(self._show_theme_menu)
        self._discord_btn.clicked.connect(self._copy_discord)
        self._bg_btn.clicked.connect(self._show_bg_menu)

        self._page_tabs.mode_changed.connect(self._on_page_changed)

        # clicker
        self._mode_tabs.mode_changed.connect(self._on_mode_changed)
        self._cps_spin.valueChanged.connect(self._on_cps_changed)
        self._min_spin.valueChanged.connect(self._on_range_changed)
        self._max_spin.valueChanged.connect(self._on_range_changed)
        self._presets.preset_selected.connect(self._on_preset)

        self._bind_btn.clicked.connect(lambda: self._start_bind("click"))
        self._hide_btn.clicked.connect(lambda: self._start_bind("hide"))
        self._bind_clear_btn.clicked.connect(lambda: self._clear_bind("click"))
        self._hide_clear_btn.clicked.connect(lambda: self._clear_bind("hide"))

        self._hold_btn.clicked.connect(lambda: self._set_hold_mode(True))
        self._toggle_btn.clicked.connect(lambda: self._set_hold_mode(False))

        self._roblox_toggle.toggled.connect(self._engine.set_only_roblox)

        self._bind_listener.bind_set.connect(self._on_bind_set)
        self._bind_listener.bind_pressed.connect(self._on_bind_pressed)
        self._bind_listener.bind_released.connect(self._on_bind_released)
        self._bind_listener.hide_pressed.connect(self._on_hide_toggle)

        self._engine.cps_update.connect(self._on_cps_update)
        self._engine.status_changed.connect(self._on_status_changed)

        # macros
        self._macro_add_btn.clicked.connect(self._macro_start_add)
        self._macro_copy_btn.clicked.connect(self._macro_copy_last)
        self._bind_listener.macro_key_captured.connect(self._macro_on_key_captured)

        self._macro_bind_btn.clicked.connect(lambda: self._start_bind("click"))
        self._macro_hold_btn.clicked.connect(lambda: self._set_macro_hold_mode(True))
        self._macro_toggle_btn.clicked.connect(lambda: self._set_macro_hold_mode(False))

        # music
        self._url_load_btn.clicked.connect(self._music_load_url)
        self._file_load_btn.clicked.connect(self._music_load_file)
        self._play_btn.clicked.connect(self._music_player.toggle_play_pause)
        self._stop_btn.clicked.connect(self._music_player.stop)
        self._volume_slider.valueChanged.connect(
            lambda v: self._music_player.set_volume(v / 100.0)
        )
        self._progress_slider.sliderMoved.connect(self._music_player.set_position)

        self._music_player.title_changed.connect(self._on_track_title)
        self._music_player.duration_changed.connect(self._on_track_duration)
        self._music_player.position_changed.connect(self._on_track_position)
        self._music_player.state_changed.connect(self._on_playback_state)
        self._music_player.error_occurred.connect(self._on_music_error)
        self._music_player.loading.connect(self._on_music_loading)

    # ── Callbacks ────────────────────────────────────────────────

    def _on_page_changed(self, page: str) -> None:
        pages = {"Clicker": 0, "Macros": 1, "Music": 2}
        self._stack.setCurrentIndex(pages.get(page, 0))

    def _show_theme_menu(self) -> None:
        menu = QMenu(self)
        for i, t in enumerate(ALL_THEMES):
            act = menu.addAction(t["name"])
            act.triggered.connect(lambda checked=False, idx=i: self._set_theme(idx))
        pos = self._theme_btn.mapToGlobal(self._theme_btn.rect().bottomLeft())
        menu.exec(pos)

    def _set_theme(self, idx: int) -> None:
        self._theme_idx = idx
        self._theme = ALL_THEMES[idx]
        self._theme_btn.setText(self._theme["name"])
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(build_stylesheet(t))
        self._roblox_toggle.set_colors(t["toggle_on"], t["toggle_off"], t["primary_glow"])
        self._cps_glow.setColor(QColor(t["primary"]))

        for w in self.findChildren(GlowButton):
            w.set_glow_color(QColor(t["primary"]))

        discord_color = QColor(t.get("discord", "#5865F2"))
        self._discord_btn.set_glow_color(discord_color)

    def _copy_discord(self) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText("123.456.789.100")
        self._toast.show_message("Discord copied!")

    def _show_bg_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Set Background").triggered.connect(self._set_custom_bg)
        if self._container.has_background:
            menu.addAction("Clear Background").triggered.connect(self._clear_custom_bg)
        pos = self._bg_btn.mapToGlobal(self._bg_btn.rect().bottomLeft())
        menu.exec(pos)

    def _set_custom_bg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif);;All Files (*)",
        )
        if path:
            self._container.set_background(path)

    def _clear_custom_bg(self) -> None:
        self._container.clear_background()

    def _on_mode_changed(self, mode: str) -> None:
        mode_lower = mode.lower()
        self._engine.set_mode(mode_lower)

        is_mixed = mode_lower == "mixed"
        self._mixed_card.setVisible(is_mixed)
        self._cps_widget.setVisible(not is_mixed)
        self._update_target_label()

    def _on_cps_changed(self, v: int) -> None:
        self._engine.set_cps(float(v))
        self._presets.clear_active()
        self._update_target_label()

    def _on_range_changed(self) -> None:
        self._engine.set_cps_range(
            float(self._min_spin.value()),
            float(self._max_spin.value()),
        )
        self._update_target_label()

    def _on_preset(self, v: int) -> None:
        self._cps_spin.setValue(v)
        self._engine.set_cps(float(v))
        self._update_target_label()

    def _update_target_label(self) -> None:
        mode = self._mode_tabs.current().lower()
        if mode == "mixed":
            self._target_label.setText(
                f"Target: {self._min_spin.value()} – {self._max_spin.value()} CPS"
            )
        else:
            self._target_label.setText(f"Target: {self._cps_spin.value()} CPS")

    def _start_bind(self, target: str) -> None:
        if target == "click":
            if self._stack.currentIndex() == 1:
                self._macro_bind_btn.setText("...")
            else:
                self._bind_btn.setText("...")
        else:
            self._hide_btn.setText("...")
        self._bind_listener.start_listening(target)

    def _clear_bind(self, target: str) -> None:
        self._bind_listener.clear_bind(target)
        if target == "click":
            self._bind_display.setText("—")
            self._bind_clear_btn.setVisible(False)
            self._engine.stop()
            self._toggle_active = False
        else:
            self._hide_display.setText("—")
            self._hide_clear_btn.setVisible(False)

    def _on_bind_set(self, name: str, meta: object) -> None:
        _, _, target = meta
        if target == "click":
            if self._stack.currentIndex() == 1:
                self._macro_bind_btn.setText("Set Bind")
                self._macro_bind_display.setText(name)
            else:
                self._bind_btn.setText("Set Bind")
                self._bind_display.setText(name)
                self._bind_clear_btn.setVisible(True)
        else:
            self._hide_btn.setText("Set Bind")
            self._hide_display.setText(name)
            self._hide_clear_btn.setVisible(True)

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
        if self._stack.currentIndex() == 1:
            self._on_macro_bind_pressed()
            return
        if self._hold_mode:
            self._engine.start()
        else:
            self._toggle_active = not self._toggle_active
            if self._toggle_active:
                self._engine.start()
            else:
                self._engine.stop()

    def _on_bind_released(self) -> None:
        if self._stack.currentIndex() == 1:
            self._on_macro_bind_released()
            return
        if self._hold_mode:
            self._engine.stop()

    def _on_hide_toggle(self) -> None:
        if self._hidden:
            self._animate_show()
        else:
            self._animate_hide()

    def _on_cps_update(self, cps: float) -> None:
        self._cps_label.setText(f"{cps:.1f}")

    def _on_status_changed(self, active: bool) -> None:
        color = self._theme["success"] if active else self._theme["primary"]
        self._cps_glow.setColor(QColor(color))

    # ── Macro callbacks ──────────────────────────────────────────

    def _set_macro_hold_mode(self, hold: bool) -> None:
        self._macro_hold_mode = hold
        if hold:
            self._macro_hold_btn.setObjectName("modeTabActive")
            self._macro_toggle_btn.setObjectName("modeTab")
        else:
            self._macro_hold_btn.setObjectName("modeTab")
            self._macro_toggle_btn.setObjectName("modeTabActive")
        for btn in (self._macro_hold_btn, self._macro_toggle_btn):
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if not hold:
            self._macro_toggle_active = False
            self._macro_engine.stop()

    def _on_macro_bind_pressed(self) -> None:
        self._sync_macro_engine()
        if self._macro_hold_mode:
            self._macro_engine.start()
        else:
            self._macro_toggle_active = not self._macro_toggle_active
            if self._macro_toggle_active:
                self._macro_engine.start()
            else:
                self._macro_engine.stop()

    def _on_macro_bind_released(self) -> None:
        if self._macro_hold_mode:
            self._macro_engine.stop()

    def _sync_macro_engine(self) -> None:
        macros = [(raw_key, delay) for raw_key, _, delay in self._macro_data]
        self._macro_engine.set_macros(macros)

    def _macro_start_add(self) -> None:
        self._macro_add_btn.setText("Press key...")
        self._bind_listener.start_listening("macro_key")

    def _macro_on_key_captured(self, raw_key: object, name: str) -> None:
        self._macro_add_btn.setText("+ Add Key")
        self._macro_add_entry(raw_key, name, 1)

    def _macro_add_entry(self, raw_key: object, name: str, delay_ms: int) -> None:
        idx = len(self._macro_data)
        self._macro_data.append((raw_key, name, delay_ms))

        entry = MacroEntryWidget(idx, name, delay_ms, self._macro_list_widget)
        entry.delete_clicked.connect(self._macro_delete_entry)
        entry.delay_changed.connect(self._macro_delay_changed)

        self._macro_list_layout.insertWidget(
            self._macro_list_layout.count() - 1, entry
        )
        self._update_macro_count()

    def _macro_copy_last(self) -> None:
        if not self._macro_data:
            return
        raw_key, name, delay = self._macro_data[-1]
        self._macro_add_entry(raw_key, name, delay)

    def _macro_delete_entry(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._macro_data):
            return
        self._macro_data.pop(idx)

        item = self._macro_list_layout.itemAt(idx)
        if item and item.widget():
            item.widget().deleteLater()

        for i in range(self._macro_list_layout.count() - 1):
            item = self._macro_list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MacroEntryWidget):
                item.widget().set_index(i)
                item.widget().delete_clicked.disconnect()
                item.widget().delete_clicked.connect(self._macro_delete_entry)
                item.widget().delay_changed.disconnect()
                item.widget().delay_changed.connect(self._macro_delay_changed)

        self._update_macro_count()

    def _macro_delay_changed(self, idx: int, delay_ms: int) -> None:
        if idx < len(self._macro_data):
            raw_key, name, _ = self._macro_data[idx]
            self._macro_data[idx] = (raw_key, name, delay_ms)

    def _update_macro_count(self) -> None:
        n = len(self._macro_data)
        self._macro_count_label.setText(f"Macros: {n}")

    # ── Music callbacks ──────────────────────────────────────────

    def _music_load_url(self) -> None:
        url = self._url_input.text().strip()
        if not url:
            return
        self._music_player.play_url(url)

    def _music_load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma *.opus);;All Files (*)",
        )
        if path:
            self._music_player.play_file(path)

    def _on_track_title(self, title: str) -> None:
        display = title if len(title) <= 40 else title[:37] + "..."
        self._track_label.setText(display)

    def _on_track_duration(self, ms: int) -> None:
        self._progress_slider.setRange(0, ms)
        self._time_total.setText(self._format_time(ms))

    def _on_track_position(self, ms: int) -> None:
        if not self._progress_slider.isSliderDown():
            self._progress_slider.setValue(ms)
        self._time_current.setText(self._format_time(ms))

    def _on_playback_state(self, state: str) -> None:
        if state == "playing":
            self._play_btn.setText("❚❚")
        else:
            self._play_btn.setText("▶")

    def _on_music_error(self, msg: str) -> None:
        self._toast.show_message(f"Music: {msg[:30]}")

    def _on_music_loading(self, loading: bool) -> None:
        if loading:
            self._track_label.setText("Loading...")
            self._url_load_btn.setText("...")
        else:
            self._url_load_btn.setText("Load")

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
        self._macro_engine.shutdown()
        self._music_player.shutdown()
        self._bind_listener.shutdown()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self._engine.shutdown()
        self._macro_engine.shutdown()
        self._music_player.shutdown()
        self._bind_listener.shutdown()
        super().closeEvent(event)
