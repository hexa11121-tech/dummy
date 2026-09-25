# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for APKDeco (Windows, one-file, windowed).
# Build from the repo root:  pyinstaller --clean --noconfirm build/apkdeco.spec
import os

project_root = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
    binaries=[],
    datas=[
        (os.path.join(project_root, "assets", "icon.png"), "assets"),
    ],
    hiddenimports=[
        "apkdeco.app",
        "apkdeco.core.apk",
        "apkdeco.core.arsc",
        "apkdeco.core.axml",
        "apkdeco.core.blob",
        "apkdeco.core.dex",
        "apkdeco.core.jobs",
        "apkdeco.core.settings",
        "apkdeco.core.tools",
        "apkdeco.gui.dialogs",
        "apkdeco.gui.main_window",
        "apkdeco.gui.theme",
        "apkdeco.gui.widgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest", "pydoc"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="APKDeco",
    icon=os.path.join(project_root, "assets", "icon.ico"),
    console=False,          # windowed app: no console window
    disable_windowed_traceback=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
