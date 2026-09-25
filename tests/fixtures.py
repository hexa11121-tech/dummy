"""Builders for minimal-but-real Android binary fixtures (AXML / ARSC / DEX).

Used by the unit tests so parser behaviour is verified without shipping
proprietary sample APKs in the repository.
"""
from __future__ import annotations

import struct
import zipfile
from typing import Dict, List, Optional, Sequence, Tuple

from apkdeco.core.blob import uleb128_bytes

Attr = Tuple[str, str]                 # (name, literal string value)
Element = Tuple[str, List[Attr]]       # (tag, attrs)


# ---------------------------------------------------------------------------
# string pool
# ---------------------------------------------------------------------------

def build_string_pool(strings: Sequence[str], utf8: bool = False) -> bytes:
    """ResStringPool chunk (type 0x0001)."""
    def len8(n: int) -> bytes:
        if n < 0x80:
            return bytes([n])
        return bytes([((n >> 8) & 0x7F) | 0x80, n & 0xFF])

    def len16(n: int) -> bytes:
        if n < 0x8000:
            return struct.pack("<H", n)
        return struct.pack("<HH", ((n >> 16) & 0x7FFF) | 0x8000, n & 0xFFFF)

    offsets: List[int] = []
    body = bytearray()
    for s in strings:
        offsets.append(len(body))
        if utf8:
            u = s.encode("utf-8")
            body += len8(len(s)) + len8(len(u)) + u + b"\x00"
        else:
            body += len16(len(s)) + s.encode("utf-16-le") + b"\x00"
        while len(body) % 4:
            body += b"\x00"

    header_size = 28
    strings_start = header_size + 4 * len(strings)
    chunk_size = strings_start + len(body)
    out = bytearray()
    out += struct.pack("<HHI", 0x0001, header_size, chunk_size)
    out += struct.pack("<IIIII", len(strings), 0, (1 << 8) if utf8 else 0,
                       strings_start, 0)
    for off in offsets:
        out += struct.pack("<I", off)
    out += body
    return bytes(out)


# ---------------------------------------------------------------------------
# binary XML (AXML)
# ---------------------------------------------------------------------------

NS_URI = "http://schemas.android.com/apk/res/android"


def build_axml_document(
    elements: Sequence[Element],
    root_name: str = "manifest",
    root_attrs: Optional[Sequence[Attr]] = None,
    android_ns: bool = True,
) -> bytes:
    """Build AXML: <root_name attrs><elements .../></root_name>.

    All attribute values are stored as TYPE_STRING, which is enough for tests.
    """
    strings: List[str] = []
    index: Dict[str, int] = {}

    def sid(s: str) -> int:
        if s not in index:
            index[s] = len(strings)
            strings.append(s)
        return index[s]

    sid(root_name)
    for tag, attrs in list(elements) + ([("m", list(root_attrs or []))] if root_attrs else []):
        if tag != "m":
            sid(tag)
        for k, v in attrs:
            sid(k)
            sid(v)
    sid("android")
    sid(NS_URI)

    def chunk(ctype: int, body: bytes) -> bytes:
        return struct.pack("<HHI", ctype, 16, 8 + len(body)) + body

    def node_head() -> bytes:
        return struct.pack("<II", 1, 0xFFFFFFFF)      # lineNumber, comment

    def start_element(tag: str, attrs: Sequence[Attr]) -> bytes:
        attr_ext = struct.pack("<IIHHHHHH", 0xFFFFFFFF, sid(tag), 20, 20,
                               len(attrs), 0, 0, 0)
        attr_recs = b""
        for k, v in attrs:
            a_ns = sid(NS_URI) if android_ns else 0xFFFFFFFF
            attr_recs += struct.pack("<III", a_ns, sid(k), sid(v))
            attr_recs += struct.pack("<HBBI", 8, 0, 0x03, sid(v))  # TYPE_STRING
        return chunk(0x0102, node_head() + attr_ext + attr_recs)

    def end_element(tag: str) -> bytes:
        return chunk(0x0103,
                     node_head() + struct.pack("<II", 0xFFFFFFFF, sid(tag)))

    body = bytearray()
    if android_ns:
        body += chunk(0x0100,
                      node_head() + struct.pack("<II", sid("android"), sid(NS_URI)))

    body += start_element(root_name, root_attrs or [])
    for tag, attrs in elements:
        body += start_element(tag, attrs)
        body += end_element(tag)
    body += end_element(root_name)

    if android_ns:
        body += chunk(0x0101,
                      node_head() + struct.pack("<II", sid("android"), sid(NS_URI)))

    pool = build_string_pool(strings)
    return (struct.pack("<HHI", 0x0003, 8, 8 + len(pool) + len(body))
            + pool + bytes(body))


# ---------------------------------------------------------------------------
# resources.arsc (minimal: one package, one 'string' type with 2 entries)
# ---------------------------------------------------------------------------

def _res_value(data_type: int, data: int) -> bytes:
    return struct.pack("<HBBI", 8, 0, data_type, data)


def build_arsc_minimal() -> Tuple[bytes, Dict[str, int]]:
    """Return (arsc_bytes, {'hello': res_id, 'app_name': res_id})."""
    value_strings = ["Hello, APKDeco!", "APKDeco Test"]
    type_strings = ["string"]
    key_strings = ["hello", "app_name"]

    global_pool = build_string_pool(value_strings)
    type_pool = build_string_pool(type_strings)
    key_pool = build_string_pool(key_strings)

    # -- one ResTable_type chunk (type id 1 = 'string'), dense offsets -------
    entries = bytearray()
    entry_offsets: List[int] = []
    for key_i, val_i in ((0, 0), (1, 1)):
        entry_offsets.append(len(entries))
        entries += struct.pack("<HHI", 8, 0, key_i)      # ResTable_entry
        entries += _res_value(0x03, val_i)               # string value
    entry_count = 2
    offsets_tbl = b"".join(struct.pack("<I", o) for o in entry_offsets)

    # ResTable_type: chunk hdr(8) + id/flags/res(4) + entryCount(4)
    #   + entriesStart(4) + config(size u32 + 24 zero bytes)
    config = struct.pack("<I", 28) + b"\x00" * 24
    type_header_size = 8 + 12 + len(config)           # 0x30
    entries_start = type_header_size + len(offsets_tbl)
    type_chunk_size = entries_start + len(entries)
    type_chunk = (
        struct.pack("<HHI", 0x0201, type_header_size, type_chunk_size)
        + struct.pack("<BBHII", 1, 0, 0, entry_count, entries_start)
        + config + offsets_tbl + bytes(entries)
    )

    # -- typeSpec -----------------------------------------------------------
    type_spec = (struct.pack("<HHI", 0x0202, 16, 16 + 4 * entry_count)
                 + struct.pack("<BBHI", 1, 0, 0, entry_count)
                 + struct.pack("<II", 0, 0))

    # -- package chunk -------------------------------------------------------
    pkg_id = 0x7F
    name_raw = "com.example.test".encode("utf-16-le") + b"\x00\x00"
    name_raw = name_raw.ljust(256, b"\x00")
    pkg_header_size = 288     # with typeIdOffset (modern layout)

    inner = bytearray()
    inner += struct.pack("<I", pkg_id)
    inner += name_raw
    type_strings_slot = len(inner)
    inner += struct.pack("<I", 0)          # typeStrings placeholder
    inner += struct.pack("<I", 0)          # lastPublicType
    key_strings_slot = len(inner)
    inner += struct.pack("<I", 0)          # keyStrings placeholder
    inner += struct.pack("<I", 0)          # lastPublicKey
    inner += struct.pack("<I", 0)          # typeIdOffset
    assert 8 + len(inner) == pkg_header_size

    type_strings_off = pkg_header_size
    key_strings_off = type_strings_off + len(type_pool)
    struct.pack_into("<I", inner, type_strings_slot, type_strings_off)
    struct.pack_into("<I", inner, key_strings_slot, key_strings_off)

    pkg_body = bytes(inner) + type_pool + key_pool + type_spec + type_chunk
    pkg_chunk = struct.pack("<HHI", 0x0200, pkg_header_size,
                            8 + len(pkg_body)) + pkg_body

    # -- table ---------------------------------------------------------------
    header_size = 12
    table_body = global_pool + pkg_chunk
    table = (struct.pack("<HHI", 0x0002, header_size, header_size + len(table_body))
             + struct.pack("<I", 1) + table_body)

    ids = {
        "hello": (pkg_id << 24) | (1 << 16) | 0,
        "app_name": (pkg_id << 24) | (1 << 16) | 1,
    }
    return table, ids


# ---------------------------------------------------------------------------
# DEX (minimal but structurally valid for the parser)
# ---------------------------------------------------------------------------

def build_dex_minimal() -> bytes:
    """Tiny DEX: class com.example.Main extends Object implements IFace,
    private int hello, public static void main(String[])."""
    strings = [
        "Lcom/example/Main;",             # 0
        "Ljava/lang/Object;",             # 1
        "Lcom/example/IFace;",            # 2
        "Main.java",                      # 3
        "main",                           # 4
        "([Ljava/lang/String;)V",         # 5
        "V",                              # 6
        "Ljava/lang/String;",             # 7
        "hello",                          # 8
        "I",                              # 9
        "<init>",                         # 10
        "hello wörld ✓",                   # 11 (unicode smoke test)
        "[Ljava/lang/String;",            # 12
    ]
    types = ["Lcom/example/Main;", "Ljava/lang/Object;", "Lcom/example/IFace;",
             "V", "Ljava/lang/String;", "[Ljava/lang/String;", "I"]

    def sidx(s: str) -> int:
        return strings.index(s)

    def tidx(s: str) -> int:
        return types.index(s)

    data = bytearray()
    string_data_offs: List[int] = []
    for s in strings:
        string_data_offs.append(len(data))
        enc = s.encode("utf-8").replace(b"\x00", b"\xc0\x80") + b"\x00"
        data += uleb128_bytes(len(s)) + enc
    while len(data) % 4:
        data += b"\x00"

    params_off_rel = len(data)               # type_list: [Ljava/lang/String;
    data += struct.pack("<IH", 1, tidx("[Ljava/lang/String;"))
    while len(data) % 4:
        data += b"\x00"

    class_data_rel = len(data)
    data += uleb128_bytes(0)                 # static_fields_size
    data += uleb128_bytes(1)                 # instance_fields_size
    data += uleb128_bytes(1)                 # direct_methods_size
    data += uleb128_bytes(0)                 # virtual_methods_size
    data += uleb128_bytes(0) + uleb128_bytes(0x2)                   # field 0, private
    data += uleb128_bytes(0) + uleb128_bytes(0x9) + uleb128_bytes(0)  # method 0
    while len(data) % 4:
        data += b"\x00"

    iface_list_rel = len(data)               # type_list: Lcom/example/IFace;
    data += struct.pack("<IH", 1, tidx("Lcom/example/IFace;"))
    while len(data) % 4:
        data += b"\x00"

    header_size = 0x70
    string_ids_off = header_size
    type_ids_off = string_ids_off + 4 * len(strings)
    proto_ids_off = type_ids_off + 4 * len(types)
    field_ids_off = proto_ids_off + 12 * 1
    method_ids_off = field_ids_off + 8 * 1
    class_defs_off = method_ids_off + 8 * 1
    data_off = class_defs_off + 32 * 1

    def abs_off(rel: int) -> int:
        return data_off + rel

    out = bytearray()
    out += b"dex\n035\x00"
    out += struct.pack("<I", 0x11223344)              # checksum (unchecked)
    out += b"\x11" * 20                                # signature
    size_pos = len(out)
    out += struct.pack("<III", 0, header_size, 0x12345678)  # size, hdr, endian
    out += struct.pack("<II", 0, 0)                   # link_size/off
    out += struct.pack("<I", data_off)                # map_off (unused here)
    out += struct.pack("<II", len(strings), string_ids_off)
    out += struct.pack("<II", len(types), type_ids_off)
    out += struct.pack("<II", 1, proto_ids_off)
    out += struct.pack("<II", 1, field_ids_off)
    out += struct.pack("<II", 1, method_ids_off)
    out += struct.pack("<II", 1, class_defs_off)
    out += struct.pack("<II", len(data), data_off)
    assert len(out) == header_size, len(out)

    for rel in string_data_offs:
        out += struct.pack("<I", abs_off(rel))
    for t in types:
        out += struct.pack("<I", sidx(t))
    out += struct.pack("<III", sidx("([Ljava/lang/String;)V"),
                       tidx("V"), abs_off(params_off_rel))
    out += struct.pack("<HHI", tidx("Lcom/example/Main;"), tidx("I"), sidx("hello"))
    out += struct.pack("<HHI", tidx("Lcom/example/Main;"), 0, sidx("main"))
    out += struct.pack("<IIII", tidx("Lcom/example/Main;"), 0x1,
                       tidx("Ljava/lang/Object;"), abs_off(iface_list_rel))
    out += struct.pack("<IIII", sidx("Main.java"), 0, abs_off(class_data_rel), 0)

    out += data
    struct.pack_into("<I", out, size_pos, len(out))
    return bytes(out)


# ---------------------------------------------------------------------------
# APK assembly
# ---------------------------------------------------------------------------

def build_test_apk(path: str, manifest: Optional[bytes] = None,
                   with_dex: bool = True, with_arsc: bool = True) -> str:
    arsc, _ids = build_arsc_minimal()
    if manifest is None:
        manifest = build_axml_document(
            elements=[
                ("uses-permission", [("name", "android.permission.INTERNET")]),
                ("application", [("label", "@string/app_name")]),
            ],
            root_attrs=[("package", "com.example.test"),
                        ("versionName", "1.2.3")],
        )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AndroidManifest.xml", manifest)
        if with_arsc:
            zf.writestr("resources.arsc", arsc)
        if with_dex:
            zf.writestr("classes.dex", build_dex_minimal())
        zf.writestr("res/values/strings.xml", "<resources>plain text</resources>")
        zf.writestr("assets/config.json", '{"debug": true}')
        zf.writestr("META-INF/CERT.SF", "Signature-Version: 1.0\n")
        zf.writestr("lib/arm64-v8a/libnative.so", b"\x7fELF\x02\x01\x01\x00fake")
    return path
