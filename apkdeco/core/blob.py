"""Little-endian binary reader shared by the AXML / ARSC / DEX parsers."""
from __future__ import annotations

import struct


class BlobReader:
    """Sequential little-endian reader over a bytes-like object."""

    __slots__ = ("data", "pos", "_end")

    def __init__(self, data: bytes, pos: int = 0, end: int | None = None) -> None:
        self.data = data
        self.pos = pos
        self._end = len(data) if end is None else end

    # -- position helpers -------------------------------------------------
    def seek(self, pos: int) -> None:
        self.pos = pos

    def skip(self, n: int) -> None:
        self.pos += n

    def tell(self) -> int:
        return self.pos

    def remaining(self) -> int:
        return max(0, self._end - self.pos)

    def eof(self) -> bool:
        return self.pos >= self._end

    def at(self, off: int) -> "BlobReader":
        """Reader for an absolute offset in the same buffer."""
        return BlobReader(self.data, off, self._end)

    # -- primitives -------------------------------------------------------
    def _unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > self._end:
            raise EOFError(f"out of data reading {fmt!r} at 0x{self.pos:x}")
        val = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return val[0] if len(val) == 1 else val

    def u8(self) -> int:
        return self._unpack("<B")

    def u16(self) -> int:
        return self._unpack("<H")

    def u32(self) -> int:
        return self._unpack("<I")

    def i32(self) -> int:
        return self._unpack("<i")

    def raw(self, n: int) -> bytes:
        if n < 0 or self.pos + n > self._end:
            raise EOFError(f"out of data reading {n} bytes at 0x{self.pos:x}")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return bytes(out)

    def uleb128(self) -> int:
        result = 0
        shift = 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result
            shift += 7
            if shift > 35:
                raise ValueError("uleb128 too long")

    def sleb128(self) -> int:
        result = 0
        shift = 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            shift += 7
            if not (b & 0x80):
                if b & 0x40 and shift < 32:
                    result |= -(1 << shift)
                # sign-extend for wider values
                if result >= 1 << 31:
                    result -= 1 << 32
                return result
            if shift > 35:
                raise ValueError("sleb128 too long")


def uleb128_bytes(value: int) -> bytes:
    """Encode an unsigned LEB128 (used by tests/fixtures)."""
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)
