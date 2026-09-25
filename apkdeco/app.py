"""Application bootstrap: DPI awareness, Tk root, main window."""
from __future__ import annotations

import base64
import os
import sys
from typing import Optional


def resource_path(*parts: str) -> str:
    """Works both from source and inside a PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def run(open_path: Optional[str] = None) -> int:
    import tkinter as tk

    from .gui.main_window import MainWindow
    from .gui.theme import enable_dpi_awareness

    enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", max(1.0, root.winfo_fpixels("1i") / 96.0))
    except tk.TclError:
        pass

    # window icon (PNG asset if present, else generated pixel icon)
    try:
        icon_file = resource_path("assets", "icon.png")
        if os.path.isfile(icon_file):
            with open(icon_file, "rb") as f:
                photo = tk.PhotoImage(data=base64.b64encode(f.read()))
            root.iconphoto(True, photo)
            root._icon_photo = photo  # keep a reference
    except Exception:
        pass

    win = MainWindow(root)
    if open_path:
        root.after(200, lambda: win.open_apk(open_path))
    root.mainloop()
    return 0
