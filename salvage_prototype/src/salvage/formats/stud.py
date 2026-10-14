"""Decoder for the prototype STUD demonstration format."""
from __future__ import annotations

from .base import Damage, FormatPlugin, Result


class STUDPlugin(FormatPlugin):
    name = "STUD"

    def detect(self, data: bytes) -> float:
        return 1.0 if data.startswith(b"STUD") else 0.0

    def decode(self, data: bytes) -> Result:
        result = Result(format="STUD", status="success")
        # Keep the original prototype's observable handling of truncated files.
        if len(data) < 6:
            result.status = "damaged"
            result.errors.append("File is too short to contain its header")
            result.damage.append(Damage("File is too short to contain its header", len(data), 6))
            return result

        version = data[4]
        name_length = data[5]
        available_bytes = len(data) - 6
        actual_length = min(name_length, available_bytes)
        name_bytes = data[6:6 + actual_length]
        result.data = {
            "version": version,
            # Preserved for behavioural compatibility with the original prototype.
            "name": name_bytes.decode("utf-8", errors="replace"),
        }
        result.records.append(dict(result.data))

        if name_length > available_bytes:
            result.status = "partially_recovered"
            message = (f"Name was truncated: expected {name_length} bytes, "
                       f"found {available_bytes}")
            result.errors.append(message)
            result.damage.append(Damage(message, len(data), 6 + name_length))
        return result
