"""Modal dialogs: Settings (tool paths, output dir, theme) and About."""
from __future__ import annotations

import os
import sys
import webbrowser
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Dict

from .. import __app_name__, __version__
from ..core.settings import Settings, settings_path
from ..core.tools import tool_report
from ..core.jobs import JobRunner
from .theme import CODE_FONT, UI_FONT, UI_FONT_BOLD


class _ModalDialog(tk.Toplevel):
    def __init__(self, master, title: str, palette: Dict[str, str]) -> None:
        super().__init__(master)
        self.palette = palette
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.configure(bg=palette["bg"])
        self.result = None

    def show(self):
        self.grab_set()
        self.wait_window()
        return self.result


class SettingsDialog(_ModalDialog):
    def __init__(self, master, settings: Settings, palette: Dict[str, str]) -> None:
        super().__init__(master, f"{__app_name__} Settings", palette)
        self.settings = settings
        self.geometry("640x480")
        self.resizable(True, True)

        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frm, text="External tools", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", **pad)

        self.vars = {}
        rows = [
            ("java_path", "Java (java.exe):",
             "Needed for apktool; jadx bundles its own runtime in some builds."),
            ("jadx_path", "jadx (jadx.bat / folder):",
             "Java decompiler - produces readable Java source."),
            ("apktool_path", "apktool (apktool.jar / apktool):",
             "Decodes resources + smali, supports rebuilding."),
            ("output_dir", "Default output folder:",
             "Empty = <apk folder>/<apk name>_decoded"),
        ]
        r = 1
        for key, label, hint in rows:
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", **pad)
            var = tk.StringVar(value=settings.get(key) or "")
            self.vars[key] = var
            entry = ttk.Entry(frm, textvariable=var, width=44)
            entry.grid(row=r, column=1, sticky="ew", **pad)
            ttk.Button(frm, text="Browse...", width=9,
                       command=lambda k=key: self._browse(k)).grid(
                row=r, column=2, **pad)
            ttk.Label(frm, text=hint, style="Dim.TLabel",
                      wraplength=520).grid(row=r + 1, column=0, columnspan=3,
                                           sticky="w", padx=8)
            r += 2

        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Appearance", style="Title.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(12, 0), **pad)
        r += 1
        self.theme_var = tk.StringVar(value=settings.get("theme") or "dark")
        ttk.Radiobutton(frm, text="Dark theme", variable=self.theme_var,
                        value="dark").grid(row=r, column=0, sticky="w", **pad)
        ttk.Radiobutton(frm, text="Light theme", variable=self.theme_var,
                        value="light").grid(row=r, column=1, sticky="w", **pad)
        r += 1

        ttk.Label(frm, text=f"Settings file: {settings_path()}",
                  style="Dim.TLabel").grid(row=r, column=0, columnspan=3,
                                           sticky="w", **pad)
        r += 1

        ttk.Label(frm, text="Tool status", style="Title.TLabel").grid(
            row=r, column=0, columnspan=3, sticky="w", pady=(12, 0), **pad)
        r += 1
        self.report = tk.Text(frm, height=7, font=CODE_FONT,
                              bg=palette["log_bg"], fg=palette["text_fg"],
                              relief="flat", wrap="word", state="disabled")
        self.report.grid(row=r, column=0, columnspan=3, sticky="ew", **pad)
        r += 1

        btns = ttk.Frame(frm)
        btns.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="Check tools", command=self._check).pack(side="left")
        ttk.Button(btns, text="Reset paths", command=self._reset_paths).pack(
            side="left", padx=6)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right")

        self.after(100, self._check)

    def _browse(self, key: str) -> None:
        cur = self.vars[key].get()
        initial = cur if os.path.isdir(cur) else (os.path.dirname(cur) or ".")
        if key == "apktool_path":
            p = filedialog.askopenfilename(
                parent=self, title="Select apktool.jar or apktool executable",
                initialdir=initial,
                filetypes=[("apktool", "apktool.jar apktool apktool.bat"),
                           ("All files", "*.*")])
        elif key == "output_dir":
            p = filedialog.askdirectory(parent=self, title="Select output folder",
                                        initialdir=initial or ".")
        else:
            p = filedialog.askopenfilename(
                parent=self, title="Select executable (or its folder via typing)",
                initialdir=initial or ".",
                filetypes=[("Executables", "*.exe *.bat *.cmd"),
                           ("All files", "*.*")])
        if p:
            self.vars[key].set(p)

    def _collect_settings_like(self) -> Settings:
        """A temp settings object with the dialog's current values."""
        tmp = Settings()
        for k, v in self.vars.items():
            tmp.set(k, v.get().strip())
        return tmp

    def _check(self) -> None:
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", "Checking tools, please wait...\n")
        self.report.configure(state="disabled")
        self.update_idletasks()
        tmp = self._collect_settings_like()
        runner = JobRunner()

        def job(sink):
            return tool_report(tmp)

        def finish():
            for kind, text in runner.poll():
                if kind == "done":
                    report = text
                    self.report.configure(state="normal")
                    self.report.delete("1.0", "end")
                    for k in ("java", "jadx", "apktool"):
                        self.report.insert("end", f"{k}:\n  {report.get(k, '?')}\n\n")
                    self.report.configure(state="disabled")
                    return
                if kind == "error":
                    self.report.configure(state="normal")
                    self.report.delete("1.0", "end")
                    self.report.insert("1.0", f"check failed: {text}")
                    self.report.configure(state="disabled")
                    return
            self.after(80, finish)

        runner.submit(job)
        self.after(80, finish)

    def _reset_paths(self) -> None:
        for k in ("java_path", "jadx_path", "apktool_path", "output_dir"):
            self.vars[k].set("")

    def _save(self) -> None:
        for k, v in self.vars.items():
            self.settings.set(k, v.get().strip())
        self.settings.set("theme", self.theme_var.get())
        self.settings.save()
        self.result = "saved"
        self.destroy()


class AboutDialog(_ModalDialog):
    def __init__(self, master, palette: Dict[str, str]) -> None:
        super().__init__(master, f"About {__app_name__}", palette)
        self.geometry("520x420")
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=16, pady=14)

        ttk.Label(frm, text=__app_name__, style="Title.TLabel",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frm, text=f"Version {__version__} - APK decompiler GUI for Windows",
                  style="Dim.TLabel").pack(anchor="w")
        body = tk.Text(frm, font=("Segoe UI", 10), bg=palette["panel"],
                       fg=palette["fg"], relief="flat", wrap="word", height=12,
                       cursor="arrow")
        body.pack(fill="both", expand=True, pady=10)
        body.insert("1.0",
                    "APKDeco opens Android .apk files and shows what is inside:\n\n"
                    "  \u2022  Decoded AndroidManifest.xml (binary XML parsed in-app)\n"
                    "  \u2022  Resources table with @string/@style reference resolution\n"
                    "  \u2022  DEX class / method / field / string explorer\n"
                    "  \u2022  Hex + text + image viewers and full-content search\n"
                    "  \u2022  One-click Java decompilation via jadx\n"
                    "  \u2022  One-click resource + smali decode via apktool\n\n"
                    "Use only on APKs you are allowed to analyze.\n"
                    "jadx and apktool are separate projects - install them for\n"
                    "full decompilation (Settings > Check tools).")
        body.configure(state="disabled")

        links = ttk.Frame(frm)
        links.pack(fill="x")
        for label, url in (
            ("jadx releases", "https://github.com/skylot/jadx/releases"),
            ("apktool", "https://apktool.org/"),
        ):
            lbl = ttk.Label(links, text=label, foreground=palette["accent"],
                            cursor="hand2")
            lbl.pack(side="left", padx=(0, 16))
            lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))

        ttk.Button(frm, text="Close", command=self.destroy).pack(anchor="e")


def confirm_overwrite_dir(parent, path: str) -> bool:
    from tkinter import messagebox
    if os.path.isdir(path) and os.listdir(path):
        return messagebox.askyesno(
            "Output folder not empty",
            f"Folder already exists and is not empty:\n{path}\n\n"
            "Tools will overwrite files there (apktool uses -f). Continue?",
            parent=parent)
    return True
