#!/usr/bin/env python3
"""APKDeco - APK decompiler GUI for Windows.

Usage:
    python main.py               # start the GUI
    python main.py app.apk       # start and open an APK
    python main.py --selftest    # headless self-test (parsers + fixtures)
"""
from __future__ import annotations

import sys


def selftest() -> int:
    """Run the headless test-suite (no GUI required)."""
    import os
    import tempfile
    import unittest

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    loader = unittest.TestLoader()
    suite = loader.discover("tests", top_level_dir=os.getcwd())
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)

    # additionally open a synthetic APK end-to-end through the core
    ok = result.wasSuccessful()
    try:
        from tests.fixtures import build_test_apk
        from apkdeco.core.apk import ApkFile
        with tempfile.TemporaryDirectory() as td:
            path = build_test_apk(os.path.join(td, "selftest.apk"))
            apk = ApkFile(path)
            assert apk.manifest_summary().get("package") == "com.example.test"
            assert apk.resources is not None
            assert apk.dex("classes.dex").info.class_count == 1
            assert "debug" in apk.text_preview("assets/config.json")
            apk.close()
        print("core self-test: OK")
    except Exception as e:
        print(f"core self-test: FAIL ({e})")
        ok = False
    return 0 if ok else 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("--selftest", "--test"):
        return selftest()
    if args and args[0] in ("--help", "-h"):
        print(__doc__)
        return 0
    open_path = args[0] if args else None
    from apkdeco.app import run
    return run(open_path)


if __name__ == "__main__":
    sys.exit(main())
