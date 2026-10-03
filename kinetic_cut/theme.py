"""Theme definitions and stylesheet generator for Kinetic Cut.

Three workspace palettes: Default, Obsidian and Ableton Grey.
Saved IDs remain stable; retired or unknown IDs safely resolve to Default.

Includes comprehensive component styling, seamless tree highlights without
branch boxes, dynamic icon color tokens, and theme-matched canvas/timeline tokens.
"""
from typing import Any

PALETTES: dict[str, dict[str, Any]] = {
    "default": {
        "id": "default",
        "name": "DaVinci Dark (Default)",
        "tagline": "Professional post-production charcoal dark workspace",
        "is_light": False,
        "bg_main": "#1b1c20",
        "bg_topbar": "#1d1e22",
        "bg_panel": "#202126",
        "bg_viewer": "#1f2024",
        "bg_timeline": "#1b1c20",
        "bg_surface": "#24252a",
        "bg_input": "#1d1e22",
        "bg_selected": "#404550",
        "bg_hover": "#32343a",
        "border": "#111216",
        "border_subtle": "#282b32",
        "text_main": "#f2f3f5",
        "text_sub": "#9397a0",
        "text_selected": "#ffffff",
        "accent": "#dc7465",
        "accent_hover": "#ed8878",
        "slider_groove": "#15161a",
        "slider_handle": "#96999e",
        "scroll_handle": "#555a64",
        "icon_color": "#d8dae0",
        "icon_sub_color": "#9397a0",
        "effect_icon_color": "#8ba2bd",
        "viewer_bg": "#191a1d",
        "timeline_bg": "#191a1e",
        "timeline_track_bg": "#202126",
        "timeline_track_alt": "#1c1d22",
        "timeline_header_bg": "#2b2c31",
        "timeline_ruler_bg": "#26272c",
        "timeline_divider": "#0b0c0f",
        "timeline_text": "#eef0f3",
        "swatch1": "#1b1c20",
        "swatch2": "#202126",
        "swatch3": "#dc7465",
        "swatch4": "#f2f3f5",
        "bg_tool_checked": "#2c303c",
        "text_tool_checked": "#ffffff",
        "nav_edit_color": "#e0796b",
        "nav_deliver_color": "#68a8df",
        "nav_phone_color": "#8bbce3",
        "nav_inactive_color": "#8b919e",
    },
    "ableton_gray": {
        "id": "ableton_gray",
        "name": "Ableton Studio Gray",
        "tagline": "Authentic matte neutral studio gray inspired by Ableton Live",
        "is_light": True,
        "bg_main": "#8c8c8c",
        "bg_topbar": "#808080",
        "bg_panel": "#888888",
        "bg_viewer": "#767676",
        "bg_timeline": "#7a7a7a",
        "bg_surface": "#969696",
        "bg_input": "#707070",
        "bg_selected": "#2d2d2d",
        "bg_hover": "#767676",
        "border": "#4c4c4c",
        "border_subtle": "#606060",
        "text_main": "#101010",
        "text_sub": "#262626",
        "text_selected": "#ffffff",
        "accent": "#ff764d",
        "accent_hover": "#ff8d69",
        "bg_tool_checked": "#ff764d",
        "text_tool_checked": "#101010",
        "slider_groove": "#545454",
        "slider_handle": "#222222",
        "scroll_handle": "#4a4a4a",
        "icon_color": "#141414",
        "icon_sub_color": "#2c2c2c",
        "effect_icon_color": "#1a1a1a",
        "viewer_bg": "#727272",
        "timeline_bg": "#7a7a7a",
        "timeline_track_bg": "#6a6a6a",
        "timeline_track_alt": "#646464",
        "timeline_header_bg": "#585858",
        "timeline_ruler_bg": "#6e6e6e",
        "timeline_divider": "#444444",
        "timeline_text": "#ffffff",
        "swatch1": "#8c8c8c",
        "swatch2": "#808080",
        "swatch3": "#ff764d",
        "swatch4": "#101010",
        "nav_edit_color": "#ff764d",
        "nav_deliver_color": "#ff764d",
        "nav_phone_color": "#ff764d",
        "nav_inactive_color": "#1c1c1c",
    },
    "final_cut_obsidian": {
        "id": "final_cut_obsidian",
        "name": "Final Cut Obsidian",
        "tagline": "Deep macOS obsidian dark with refined cool graphite panels",
        "is_light": False,
        "bg_main": "#121214",
        "bg_topbar": "#161619",
        "bg_panel": "#1b1b1f",
        "bg_viewer": "#0c0c0e",
        "bg_timeline": "#121214",
        "bg_surface": "#222226",
        "bg_input": "#161619",
        "bg_selected": "#283b54",
        "bg_hover": "#2e2e34",
        "border": "#0a0a0c",
        "border_subtle": "#2a2a30",
        "text_main": "#f0f0f4",
        "text_sub": "#8c8c94",
        "text_selected": "#ffffff",
        "accent": "#388bfd",
        "accent_hover": "#58a6ff",
        "bg_tool_checked": "#388bfd",
        "text_tool_checked": "#ffffff",
        "slider_groove": "#0e0e11",
        "slider_handle": "#909098",
        "scroll_handle": "#484850",
        "icon_color": "#f0f0f4",
        "icon_sub_color": "#8c8c94",
        "effect_icon_color": "#388bfd",
        "viewer_bg": "#0e0e10",
        "timeline_bg": "#101012",
        "timeline_track_bg": "#18181c",
        "timeline_track_alt": "#141417",
        "timeline_header_bg": "#202026",
        "timeline_ruler_bg": "#19191e",
        "timeline_divider": "#09090a",
        "timeline_text": "#f0f0f4",
        "swatch1": "#121214",
        "swatch2": "#1b1b1f",
        "swatch3": "#388bfd",
        "swatch4": "#f0f0f4",
        "nav_edit_color": "#388bfd",
        "nav_deliver_color": "#388bfd",
        "nav_phone_color": "#388bfd",
        "nav_inactive_color": "#8c8c94",
    },
}

# Keep persisted IDs stable; retired IDs deliberately fall back to Default.
PALETTES = {key: PALETTES[key] for key in ('default', 'final_cut_obsidian', 'ableton_gray')}
PALETTES['default'].update(name='Default', tagline='Familiar charcoal, warm coral accents.')
PALETTES['final_cut_obsidian'].update(name='Obsidian', tagline='Deep graphite, crisp blue accents.')
PALETTES['ableton_gray'].update(
    name='Ableton Grey', tagline='Matte studio grey, dark ink, orange accents.',
    bg_main='#999999', bg_topbar='#969696', bg_panel='#a3a3a3', bg_surface='#adadad',
    bg_input='#b9b9b9', bg_hover='#bcbcbc', bg_viewer='#858585',
    text_sub='#303030', icon_sub_color='#303030',
    timeline_header_bg='#969696', timeline_ruler_bg='#a3a3a3', timeline_text='#101010',
    slider_handle='#242424', viewer_bg='#505050',
)
for _p in PALETTES.values():
    _light = _p['is_light']
    _p.update(
        text_disabled='#505050' if _light else '#858991',
        accent_text='#101010',
        accent_ink='#762600' if _light else _p['accent'],
        info='#0b2c4d' if _light else '#8fbbe7',
        success='#06351a' if _light else '#75d99c',
        warning='#492900' if _light else '#f3cf7c',
        danger='#5b1018' if _light else '#ff9399',
        success_bg='#a8b9ab' if _light else '#192d23',
        danger_bg='#c7aaa9' if _light else '#302027',
        on_badge='#ffffff', badge_bg='#245c38' if _light else '#25663e',
        warning_badge='#775000' if _light else '#775716',
        on_dark='#c6ceda',
        tab_icon=_p['icon_color'],
        progress_fill=_p['accent'] if _light else '#205ba4' if _p['id']=='final_cut_obsidian' else '#a64739',
    )

THEME_DEFINITIONS = [
    {
        "id": p["id"],
        "name": p["name"],
        "tagline": p["tagline"],
        "swatches": [p["swatch1"], p["swatch2"], p["swatch3"], p["swatch4"]],
    }
    for p in PALETTES.values()
]


def get_active_theme_palette(theme_key: str = "default") -> dict[str, Any]:
    """Retrieve color palette dictionary for the given theme key."""
    return PALETTES.get(theme_key) or PALETTES["default"]


def get_icon_color(theme_key: str = "default") -> str:
    """Retrieve primary icon color for the given theme."""
    p = get_active_theme_palette(theme_key)
    return str(p.get("icon_color", "#d8dae0"))


def get_theme_stylesheet(theme_key: str = "default") -> str:
    p = PALETTES.get(theme_key) or PALETTES["default"]
    is_light = bool(p.get("is_light", False))
    tab_border = p["accent"]

    return f"""
/* --- Core Base --- */
* {{ font-family: "Segoe UI", "Segoe UI Variable", sans-serif; font-size: 11px; }}
QMainWindow, QWidget {{ background: {p["bg_main"]}; color: {p["text_main"]}; }}
QLabel {{ background: transparent; color: {p["text_main"]}; }}

/* --- Toolbars & Panels --- */
QFrame#topbar {{ background: {p["bg_topbar"]}; border-bottom: 1px solid {p["border"]}; }}
QWidget#viewerPanel {{ background: {p["bg_viewer"]}; }}
QWidget#timelinePanel {{ background: {p["bg_timeline"]}; border-top: 1px solid {p["border"]}; }}
QWidget#pageFooter {{ background: {p["bg_topbar"]}; border-top: 1px solid {p["border"]}; }}

/* --- Media Pool & Power Bins Headers & Trees --- */
QLabel#mediaPoolTitle {{
    color: {p["text_main"]};
    font-size: 14px;
    font-weight: 700;
    padding: 7px 6px;
    border-bottom: 1px solid {p["border"]};
}}
QLabel#powerBinsTitle, QLabel#panelTitle, QLabel#inspectorFilename {{
    background: {p["bg_panel"]};
    border-bottom: 1px solid {p["border"]};
    color: {p["text_main"]};
    font-size: 13px;
    font-weight: 700;
    padding: 6px 8px;
}}

/* --- Continuous Selection Tree Widgets (Zero empty branch boxes) --- */
QTreeWidget {{
    show-decoration-selected: 1;
    background: {p["bg_surface"]};
    color: {p["text_main"]};
    border: none;
    font-size: 13px;
    font-weight: 500;
}}
QTreeWidget#poolFolderTree, QTreeWidget#powerFolderTree {{
    show-decoration-selected: 1;
    background: {p["bg_surface"]};
    border: none;
    font-size: 13px;
    font-weight: 500;
}}
QTreeWidget::branch {{
    background: transparent;
}}
QTreeWidget::branch:selected,
QTreeWidget#poolFolderTree::branch:selected,
QTreeWidget#powerFolderTree::branch:selected {{
    background: {p["bg_selected"]};
}}
QTreeWidget::branch:hover,
QTreeWidget#poolFolderTree::branch:hover,
QTreeWidget#powerFolderTree::branch:hover {{
    background: {p["bg_hover"]};
}}
QTreeWidget::item,
QTreeWidget#poolFolderTree::item,
QTreeWidget#powerFolderTree::item {{
    height: 25px;
    padding: 3px 5px;
    margin: 0px;
    border: none;
    border-radius: 0px;
    color: {p["text_main"]};
}}
QTreeWidget::item:hover,
QTreeWidget#poolFolderTree::item:hover,
QTreeWidget#powerFolderTree::item:hover {{
    background: {p["bg_hover"]};
    color: {p["text_main"]};
    border: none;
    border-radius: 0px;
}}
QTreeWidget::item:selected,
QTreeWidget#poolFolderTree::item:selected,
QTreeWidget#powerFolderTree::item:selected {{
    background: {p["bg_selected"]};
    color: {p["text_selected"]};
    border: none;
    border-radius: 0px;
}}

/* --- Controls & ToolButtons --- */
QToolButton {{ background: {p["bg_panel"]}; border: 0; padding: 5px; color: {p["text_main"]}; border-radius: 4px; }}
QToolButton:hover {{ background: {p["bg_hover"]}; }}
QToolButton:checked {{ background: {p["bg_selected"]}; color: {p["text_selected"]}; border-bottom: 2px solid {p["accent"]}; }}
QToolButton[editorTool="true"]:checked {{ background: {p.get("bg_tool_checked", p["bg_selected"])}; border: 1px solid {p["accent"]}; color: {p.get("text_tool_checked", p["text_selected"])}; }}
QToolButton[panelToggle="true"] {{ background: {p["bg_panel"]}; color: {p["text_main"]}; padding: 7px 9px; }}
QToolButton[panelToggle="true"]:hover {{ background: {p["bg_hover"]}; color: {p["text_main"]}; }}
QToolButton[panelToggle="true"]:checked {{ background: {p["bg_selected"]}; border-bottom: 2px solid {p["accent"]}; color: {p["text_selected"]}; }}
QToolButton[pageNav="true"] {{ background: transparent; color: {p["text_sub"]}; padding: 3px 12px; }}
QToolButton[pageNav="true"]:hover {{ background: {p["bg_hover"]}; color: {p["text_main"]}; }}
QToolButton[pageNav="true"]:checked {{ background: {p["bg_selected"]}; border-bottom: 2px solid {p["accent"]}; color: {p["text_selected"]}; }}
QToolButton:disabled {{ color: {p["text_sub"]}; background: transparent; border-color: transparent; }}

/* --- Buttons --- */
QPushButton {{
    border: 1px solid {p["border_subtle"]};
    background: {p["bg_panel"]};
    color: {p["text_main"]};
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {p["bg_hover"]}; border-color: {p["accent"]}; }}
QPushButton:pressed {{ background: {p["bg_input"]}; border-color: {p["accent"]}; }}
QPushButton[accent="true"] {{
    background: {p["accent"]};
    color: {p['accent_text']};
    border-color: {p["accent_hover"]};
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {p["accent_hover"]}; }}
QPushButton[quiet="true"] {{ background: transparent; border: 0; color: {p["text_main"]}; font-weight: 500; }}
QPushButton[quiet="true"]:hover {{ background: {p["bg_hover"]}; color: {p["text_main"]}; }}
QPushButton:disabled {{ background: {p["bg_input"]}; color: {p["text_sub"]}; border-color: {p["border"]}; }}

/* --- Inputs --- */
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
    background: {p["bg_input"]};
    color: {p["text_main"]};
    border: 1px solid {p["border"]};
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: {p["bg_selected"]};
    selection-color: {p["text_selected"]};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
    border-color: {p["accent"]};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {p["text_sub"]};
    background: {p["bg_panel"]};
    border-color: {p["border"]};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {p["bg_panel"]};
    width: 16px;
    border-color: {p["border"]};
}}

/* --- ComboBox --- */
QComboBox {{
    background: {p["bg_input"]};
    color: {p["text_main"]};
    border: 1px solid {p["border"]};
    border-radius: 4px;
    padding: 4px 8px;
    padding-right: 24px;
    min-height: 20px;
    selection-background-color: {p["bg_selected"]};
    selection-color: {p["text_selected"]};
}}
QComboBox:hover {{
    border-color: {p["accent"]};
    background: {p["bg_hover"]};
}}
QComboBox:focus, QComboBox:on {{
    border-color: {p["accent"]};
}}
QComboBox:disabled {{
    color: {p["text_sub"]};
    background: {p["bg_panel"]};
    border-color: {p["border"]};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid {p["border_subtle"]};
    background: {p["bg_panel"]};
    border-top-right-radius: 4px;
    border-bottom-right-radius: 4px;
}}
QComboBox::drop-down:hover {{
    background: {p["bg_hover"]};
}}
QComboBox::down-arrow {{
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {p["text_main"]};
    margin: auto;
}}
QComboBox QAbstractItemView {{
    background-color: {p["bg_surface"]};
    color: {p["text_main"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["bg_selected"]};
    selection-color: {p["text_selected"]};
    selection-color: {p["text_selected"]};
    outline: 0;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    min-height: 22px;
    padding: 3px 8px;
    border-radius: 3px;
    color: {p["text_main"]};
    background: transparent;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {p["bg_hover"]};
    color: {p["text_main"]};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {p["bg_selected"]};
    color: {p["text_selected"]};
}}

/* --- Views, Lists, Tables, Trees --- */
QListWidget, QTableWidget {{
    background: {p["bg_surface"]};
    color: {p["text_main"]};
    border: 1px solid {p["border"]};
    font-size: 12px;
}}
QListWidget::item {{
    padding: 5px;
    margin: 1px;
    border-radius: 3px;
    color: {p["text_main"]};
}}
QListWidget::item:hover {{
    background: {p["bg_hover"]};
    color: {p["text_main"]};
}}
QListWidget::item:selected {{
    background: {p["bg_selected"]};
    color: {p["text_selected"]};
}}
QTreeWidget {{
    background: {p["bg_surface"]};
    color: {p["text_main"]};
    border: 1px solid {p["border"]};
    font-size: 12px;
    show-decoration-selected: 1;
    outline: 0;
}}
QTreeWidget::item {{
    padding: 4px 6px;
    border-radius: 3px;
    color: {p["text_main"]};
    border: none;
    outline: 0;
}}
QTreeWidget::item:hover {{
    background: {p["bg_hover"]};
    color: {p["text_main"]};
}}
QTreeWidget::item:selected {{
    background: {p["bg_selected"]};
    color: {p["text_selected"]};
    border: none;
    outline: 0;
}}
QTreeWidget::branch {{
    background: transparent;
    border: none;
    outline: 0;
}}
QTreeWidget::branch:selected {{
    background: {p["bg_selected"]};
    border: none;
    outline: 0;
}}
QHeaderView::section {{
    background: {p["bg_panel"]};
    color: {p["text_sub"]};
    border: none;
    border-bottom: 1px solid {p["border"]};
    padding: 5px 8px;
    font-weight: 600;
}}

/* --- Sliders --- */
QSlider::groove:horizontal {{ background: {p["slider_groove"]}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {p["slider_handle"]};
    border: 0;
    width: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {p["accent"]}; }}
QSlider::handle:horizontal:pressed {{ background: {p["accent_hover"]}; }}

/* --- ScrollBars --- */
QScrollBar:vertical, QScrollBar:horizontal {{ background: {p["bg_main"]}; border: none; }}
QScrollBar:vertical {{ width: 10px; }}
QScrollBar:horizontal {{ height: 10px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {p["scroll_handle"]};
    border-radius: 4px;
    min-height: 20px;
    min-width: 20px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {p["accent"]};
}}
QScrollBar::add-line, QScrollBar::sub-line {{ border: none; background: none; }}

/* --- Splitters, Menus, ToolTips --- */
QSplitter::handle {{ background: {p["border"]}; width: 3px; height: 3px; }}
QMenuBar {{ background: {p["bg_topbar"]}; color: {p["text_main"]}; }}
QMenuBar::item:selected {{ background: {p["bg_hover"]}; color: {p["text_selected"]}; }}
QMenu {{
    background: {p["bg_panel"]};
    color: {p["text_main"]};
    border: 1px solid {p["border_subtle"]};
    padding: 4px;
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 3px; }}
QMenu::item:selected {{ background: {p["bg_selected"]}; color: {p["text_selected"]}; }}
QMenu::item:disabled {{ color: {p["text_sub"]}; }}
QMenu::separator {{ height: 1px; background: {p["border"]}; margin: 4px 6px; }}
QToolTip {{
    background: {p["bg_panel"]};
    color: {p["text_main"]};
    border: 1px solid {p["border_subtle"]};
    padding: 6px;
    border-radius: 4px;
}}

/* --- Tabs --- */
QTabBar::tab {{
    background: {p["bg_panel"]};
    color: {p["text_sub"]};
    padding: 8px 12px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {p["text_main"]}; border-bottom-color: {tab_border}; font-weight: 600; }}
QTabBar::tab:disabled {{ color: {p["text_sub"]}; }}

/* --- Status & Progress --- */
QStatusBar {{ background: {p["bg_main"]}; border-top: 1px solid {p["border"]}; color: {p["text_sub"]}; }}
QProgressBar {{
    background: {p["bg_input"]};
    border: 1px solid {p["border_subtle"]};
    border-radius: 3px;
    color: {p["text_main"]};
    text-align: center;
}}
QProgressBar::chunk {{ background: {p['progress_fill']}; border-radius: 2px; }}

/* --- Effect Library & Special Widgets --- */
QListWidget#effectLibrary::item {{
    background: {p["bg_panel"]};
    border: 1px solid {p["border"]};
    border-radius: 3px;
    margin: 2px 3px;
    padding: 5px 7px;
}}
QListWidget#effectLibrary::item:hover {{ background: {p["bg_hover"]}; border-color: {p["accent"]}; }}
QListWidget#effectLibrary::item:selected {{ background: {p["bg_selected"]}; border-color: {p["accent"]}; }}
QLabel#reviewBadge {{ color: {p["accent_ink"]}; font-size: 11px; padding-left: 8px; }}
QLabel#jobStatus {{ color: {p["text_sub"]}; padding: 0 8px; }}
QToolButton#sectionEnabled {{ background: {p["bg_panel"]}; color: {p["text_sub"]}; border: 0; border-radius: 8px; padding: 0; margin-left: 4px; }}
QToolButton#sectionEnabled:checked {{ color: {p["accent_ink"]}; }}
QToolButton#sectionEnabled:hover {{ background: {p["bg_hover"]}; }}

/* --- Phone Connect Theming --- */
QWidget#phoneConnect {{ background: {p["bg_main"]}; }}
QFrame.panelCard {{ background: {p["bg_panel"]}; border: 1px solid {p["border_subtle"]}; border-radius: 8px; }}
QFrame#connectedCard {{ background: {p["bg_surface"]}; border: 1px solid {p["accent"]}; border-radius: 8px; }}
QFrame#phoneDrop {{ border: 1px dashed {p["border_subtle"]}; border-radius: 8px; background: {p["bg_panel"]}; }}
QFrame#phoneDrop[hover="true"] {{ border: 2px solid {p["accent"]}; background: {p["bg_hover"]}; }}

QPushButton.segmentedBtn {{
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    border-radius: 6px;
    border: 1px solid {p["border_subtle"]};
    background: {p["bg_panel"]};
    color: {p["text_main"]};
}}
QPushButton.segmentedBtn:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
    color: {p["text_main"]};
}}
QPushButton.segmentedBtn:checked {{
    border: 1px solid {p["accent"]};
    background: {p["bg_selected"]};
    color: {p["text_selected"]};
}}

QPushButton.actionCard {{
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    border: 1px solid {p["border_subtle"]};
    background: {p["bg_panel"]};
    color: {p["text_main"]};
    font-weight: 500;
}}
QPushButton.actionCard:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
    color: {p["text_main"]};
}}

QFrame#driveCard {{
    background: {p["bg_panel"]};
    border: 1px solid {p["border_subtle"]};
    border-radius: 8px;
}}
QFrame#driveCard:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
}}

QPushButton.crumbBtn {{
    background: transparent;
    border: 1px solid transparent;
    color: {p["text_sub"]};
    font-size: 12px;
    font-weight: 500;
    padding: 3px 8px;
    border-radius: 4px;
}}
QPushButton.crumbBtn:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
    color: {p["text_main"]};
}}

QPushButton.chipBtn {{
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 500;
    border-radius: 6px;
    border: 1px solid {p["border_subtle"]};
    background: {p["bg_panel"]};
    color: {p["text_main"]};
}}
QPushButton.chipBtn:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
    color: {p["text_main"]};
}}

QPushButton.utilityBtn {{
    padding: 6px 12px;
    border-radius: 6px;
    background: {p["bg_panel"]};
    border: 1px solid {p["border_subtle"]};
    color: {p["text_main"]};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton.utilityBtn:hover {{
    background: {p["bg_hover"]};
    border-color: {p["accent"]};
    color: {p["text_main"]};
}}

QPushButton.primaryActionBtn {{
    padding: 6px 14px;
    border-radius: 6px;
    background: {p["accent"]};
    border: 1px solid {p["accent_hover"]};
    color: {p['accent_text']};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton.primaryActionBtn:hover {{
    background: {p["accent_hover"]};
}}

QProgressBar#storageBar {{
    border: none;
    border-radius: 3px;
    background: {p["slider_groove"]};
}}
QProgressBar#storageBar::chunk {{
    border-radius: 3px;
    background: {p["accent"]};
}}

/* Shared states, including native dialogs and controls without local styles. */
QWidget:disabled {{ color: {p['text_disabled']}; }}
QAbstractItemView {{ selection-color: {p['text_selected']}; selection-background-color: {p['bg_selected']}; }}
QTextEdit, QPlainTextEdit {{ background: {p['bg_input']}; color: {p['text_main']}; selection-color: {p['text_selected']}; }}
QTabWidget::pane {{ border: 1px solid {p['border_subtle']}; }}
QTabBar#inspectorTabs::tab {{ padding: 8px 6px; }}
QWidget[inspectorSectionHeader="true"] {{ background: {p['bg_panel']}; border-bottom: 1px solid {p['border_subtle']}; }}
QToolButton[sectionToggle="true"] {{ text-align: left; color: {p['text_main']}; }}
QToolButton[sectionToggle="true"]:checked {{ background: {p['bg_panel']}; color: {p['text_main']}; border: none; }}
QGroupBox {{ border: 1px solid {p['border_subtle']}; border-radius: 4px; margin-top: 12px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; color: {p['text_main']}; padding: 0 5px; }}
QSlider::groove:vertical {{ background: {p['slider_groove']}; width: 4px; border-radius: 2px; }}
QSlider::handle:vertical {{ background: {p['slider_handle']}; height: 12px; margin: 0 -4px; border-radius: 6px; }}
QToolButton:focus, QPushButton:focus {{ border: 1px solid {p['accent_ink']}; }}
QPushButton[compact="true"] {{ padding: 2px; }}
"""


STYLESHEET = get_theme_stylesheet("default")
