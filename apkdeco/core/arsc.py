"""resources.arsc (resource table) parser.

Resolves resource IDs such as ``0x7f010001`` to ``@type/entry`` names and
display values, so the manifest viewer can show ``@string/app_name`` -> ``My App``.

Supports dense, offset-16 and sparse entry offset tables and map (bag) entries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .blob import BlobReader
from .axml import ResValue, TYPE_STRING, _decode_string_pool, _read_value

RES_TABLE_TYPE = 0x0002
RES_STRING_POOL_TYPE = 0x0001
RES_TABLE_PACKAGE_TYPE = 0x0200
RES_TABLE_TYPE_TYPE = 0x0201
RES_TABLE_TYPE_SPEC_TYPE = 0x0202

FLAG_SPARSE = 0x01
FLAG_OFFSET16 = 0x02
ENTRY_FLAG_COMPLEX = 0x0001
NO_ENTRY = 0xFFFFFFFF
NO_INDEX = 0xFFFFFFFF


@dataclass
class ResEntry:
    key: str                 # entry name, e.g. "app_name"
    type_name: str           # e.g. "string"
    value: Optional[ResValue] = None
    parent: int = 0
    is_map: bool = False
    map_items: List[Tuple[int, ResValue]] = field(default_factory=list)


@dataclass
class Package:
    id: int
    name: str
    entries: Dict[int, ResEntry] = field(default_factory=dict)  # by res id


class ResourcesError(ValueError):
    pass


class ResourcesTable:
    """Parsed resources.arsc with reference lookup."""

    def __init__(self) -> None:
        self.global_strings: List[str] = []
        self.packages: List[Package] = []
        self._by_id: Dict[int, ResEntry] = {}

    # -- public API -------------------------------------------------------
    def res_name(self, res_id: int) -> Optional[str]:
        """``0x7f010001`` -> ``@string/app_name`` (or None)."""
        e = self._by_id.get(res_id)
        if e is None:
            return None
        return f"@{e.type_name}/{e.key}"

    def lookup(self, res_id: int) -> Optional[ResEntry]:
        return self._by_id.get(res_id)

    def display_value(self, res_id: int, _depth: int = 0) -> Optional[str]:
        """Best-effort human readable value of a resource id."""
        e = self._by_id.get(res_id)
        if e is None or e.value is None or _depth > 4:
            return None
        v = e.value
        if v.data_type in (0x01, 0x07):  # reference -> follow once
            inner = self.display_value(v.data, _depth + 1)
            if inner is not None:
                return inner
            name = self.res_name(v.data)
            return name or f"@{v.data:#010x}"
        return v.format(self.global_strings, self.res_name)

    def resolver(self):
        """Function suitable for ``ResValue.format(resolver=...)``."""
        return self.res_name

    def stats(self) -> str:
        n = sum(len(p.entries) for p in self.packages)
        pkgs = ", ".join(f"{p.name} (0x{p.id:02x})" for p in self.packages) or "-"
        return (f"{len(self.packages)} package(s): {pkgs} - "
                f"{n} resource entries - {len(self.global_strings)} value strings")


def parse_arsc(data: bytes) -> ResourcesTable:
    table = ResourcesTable()
    r = BlobReader(data)
    ctype, header_size, chunk_size = r.u16(), r.u16(), r.u32()
    if ctype != RES_TABLE_TYPE:
        raise ResourcesError(f"not a resource table (chunk type 0x{ctype:04x})")
    r.u32()  # packageCount
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
            table.global_strings = _decode_string_pool(r)
        elif c_type == RES_TABLE_PACKAGE_TYPE:
            _parse_package(r.at(chunk_off), c_header, c_size, table)
        r.seek(chunk_end)
    return table


def _parse_package(r: BlobReader, header_size: int, chunk_size: int,
                   table: ResourcesTable) -> None:
    start = r.tell()
    r.seek(start + 8)
    pkg_id = r.u32()
    name_raw = r.raw(256)
    pkg_name = name_raw.decode("utf-16-le", "replace").split("\x00", 1)[0]
    type_strings_off = r.u32()
    r.u32()  # lastPublicType
    key_strings_off = r.u32()
    r.u32()  # lastPublicKey

    type_strings = _decode_string_pool(r.at(start + type_strings_off))
    key_strings = _decode_string_pool(r.at(start + key_strings_off))

    pkg = Package(id=pkg_id, name=pkg_name)
    table.packages.append(pkg)

    pos = start + header_size
    pkg_end = start + chunk_size
    type_specs: Dict[int, int] = {}
    while pos < pkg_end - 8:
        r.seek(pos)
        c_type, c_header, c_size = r.u16(), r.u16(), r.u32()
        if c_size < 8:
            break
        if c_type == RES_TABLE_TYPE_SPEC_TYPE:
            rr = r.at(pos + 8)
            type_id = rr.u8()
            type_specs[type_id] = type_specs.get(type_id, 0) + 1
        elif c_type == RES_TABLE_TYPE_TYPE:
            _parse_type_chunk(r.at(pos), c_header, c_size,
                              type_strings, key_strings, pkg, table)
        pos += c_size


def _parse_type_chunk(r: BlobReader, header_size: int, chunk_size: int,
                      type_strings: List[str], key_strings: List[str],
                      pkg: Package, table: ResourcesTable) -> None:
    start = r.tell()
    r.seek(start + 8)
    type_id = r.u8()
    flags = r.u8()
    r.u16()  # reserved
    entry_count = r.u32()
    entries_start = r.u32()
    # config follows immediately (already included in header_size)

    type_name = type_strings[type_id - 1] if 0 < type_id <= len(type_strings) else f"type{type_id}"
    sparse = bool(flags & FLAG_SPARSE)
    offset16 = bool(flags & FLAG_OFFSET16)

    entries_dir = start + header_size

    def offset_for(i: int) -> Optional[int]:
        er = r.at(entries_dir)
        if sparse:
            # ResTable_sparseEntry: u16 idx, u32 offset (offset is in units of 4)
            er.seek(entries_dir + i * 6)
            _idx = er.u16()
            off = er.u32()
            return off * 4 if off != 0xFFFFFFFF else None
        if offset16:
            er.seek(entries_dir + i * 2)
            v = er.u16()
            return v * 4 if v != 0xFFFF else None
        er.seek(entries_dir + i * 4)
        v = er.u32()
        return v if v != NO_ENTRY else None

    for i in range(entry_count):
        rel = offset_for(i)
        if rel is None:
            continue
        epos = start + entries_start + rel
        er = r.at(epos)
        try:
            esize = er.u16()
            eflags = er.u16()
            key_idx = er.u32()
            key = key_strings[key_idx] if key_idx < len(key_strings) else f"entry{i}"
            entry = ResEntry(key=key, type_name=type_name)
            if eflags & ENTRY_FLAG_COMPLEX:
                entry.is_map = True
                entry.parent = er.u32()
                count = er.u32()
                for _ in range(min(count, 64)):
                    map_name = er.u32()
                    mv = _read_value(er, table.global_strings)
                    entry.map_items.append((map_name, mv))
            else:
                # Res_value starts at offset `esize` from entry start
                er.seek(epos + esize)
                entry.value = _read_value(er, table.global_strings)
            res_id = ((pkg.id & 0xFF) << 24) | ((type_id & 0xFF) << 16) | (i & 0xFFFF)
            pkg.entries[res_id] = entry
            table._by_id[res_id] = entry
        except EOFError:
            continue
