"""Dark / light ttk themes and DPI awareness for Windows."""
from __future__ import annotations

import sys
from typing import Dict

PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#1e2027",
        "panel": "#242730",
        "panel2": "#2a2e39",
        "text_bg": "#16181e",
        "text_fg": "#d6dae5",
        "fg": "#d6dae5",
        "fg_dim": "#8b92a5",
        "border": "#343947",
        "accent": "#4fa3ff",
        "accent_fg": "#0d1017",
        "select_bg": "#2f4568",
        "select_fg": "#ffffff",
        "green": "#8fd19e",
        "orange": "#e3b34c",
        "red": "#ef6b73",
        "purple": "#b39ddb",
        "cyan": "#6fd3d3",
        "line_bg": "#1b1e25",
        "log_bg": "#12141a",
    },
    "light": {
        "bg": "#eef0f4",
        "panel": "#ffffff",
        "panel2": "#f4f6fa",
        "text_bg": "#ffffff",
        "text_fg": "#20242c",
        "fg": "#20242c",
        "fg_dim": "#6a7384",
        "border": "#c9cfdb",
        "accent": "#2563eb",
        "accent_fg": "#ffffff",
        "select_bg": "#cfe0ff",
        "select_fg": "#101418",
        "green": "#15803d",
        "orange": "#b45309",
        "red": "#b91c1c",
        "purple": "#6d28d9",
        "cyan": "#0e7490",
        "line_bg": "#f0f2f7",
        "log_bg": "#f7f8fb",
    },
}

UI_FONT = ("Segoe UI", 10)
UI_FONT_BOLD = ("Segoe UI", 10, "bold")
CODE_FONT = ("Consolas", 10)
CODE_FONT_BOLD = ("Consolas", 10, "bold")
SMALL_FONT = ("Segoe UI", 9)


def enable_dpi_awareness() -> None:
    """Best-effort DPI awareness so the UI is crisp on high-DPI Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:  # Per-monitor DPI awareness v2 (Win10 1703+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass


def apply_theme(root, theme_name: str) -> Dict[str, str]:
    """Apply ttk styles for the chosen palette. Returns the palette dict."""
    import tkinter as tk
    from tkinter import ttk

    pal = PALETTES.get(theme_name, PALETTES["dark"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=pal["bg"])
    style.configure(".", font=UI_FONT, background=pal["bg"], foreground=pal["fg"],
                    bordercolor=pal["border"], darkcolor=pal["bg"],
                    lightcolor=pal["bg"], troughcolor=pal["panel2"],
                    focuscolor=pal["accent"])
    style.configure("TFrame", background=pal["bg"])
    style.configure("Panel.TFrame", background=pal["panel"])
    style.configure("TLabel", background=pal["bg"], foreground=pal["fg"])
    style.configure("Panel.TLabel", background=pal["panel"], foreground=pal["fg"])
    style.configure("Dim.TLabel", background=pal["bg"], foreground=pal["fg_dim"])
    style.configure("Title.TLabel", background=pal["bg"], foreground=pal["fg"],
                    font=UI_FONT_BOLD)
    style.configure("TButton", background=pal["panel2"], foreground=pal["fg"],
                    borderwidth=1, focusthickness=1)
    style.map("TButton",
              background=[("active", pal["select_bg"]), ("disabled", pal["panel"])],
              foreground=[("disabled", pal["fg_dim"])])
    style.configure("Accent.TButton", background=pal["accent"],
                    foreground=pal["accent_fg"], font=UI_FONT_BOLD)
    style.map("Accent.TButton", background=[("active", pal["select_bg"])])
    style.configure("TEntry", fieldbackground=pal["text_bg"],
                    foreground=pal["text_fg"], insertcolor=pal["text_fg"])
    style.configure("TCombobox", fieldbackground=pal["text_bg"],
                    foreground=pal["text_fg"], background=pal["panel2"])
    style.configure("TNotebook", background=pal["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=pal["panel2"],
                    foreground=pal["fg"], padding=(10, 4), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", pal["panel"])],
              foreground=[("selected", pal["accent"])])
    style.configure("Treeview", background=pal["panel"],
                    fieldbackground=pal["panel"], foreground=pal["fg"],
                    borderwidth=0)
    style.map("Treeview",
              background=[("selected", pal["select_bg"])],
              foreground=[("selected", pal["select_fg"])])
    style.configure("Treeview.Heading", background=pal["panel2"],
                    foreground=pal["fg"], relief="flat")
    style.map("Treeview.Heading", background=[("active", pal["select_bg"])])
    style.configure("Horizontal.TProgressbar", background=pal["accent"],
                    troughcolor=pal["panel2"])
    style.configure("TPanedwindow", background=pal["border"])
    style.configure("TSeparator", background=pal["border"])
    style.configure("TCheckbutton", background=pal["bg"], foreground=pal["fg"])
    style.configure("TRadiobutton", background=pal["bg"], foreground=pal["fg"])
    style.configure("TLabelframe", background=pal["bg"], foreground=pal["fg"])
    style.configure("TLabelframe.Label", background=pal["bg"],
                    foreground=pal["fg_dim"])
    style.configure("Status.TLabel", background=pal["panel2"],
                    foreground=pal["fg_dim"], font=SMALL_FONT)
    return pal


def apply_code_tags(text_widget, pal: Dict[str, str]) -> None:
    """Configure syntax-highlight tags on a tk.Text widget."""
    t = text_widget
    t.tag_configure("tok_tag", foreground=pal["accent"])
    t.tag_configure("tok_attr", foreground=pal["cyan"])
    t.tag_configure("tok_str", foreground=pal["green"])
    t.tag_configure("tok_comment", foreground=pal["fg_dim"])
    t.tag_configure("tok_kw", foreground=pal["orange"])
    t.tag_configure("tok_type", foreground=pal["purple"])
    t.tag_configure("tok_num", foreground=pal["red"])
    t.tag_configure("hit", background=pal["select_bg"],
                    foreground=pal["select_fg"])
