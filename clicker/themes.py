"""Theme definitions and stylesheet generation."""

DARK = {
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
}

LIGHT = {
    "bg": "#ededf4",
    "surface": "#ffffff",
    "surface_hover": "#e0e0ec",
    "surface_alt": "#f4f4fa",
    "primary": "#4a5cf7",
    "primary_hover": "#3a48e0",
    "primary_glow": "rgba(74,92,247,0.35)",
    "primary_glow_strong": "rgba(74,92,247,0.65)",
    "text": "#1a1a30",
    "text_sec": "#68688a",
    "text_dim": "#9898b0",
    "border": "#d0d0e0",
    "input_bg": "#f0f0f8",
    "input_border": "#c0c0d5",
    "active_bg": "#d8d8ec",
    "toggle_off": "#c0c0d0",
    "toggle_on": "#4a5cf7",
    "thumb": "#ffffff",
    "danger": "#ff4050",
    "success": "#28c870",
    "card_shadow": "rgba(0,0,0,0.08)",
}


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
        padding: 6px 10px;
        font-size: 11px;
        min-width: 42px;
        border-radius: 6px;
    }}
    QPushButton#presetActive {{
        background-color: {t['primary']};
        color: #ffffff;
        border: 1px solid {t['primary']};
        padding: 6px 10px;
        font-size: 11px;
        min-width: 42px;
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
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 500;
        min-height: 26px;
        max-height: 26px;
    }}
    QPushButton#themeBtn:hover {{
        background-color: {t['surface_hover']};
        border-color: {t['primary']};
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
    """
