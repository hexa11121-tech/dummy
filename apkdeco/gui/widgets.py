"""Reusable viewer widgets: virtual hex view, code view, image preview, log."""
from __future__ import annotations

import math
import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from .theme import (CODE_FONT, SMALL_FONT, UI_FONT, apply_code_tags)

# ---------------------------------------------------------------------------
# 16x16 pixel icons generated at runtime (no image assets required)
# ---------------------------------------------------------------------------

_ICON_GRIDS = {
    "folder": (
        "................",
        "................",
        "..kkkk..........",
        ".kYYYYk.........",
        ".kYYYYkkkkkkkk..",
        ".kYYYYYYYYYYYYk.",
        ".kYYYYYYYYYYYYk.",
        ".kYYYYYYYYYYYYk.",
        ".kYYYYYYYYYYYYk.",
        ".kYYYYYYYYYYYYk.",
        ".kYYYYYYYYYYYYk.",
        ".kkkkkkkkkkkkkk.",
        "................",
        "................",
        "................",
        "................",
    ),
    "file": (
        "................",
        ".kkkkkkk........",
        ".kWWWWWkk.......",
        ".kWWWWWkWk......",
        ".kWWWWWkWWk.....",
        ".kWWWWWWWWWk....",
        ".kWWWWWWWWWk....",
        ".kWWWWWWWWWk....",
        ".kWWWWWWWWWk....",
        ".kWWWWWWWWWk....",
        ".kWWWWWWWWWk....",
        ".kkkkkkkkkkk....",
        "................",
        "................",
        "................",
        "................",
    ),
    "dex": (
        "................",
        ".kkkkkkkkkkkkk..",
        ".kGGGGGGGGGGGk..",
        ".kGGkkkkkkkGGk..",
        ".kGGk.....kGGk..",
        ".kGGk.....kGGk..",
        ".kGGk.....kGGk..",
        ".kGGk.....kGGk..",
        ".kGGk.....kGGk..",
        ".kGGkkkkkkkGGk..",
        ".kGGGGGGGGGGGk..",
        ".kkkkkkkkkkkkk..",
        "................",
        "................",
        "................",
        "................",
    ),
    "xml": (
        "................",
        ".kkkkkkkkk......",
        ".kBBBkBBBkk.....",
        ".kBBBkBBBBBk....",
        ".kBBkkkkBBBk....",
        ".kBBk...kBBk....",
        ".kBBkkkkkBBk....",
        ".kBBk...kBBk....",
        ".kBBkkkkkBBk....",
        ".kBBBBBBBBBk....",
        ".kkkkkkkkkkk....",
        "................",
        "................",
        "................",
        "................",
        "................",
    ),
    "bin": (
        "................",
        ".kkkkkkkkkkkk...",
        ".kPPPPPPPPPPk...",
        ".kPkkkPPkkkPk...",
        ".kPPPPPPPPPPk...",
        ".kPkkkkkkkkPk...",
        ".kPPPPPPPPPPk...",
        ".kPPkPPPPkPPk...",
        ".kPPPPkkPPPPk...",
        ".kPPPPPPPPPPk...",
        ".kkkkkkkkkkkk...",
        "................",
        "................",
        "................",
        "................",
        "................",
    ),
    "image": (
        "................",
        ".kkkkkkkkkkkkk..",
        ".kWWWWWWWWWWWk..",
        ".kWWkkkkkkkWWk..",
        ".kWkkCCCkkkWWk..",
        ".kWkCCCCCCkWWk..",
        ".kWWCCCCCCCWWk..",
        ".kWWkkkkkkCWWk..",
        ".kWWMMMkkkWWWk..",
        ".kWMMMMMkWWWWk..",
        ".kWWWWWWWWWWWk..",
        ".kkkkkkkkkkkkk..",
        "................",
        "................",
        "................",
        "................",
    ),
    "manifest": (
        "................",
        "..kkkkkkkkkkk...",
        ".kOOOOOOOOOOk...",
        ".kOkkOkkOkkOk...",
        ".kOOOOOOOOOOk...",
        ".kOkkkkkkkkOk...",
        ".kOOkOOOOkOOk...",
        ".kOOkOkkOkOOk...",
        ".kOOkOOOOkOOk...",
        ".kOkkkkkkkkOk...",
        ".kOOOOOOOOOOk...",
        ".kkkkkkkkkkkk...",
        "................",
        "................",
        "................",
        "................",
    ),
}


def make_icon(root, kind: str, palette: Dict[str, str]) -> tk.PhotoImage:
    img = tk.PhotoImage(width=16, height=16)
    colors = {
        "k": palette["border"],
        "Y": "#d9b23a", "y": "#b08d22",
        "W": palette["panel2"] if palette["text_bg"] != "#ffffff" else "#f8fafc",
        "G": "#5fb878", "B": "#5b9bd5", "P": "#a98bd6",
        "O": "#e39a4c", "C": "#4fb3c4", "M": "#d06fa8",
    }
    if palette["text_bg"] == "#ffffff":
        colors["W"] = "#ffffff"
    grid = _ICON_GRIDS.get(kind, _ICON_GRIDS["file"])
    for y, row in enumerate(grid):
        line = "{" + " ".join(colors.get(c, palette["bg"]) for c in row) + "}"
        img.put(line, to=(0, y, 16, y + 1))
    return img


class IconSet:
    """Lazily builds and keeps alive per-theme icon images."""

    def __init__(self, root, palette: Dict[str, str]) -> None:
        self._root = root
        self._pal = palette
        self._cache: Dict[str, tk.PhotoImage] = {}

    def get(self, kind: str) -> tk.PhotoImage:
        if kind not in self._cache:
            self._cache[kind] = make_icon(self._root, kind, self._pal)
        return self._cache[kind]


def icon_for_entry(name: str, group: str, is_dir: bool = False) -> str:
    if is_dir:
        return "folder"
    if group == "manifest" or name == "AndroidManifest.xml":
        return "manifest"
    if group == "dex" or name.endswith(".dex"):
        return "dex"
    if group == "arsc" or name.endswith(".arsc"):
        return "bin"
    lower = name.lower()
    if lower.endswith((".png", ".gif", ".bmp", ".jpg", ".jpeg", ".webp")):
        return "image"
    if lower.endswith((".xml", ".json", ".txt", ".html", ".js", ".css")):
        return "xml"
    return "file"


# ---------------------------------------------------------------------------
# Hex viewer (virtualized: renders only the visible window of rows)
# ---------------------------------------------------------------------------

HEX_ROW_BYTES = 16


def format_hex_rows(data: bytes, first_row: int, row_count: int) -> List[str]:
    rows: List[str] = []
    total = len(data)
    for i in range(row_count):
        off = (first_row + i) * HEX_ROW_BYTES
        if off >= total:
            break
        chunk = data[off:off + HEX_ROW_BYTES]
        hexpart = " ".join(f"{b:02x}" for b in chunk)
        hexpart = hexpart.ljust(HEX_ROW_BYTES * 3 - 1)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        rows.append(f"{off:08x}  {hexpart}  |{asc}|")
    return rows


class HexView(ttk.Frame):
    """Hex + ASCII dump with virtual scrolling (safe for huge buffers)."""

    VISIBLE_ROWS = 40

    def __init__(self, master, palette: Dict[str, str], **kw) -> None:
        super().__init__(master, **kw)
        self.palette = palette
        self.data = b""
        self.name = ""
        self._top_row = 0

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        self.info_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.info_var, style="Dim.TLabel").pack(
            side="left", padx=6, pady=3)
        ttk.Button(bar, text="Copy hex", command=self._copy_hex,
                   width=9).pack(side="right", padx=4, pady=2)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, font=CODE_FONT, bg=palette["line_bg"],
                            fg=palette["text_fg"], insertbackground=palette["text_fg"],
                            relief="flat", wrap="none", cursor="arrow",
                            state="disabled", takefocus=True)
        self.scroll = ttk.Scrollbar(body, orient="vertical", command=self._on_scroll)
        self.text.configure(yscrollcommand=self._scroll_set)
        self.text.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.text.bind("<MouseWheel>", self._wheel)
        self.text.bind("<Button-4>", self._wheel)
        self.text.bind("<Button-5>", self._wheel)

    # -- public -------------------------------------------------------------
    def set_data(self, data: bytes, name: str = "") -> None:
        self.data = data
        self.name = name
        self._top_row = 0
        self._update_info()
        self._render(0)

    def _update_info(self) -> None:
        n = len(self.data)
        self.info_var.set(f"{self.name or 'buffer'} - {n:,} bytes")

    def _total_rows(self) -> int:
        return max(1, math.ceil(len(self.data) / HEX_ROW_BYTES))

    def _render(self, top_row: int) -> None:
        total = self._total_rows()
        top = max(0, min(top_row, max(0, total - 1)))
        self._top_row = top
        rows = format_hex_rows(self.data, top, self.VISIBLE_ROWS)
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        if rows:
            t.insert("1.0", "\n".join(rows))
        else:
            t.insert("1.0", "(empty file)")
        t.configure(state="disabled")
        if total > 1:
            self.scroll.set(top / total, min(1, (top + self.VISIBLE_ROWS) / total))

    # -- scrolling ----------------------------------------------------------
    def _scroll_set(self, first: str, last: str) -> None:
        total = self._total_rows()
        top = self._top_row / total
        self.scroll.set(top, min(1, top + self.VISIBLE_ROWS / total))

    def _on_scroll(self, *args) -> None:
        total = self._total_rows()
        if not args:
            return
        cmd = args[0]
        if cmd == "moveto":
            self._render(int(float(args[1]) * total))
        elif cmd == "scroll":
            n = int(args[1])
            if args[2] == "pages":
                n *= self.VISIBLE_ROWS - 2
            self._render(self._top_row + n)

    def _wheel(self, event) -> None:
        if getattr(event, "num", 0) == 4 or event.delta > 0:
            self._render(self._top_row - 3)
        else:
            self._render(self._top_row + 3)
        return "break"

    def _copy_hex(self) -> None:
        rows = format_hex_rows(self.data, self._top_row, self.VISIBLE_ROWS)
        self.clipboard_clear()
        self.clipboard_append("\n".join(rows))


# ---------------------------------------------------------------------------
# Code / text viewer with find bar and light syntax tinting
# ---------------------------------------------------------------------------

_XML_RE = [
    ("tok_comment", re.compile(r"<!--.*?-->")),
    ("tok_tag", re.compile(r"</?[\w.:-]+")),
    ("tok_attr", re.compile(r"[\w.:-]+(?==)")),
    ("tok_str", re.compile(r"\"[^\"]*\"")),
]
_CODE_RE = [
    ("tok_comment", re.compile(r"(//.*$|#.*$|/\*.*?\*/)", re.M)),
    ("tok_kw", re.compile(r"\b(public|private|protected|class|interface|extends|"
                          r"implements|static|final|void|return|new|import|package|"
                          r"if|else|for|while|try|catch|throw|throws|const|enum|"
                          r".method|\.class|\.field|\.registers|super|this|"
                          r"invoke-\w+|move-\w+|const-\w+|iput|iget|sput|sget)\b")),
    ("tok_type", re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")),
    ("tok_num", re.compile(r"\b(0x[0-9a-fA-F]+|\d+)\b")),
    ("tok_str", re.compile(r"\"[^\"]*\"")),
]

MAX_HIGHLIGHT_CHARS = 400_000


class CodeView(ttk.Frame):
    """Read-only text viewer with search and basic highlighting."""

    def __init__(self, master, palette: Dict[str, str], **kw) -> None:
        super().__init__(master, **kw)
        self.palette = palette
        self._hits: List[int] = []
        self._hit_index = -1

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text="Find:", style="Dim.TLabel").pack(side="left", padx=(6, 2))
        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(bar, textvariable=self.find_var, width=28)
        self.find_entry.pack(side="left", padx=2, pady=3)
        self.find_entry.bind("<Return>", lambda e: self.find_next())
        ttk.Button(bar, text="Next", width=5, command=self.find_next).pack(
            side="left", padx=2)
        ttk.Button(bar, text="Prev", width=5, command=self.find_prev).pack(
            side="left", padx=2)
        ttk.Button(bar, text="Copy all", width=8, command=self._copy_all).pack(
            side="right", padx=6, pady=2)
        self.status_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.status_var, style="Dim.TLabel").pack(
            side="right", padx=6)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, font=CODE_FONT, bg=palette["text_bg"],
                            fg=palette["text_fg"], insertbackground=palette["text_fg"],
                            selectbackground=palette["select_bg"],
                            selectforeground=palette["select_fg"],
                            relief="flat", wrap="none", undo=False,
                            tabs=("2.2c",))
        scroll_y = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        scroll_x = ttk.Scrollbar(body, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.text.configure(state="disabled")
        apply_code_tags(self.text, palette)
        self.text.bind("<Control-f>", lambda e: (self.find_entry.focus_set(), "break")[1])

    def set_text(self, content: str, highlight: str = "auto", name: str = "") -> None:
        self._hits = []
        self._hit_index = -1
        self.status_var.set(f"{len(content):,} chars")
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        truncated = content[:MAX_HIGHLIGHT_CHARS]
        t.insert("1.0", truncated)
        if len(content) > MAX_HIGHLIGHT_CHARS:
            t.insert("end", f"\n\n/* ... preview truncated ({len(content):,} chars total) ... */",
                     "tok_comment")
        if highlight == "auto":
            lower = name.lower()
            if lower.endswith(".xml") or content.lstrip().startswith("<?xml") \
                    or content.lstrip().startswith("<manifest"):
                highlight = "xml"
            elif lower.endswith((".java", ".smali", ".kt", ".js", ".py", ".gradle")):
                highlight = "code"
            else:
                highlight = "none"
        if highlight in ("xml", "code"):
            self._highlight(_XML_RE if highlight == "xml" else _CODE_RE)
        t.configure(state="disabled")

    def _highlight(self, rules) -> None:
        text = self.text.get("1.0", "end-1c")
        for tag, regex in rules:
            for m in regex.finditer(text):
                start = f"1.0+{m.start()}c"
                end = f"1.0+{m.end()}c"
                self.text.tag_add(tag, start, end)

    # -- find ---------------------------------------------------------------
    def find_next(self) -> None:
        self._find(step=1)

    def find_prev(self) -> None:
        self._find(step=-1)

    def _find(self, step: int) -> None:
        needle = self.find_var.get()
        t = self.text
        if not needle:
            return
        if not self._hits:
            content = t.get("1.0", "end-1c")
            start = 0
            low_content = content.lower()
            low_needle = needle.lower()
            while True:
                i = low_content.find(low_needle, start)
                if i < 0:
                    break
                self._hits.append(i)
                start = i + max(1, len(needle))
            if not self._hits:
                self.status_var.set(f"0 hits for {needle!r}")
                return
            self._hit_index = -1
        self._hit_index = (self._hit_index + step) % len(self._hits)
        pos = self._hits[self._hit_index]
        t.tag_remove("hit", "1.0", "end")
        start = f"1.0+{pos}c"
        end = f"1.0+{pos + len(self.find_var.get())}c"
        t.tag_add("hit", start, end)
        t.see(start)
        self.status_var.set(f"hit {self._hit_index + 1}/{len(self._hits)}")

    def clear_hits_cache(self) -> None:
        self._hits = []
        self._hit_index = -1

    def _copy_all(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))

    def focus_find(self) -> None:
        self.find_entry.focus_set()
        self.find_entry.selection_range(0, "end")


# ---------------------------------------------------------------------------
# Image preview
# ---------------------------------------------------------------------------

class ImageView(ttk.Frame):
    def __init__(self, master, palette: Dict[str, str], **kw) -> None:
        super().__init__(master, **kw)
        self.palette = palette
        self.info_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.info_var, style="Dim.TLabel").pack(
            side="top", anchor="w", padx=6, pady=3)
        self.canvas = tk.Canvas(self, bg=palette["text_bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._photo: Optional[tk.PhotoImage] = None

    def set_image(self, data: bytes, name: str) -> None:
        import base64
        self.canvas.delete("all")
        self._photo = None
        try:
            photo = tk.PhotoImage(data=base64.b64encode(data).decode("ascii"))
        except tk.TclError:
            self.info_var.set(
                f"{name}: preview supports PNG/GIF only in the built-in viewer.\n"
                "Use 'jadx' or 'apktool' to decode all image formats.")
            return
        # subsample to fit ~1000x700
        w, h = photo.width(), photo.height()
        factor = 1
        while max(w // (factor + 1), 1) > 1000 or max(h // (factor + 1), 1) > 700:
            factor += 1
            if factor > 32:
                break
        if factor > 1:
            photo = photo.subsample(factor, factor)
        self._photo = photo
        self.canvas.create_image(8, 8, anchor="nw", image=photo)
        self.info_var.set(f"{name} - {w}x{h}"
                          + (f" (shown 1/{factor})" if factor > 1 else ""))


# ---------------------------------------------------------------------------
# Log panel
# ---------------------------------------------------------------------------

class LogPanel(ttk.Frame):
    def __init__(self, master, palette: Dict[str, str], **kw) -> None:
        super().__init__(master, **kw)
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text="Job log", style="Title.TLabel").pack(side="left", padx=6)
        ttk.Button(bar, text="Clear", width=6, command=self.clear).pack(
            side="right", padx=4, pady=2)
        ttk.Button(bar, text="Copy", width=6, command=self._copy).pack(
            side="right", padx=2, pady=2)
        self.text = tk.Text(bar.master, height=8, font=CODE_FONT,
                            bg=palette["log_bg"], fg=palette["text_fg"],
                            insertbackground=palette["text_fg"],
                            relief="flat", wrap="none", state="disabled")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def append(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.text.get("1.0", "end-1c"))


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

class StatusBar(ttk.Frame):
    def __init__(self, master, **kw) -> None:
        super().__init__(master, style="Panel.TFrame", **kw)
        self.left = tk.StringVar(value="Ready")
        self.right = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.left, style="Status.TLabel",
                  anchor="w").pack(side="left", fill="x", expand=True, padx=8, pady=3)
        self.progress = ttk.Progressbar(self, mode="indeterminate", length=140)
        ttk.Label(self, textvariable=self.right, style="Status.TLabel",
                  anchor="e").pack(side="right", padx=8)

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.progress.pack(side="right", padx=8, pady=3)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.forget()


def hexdump_preview(data: bytes, length: int = 256) -> str:
    return "\n".join(format_hex_rows(data[:length], 0, math.ceil(min(length, len(data)) / 16)))
