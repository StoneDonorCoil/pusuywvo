"""Theme definitions and stylesheet generation."""

DARK = {
    "name": "Dark",
    "bg": "#0d0d1a",
    "surface": "#161628",
    "surface_hover": "#1e1e38",
    "surface_alt": "#1a1a30",
    "primary": "#5c6fff",
    "primary_hover": "#7c8bff",
    "primary_glow": "rgba(92,111,255,0.45)",
    "primary_glow_strong": "rgba(92,111,255,0.75)",
    "text": "#dcdce8",
    "text_sec": "#8585a0",
    "text_dim": "#505068",
    "border": "#282845",
    "input_bg": "#101025",
    "input_border": "#303050",
    "active_bg": "#252548",
    "toggle_off": "#303050",
    "toggle_on": "#5c6fff",
    "thumb": "#ffffff",
    "danger": "#ff5c5c",
    "success": "#4dd4c4",
    "card_shadow": "rgba(0,0,0,0.3)",
    "scroll_bg": "#101025",
    "scroll_handle": "#303050",
    "discord": "#5865F2",
    "toast_bg": "rgba(30,30,56,0.95)",
}

LIGHT = {
    "name": "Light",
    "bg": "#f5f5fa",
    "surface": "#ffffff",
    "surface_hover": "#eeeef6",
    "surface_alt": "#f8f8fc",
    "primary": "#6366f1",
    "primary_hover": "#4f46e5",
    "primary_glow": "rgba(99,102,241,0.30)",
    "primary_glow_strong": "rgba(99,102,241,0.55)",
    "text": "#1e1b4b",
    "text_sec": "#6b7280",
    "text_dim": "#9ca3af",
    "border": "#e5e7eb",
    "input_bg": "#f9fafb",
    "input_border": "#d1d5db",
    "active_bg": "#e0e7ff",
    "toggle_off": "#d1d5db",
    "toggle_on": "#6366f1",
    "thumb": "#ffffff",
    "danger": "#ef4444",
    "success": "#10b981",
    "card_shadow": "rgba(0,0,0,0.06)",
    "scroll_bg": "#f3f4f6",
    "scroll_handle": "#d1d5db",
    "discord": "#5865F2",
    "toast_bg": "rgba(255,255,255,0.95)",
}

MIDNIGHT = {
    "name": "Midnight",
    "bg": "#0a0e1a",
    "surface": "#111827",
    "surface_hover": "#1a2236",
    "surface_alt": "#141c2e",
    "primary": "#3b82f6",
    "primary_hover": "#60a5fa",
    "primary_glow": "rgba(59,130,246,0.40)",
    "primary_glow_strong": "rgba(59,130,246,0.70)",
    "text": "#e2e8f0",
    "text_sec": "#94a3b8",
    "text_dim": "#475569",
    "border": "#1e293b",
    "input_bg": "#0f172a",
    "input_border": "#1e293b",
    "active_bg": "#1e3a5f",
    "toggle_off": "#334155",
    "toggle_on": "#3b82f6",
    "thumb": "#ffffff",
    "danger": "#f87171",
    "success": "#34d399",
    "card_shadow": "rgba(0,0,0,0.35)",
    "scroll_bg": "#0f172a",
    "scroll_handle": "#334155",
    "discord": "#5865F2",
    "toast_bg": "rgba(15,23,42,0.95)",
}

ROSE = {
    "name": "Rose",
    "bg": "#1a0d14",
    "surface": "#231520",
    "surface_hover": "#2e1c28",
    "surface_alt": "#1f1219",
    "primary": "#e879a8",
    "primary_hover": "#f0a0c0",
    "primary_glow": "rgba(232,121,168,0.40)",
    "primary_glow_strong": "rgba(232,121,168,0.70)",
    "text": "#f0dde5",
    "text_sec": "#b0889a",
    "text_dim": "#6e4a5a",
    "border": "#3a2030",
    "input_bg": "#150a10",
    "input_border": "#3a2030",
    "active_bg": "#3a2038",
    "toggle_off": "#3a2030",
    "toggle_on": "#e879a8",
    "thumb": "#ffffff",
    "danger": "#ff6b8a",
    "success": "#6ee7b7",
    "card_shadow": "rgba(0,0,0,0.3)",
    "scroll_bg": "#150a10",
    "scroll_handle": "#3a2030",
    "discord": "#5865F2",
    "toast_bg": "rgba(35,21,32,0.95)",
}

FOREST = {
    "name": "Forest",
    "bg": "#0a1410",
    "surface": "#112018",
    "surface_hover": "#1a2e22",
    "surface_alt": "#0f1a14",
    "primary": "#34d399",
    "primary_hover": "#6ee7b7",
    "primary_glow": "rgba(52,211,153,0.40)",
    "primary_glow_strong": "rgba(52,211,153,0.70)",
    "text": "#d1fae5",
    "text_sec": "#86b098",
    "text_dim": "#4a6b56",
    "border": "#1a3828",
    "input_bg": "#081210",
    "input_border": "#1a3828",
    "active_bg": "#1a3830",
    "toggle_off": "#1a3828",
    "toggle_on": "#34d399",
    "thumb": "#ffffff",
    "danger": "#f87171",
    "success": "#34d399",
    "card_shadow": "rgba(0,0,0,0.3)",
    "scroll_bg": "#081210",
    "scroll_handle": "#1a3828",
    "discord": "#5865F2",
    "toast_bg": "rgba(17,32,24,0.95)",
}

ALL_THEMES = [DARK, LIGHT, MIDNIGHT, ROSE, FOREST]
THEME_NAMES = [t["name"] for t in ALL_THEMES]


def build_stylesheet(t: dict) -> str:
    return f"""
    QWidget#container {{
        background-color: {t['bg']};
        border-radius: 12px;
    }}
    QLabel {{
        color: {t['text']};
        background: transparent;
        font-family: 'Segoe UI', 'Inter', 'SF Pro Display', sans-serif;
    }}
    QLabel#sec {{
        color: {t['text_sec']};
        font-size: 11px;
    }}
    QLabel#dim {{
        color: {t['text_dim']};
        font-size: 11px;
    }}
    QLabel#cpsLive {{
        color: {t['primary']};
        font-size: 36px;
        font-weight: 700;
        font-family: 'Segoe UI', 'JetBrains Mono', monospace;
    }}
    QLabel#targetCps {{
        color: {t['text_sec']};
        font-size: 11px;
    }}
    QLabel#macroKey {{
        color: {t['primary']};
        font-size: 12px;
        font-weight: 600;
        background-color: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 4px;
        padding: 2px 6px;
    }}
    QLabel#macroCount {{
        color: {t['text_dim']};
        font-size: 10px;
    }}
    QLabel#toast {{
        color: {t['text']};
        background-color: {t['toast_bg']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 500;
    }}
    QPushButton {{
        background-color: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 500;
        font-family: 'Segoe UI', 'Inter', sans-serif;
    }}
    QPushButton:hover {{
        background-color: {t['surface_hover']};
        border-color: {t['primary']};
    }}
    QPushButton:pressed {{
        background-color: {t['active_bg']};
    }}
    QPushButton#primary {{
        background-color: {t['primary']};
        color: #ffffff;
        border: none;
    }}
    QPushButton#primary:hover {{
        background-color: {t['primary_hover']};
    }}
    QPushButton#modeTab {{
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#modeTabActive {{
        background-color: {t['primary']};
        color: #ffffff;
        border: 1px solid {t['primary']};
        border-radius: 6px;
        padding: 8px 16px;
        font-size: 12px;
        font-weight: 600;
    }}
    QPushButton#preset {{
        padding: 4px 2px;
        font-size: 11px;
        min-width: 0px;
        border-radius: 6px;
    }}
    QPushButton#presetActive {{
        background-color: {t['primary']};
        color: #ffffff;
        border: 1px solid {t['primary']};
        padding: 4px 2px;
        font-size: 11px;
        min-width: 0px;
        border-radius: 6px;
    }}
    QPushButton#iconBtn {{
        background-color: transparent;
        border: none;
        padding: 4px;
        border-radius: 4px;
        font-size: 14px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
    }}
    QPushButton#iconBtn:hover {{
        background-color: {t['surface_hover']};
    }}
    QPushButton#themeBtn {{
        background-color: {t['surface']};
        border: 1px solid {t['border']};
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 10px;
        font-weight: 500;
        min-height: 26px;
        max-height: 26px;
    }}
    QPushButton#themeBtn:hover {{
        background-color: {t['surface_hover']};
        border-color: {t['primary']};
    }}
    QPushButton#discordBtn {{
        background-color: {t['discord']};
        color: #ffffff;
        border: none;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 10px;
        font-weight: 600;
        min-height: 26px;
        max-height: 26px;
    }}
    QPushButton#discordBtn:hover {{
        background-color: #4752c4;
    }}
    QPushButton#closeBtn {{
        background-color: transparent;
        border: none;
        padding: 4px;
        border-radius: 4px;
        font-size: 14px;
        min-width: 28px;
        max-width: 28px;
        min-height: 28px;
        max-height: 28px;
        color: {t['text_sec']};
    }}
    QPushButton#closeBtn:hover {{
        background-color: {t['danger']};
        color: #ffffff;
    }}
    QPushButton#clearBindBtn {{
        background-color: transparent;
        border: 1px solid {t['border']};
        border-radius: 4px;
        padding: 0px;
        font-size: 9px;
        color: {t['text_dim']};
        min-width: 22px;
        max-width: 22px;
        min-height: 22px;
        max-height: 22px;
    }}
    QPushButton#clearBindBtn:hover {{
        background-color: {t['danger']};
        color: #ffffff;
        border-color: {t['danger']};
    }}
    QPushButton#macroDelBtn {{
        background-color: transparent;
        border: 1px solid {t['border']};
        border-radius: 4px;
        padding: 0px;
        font-size: 10px;
        color: {t['text_dim']};
    }}
    QPushButton#macroDelBtn:hover {{
        background-color: {t['danger']};
        color: #ffffff;
        border-color: {t['danger']};
    }}
    QPushButton#macroAddBtn {{
        background-color: {t['surface']};
        border: 1px dashed {t['border']};
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        color: {t['text_sec']};
    }}
    QPushButton#macroAddBtn:hover {{
        border-color: {t['primary']};
        color: {t['primary']};
    }}
    QSpinBox, QLineEdit {{
        background-color: {t['input_bg']};
        color: {t['text']};
        border: 1px solid {t['input_border']};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 13px;
        font-family: 'Segoe UI', 'JetBrains Mono', monospace;
    }}
    QSpinBox:focus, QLineEdit:focus {{
        border-color: {t['primary']};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 0px;
        border: none;
    }}
    QFrame#separator {{
        background-color: {t['border']};
        max-height: 1px;
    }}
    QFrame#card {{
        background-color: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 10px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {t['scroll_bg']};
        width: 6px;
        border-radius: 3px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t['scroll_handle']};
        min-height: 20px;
        border-radius: 3px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QMenu {{
        background-color: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 20px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: {t['primary']};
        color: #ffffff;
    }}
    """
