# APKDeco — APK Decompiler GUI for Windows

A desktop GUI for opening, exploring and decompiling Android **.apk** files on Windows.

APKDeco combines a **built-in analysis core** (pure Python, zero dependencies — works
offline, no Java required) with **one-click integration of jadx and apktool** for full
Java/smali decompilation.

```
+----------------------------------------------------------------------+
|  [Open APK]  [Decompile Java]  [Decode (apktool)]  [Extract All]      |
+----------------------+-----------------------------------------------+
| Files tree           |  [Overview] [Manifest] [classes.dex] [res/…]  |
|  ├ Manifest          |                                               |
|  ├ DEX code          |   decoded binary XML / hex / images /         |
|  ├ Resources table   |   DEX class explorer / search results         |
|  ├ res/  assets/     |                                               |
|  └ lib/  META-INF/   |                                               |
| Search tab           |                                               |
+----------------------+-----------------------------------------------+
|  job log (jadx / apktool output)                                     |
+----------------------------------------------------------------------+
|  status bar: file info · busy spinner · tool results                 |
+----------------------------------------------------------------------+
```

## Features

**Built-in (no external tools needed)**

- **APK browser** — full zip listing grouped by Manifest / DEX / resources / res / assets / lib / signatures, with folder tree, sizes and icons
- **AndroidManifest.xml decoder** — parses compiled (binary) XML in pure Python and
  pretty-prints it, with `android:` namespace handling
- **Manifest overview** — package, version, min/target SDK, permissions, activities,
  services, receivers, providers and their `exported` flags at a glance
- **resources.arsc resolver** — `@string/app_name`-style references resolve to real
  values (dense, offset-16 and sparse resource tables supported)
- **DEX explorer** — class / method / field listings with proper Java signatures
  (`public static void main(java.lang.String[])`), access flags, super/interfaces,
  plus a filterable string table and DEX header info (multi-DEX aware)
- **Viewers** — virtualized hex+ASCII viewer (GB-safe), text viewer with find
  (Ctrl+F) and light syntax highlighting, PNG/GIF image preview
- **Search** — file names, file contents and DEX strings in one query
- **Extract** — save any entry or extract the whole APK (with zip-slip protection)

**One-click decompilation (via free external tools)**

- **jadx** — decompile to readable **Java source** + resources (`F5`)
- **apktool** — decode to **smali** + fully decoded resources, `apktool.yml`
  for rebuilding (`F6`)
- Live job log, cancel support, console-window-free process launching,
  open-output-in-Explorer when done
- Auto-detection of tools on `PATH` / `JAVA_HOME`, or set explicit paths in Settings

**Windows-native feel**

- Dark and light themes
- DPI-aware (crisp on high-DPI displays)
- Remembers window size, recent APKs, tool paths (`%APPDATA%\APKDeco`)
- Runs from source **or** as a single `APKDeco.exe` (no Python needed)

## Install & run

### Option A — run from source (Windows)

1. Install [Python 3.9+](https://www.python.org/downloads/windows/) (tkinter is included)
2. Clone and start:

```bat
git clone https://github.com/hexa11121-tech/dummy.git
cd dummy
python main.py
python main.py some.apk      (optional: open an APK immediately)
```

No pip packages required — the app is pure standard library.

### Option B — build the .exe

```bat
build\build_windows.bat
dist\APKDeco.exe
```

Or grab `APKDeco.exe` from the CI artifact / GitHub Release (see the
**Build Windows exe** workflow). To build the exe you need
`pip install pyinstaller pillow` (the script does this for you).

### Option C — Linux/macOS (dev)

The GUI runs anywhere Tk 8.6+ exists (`python3-tk` package). The decompiler-tool
integration works the same when `jadx` / `apktool` / `java` are on `PATH`.

## Full Java/smali decompilation (recommended install)

The built-in core shows structure instantly; for **Java source** and **smali** add:

| Tool    | What it gives you                | Install |
|---------|----------------------------------|---------|
| **jadx** 1.4+ | Java source + resources    | [github.com/skylot/jadx/releases](https://github.com/skylot/jadx/releases) (get the `-without-jre` zip or the JRE bundle) |
| **apktool** 2.9+ | smali + decoded resources (rebuildable) | [apktool.org](https://apktool.org/) (`apktool.jar`) |
| **Java** 11+  | required by apktool (jadx bundles its own runtime in some builds) | [adoptium.net](https://adoptium.net/) |

Then in APKDeco: **Settings → Check tools** should show all green. Either put the
tools on `PATH` or browse to their location (`jadx.bat` or the jadx folder,
`apktool.jar`).

> Where is my jadx/apktool? Typical places: `%USERPROFILE%\jadx\bin\jadx.bat`,
> `%LOCALAPPDATA%\Programs\jadx\bin\jadx.bat`. The Settings dialog accepts the
> folder too.

## Usage tips

- `Ctrl+O` open · `F5` jadx decompile · `F6` apktool decode · `Ctrl+F` find in current tab
- Right-click a file in the tree: open as hex, save entry, copy name
- Middle-click (or `Ctrl+W`) closes a viewer tab
- Double-click a class member / string copies it to the clipboard
- The **Search** tab indexes entry names, text contents and all DEX strings
- Output goes to `<apk folder>\<apk name>_decoded` (configurable in Settings)

## Architecture

```
main.py                  entry point (+ --selftest)
apkdeco/
  app.py                 Tk bootstrap, DPI awareness, icon
  core/                  pure-stdlib analysis (GUI-independent, unit-tested)
    axml.py              Android binary XML parser + pretty printer
    arsc.py              resources.arsc parser + reference resolver
    dex.py               DEX parser: classes, members, strings, header
    apk.py               APK/zip model, lazy parsing, previews
    tools.py             jadx / apktool / java discovery + runner
    jobs.py              background job queue (keeps UI responsive)
    settings.py          %APPDATA% settings + recent files
  gui/
    theme.py             dark/light ttk themes
    widgets.py           hex viewer, code viewer, image preview, log, icons
    dialogs.py           settings + about dialogs
    main_window.py       the application window
tests/                   unit tests + synthetic AXML/ARSC/DEX/APK fixtures
build/                   PyInstaller spec, build_windows.bat, png2ico.py
```

Run the test-suite headless (also used by CI):

```bat
python main.py --selftest
:: or
python -m unittest discover -s tests -t .
```

The tests build *synthetic* Android binaries (AXML documents, a resource table, a
DEX file, a full APK) and verify every parser round-trips them — no proprietary
sample APKs are stored in the repo.

## Scope & roadmap

- APKDeco is an **analyzer**: it never modifies or signs APKs
- Planned: APK rebuild shortcut (apktool `b`), signing helper, export decompiled
  tree to project folder, JPEG/WebP preview via optional Pillow, drag & drop

## Legal

Use only on APKs you own or are authorized to analyze. Decompiling third-party
apps may be restricted by local law and by the app's license. This tool is provided
for interoperability testing, security research and education.

## License

MIT — see [LICENSE](LICENSE). jadx and apktool are separate projects with their
own licenses; APKDeco simply launches them when installed.
