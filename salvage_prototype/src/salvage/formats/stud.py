"""Decoder for the STUD demonstration format.

Layout: 4-byte signature, 1-byte version, 1-byte UTF-8 name length, name bytes.
"""
from __future__ import annotations

from ..reader import ByteReader
from .base import Damage, FormatPlugin, Result


class STUDPlugin(FormatPlugin):
    name = "STUD"

    def detect(self, data: bytes) -> float:
        return 1.0 if data.startswith(b"STUD") else 0.0

    def decode(self, data: bytes) -> Result:
        result = Result(format="STUD", status="recovered")
        reader = ByteReader(data, endian="big")
        header = reader.read(6, field="header")
        if len(header) < 6:
            result.status = "damaged"
            result.damage.extend(reader.damage)
            return result

        version = header[4]
        name_length = header[5]
        name_offset = 6
        name_bytes = reader.read(name_length, field="name")
        name_damage = list(reader.damage)
        try:
            name = name_bytes.decode("utf-8", errors="strict")
            result.data = {"version": version, "name": name}
        except UnicodeDecodeError as error:
            # Preserve the bytes exactly. Never inject U+FFFD replacement chars.
            bad_start = name_offset + error.start
            bad_end = name_offset + max(error.end, error.start + 1)
            result.data = {
                "version": version,
                "name": None,
                "name_raw_hex": name_bytes.hex(),
                "name_decode_error": "invalid UTF-8",
            }
            result.damage.append(Damage(
                field="name", offset=bad_start, expected=bad_end - bad_start,
                found=bad_end - bad_start, reason="invalid UTF-8; raw bytes preserved as hex",
                byte_range=(bad_start, bad_end),
            ))
            result.status = "damaged"

        result.records.append(dict(result.data))
        # These diagnostics are the exact structured entries emitted by the
        # bounds-checked reader; output.py adds normalized byte_range objects.
        result.damage.extend(name_damage)
        if name_damage:
            result.status = "partial" if result.status == "recovered" else "damaged"
        return result
