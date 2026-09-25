"""Locating and running external decompilers (jadx, apktool) and Java.

All process launches are console-window-free on Windows (CREATE_NO_WINDOW),
which matters when the app runs as a windowed PyInstaller exe.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Sequence

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _popen_kwargs() -> dict:
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = CREATE_NO_WINDOW
    return kw


class ToolError(Exception):
    pass


def find_java(explicit: str = "") -> Optional[str]:
    if explicit:
        cand = explicit
        if os.path.isdir(cand):
            cand = os.path.join(cand, "java.exe" if sys.platform == "win32" else "java")
        return cand if os.path.isfile(cand) else None
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        cand = os.path.join(java_home, "bin", "java.exe" if sys.platform == "win32" else "java")
        if os.path.isfile(cand):
            return cand
    return shutil.which("java")


def _as_exe_candidates(path: str) -> List[str]:
    if sys.platform == "win32":
        return [path, path + ".bat", path + ".exe", path + ".cmd"]
    return [path]


def find_tool(explicit: str, names: Sequence[str]) -> Optional[str]:
    """Find an executable. ``explicit`` may be the exe itself or its folder."""
    if explicit:
        for cand in _as_exe_candidates(explicit):
            if os.path.isfile(cand):
                return cand
        if os.path.isdir(explicit):
            for n in names:
                for cand in _as_exe_candidates(os.path.join(explicit, n)):
                    if os.path.isfile(cand):
                        return cand
                for cand in _as_exe_candidates(os.path.join(explicit, "bin", n)):
                    if os.path.isfile(cand):
                        return cand
        return None
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def find_jadx(explicit: str = "") -> Optional[str]:
    return find_tool(explicit, ("jadx",))


def find_apktool(explicit: str = "", java: Optional[str] = None) -> Optional[str]:
    """Return a *command prefix* list, e.g. ['java', '-jar', 'apktool.jar']."""
    if explicit:
        if os.path.isfile(explicit) and explicit.lower().endswith(".jar"):
            java_bin = java or find_java()
            if not java_bin:
                raise ToolError("apktool.jar found but Java is not installed / not configured")
            return [java_bin, "-jar", explicit]
        cmd = find_tool(explicit, ("apktool",))
        if cmd:
            return [cmd]
        return None
    cmd = find_tool("", ("apktool",))
    if cmd:
        return [cmd]
    return None


def open_in_file_manager(path: str) -> None:
    """Open a folder in Explorer (or the OS file manager elsewhere)."""
    path = os.path.normpath(path)
    if sys.platform == "win32":
        try:
            os.startfile(path)  # type: ignore[attr-defined]
            return
        except OSError:
            pass
    opener = "explorer" if sys.platform == "win32" else (
        "open" if sys.platform == "darwin" else "xdg-open")
    subprocess.Popen([opener, path], **_popen_kwargs())


def run_capture(cmd: List[str], timeout: int = 20) -> (str, str, int):
    """Run a short command (e.g. --version) and capture output."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            errors="replace", **_popen_kwargs())
        out = (p.stdout or "") + (p.stderr or "")
        return out.strip(), "", p.returncode
    except FileNotFoundError:
        return "", f"not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", "timed out", -2
    except OSError as e:
        return "", str(e), -3


class ToolJob:
    """A long-running external process whose output streams to a sink."""

    def __init__(self, name: str, cmd: List[str], cwd: Optional[str] = None) -> None:
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.proc: Optional[subprocess.Popen] = None
        self._killed = False

    def run(self, sink: Callable[[str], None]) -> int:
        sink(f"$ {' '.join(self.cmd)}")
        try:
            self.proc = subprocess.Popen(
                self.cmd, cwd=self.cwd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1,
                **_popen_kwargs())
        except FileNotFoundError:
            sink(f"ERROR: executable not found: {self.cmd[0]}")
            return -1
        except OSError as e:
            sink(f"ERROR: {e}")
            return -2
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            sink(line.rstrip("\n"))
        code = self.proc.wait()
        if self._killed:
            sink("Job cancelled.")
        return code

    def kill(self) -> None:
        self._killed = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except OSError:
                pass


def build_jadx_command(jadx: str, apk_path: str, out_dir: str,
                       sources: bool = True, resources: bool = True,
                       show_bad_code: bool = False) -> List[str]:
    cmd = [jadx, "-d", out_dir]
    if not sources:
        cmd.append("--no-src")
    if not resources:
        cmd.append("--no-res")
    if show_bad_code:
        cmd.append("--show-bad-code")
    cmd.append(apk_path)
    return cmd


def build_apktool_command(prefix: List[str], apk_path: str, out_dir: str,
                          no_res: bool = False, no_src: bool = False) -> List[str]:
    cmd = list(prefix) + ["d", "-f", "-o", out_dir]
    if no_res:
        cmd.append("-r")
    if no_src:
        cmd.append("-s")
    cmd.append(apk_path)
    return cmd


def tool_report(settings) -> Dict[str, str]:
    """Diagnostic snapshot used by the Settings dialog 'Check tools' button."""
    report: Dict[str, str] = {}
    java = find_java(settings.get("java_path") or "")
    if java:
        out, err, code = run_capture([java, "-version"])
        # java -version prints to stderr
        report["java"] = f"OK: {java}\n{(out or err).splitlines()[0] if (out or err) else ''}"
    else:
        report["java"] = "NOT FOUND (install a JRE/JDK 11+ or set path in Settings)"

    jadx = find_jadx(settings.get("jadx_path") or "")
    if jadx:
        out, err, code = run_capture([jadx, "--version"])
        report["jadx"] = f"OK: {jadx}\n{(out or err).splitlines()[0] if (out or err) else 'version ?'}"
    else:
        report["jadx"] = "NOT FOUND (install jadx 1.4+ or set path in Settings)"

    try:
        apktool = find_apktool(settings.get("apktool_path") or "",
                               java or None)
    except ToolError as e:
        report["apktool"] = f"ERROR: {e}"
        apktool = None
    if apktool:
        out, err, code = run_capture(apktool + ["--version"])
        report["apktool"] = f"OK: {' '.join(apktool)}\n{(out or err).splitlines()[0] if (out or err) else 'version ?'}"
    else:
        report["apktool"] = "NOT FOUND (install apktool or set apktool.jar path in Settings)"
    return report
