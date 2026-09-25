"""Main application window: file tree, viewers, search, decompile actions."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from .. import __app_name__, __version__
from ..core.apk import (ApkFile, ApkError, GROUP_ORDER, EntryInfo, GROUP_DEX,
                        GROUP_MANIFEST, GROUP_OTHER, MAX_HEX_PREVIEW)
from ..core.jobs import JobRunner
from ..core.settings import Settings
from ..core import tools as tl
from .dialogs import AboutDialog, SettingsDialog, confirm_overwrite_dir
from .theme import (CODE_FONT, SMALL_FONT, UI_FONT, UI_FONT_BOLD,
                    apply_theme)
from .widgets import (CodeView, HexView, IconSet, ImageView, LogPanel,
                      StatusBar, icon_for_entry)

MAX_SEARCH_FILE_BYTES = 512 * 1024
MAX_TREE_ITEMS = 5000


class DexViewer(ttk.Frame):
    """Info / class tree / strings for one classesN.dex."""

    def __init__(self, master, apk: ApkFile, dex_name: str,
                 palette: Dict[str, str], icons: IconSet) -> None:
        super().__init__(master)
        self.palette = palette
        self.apk = apk
        try:
            self.dex = apk.dex(dex_name)
        except Exception as e:
            self.dex = None
            self.error = str(e)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        if self.dex is None:
            err = ttk.Frame(nb)
            ttk.Label(err, text=f"Could not parse {dex_name}:\n"
                                f"{getattr(self, 'error', '')}").pack(
                padx=12, pady=12)
            nb.add(err, text="Error")
            return

        # -- Info tab --
        info = CodeView(nb, palette)
        info.set_text(self.dex.info_text() + "\nClasses:\n" + "\n".join(
            f"  {c.name}" for c in self.dex.classes[:2000]),
            highlight="none", name=dex_name)
        nb.add(info, text="Info")

        # -- Classes tab --
        cls_frame = ttk.Frame(nb)
        tree = ttk.Treeview(cls_frame, columns=("info",), show="tree headings",
                            selectmode="browse")
        tree.heading("#0", text="Class / member")
        tree.heading("info", text="Details")
        tree.column("#0", width=420)
        tree.column("info", width=420)
        sy = ttk.Scrollbar(cls_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sy.set)
        tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.cls_tree = tree
        self._populate_classes(tree)
        tree.bind("<Double-1>", self._copy_member)
        nb.add(cls_frame, text=f"Classes ({len(self.dex.classes)})")

        # -- Strings tab --
        str_frame = ttk.Frame(nb)
        bar = ttk.Frame(str_frame)
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left", padx=6, pady=4)
        self.str_filter = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.str_filter, width=30)
        ent.pack(side="left", padx=2)
        ent.bind("<Return>", lambda e: self._populate_strings())
        ttk.Button(bar, text="Apply", width=6,
                   command=self._populate_strings).pack(side="left", padx=2)
        self.str_count = tk.StringVar()
        ttk.Label(bar, textvariable=self.str_count, style="Dim.TLabel").pack(
            side="right", padx=8)
        self.str_tree = ttk.Treeview(str_frame, columns=("s",), show="tree headings")
        self.str_tree.heading("#0", text="#")
        self.str_tree.heading("s", text="String")
        self.str_tree.column("#0", width=70, anchor="e")
        self.str_tree.column("s", width=700)
        sy2 = ttk.Scrollbar(str_frame, orient="vertical", command=self.str_tree.yview)
        self.str_tree.configure(yscrollcommand=sy2.set)
        self.str_tree.pack(side="left", fill="both", expand=True, pady=(2, 0))
        sy2.pack(side="right", fill="y", pady=(2, 0))
        self.str_tree.bind("<Double-1>", self._copy_string)
        self._populate_strings()
        nb.add(str_frame, text=f"Strings ({len(self.dex.strings)})")

    def _populate_classes(self, tree: ttk.Treeview) -> None:
        assert self.dex is not None
        tree.delete(*tree.get_children())
        for cls in self.dex.classes:
            label = cls.name
            sup = f"extends {cls.super_name}" if cls.super_name else ""
            node = tree.insert("", "end", text=label, open=False,
                               values=(f"{sup} [{len(cls.methods)} methods, "
                                       f"{len(cls.fields)} fields]"))
            for f in cls.fields:
                tree.insert(node, "end", text=f"  {f.signature()}", values=("field",))
            for m in cls.methods:
                tree.insert(node, "end", text=f"  {m.signature()}", values=("method",))

    def _populate_strings(self) -> None:
        assert self.dex is not None
        tree = self.str_tree
        tree.delete(*tree.get_children())
        needle = self.str_filter.get().lower()
        shown = 0
        for i, s in enumerate(self.dex.strings):
            if needle and needle not in s.lower():
                continue
            tree.insert("", "end", text=str(i), values=(s[:400],))
            shown += 1
            if shown >= MAX_TREE_ITEMS:
                break
        self.str_count.set(f"{shown} shown" + (" (capped)" if shown >= MAX_TREE_ITEMS else ""))

    def _copy_member(self, _event) -> None:
        item = self.cls_tree.focus()
        if not item:
            return
        text = self.cls_tree.item(item, "text").strip()
        self.clipboard_clear()
        self.clipboard_append(text)

    def _copy_string(self, _event) -> None:
        item = self.str_tree.focus()
        if not item:
            return
        s = self.str_tree.item(item, "values")[0]
        self.clipboard_clear()
        self.clipboard_append(s)


class EntryViewer(ttk.Frame):
    """Generic file viewer with Text / Hex / Image modes."""

    def __init__(self, master, apk: ApkFile, entry_name: str,
                 palette: Dict[str, str]) -> None:
        super().__init__(master)
        self.apk = apk
        self.entry_name = entry_name
        self.palette = palette

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        self.mode_var = tk.StringVar(value="auto")
        for mode, label in (("text", "Text"), ("hex", "Hex"), ("image", "Image")):
            ttk.Radiobutton(bar, text=label, value=mode, variable=self.mode_var,
                            command=self._refresh).pack(side="left", padx=4, pady=3)
        ttk.Button(bar, text="Save as...", width=9,
                   command=self._save_as).pack(side="right", padx=6, pady=2)
        info = apk._entry_map.get(entry_name)
        size_txt = f"{info.size:,} bytes" if info else "?"
        ttk.Label(bar, text=f"{entry_name}  ({size_txt})",
                  style="Dim.TLabel").pack(side="left", padx=10)

        self.holder = ttk.Frame(self)
        self.holder.pack(fill="both", expand=True)
        self.code = CodeView(self.holder, palette)
        self.hex = HexView(self.holder, palette)
        self.image = ImageView(self.holder, palette)
        self._auto_mode()
        self._refresh()

    def _auto_mode(self) -> None:
        name = self.entry_name
        data_head = b""
        try:
            with self.apk.zf.open(name) as f:
                data_head = f.read(8)
        except Exception:
            pass
        if self.apk.is_image(name):
            mode = "image"
        elif self.apk.is_textish(name) or data_head[:2] == b"\x03\x00":
            mode = "text"
        else:
            mode = "hex"
        self.mode_var.set(mode)

    def _refresh(self) -> None:
        for w in (self.code, self.hex, self.image):
            w.pack_forget()
        mode = self.mode_var.get()
        try:
            if mode == "text":
                self.code.set_text(self.apk.text_preview(self.entry_name),
                                   name=self.entry_name)
                self.code.pack(fill="both", expand=True)
            elif mode == "image":
                self.image.set_image(self.apk.read(self.entry_name),
                                     self.entry_name)
                self.image.pack(fill="both", expand=True)
            else:
                self.hex.set_data(self.apk.hex_preview(self.entry_name),
                                  self.entry_name)
                self.hex.pack(fill="both", expand=True)
        except Exception as e:
            self.code.set_text(f"Error reading {self.entry_name}:\n{e}",
                               highlight="none")
            self.code.pack(fill="both", expand=True)

    def _save_as(self) -> None:
        base = os.path.basename(self.entry_name) or "entry.bin"
        path = filedialog.asksaveasfilename(
            parent=self, title="Save entry as", initialfile=base,
            defaultextension=os.path.splitext(base)[1])
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self.apk.read(self.entry_name))
            messagebox.showinfo("Saved", f"Saved to:\n{path}", parent=self)
        except OSError as e:
            messagebox.showerror("Save failed", str(e), parent=self)


class OverviewViewer(ttk.Frame):
    """Key facts extracted from AndroidManifest.xml."""

    def __init__(self, master, apk: ApkFile, palette: Dict[str, str]) -> None:
        super().__init__(master)
        view = CodeView(self, palette)
        view.pack(fill="both", expand=True)
        s = apk.manifest_summary()
        lines: List[str] = []
        if "error" in s:
            lines.append(f"Overview unavailable: {s['error']}")
        else:
            lines.append(f"Package:      {s.get('package') or '?'}")
            lines.append(f"Version:      {s.get('versionName') or '?'} "
                         f"(code {s.get('versionCode') or '?'})")
            sdk = s.get("sdk") or {}
            if sdk:
                lines.append(f"SDK:          min {sdk.get('minSdkVersion', '?')}  "
                             f"target {sdk.get('targetSdkVersion', '?')}")
            if s.get("app_label"):
                lines.append(f"App label:    {s['app_label']}")
            if s.get("debuggable"):
                lines.append(f"Debuggable:   {s['debuggable']}")
            lines.append("")
            perms = s.get("permissions") or []
            lines.append(f"Permissions ({len(perms)}):")
            lines.extend(f"    {p}" for p in perms)
            for key, title in (("activities", "Activities"),
                               ("activity-aliases", "Activity aliases"),
                               ("services", "Services"),
                               ("receivers", "Broadcast receivers"),
                               ("providers", "Content providers")):
                comps = s.get(key) or []
                if not comps:
                    continue
                lines.append("")
                lines.append(f"{title} ({len(comps)}):")
                for c in comps:
                    extra = ""
                    if c.get("exported") is not None:
                        extra += f"  exported={c['exported']}"
                    if c.get("permission"):
                        extra += f"  permission={c['permission']}"
                    lines.append(f"    {c['name']}{extra}")
            lines.append("")
            lines.append(f"Entries in APK: {len(apk.entries)}  "
                         f"({apk.size:,} bytes on disk)")
            for name in apk.dex_names():
                try:
                    d = apk.dex(name)
                    lines.append(f"  {d.summary_line()}")
                except Exception as e:
                    lines.append(f"  {name}: parse error: {e}")
            res = apk.resources
            if res is not None:
                lines.append(f"  {res.stats()}")
            elif apk.resources_error:
                lines.append(f"  resources.arsc: parse error: {apk.resources_error}")
        view.set_text("\n".join(lines), highlight="none")


class MainWindow:
    """The APKDeco application window."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = Settings()
        self.jobs = JobRunner()
        self.apk: Optional[ApkFile] = None
        self.current_tool_job: Optional[tl.ToolJob] = None
        self.tabs: Dict[str, ttk.Frame] = {}
        self.tab_keys: Dict[str, str] = {}  # display label -> full key
        self._pending_done = None

        self.palette = apply_theme(root, self.settings.get("theme"))
        self.icons = IconSet(root, self.palette)

        root.title(__app_name__)
        root.geometry(self.settings.get("geometry") or "1280x800")
        root.minsize(900, 560)
        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()
        self._bind_shortcuts()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_jobs()
        self.set_status("Open an APK to start (Ctrl+O). "
                        "jadx + apktool unlock full Java/smali decompilation.")

    # ------------------------------------------------------------------ UI
    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Open APK...", accelerator="Ctrl+O",
                           command=self.open_apk_dialog)
        self.recent_menu = tk.Menu(m_file, tearoff=0)
        m_file.add_cascade(label="Recent", menu=self.recent_menu)
        self._fill_recent_menu()
        m_file.add_separator()
        m_file.add_command(label="Extract All...", command=self.extract_all)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=m_file)

        m_tools = tk.Menu(menubar, tearoff=0)
        m_tools.add_command(label="Decompile to Java (jadx)", accelerator="F5",
                            command=self.decompile_jadx)
        m_tools.add_command(label="Decode resources + smali (apktool)",
                            accelerator="F6", command=self.decode_apktool)
        m_tools.add_separator()
        m_tools.add_command(label="Open Output Folder",
                            command=self.open_output_folder)
        m_tools.add_command(label="Cancel Running Job",
                            command=self.cancel_job)
        m_tools.add_separator()
        m_tools.add_command(label="Check Tools...", command=self.open_settings)
        menubar.add_cascade(label="Tools", menu=m_tools)

        m_view = tk.Menu(menubar, tearoff=0)
        self.theme_var = tk.StringVar(value=self.settings.get("theme"))
        m_view.add_radiobutton(label="Dark theme", value="dark",
                               variable=self.theme_var, command=self._switch_theme)
        m_view.add_radiobutton(label="Light theme", value="light",
                               variable=self.theme_var, command=self._switch_theme)
        m_view.add_separator()
        self.log_var = tk.BooleanVar(value=bool(self.settings.get("log_visible")))
        m_view.add_checkbutton(label="Job log", variable=self.log_var,
                               command=self._toggle_log)
        menubar.add_cascade(label="View", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="About", command=lambda: AboutDialog(
            self.root, self.palette).show())
        menubar.add_cascade(label="Help", menu=m_help)
        self.root.config(menu=menubar)

    def _fill_recent_menu(self) -> None:
        self.recent_menu.delete(0, "end")
        recent = self.settings.get("recent") or []
        if not recent:
            self.recent_menu.add_command(label="(empty)", state="disabled")
        for p in recent:
            self.recent_menu.add_command(
                label=p, command=lambda path=p: self.open_apk(path))
        if recent:
            self.recent_menu.add_separator()
            self.recent_menu.add_command(label="Clear list",
                                         command=self._clear_recent)

    def _clear_recent(self) -> None:
        self.settings.clear_recent()
        self._fill_recent_menu()

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root)
        bar.pack(side="top", fill="x", padx=4, pady=4)
        self.btn_open = ttk.Button(bar, text="Open APK", command=self.open_apk_dialog)
        self.btn_open.pack(side="left", padx=2)
        self.btn_jadx = ttk.Button(bar, text="Decompile Java",
                                   style="Accent.TButton",
                                   command=self.decompile_jadx)
        self.btn_jadx.pack(side="left", padx=2)
        self.btn_apktool = ttk.Button(bar, text="Decode (apktool)",
                                      command=self.decode_apktool)
        self.btn_apktool.pack(side="left", padx=2)
        self.btn_extract = ttk.Button(bar, text="Extract All",
                                      command=self.extract_all)
        self.btn_extract.pack(side="left", padx=2)
        ttk.Button(bar, text="Settings", command=self.open_settings).pack(
            side="left", padx=(12, 2))
        self.btn_cancel = ttk.Button(bar, text="Cancel job", command=self.cancel_job)
        self.btn_cancel.pack(side="right", padx=2)
        self.btn_cancel.state(["disabled"])

    def _build_body(self) -> None:
        panes = ttk.Panedwindow(self.root, orient="horizontal")
        panes.pack(fill="both", expand=True)

        left = ttk.Frame(panes)
        self.left_nb = ttk.Notebook(left)
        self.left_nb.pack(fill="both", expand=True)

        # Files tab
        files_tab = ttk.Frame(self.left_nb)
        self.file_tree = ttk.Treeview(files_tab, show="tree", selectmode="browse")
        sy = ttk.Scrollbar(files_tab, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=sy.set)
        self.file_tree.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.file_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.file_tree.bind("<Double-1>", self._on_tree_open)
        self.file_tree.bind("<Button-3>", self._on_tree_menu)
        self.left_nb.add(files_tab, text="Files")

        # Search tab
        search_tab = ttk.Frame(self.left_nb)
        top = ttk.Frame(search_tab)
        top.pack(side="top", fill="x")
        self.search_var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=self.search_var)
        ent.pack(side="left", fill="x", expand=True, padx=6, pady=4)
        ent.bind("<Return>", lambda e: self.run_search())
        ttk.Button(top, text="Search", width=8,
                   command=self.run_search).pack(side="right", padx=6)
        opts = ttk.Frame(search_tab)
        opts.pack(side="top", fill="x")
        self.opt_names = tk.BooleanVar(value=True)
        self.opt_content = tk.BooleanVar(value=True)
        self.opt_strings = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Names", variable=self.opt_names).pack(
            side="left", padx=6)
        ttk.Checkbutton(opts, text="Contents", variable=self.opt_content).pack(
            side="left")
        ttk.Checkbutton(opts, text="DEX strings",
                        variable=self.opt_strings).pack(side="left", padx=6)
        self.search_status = tk.StringVar(value="")
        ttk.Label(search_tab, textvariable=self.search_status,
                  style="Dim.TLabel").pack(anchor="w", padx=8)
        res_frame = ttk.Frame(search_tab)
        res_frame.pack(fill="both", expand=True)
        self.search_tree = ttk.Treeview(res_frame, columns=("where",),
                                        show="tree headings")
        self.search_tree.heading("#0", text="Match")
        self.search_tree.heading("where", text="Location")
        self.search_tree.column("#0", width=340)
        self.search_tree.column("where", width=140)
        sy2 = ttk.Scrollbar(res_frame, orient="vertical",
                            command=self.search_tree.yview)
        self.search_tree.configure(yscrollcommand=sy2.set)
        self.search_tree.pack(side="left", fill="both", expand=True)
        sy2.pack(side="right", fill="y")
        self.search_tree.bind("<Double-1>", self._on_search_open)
        self.left_nb.add(search_tab, text="Search")

        panes.add(left, weight=1)

        # right: viewer tabs
        right = ttk.Frame(panes)
        self.viewer_nb = ttk.Notebook(right)
        self.viewer_nb.pack(fill="both", expand=True)
        self.viewer_nb.bind("<Button-2>", self._close_tab_event)
        self.viewer_nb.bind("<Control-w>", self._close_current_tab)
        panes.add(right, weight=3)

        # log
        self.log = LogPanel(self.root, self.palette)
        if self.settings.get("log_visible"):
            self.log.pack(side="top", fill="x")

    def _build_status(self) -> None:
        self.status = StatusBar(self.root)
        self.status.pack(side="bottom", fill="x")

    def _bind_shortcuts(self) -> None:
        r = self.root
        r.bind("<Control-o>", lambda e: self.open_apk_dialog())
        r.bind("<F5>", lambda e: self.decompile_jadx())
        r.bind("<F6>", lambda e: self.decode_apktool())
        r.bind("<Control-f>", self._focus_find)

    # ------------------------------------------------------------- helpers
    def set_status(self, text: str) -> None:
        self.status.left.set(text)

    def log_line(self, text: str) -> None:
        self.log.append(text)

    def _set_busy(self, busy: bool, what: str = "") -> None:
        self.status.set_busy(busy)
        state = ["disabled"] if busy else ["!disabled"]
        for b in (self.btn_jadx, self.btn_apktool, self.btn_extract):
            b.state(state)
        self.btn_cancel.state(["!disabled"] if busy else ["disabled"])
        if busy:
            self.set_status(what or "Working...")

    # -------------------------------------------------------------- open
    def open_apk_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Open APK",
            filetypes=[("Android packages", "*.apk *.apks *.xapk *.zip *.aar"),
                       ("All files", "*.*")])
        if path:
            self.open_apk(path)

    def open_apk(self, path: str) -> None:
        if self.jobs.busy:
            messagebox.showwarning("Busy", "A job is running - cancel it first.",
                                   parent=self.root)
            return
        try:
            new_apk = ApkFile(path)
        except ApkError as e:
            messagebox.showerror("Cannot open APK", str(e), parent=self.root)
            return
        if self.apk is not None:
            self.apk.close()
            self._close_all_tabs()
        self.apk = new_apk
        self.settings.add_recent(path)
        self._fill_recent_menu()
        self._build_file_tree()
        self.root.title(f"{__app_name__} - {new_apk.name}")
        self.set_status(f"Opened {path}  ({new_apk.size:,} bytes, "
                        f"{len(new_apk.entries)} entries)")
        self.log_line(f"Opened {path}")
        self._open_overview_tab()
        self._open_manifest_tab()

    # ---------------------------------------------------------- file tree
    def _build_file_tree(self) -> None:
        assert self.apk is not None
        tree = self.file_tree
        tree.delete(*tree.get_children())
        self.icons  # noqa - icons kept alive on purpose
        tree.image = self.icons  # type: ignore[attr-defined]

        groups: Dict[str, List[EntryInfo]] = {g: [] for g in GROUP_ORDER}
        for e in self.apk.entries:
            groups.setdefault(e.group, []).append(e)

        labels = {
            "manifest": "Manifest", "dex": "DEX code", "arsc": "Resources table",
            "res": "res/ (resources)", "assets": "assets/", "lib": "lib/ (native)",
            "META-INF": "META-INF/ (signatures)", "other": "Other files",
        }
        self._dir_nodes: Dict[Tuple[str, str], str] = {}
        for g in GROUP_ORDER:
            entries = groups.get(g) or []
            if not entries:
                continue
            total = sum(e.size for e in entries)
            node = tree.insert(
                "", "end", text=f"{labels.get(g, g)}  ({len(entries)} files, "
                                f"{total:,} B)",
                image=self.icons.get(
                    {"dex": "dex", "manifest": "manifest", "arsc": "bin",
                     "res": "xml", "assets": "folder", "lib": "bin",
                     "META-INF": "file", "other": "folder"}.get(g, "folder")),
                open=(g in ("manifest", "dex", "arsc")))
            for e in sorted(entries, key=lambda x: x.name):
                self._insert_entry(tree, node, e)

    def _insert_entry(self, tree: ttk.Treeview, root_node: str,
                      entry: EntryInfo) -> None:
        parts = entry.name.split("/")
        parent = root_node
        path_so_far = ""
        for d in parts[:-1]:
            path_so_far = f"{path_so_far}{d}/"
            key = (root_node, path_so_far)
            if key not in self._dir_nodes:
                node = tree.insert(parent, "end", text=d + "/",
                                   image=self.icons.get("folder"), open=True)
                self._dir_nodes[key] = node
            parent = self._dir_nodes[key]
        tree.insert(parent, "end", text=parts[-1],
                    image=self.icons.get(icon_for_entry(entry.name, entry.group)),
                    values=(entry.name,))

    def _selected_entry_name(self) -> Optional[str]:
        item = self.file_tree.focus()
        if not item:
            return None
        vals = self.file_tree.item(item, "values")
        return vals[0] if vals else None

    def _on_tree_select(self, _event=None) -> None:
        name = self._selected_entry_name()
        if name and self.apk:
            e = self.apk._entry_map.get(name)
            if e:
                self.set_status(f"{name}  ({e.size:,} bytes, "
                                f"stored {e.compress_size:,})")

    def _on_tree_open(self, _event=None) -> None:
        name = self._selected_entry_name()
        if name:
            self.open_entry_tab(name)

    def _on_tree_menu(self, event) -> None:
        item = self.file_tree.identify_row(event.y)
        if item:
            self.file_tree.selection_set(item)
            self.file_tree.focus(item)
        name = self._selected_entry_name()
        if not name:
            return
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Open in viewer",
                         command=lambda: self.open_entry_tab(name))
        menu.add_command(label="Open as hex",
                         command=lambda: self.open_entry_tab(name, mode="hex"))
        menu.add_command(label="Save entry as...",
                         command=lambda: self._save_entry(name))
        menu.add_command(label="Copy entry name",
                         command=lambda: self._copy_text(name))
        menu.tk_popup(event.x_root, event.y_root)

    def _copy_text(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _save_entry(self, name: str) -> None:
        assert self.apk is not None
        base = os.path.basename(name) or "entry.bin"
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save entry as", initialfile=base)
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(self.apk.read(name))
            self.set_status(f"Saved {name} -> {path}")
        except (OSError, ApkError) as e:
            messagebox.showerror("Save failed", str(e), parent=self.root)

    # ----------------------------------------------------------- viewer tabs
    def _tab_label(self, key: str) -> str:
        if key == "overview":
            return "Overview"
        if key == "manifest::pretty":
            return "Manifest"
        if key.startswith("dex::"):
            return key.split("::", 1)[1]
        return key.split("/")[-1] or key

    def _unique_tab_label(self, key: str) -> str:
        label = self._tab_label(key)
        used = set(self.tab_keys)
        if label not in used:
            return label
        # disambiguate with parent folder
        parts = key.split("/")
        if len(parts) > 1:
            label = f"{parts[-2]}/{parts[-1]}"
        n = 2
        base = label
        while label in used:
            label = f"{base} ({n})"
            n += 1
        return label

    def _add_tab(self, key: str, frame: ttk.Frame) -> None:
        label = self._unique_tab_label(key)
        self.tabs[key] = frame
        self.tab_keys[label] = key
        self.viewer_nb.add(frame, text=label)
        self.viewer_nb.select(frame)

    def _close_tab_event(self, event) -> None:
        try:
            idx = self.viewer_nb.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return
        self._close_tab_index(idx)

    def _close_current_tab(self, _event=None) -> None:
        try:
            idx = self.viewer_nb.index("current")
        except tk.TclError:
            return
        self._close_tab_index(idx)

    def _close_tab_index(self, idx: int) -> None:
        label = self.viewer_nb.tab(idx, "text")
        key = self.tab_keys.pop(label, None)
        frame = self.tabs.pop(key, None) if key else None
        self.viewer_nb.forget(idx)
        if frame is not None:
            frame.destroy()

    def _close_all_tabs(self) -> None:
        for label in list(self.tab_keys):
            key = self.tab_keys.pop(label)
            frame = self.tabs.pop(key, None)
            if frame:
                frame.destroy()
        self.viewer_nb.forget()

    def open_entry_tab(self, name: str, mode: Optional[str] = None) -> None:
        if self.apk is None:
            return
        if name in self.tabs:
            self.viewer_nb.select(self.tabs[name])
            return
        frame = EntryViewer(self.viewer_nb, self.apk, name, self.palette)
        if mode:
            frame.mode_var.set(mode)
            frame._refresh()
        self._add_tab(name, frame)
        if name == "AndroidManifest.xml":
            self._open_manifest_tab()

    def _open_manifest_tab(self) -> None:
        if self.apk is None or "manifest::pretty" in self.tabs:
            return
        frame = ttk.Frame(self.viewer_nb)
        view = CodeView(frame, self.palette)
        view.pack(fill="both", expand=True)
        view.set_text(self.apk.manifest_pretty(), highlight="xml",
                      name="AndroidManifest.xml")
        self._add_tab("manifest::pretty", frame)

    def _open_overview_tab(self) -> None:
        if self.apk is None or "overview" in self.tabs:
            return
        frame = OverviewViewer(self.viewer_nb, self.apk, self.palette)
        self._add_tab("overview", frame)

    def _open_dex_tab(self, dex_name: str) -> None:
        if self.apk is None:
            return
        key = f"dex::{dex_name}"
        if key in self.tabs:
            self.viewer_nb.select(self.tabs[key])
            return
        frame = DexViewer(self.viewer_nb, self.apk, dex_name, self.palette,
                          self.icons)
        self._add_tab(key, frame)

    def _focus_find(self, _event=None):
        try:
            frame = self.viewer_nb.nametowidget(self.viewer_nb.select())
            if isinstance(frame, EntryViewer):
                frame.code.focus_find()
                return "break"
            if isinstance(frame, CodeView):
                frame.focus_find()
                return "break"
        except (tk.TclError, AttributeError):
            pass
        return None

    # -------------------------------------------------------------- search
    def run_search(self) -> None:
        if self.apk is None:
            messagebox.showinfo("No APK", "Open an APK first.", parent=self.root)
            return
        needle = self.search_var.get().strip()
        if not needle:
            return
        apk = self.apk
        want_names = self.opt_names.get()
        want_content = self.opt_content.get()
        want_strings = self.opt_strings.get()
        self.search_tree.delete(*self.search_tree.get_children())
        self.search_status.set("Searching...")
        self._set_busy(True, f"Searching for {needle!r}...")

        def job(sink):
            results: List[Tuple[str, str, str]] = []
            low = needle.lower()
            if want_names:
                for e in apk.entries:
                    if low in e.name.lower():
                        results.append((e.name, "name", e.name))
            if want_content:
                for e in apk.entries:
                    if e.size > MAX_SEARCH_FILE_BYTES:
                        continue
                    try:
                        data = apk.read(e.name)
                    except Exception:
                        continue
                    if b"\x00" in data[:1024]:
                        continue
                    text = data.decode("utf-8", "replace")
                    i = text.lower().find(low)
                    if i >= 0:
                        ctx = text[max(0, i - 30):i + len(needle) + 30].replace("\n", " ")
                        results.append((e.name, "content", f"...{ctx}..."))
            if want_strings:
                for name in apk.dex_names():
                    try:
                        dex = apk.dex(name)
                    except Exception:
                        continue
                    for s in dex.strings:
                        if low in s.lower():
                            results.append((name, f"dex string", s[:200]))
            return results[:5000]

        def done(results):
            self.search_tree.delete(*self.search_tree.get_children())
            for where, kind, preview in results[:MAX_TREE_ITEMS]:
                self.search_tree.insert("", "end", text=preview[:300],
                                        values=(f"{where} ({kind})",),
                                        tags=(where,))
            self.search_status.set(
                f"{len(results)} result(s)" +
                (" (capped)" if len(results) >= 5000 else ""))
            self._set_busy(False)
            self.set_status("Search done.")

        self._pending_done = done
        self.jobs.submit(job)

    def _on_search_open(self, _event=None) -> None:
        item = self.search_tree.focus()
        if not item:
            return
        tags = self.search_tree.item(item, "tags")
        if not tags:
            return
        target = tags[0]
        if target in (self.apk.dex_names() if self.apk else []):
            self._open_dex_tab(target)
        else:
            self.open_entry_tab(target)

    # --------------------------------------------------------- decompile
    def _output_dir(self) -> Optional[str]:
        assert self.apk is not None
        out = self.settings.default_output_dir(self.apk.path)
        if not os.path.isdir(out):
            try:
                os.makedirs(out, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Output folder", str(e), parent=self.root)
                return None
        return out

    def decompile_jadx(self) -> None:
        self._run_tool("jadx")

    def decode_apktool(self) -> None:
        self._run_tool("apktool")

    def _run_tool(self, which: str) -> None:
        if self.apk is None:
            messagebox.showinfo("No APK", "Open an APK first.", parent=self.root)
            return
        if self.jobs.busy:
            messagebox.showwarning("Busy", "Another job is running.", parent=self.root)
            return
        out = self._output_dir()
        if out is None:
            return
        if not confirm_overwrite_dir(self.root, out):
            return
        try:
            if which == "jadx":
                jadx = tl.find_jadx(self.settings.get("jadx_path") or "")
                if not jadx:
                    self._missing_tool(
                        "jadx not found.",
                        "Install jadx 1.4+ and/or set its path in Settings.\n"
                        "Download: https://github.com/skylot/jadx/releases")
                    return
                cmd = tl.build_jadx_command(jadx, self.apk.path, out)
                job_name = "jadx"
            else:
                try:
                    prefix = tl.find_apktool(self.settings.get("apktool_path") or "",
                                             tl.find_java(self.settings.get("java_path") or ""))
                except tl.ToolError as e:
                    self._missing_tool(str(e),
                                       "apktool needs Java (JRE/JDK 11+).\n"
                                       "Download: https://apktool.org/")
                    return
                if not prefix:
                    self._missing_tool(
                        "apktool not found.",
                        "Install apktool or point Settings at apktool.jar.\n"
                        "Download: https://apktool.org/")
                    return
                cmd = tl.build_apktool_command(prefix, self.apk.path, out)
                job_name = "apktool"
        except Exception as e:
            messagebox.showerror("Tool error", str(e), parent=self.root)
            return

        self.log_line(f"--- {job_name} ---")
        tool_job = tl.ToolJob(job_name, cmd)
        self.current_tool_job = tool_job

        def job(sink):
            code = tool_job.run(sink)
            return code

        def done(code):
            self.log_line(f"--- {job_name} finished (exit {code}) ---")
            if code == 0:
                self.set_status(f"{job_name} finished. Output: {out}")
                if messagebox.askyesno(
                        "Done", f"{job_name} finished successfully.\n\n"
                                f"Output:\n{out}\n\nOpen the folder?",
                        parent=self.root):
                    tl.open_in_file_manager(out)
            else:
                self.set_status(f"{job_name} failed (exit {code}) - see log")
                messagebox.showwarning(
                    "Tool failed",
                    f"{job_name} exited with code {code}. See the job log.",
                    parent=self.root)

        self._pending_done = done
        self._set_busy(True, f"Running {job_name}...")
        self.jobs.submit(job, on_cancel=tool_job.kill)

    def _missing_tool(self, short: str, long: str) -> None:
        messagebox.showwarning("Missing tool", f"{short}\n\n{long}", parent=self.root)
        self.log_line(f"MISSING TOOL: {short}")

    def cancel_job(self) -> None:
        if self.jobs.busy:
            self.jobs.cancel()
            self.set_status("Cancelling job...")

    def open_output_folder(self) -> None:
        if self.apk is None:
            return
        out = self.settings.default_output_dir(self.apk.path)
        if os.path.isdir(out):
            tl.open_in_file_manager(out)
        else:
            self.set_status(f"No output folder yet: {out}")

    def extract_all(self) -> None:
        if self.apk is None:
            messagebox.showinfo("No APK", "Open an APK first.", parent=self.root)
            return
        dest = filedialog.askdirectory(parent=self.root,
                                       title="Extract all entries to folder")
        if not dest:
            return
        apk = self.apk
        self._set_busy(True, "Extracting...")

        def job(sink):
            n = 0
            for e in apk.entries:
                target = os.path.join(dest, *e.name.split("/"))
                # zip-slip guard
                if not os.path.abspath(target).startswith(os.path.abspath(dest) + os.sep):
                    sink(f"skipped unsafe path: {e.name}")
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as f:
                    f.write(apk.read(e.name))
                n += 1
                if n % 50 == 0:
                    sink(f"extracted {n} files...")
            return n

        self._pending_done = lambda n: (
            self.set_status(f"Extracted {n} files to {dest}"),
            self.log_line(f"Extracted {n} files to {dest}"))
        self.jobs.submit(job)

    # ------------------------------------------------------------- settings
    def open_settings(self) -> None:
        dlg = SettingsDialog(self.root, self.settings, self.palette)
        if dlg.show() == "saved":
            self.set_status("Settings saved.")
            if self.settings.get("theme") != self.theme_var.get():
                self.theme_var.set(self.settings.get("theme"))
                self._switch_theme()

    def _switch_theme(self) -> None:
        name = self.theme_var.get()
        self.settings.set("theme", name)
        self.settings.save()
        self.palette = apply_theme(self.root, name)
        self._restyle_tk_widgets(self.root)
        self.set_status(f"Switched to {name} theme "
                        "(re-open tabs to recolor viewers fully).")

    def _restyle_tk_widgets(self, widget) -> None:
        pal = self.palette
        cls = widget.winfo_class()
        try:
            if cls in ("Text",):
                widget.configure(bg=pal["text_bg"], fg=pal["text_fg"],
                                 insertbackground=pal["text_fg"],
                                 selectbackground=pal["select_bg"],
                                 selectforeground=pal["select_fg"])
            elif cls == "Canvas":
                widget.configure(bg=pal["text_bg"])
            elif cls == "Menu":
                widget.configure(bg=pal["panel"], fg=pal["fg"],
                                 activebackground=pal["select_bg"],
                                 activeforeground=pal["select_fg"])
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._restyle_tk_widgets(child)

    def _toggle_log(self) -> None:
        visible = self.log_var.get()
        self.settings.set("log_visible", visible)
        self.settings.save()
        if visible:
            self.log.pack(side="top", fill="x")
        else:
            self.log.pack_forget()

    # ----------------------------------------------------------- job poll
    def _poll_jobs(self) -> None:
        pending = self.jobs.poll()
        for kind, payload in pending:
            if kind == "log":
                self.log_line(payload)
            elif kind in ("done", "error", "cancelled"):
                self._set_busy(False)
                self.current_tool_job = None
                cb = self._pending_done
                self._pending_done = None
                if kind == "done":
                    if cb:
                        cb(payload)
                elif kind == "error":
                    self.log_line(f"ERROR: {payload}")
                    messagebox.showerror("Job failed", payload, parent=self.root)
                else:
                    self.set_status("Job cancelled.")
        self.root.after(100, self._poll_jobs)

    def _on_close(self) -> None:
        if self.jobs.busy:
            if not messagebox.askyesno(
                    "Quit", "A job is still running. Quit anyway?",
                    parent=self.root):
                return
            self.jobs.cancel()
        self.settings.set("geometry", self.root.geometry())
        self.settings.save()
        if self.apk is not None:
            self.apk.close()
        self.root.destroy()
