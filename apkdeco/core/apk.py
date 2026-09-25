"""APK container model: zip listing plus lazy-parsed manifest / resources / dex."""
from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from .axml import AxmlDocument, manifest_summary, parse_axml
from .arsc import ResourcesTable, parse_arsc
from .dex import DexFile

# Entry-group buckets used by the GUI file tree
GROUP_MANIFEST = "manifest"
GROUP_DEX = "dex"
GROUP_ARSC = "arsc"
GROUP_RES = "res"
GROUP_ASSETS = "assets"
GROUP_LIB = "lib"
GROUP_META = "META-INF"
GROUP_OTHER = "other"

GROUP_ORDER = [GROUP_MANIFEST, GROUP_DEX, GROUP_ARSC, GROUP_RES,
               GROUP_ASSETS, GROUP_LIB, GROUP_META, GROUP_OTHER]

MAX_TEXT_PREVIEW = 2 * 1024 * 1024      # 2 MiB text preview cap
MAX_HEX_PREVIEW = 1 * 1024 * 1024       # 1 MiB hex preview cap


@dataclass
class EntryInfo:
    name: str
    size: int
    compress_size: int
    group: str


def classify_entry(name: str) -> str:
    if name == "AndroidManifest.xml":
        return GROUP_MANIFEST
    if name == "resources.arsc":
        return GROUP_ARSC
    base = os.path.basename(name)
    if base.startswith("classes") and base.endswith(".dex"):
        return GROUP_DEX
    if name.startswith("res/") or name.startswith("res\\"):
        return GROUP_RES
    if name.startswith("assets/"):
        return GROUP_ASSETS
    if name.startswith("lib/"):
        return GROUP_LIB
    if name.startswith("META-INF/"):
        return GROUP_META
    return GROUP_OTHER


class ApkError(Exception):
    pass


class ApkFile:
    """Read-only view over an .apk (zip) with lazily parsed internals."""

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        if not os.path.isfile(self.path):
            raise ApkError(f"file not found: {path}")
        try:
            self.zf = zipfile.ZipFile(self.path, "r")
        except zipfile.BadZipFile as e:
            raise ApkError(f"not a valid APK/ZIP: {e}") from e
        self.entries: List[EntryInfo] = []
        for zi in self.zf.infolist():
            if zi.is_dir():
                continue
            self.entries.append(EntryInfo(
                name=zi.filename.replace("\\", "/"),
                size=zi.file_size,
                compress_size=zi.compress_size,
                group=classify_entry(zi.filename.replace("\\", "/")),
            ))
        self._entry_map: Dict[str, EntryInfo] = {e.name: e for e in self.entries}
        self._manifest: Optional[AxmlDocument] = None
        self._manifest_error: Optional[str] = None
        self._resources: Optional[ResourcesTable] = None
        self._resources_error: Optional[str] = None
        self._dex: Dict[str, DexFile] = {}

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        try:
            self.zf.close()
        except Exception:
            pass

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def size(self) -> int:
        return os.path.getsize(self.path)

    def names(self) -> List[str]:
        return [e.name for e in self.entries]

    def read(self, name: str) -> bytes:
        name = name.replace("\\", "/")
        try:
            return self.zf.read(name)
        except KeyError:
            raise ApkError(f"no such entry: {name}") from None

    def has(self, name: str) -> bool:
        return name.replace("\\", "/") in self._entry_map

    # -- lazily parsed internals ------------------------------------------
    @property
    def resources(self) -> Optional[ResourcesTable]:
        if self._resources is None and self._resources_error is None:
            if self.has("resources.arsc"):
                try:
                    self._resources = parse_arsc(self.read("resources.arsc"))
                except Exception as e:  # keep GUI alive on weird tables
                    self._resources_error = str(e)
        return self._resources

    @property
    def resources_error(self) -> Optional[str]:
        _ = self.resources
        return self._resources_error

    def _resolver(self):
        res = self.resources
        return res.resolver() if res is not None else None

    @property
    def manifest(self) -> Optional[AxmlDocument]:
        if self._manifest is None and self._manifest_error is None:
            if self.has("AndroidManifest.xml"):
                data = self.read("AndroidManifest.xml")
                stripped = data.lstrip()
                if stripped.startswith(b"<?xml") or stripped.startswith(b"<manifest"):
                    # Rare: plain-text manifest (uncompressed debug builds).
                    self._manifest = _TextManifest(data)
                else:
                    try:
                        self._manifest = parse_axml(data, resolver=self._resolver())
                    except Exception as e:
                        self._manifest_error = f"manifest parse error: {e}"
        return self._manifest

    @property
    def manifest_error(self) -> Optional[str]:
        _ = self.manifest
        return self._manifest_error

    def manifest_pretty(self) -> str:
        doc = self.manifest
        if doc is None:
            return f"// Could not parse AndroidManifest.xml\n// {self.manifest_error}"
        return doc.pretty_xml()

    def manifest_summary(self) -> dict:
        doc = self.manifest
        if doc is None:
            return {"error": self.manifest_error or "no manifest"}
        try:
            return manifest_summary(doc.root, resolver=self._resolver())
        except Exception as e:
            return {"error": str(e)}

    def dex_names(self) -> List[str]:
        return [e.name for e in self.entries if e.group == GROUP_DEX]

    def dex(self, name: str) -> DexFile:
        if name not in self._dex:
            self._dex[name] = DexFile(self.read(name), name=name)
        return self._dex[name]

    # -- previews ---------------------------------------------------------
    def is_textish(self, name: str) -> bool:
        ext = os.path.splitext(name)[1].lower()
        return ext in (".xml", ".txt", ".json", ".html", ".htm", ".css", ".js",
                       ".java", ".smali", ".properties", ".version", ".name",
                       ".kts", ".gradle", ".pro", ".csv", ".md", ".yml",
                       ".yaml", ".ini", ".cfg", ".list", ".sha1", ".sf",
                       ".mf", ".rsa", ".ec", ".version", ".txt")

    def is_image(self, name: str) -> bool:
        ext = os.path.splitext(name)[1].lower()
        return ext in (".png", ".gif", ".bmp", ".ppm", ".pgm")

    def text_preview(self, name: str) -> str:
        data = self.read(name)
        truncated = len(data) > MAX_TEXT_PREVIEW
        if truncated:
            data = data[:MAX_TEXT_PREVIEW]
        # An XML resource (binary) that lives under res/ or root
        if len(data) >= 2 and data[0:2] == b"\x03\x00":
            try:
                return parse_axml(data, resolver=self._resolver()).pretty_xml()
            except Exception:
                pass
        for enc in ("utf-8", "utf-16-le", "latin-1"):
            try:
                text = data.decode(enc)
                if enc == "utf-16-le" and "\x00" in text[:40]:
                    continue
                if truncated:
                    text += f"\n\n/* preview truncated at {MAX_TEXT_PREVIEW} bytes */\n"
                return text
            except UnicodeDecodeError:
                continue
        return data[:4096].decode("latin-1", "replace")

    def hex_preview(self, name: str) -> bytes:
        data = self.read(name)
        return data[:MAX_HEX_PREVIEW]


class _TextManifest:
    """Adapter so plain-text manifests use the same interface."""

    def __init__(self, data: bytes) -> None:
        self._text = data.decode("utf-8", "replace")
        self.root = None

    def pretty_xml(self) -> str:
        return self._text
