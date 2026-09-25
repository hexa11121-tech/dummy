"""Dalvik DEX parser: header info, class / method / field listings, strings.

This is a *viewer* (not a decompiler): it extracts the class structure and the
string pool from ``classes.dex`` without any external tools. Full Java/smali
decompilation is delegated to jadx / apktool when they are installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .blob import BlobReader

NO_INDEX = 0xFFFFFFFF

ACCESS_FLAGS = [
    (0x00000001, "public"),
    (0x00000002, "private"),
    (0x00000004, "protected"),
    (0x00000008, "static"),
    (0x00000010, "final"),
    (0x00000020, "synchronized"),
    (0x00000040, "bridge"),
    (0x00000080, "varargs"),
    (0x00000100, "native"),
    (0x00000200, "interface"),
    (0x00000400, "abstract"),
    (0x00000800, "strictfp"),
    (0x00001000, "synthetic"),
    (0x00002000, "annotation"),
    (0x00004000, "enum"),
    (0x00010000, "constructor"),
    (0x00020000, "declared-synchronized"),
]


def access_flags_str(flags: int) -> str:
    names = [n for bit, n in ACCESS_FLAGS if flags & bit]
    return " ".join(names)


PRIMITIVES = {
    "V": "void", "Z": "boolean", "B": "byte", "S": "short", "C": "char",
    "I": "int", "J": "long", "F": "float", "D": "double",
}


def type_name(desc: str) -> str:
    """``Lfoo/Bar;`` -> ``foo.Bar``, ``[I`` -> ``int[]``."""
    dims = 0
    while desc.startswith("["):
        dims += 1
        desc = desc[1:]
    if desc in PRIMITIVES:
        base = PRIMITIVES[desc]
    elif desc.startswith("L") and desc.endswith(";"):
        base = desc[1:-1].replace("/", ".")
    elif desc == "":
        base = "?"
    else:
        base = desc
    return base + "[]" * dims


@dataclass
class DexField:
    name: str
    type_desc: str
    access: int

    def signature(self) -> str:
        return (f"{access_flags_str(self.access)} {type_name(self.type_desc)} "
                f"{self.name}").strip()


@dataclass
class DexMethod:
    name: str
    proto_desc: str          # e.g. (ILjava/lang/String;)V
    access: int
    code_off: int = 0

    def signature(self) -> str:
        ret, params = split_proto(self.proto_desc)
        return (f"{access_flags_str(self.access)} {type_name(ret)} {self.name}"
                f"({', '.join(type_name(p) for p in params)})").strip()


@dataclass
class DexClass:
    name: str                # dotted java name
    raw_name: str            # descriptor Lfoo/Bar;
    super_name: Optional[str]
    interfaces: List[str] = field(default_factory=list)
    source_file: Optional[str] = None
    access: int = 0
    fields: List[DexField] = field(default_factory=list)
    methods: List[DexMethod] = field(default_factory=list)


@dataclass
class DexInfo:
    dex_version: str = ""
    file_size: int = 0
    checksum: int = 0
    class_count: int = 0
    method_count: int = 0
    field_count: int = 0
    string_count: int = 0
    type_count: int = 0


def split_proto(proto_desc: str) -> Tuple[str, List[str]]:
    """``(ILjava/lang/String;)V`` -> ``('V', ['I', 'Ljava/lang/String;'])``."""
    assert proto_desc.startswith("(")
    end = proto_desc.index(")")
    params_s = proto_desc[1:end]
    ret = proto_desc[end + 1:]
    params: List[str] = []
    i = 0
    while i < len(params_s):
        j = i
        while params_s[j] == "[":
            j += 1
        if params_s[j] == "L":
            j = params_s.index(";", j) + 1
        else:
            j += 1
        params.append(params_s[i:j])
        i = j
    return ret, params


def _mutf8_decode(raw: bytes) -> str:
    """Decode Modified UTF-8 (as used by DEX string ids)."""
    fixed = raw.replace(b"\xc0\x80", b"\x00")
    try:
        return fixed.decode("utf-8", "surrogatepass")
    except UnicodeDecodeError:
        return fixed.decode("latin-1")


class DexFile:
    def __init__(self, data: bytes, name: str = "classes.dex") -> None:
        self.name = name
        self.data = data
        self._strings: Optional[List[str]] = None
        self._classes: Optional[List[DexClass]] = None
        self._parse_header()

    # -- header -----------------------------------------------------------
    def _parse_header(self) -> None:
        r = BlobReader(self.data)
        magic = r.raw(8)
        if not magic.startswith(b"dex\n"):
            raise ValueError(f"{self.name}: not a standard DEX file (magic {magic[:8]!r})")
        self.info = DexInfo(dex_version=magic[4:7].decode("ascii", "replace"))
        self.info.checksum = r.u32()
        r.raw(20)  # signature
        self.info.file_size = r.u32()
        header_size = r.u32()
        endian = r.u32()
        if endian != 0x12345678:
            raise ValueError(f"{self.name}: unsupported endian tag 0x{endian:08x}")
        r.u32(); r.u32()  # link_size, link_off
        r.u32()           # map_off
        self._string_ids_size, self._string_ids_off = r.u32(), r.u32()
        self._type_ids_size, self._type_ids_off = r.u32(), r.u32()
        self._proto_ids_size, self._proto_ids_off = r.u32(), r.u32()
        self._field_ids_size, self._field_ids_off = r.u32(), r.u32()
        self._method_ids_size, self._method_ids_off = r.u32(), r.u32()
        self._class_defs_size, self._class_defs_off = r.u32(), r.u32()
        self.info.string_count = self._string_ids_size
        self.info.type_count = self._type_ids_size
        self.info.field_count = self._field_ids_size
        self.info.method_count = self._method_ids_size
        self.info.class_count = self._class_defs_size
        _ = header_size

    # -- strings ----------------------------------------------------------
    @property
    def strings(self) -> List[str]:
        if self._strings is None:
            out: List[str] = []
            r = BlobReader(self.data)
            for i in range(self._string_ids_size):
                r.seek(self._string_ids_off + i * 4)
                data_off = r.u32()
                sr = r.at(data_off)
                try:
                    sr.uleb128()  # utf16_size
                    # read MUTF-8 bytes until NUL
                    start = sr.tell()
                    while sr.u8() != 0:
                        pass
                    raw = self.data[start:sr.tell() - 1]
                    out.append(_mutf8_decode(raw))
                except (EOFError, ValueError):
                    out.append("")
            self._strings = out
        return self._strings

    # -- types / protos ----------------------------------------------------
    def _type_desc(self, idx: int) -> str:
        if idx == NO_INDEX or idx >= self._type_ids_size:
            return "?"
        r = BlobReader(self.data)
        r.seek(self._type_ids_off + idx * 4)
        return self.strings[r.u32()]

    def _proto_desc(self, idx: int) -> str:
        r = BlobReader(self.data)
        r.seek(self._proto_ids_off + idx * 12)
        shorty_i, ret_i, params_off = r.u32(), r.u32(), r.u32()
        ret = self._type_desc(ret_i)
        params: List[str] = []
        if params_off:
            pr = r.at(params_off)
            size = pr.u32()
            for _ in range(min(size, 255)):
                params.append(self._type_desc(pr.u16()))
        return "(" + "".join(params) + ")" + ret

    # -- classes ----------------------------------------------------------
    @property
    def classes(self) -> List[DexClass]:
        if self._classes is None:
            self._classes = self._parse_classes()
        return self._classes

    def _parse_classes(self) -> List[DexClass]:
        out: List[DexClass] = []
        r = BlobReader(self.data)
        for i in range(self._class_defs_size):
            base = self._class_defs_off + i * 32
            r.seek(base)
            class_idx, access, super_idx = r.u32(), r.u32(), r.u32()
            interfaces_off, source_idx = r.u32(), r.u32()
            r.u32()  # annotations_off
            class_data_off, _static_values_off = r.u32(), r.u32()
            raw_name = self._type_desc(class_idx)
            super_name = (self._type_desc(super_idx)
                          if super_idx != NO_INDEX else None)
            cls = DexClass(
                name=type_name(raw_name) if raw_name != "?" else f"class{i}",
                raw_name=raw_name,
                super_name=super_name,
                access=access,
                source_file=(self.strings[source_idx]
                             if source_idx != NO_INDEX and source_idx < len(self.strings)
                             else None),
            )
            if interfaces_off:
                ir = r.at(interfaces_off)
                try:
                    n = ir.u32()
                    for _ in range(min(n, 255)):
                        cls.interfaces.append(self._type_desc(ir.u16()))
                except EOFError:
                    pass
            if class_data_off:
                self._parse_class_data(r.at(class_data_off), cls)
            out.append(cls)
        out.sort(key=lambda c: c.name)
        return out

    def _parse_class_data(self, cr: BlobReader, cls: DexClass) -> None:
        try:
            n_static = cr.uleb128()
            n_instance = cr.uleb128()
            n_direct = cr.uleb128()
            n_virtual = cr.uleb128()
        except EOFError:
            return

        def read_fields(n: int) -> List[DexField]:
            fields: List[DexField] = []
            idx = 0
            for _ in range(n):
                idx += cr.uleb128()
                acc = cr.uleb128()
                if idx < self._field_ids_size:
                    fr = BlobReader(self.data)
                    fr.seek(self._field_ids_off + idx * 8)
                    class_idx, type_idx, name_idx = fr.u16(), fr.u16(), fr.u32()
                    _ = class_idx
                    name = self.strings[name_idx] if name_idx < len(self.strings) else "?"
                    fields.append(DexField(name, self._type_desc(type_idx), acc))
            return fields

        def read_methods(n: int) -> List[DexMethod]:
            methods: List[DexMethod] = []
            idx = 0
            for _ in range(n):
                idx += cr.uleb128()
                acc = cr.uleb128()
                code_off = cr.uleb128()
                if idx < self._method_ids_size:
                    mr = BlobReader(self.data)
                    mr.seek(self._method_ids_off + idx * 8)
                    class_idx, proto_idx, name_idx = mr.u16(), mr.u16(), mr.u32()
                    _ = class_idx
                    name = self.strings[name_idx] if name_idx < len(self.strings) else "?"
                    methods.append(DexMethod(name, self._proto_desc(proto_idx), acc,
                                             code_off))
            return methods

        try:
            static_f = read_fields(n_static)
            instance_f = read_fields(n_instance)
            direct_m = read_methods(n_direct)
            virtual_m = read_methods(n_virtual)
        except EOFError:
            return
        cls.fields = static_f + instance_f
        cls.methods = direct_m + virtual_m

    # -- helpers ----------------------------------------------------------
    def info_text(self) -> str:
        i = self.info
        return (
            f"File:            {self.name}\n"
            f"DEX version:     {i.dex_version}\n"
            f"File size:       {i.file_size:,} bytes\n"
            f"Checksum:        0x{i.checksum:08x}\n"
            f"Classes:         {i.class_count:,}\n"
            f"Methods (ids):   {i.method_count:,}\n"
            f"Fields (ids):    {i.field_count:,}\n"
            f"Types:           {i.type_count:,}\n"
            f"Strings:         {i.string_count:,}\n"
        )

    def summary_line(self) -> str:
        i = self.info
        return (f"{self.name}: DEX {i.dex_version}, {i.class_count} classes, "
                f"{i.method_count} method ids, {i.string_count} strings")
