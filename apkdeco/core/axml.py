"""Android binary XML (AXML) parser.

Decodes compiled ``.xml`` resources (most importantly ``AndroidManifest.xml``)
back into an element tree plus pretty-printed textual XML. Pure stdlib.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .blob import BlobReader

# Chunk types
RES_NULL_TYPE = 0x0000
RES_STRING_POOL_TYPE = 0x0001
RES_TABLE_TYPE = 0x0002
RES_XML_TYPE = 0x0003
RES_XML_START_NAMESPACE_TYPE = 0x0100
RES_XML_END_NAMESPACE_TYPE = 0x0101
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103
RES_XML_CDATA_TYPE = 0x0104
RES_XML_RESOURCE_MAP_TYPE = 0x0180

# TypedValue data types
TYPE_NULL = 0x00
TYPE_REFERENCE = 0x01
TYPE_ATTRIBUTE = 0x02
TYPE_STRING = 0x03
TYPE_FLOAT = 0x04
TYPE_DIMENSION = 0x05
TYPE_FRACTION = 0x06
TYPE_DYNAMIC_REFERENCE = 0x07
TYPE_DYNAMIC_ATTRIBUTE = 0x08
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_INT_BOOLEAN = 0x12
TYPE_INT_COLOR_ARGB8 = 0x1C
TYPE_INT_COLOR_RGB8 = 0x1D
TYPE_INT_COLOR_RGB4 = 0x1E

ANDROID_NS_URI = "http://schemas.android.com/apk/res/android"

# Complex unit constants (TypedValue)
COMPLEX_UNIT_MASK = 0x0F
COMPLEX_UNIT_SHIFT = 0
COMPLEX_RADIX_MASK = 0x30
COMPLEX_RADIX_SHIFT = 4
_DIMENSION_UNITS = ("px", "dp", "sp", "pt", "in", "mm", "", "")
_FRACTION_UNITS = ("%", "%p", "", "", "", "", "", "")
_RADIX_MULTS = (1.0, 1.0 / (1 << 7), 1.0 / (1 << 15), 1.0 / (1 << 23))

NO_INDEX = 0xFFFFFFFF


@dataclass
class ResValue:
    """A typed resource value (Res_value)."""

    data_type: int
    data: int
    raw: Optional[str] = None  # raw string index value when present

    def format(self, strings: Optional[List[str]] = None,
               resolver=None) -> str:
        """Human readable form. ``resolver`` may map res ids to names."""
        if self.raw is not None and self.data_type == TYPE_STRING:
            return self.raw
        t = self.data_type
        d = self.data
        if t == TYPE_NULL:
            return ""
        if t in (TYPE_REFERENCE, TYPE_DYNAMIC_REFERENCE):
            if resolver is not None:
                name = resolver(d)
                if name:
                    return name
            return f"@{d:#010x}" if d else "@null"
        if t in (TYPE_ATTRIBUTE, TYPE_DYNAMIC_ATTRIBUTE):
            return f"?{d:#010x}"
        if t == TYPE_STRING:
            if strings is not None and 0 <= d < len(strings):
                return strings[d]
            return ""
        if t == TYPE_FLOAT:
            import struct as _s
            return repr(_s.unpack("<f", _s.pack("<I", d))[0])
        if t == TYPE_DIMENSION:
            return f"{_complex_to_float(d):g}{_DIMENSION_UNITS[d & COMPLEX_UNIT_MASK]}"
        if t == TYPE_FRACTION:
            return f"{_complex_to_float(d) * 100:g}{_FRACTION_UNITS[d & COMPLEX_UNIT_MASK]}"
        if t == TYPE_INT_DEC:
            if d >= 0x80000000:
                d -= 0x100000000
            return str(d)
        if t == TYPE_INT_HEX:
            return f"0x{d:08x}"
        if t == TYPE_INT_BOOLEAN:
            return "true" if d else "false"
        if t == TYPE_INT_COLOR_ARGB8:
            return f"#{d:08x}"
        if t == TYPE_INT_COLOR_RGB8:
            return f"#{d:06x}"
        if t == TYPE_INT_COLOR_RGB4:
            return f"#{d:04x}"
        return f"(type 0x{t:02x}) 0x{d:08x}"


def _complex_to_float(data: int) -> float:
    radix = (data >> COMPLEX_RADIX_SHIFT) & 0x3
    mantissa = data & 0xFFFFFF00
    import struct as _s
    # mantissa is a signed fixed point number
    m = mantissa if mantissa < 0x80000000 else mantissa - 0x100000000
    return m * _RADIX_MULTS[radix]


@dataclass
class XmlAttr:
    name: str
    value: ResValue
    ns_uri: str = ""


@dataclass
class XmlNode:
    name: str
    ns_uri: str = ""
    attrs: List[XmlAttr] = field(default_factory=list)
    children: List["XmlNode"] = field(default_factory=list)
    text: str = ""

    def get(self, name: str) -> Optional[str]:
        for a in self.attrs:
            if a.name == name:
                return a.value.format()
        return None

    def get_value(self, name: str) -> Optional[ResValue]:
        for a in self.attrs:
            if a.name == name:
                return a.value
        return None

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()


class AxmlError(ValueError):
    pass


def _decode_string_pool(r: BlobReader) -> List[str]:
    start = r.tell()
    (ctype, header_size, chunk_size) = r.u16(), r.u16(), r.u32()
    if ctype != RES_STRING_POOL_TYPE:
        raise AxmlError(f"expected string pool chunk, got 0x{ctype:04x}")
    string_count, style_count, flags, strings_start, styles_start = (
        r.u32(), r.u32(), r.u32(), r.u32(), r.u32())
    utf8 = bool(flags & (1 << 8))
    offsets = [r.u32() for _ in range(string_count)]
    strings: List[str] = []
    for off in offsets:
        sreader = r.at(start + strings_start + off)
        if utf8:
            # two length fields: utf16 length, utf8 byte length (both ext.)
            _u16len = _read_len8(sreader)
            bytelen = _read_len8(sreader)
            raw = sreader.raw(bytelen)
            try:
                s = raw.decode("utf-8", "replace")
            except Exception:
                s = raw.decode("latin-1")
        else:
            charlen = _read_len16(sreader)
            raw = sreader.raw(charlen * 2)
            s = raw.decode("utf-16-le", "replace")
        strings.append(s)
    return strings


def _read_len8(r: BlobReader) -> int:
    b0 = r.u8()
    if b0 & 0x80:
        b1 = r.u8()
        return ((b0 & 0x7F) << 8) | b1
    return b0


def _read_len16(r: BlobReader) -> int:
    w0 = r.u16()
    if w0 & 0x8000:
        w1 = r.u16()
        return ((w0 & 0x7FFF) << 16) | w1
    return w0


def _read_value(r: BlobReader, strings: List[str]) -> ResValue:
    size = r.u16()
    r.u8()  # res0
    data_type = r.u8()
    data = r.u32()
    raw = None
    if data_type == TYPE_STRING and 0 <= data < len(strings):
        raw = strings[data]
    return ResValue(data_type, data, raw)


class _NsStack:
    def __init__(self) -> None:
        self._stack: List[Dict[str, str]] = [{}]

    def push(self) -> None:
        self._stack.append(dict(self._stack[-1]))

    def pop(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()

    def bind(self, prefix: str, uri: str) -> None:
        self._stack[-1][uri] = prefix

    def prefix_for(self, uri: str) -> Optional[str]:
        return self._stack[-1].get(uri)


def parse_axml(data: bytes,
               resolver=None) -> "AxmlDocument":
    """Parse binary XML into an :class:`AxmlDocument`."""
    r = BlobReader(data)
    ctype, header_size, chunk_size = r.u16(), r.u16(), r.u32()
    if ctype != RES_XML_TYPE:
        raise AxmlError(f"not a binary XML document (chunk type 0x{ctype:04x})")

    strings: List[str] = []
    ns = _NsStack()
    root: Optional[XmlNode] = None
    stack: List[XmlNode] = []
    pending_text: List[str] = []

    end = min(len(data), chunk_size if chunk_size else len(data))
    while r.tell() < end:
        chunk_off = r.tell()
        if r.remaining() < 8:
            break
        c_type, c_header, c_size = r.u16(), r.u16(), r.u32()
        if c_size < 8:
            break
        chunk_end = chunk_off + c_size

        if c_type == RES_STRING_POOL_TYPE:
            r.seek(chunk_off)
            strings = _decode_string_pool(r)
        elif c_type == RES_XML_RESOURCE_MAP_TYPE:
            pass  # attribute resource ids; not needed for display
        elif c_type in (RES_XML_START_NAMESPACE_TYPE, RES_XML_END_NAMESPACE_TYPE):
            r.seek(chunk_off + c_header)
            prefix_idx, uri_idx = r.u32(), r.u32()
            uri = strings[uri_idx] if uri_idx < len(strings) else ""
            if c_type == RES_XML_START_NAMESPACE_TYPE:
                ns.bind(strings[prefix_idx] if prefix_idx < len(strings) else "", uri)
            else:
                ns.pop()
        elif c_type == RES_XML_START_ELEMENT_TYPE:
            r.seek(chunk_off + c_header)
            ns_idx, name_idx = r.u32(), r.u32()
            attr_start, attr_size, attr_count = r.u16(), r.u16(), r.u16()
            r.u16(), r.u16(), r.u16()  # idIndex, classIndex, styleIndex
            name = strings[name_idx] if name_idx < len(strings) else "?"
            node = XmlNode(name=name)
            node.ns_uri = strings[ns_idx] if ns_idx < len(strings) and ns_idx != NO_INDEX else ""
            # attributes start after the attrExt structure (offset attr_start
            # is measured from the start of ResXMLTree_attrExt).
            attr_base = chunk_off + c_header + attr_start
            for i in range(attr_count):
                ar = r.at(attr_base + i * max(attr_size, 20))
                a_ns, a_name, a_raw = ar.u32(), ar.u32(), ar.u32()
                val = _read_value(ar, strings)
                if a_raw != NO_INDEX and val.data_type == TYPE_STRING and val.raw is None:
                    if a_raw < len(strings):
                        val = ResValue(TYPE_STRING, a_raw, strings[a_raw])
                nm = strings[a_name] if a_name < len(strings) else f"attr{i}"
                uri = (strings[a_ns]
                       if a_ns != NO_INDEX and a_ns < len(strings) else "")
                node.attrs.append(XmlAttr(nm, val, uri))
            if stack:
                stack[-1].children.append(node)
            elif root is None:
                root = node
            stack.append(node)
            pending_text = []
        elif c_type == RES_XML_END_ELEMENT_TYPE:
            r.seek(chunk_off + c_header)
            r.u32(), r.u32()  # ns, name
            if pending_text and stack:
                stack[-1].text += "".join(pending_text)
                pending_text = []
            if stack:
                stack.pop()
        elif c_type == RES_XML_CDATA_TYPE:
            r.seek(chunk_off + c_header)
            text_idx = r.u32()
            if text_idx < len(strings):
                pending_text.append(strings[text_idx])
        # else: unknown/reserved chunk - skip
        r.seek(chunk_end)

    return AxmlDocument(root if root is not None else XmlNode("?"), strings, resolver)


class AxmlDocument:
    def __init__(self, root: XmlNode, strings: List[str], resolver=None) -> None:
        self.root = root
        self.strings = strings
        self._resolver = resolver

    def _res_name(self, res_id: int) -> Optional[str]:
        if self._resolver is not None:
            return self._resolver(res_id)
        return None

    def pretty_xml(self) -> str:
        out = io.StringIO()
        out.write('<?xml version="1.0" encoding="utf-8"?>\n')
        self._write_node(out, self.root, 0, set())
        return out.getvalue()

    def _qname(self, node_or_attr_name: str, ns_uri: str, seen: set) -> str:
        if not ns_uri:
            return node_or_attr_name
        prefix = ""
        if ns_uri == ANDROID_NS_URI:
            prefix = "android"
        else:
            short = ns_uri.rstrip("/").split("/")[-1] or "ns"
            prefix = short if short.isidentifier() else "ns"
            if prefix in seen and ns_uri not in seen:
                prefix = f"{prefix}{len(seen)}"
        seen.add(ns_uri if prefix else "")
        return f"{prefix}:{node_or_attr_name}"

    def _write_node(self, out, node: XmlNode, depth: int, seen_ns: set) -> None:
        pad = "    " * depth
        qn = self._qname(node.name, node.ns_uri, seen_ns)
        out.write(f"{pad}<{qn}")
        for a in node.attrs:
            aq = self._qname(a.name, a.ns_uri, seen_ns)
            disp = a.value.format(self.strings, self._res_name)
            out.write(f"\n{pad}    {aq}=\"{_escape(disp)}\"")
        if node.children:
            out.write(">\n")
            for c in node.children:
                self._write_node(out, c, depth + 1, seen_ns)
            if node.text.strip():
                out.write(f"{pad}    {_escape(node.text.strip())}\n")
            out.write(f"{pad}</{qn}>\n")
        elif node.text.strip():
            out.write(">")
            out.write(_escape(node.text.strip()))
            out.write(f"</{qn}>\n")
        else:
            out.write(" />\n")


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


ANDROID = ANDROID_NS_URI


def manifest_summary(root: XmlNode, resolver=None) -> Dict[str, object]:
    """Extract key facts from an AndroidManifest element tree."""
    def fmt(node: XmlNode, name: str) -> Optional[str]:
        v = node.get_value(name)
        if v is None:
            return None
        return v.format(resolver=resolver)

    summary: Dict[str, object] = {}
    summary["package"] = root.get("package")
    summary["versionName"] = fmt(root, "versionName")
    vc = root.get_value("versionCode")
    if vc is not None:
        summary["versionCode"] = vc.format(resolver=resolver) or str(vc.data)

    perms: List[str] = []
    components: Dict[str, List[Dict[str, str]]] = {
        "activities": [], "services": [], "receivers": [], "providers": [],
        "activity-aliases": [],
    }
    sdk: Dict[str, str] = {}

    for node in root.children:
        if node.name == "uses-permission":
            p = fmt(node, "name")
            if p:
                perms.append(p)
        elif node.name == "uses-sdk":
            for k in ("minSdkVersion", "targetSdkVersion", "maxSdkVersion"):
                v = fmt(node, k)
                if v is not None:
                    sdk[k] = v
        elif node.name == "application":
            summary["app_label"] = fmt(node, "label")
            summary["debuggable"] = fmt(node, "debuggable")
            for comp in node.children:
                key = {
                    "activity": "activities",
                    "activity-alias": "activity-aliases",
                    "service": "services",
                    "receiver": "receivers",
                    "provider": "providers",
                }.get(comp.name)
                if not key:
                    continue
                entry = {"name": fmt(comp, "name") or "?"}
                exported = fmt(comp, "exported")
                if exported is not None:
                    entry["exported"] = exported
                perm = fmt(comp, "permission")
                if perm:
                    entry["permission"] = perm
                if comp.name == "activity-alias":
                    tgt = fmt(comp, "targetActivity")
                    if tgt:
                        entry["targetActivity"] = tgt
                components[key].append(entry)

    summary["permissions"] = sorted(set(perms))
    summary["sdk"] = sdk
    summary.update(components)
    return summary
