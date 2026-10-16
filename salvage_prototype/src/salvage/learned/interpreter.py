"""Generic interpreter for safe, declarative format specs; no code execution."""
from __future__ import annotations

from typing import Any

from ..formats.base import Damage, FormatPlugin, Result, decode_fields
from .spec import PluginSpec


class SpecPlugin(FormatPlugin):
    def __init__(self, spec: PluginSpec):
        self.spec = spec
        self.name = spec.name
        self.public_format = spec.public_format
        self.signature = spec.signature or None
        self.header_length = max(spec.minimum_length, spec.signature_offset + len(spec.signature))
        if not spec.blocks:
            # Make the optional identify hook truly absent when no checksum is specified.
            self.checksum_valid = None

    def detect(self, data: bytes) -> float:
        signature = self.spec.signature
        if signature:
            start = self.spec.signature_offset
            if len(data) < start + len(signature) or data[start:start + len(signature)] != signature:
                return 0.0
            return self.spec.confidence
        return 0.0

    def _decode(self, data: bytes) -> tuple[dict[str, Any], list[dict[str, Any]], list[Damage], list[dict[str, Any]]]:
        decoded = decode_fields(data, self.spec.fields, endian=self.spec.endianness, blocks=self.spec.blocks)
        header = dict(decoded.values)
        damages = list(decoded.damage)
        records: list[dict[str, Any]] = []
        if self.spec.records:
            cfg = self.spec.records
            count_value = header.get(cfg["count_field"])
            try:
                count = int(count_value)
            except (TypeError, ValueError, OverflowError):
                count = 0
                damages.append(Damage(cfg["name"], cfg["offset"], 0, 0,
                                      "record count field is missing or invalid"))
            # Bound iteration to the bytes that could possibly contain records.
            available_count = max(0, (len(data) - cfg["offset"] + cfg["stride"] - 1) // cfg["stride"])
            if count < 0 or count > 1_000_000:
                damages.append(Damage(cfg["name"], cfg["offset"], 1_000_000, count,
                                      "record count outside safe bound"))
                count = min(max(count, 0), 1_000_000)
            for index in range(min(count, available_count)):
                start = cfg["offset"] + index * cfg["stride"]
                if start >= len(data):
                    break
                row = decode_fields(data, cfg["fields"], endian=self.spec.endianness, start_offset=start)
                record = {"index": index, **row.values}
                records.append(record)
                damages.extend(row.damage)
            if count > len(records):
                damages.append(Damage(cfg["name"], cfg["offset"] + len(records) * cfg["stride"],
                                      (count - len(records)) * cfg["stride"],
                                      max(0, len(data) - (cfg["offset"] + len(records) * cfg["stride"])),
                                      "truncated fixed-size records"))
        return header, records, damages, decoded.blocks

    def plausible_fields(self, data: bytes) -> dict[str, Any]:
        signature = self.spec.signature
        start = self.spec.signature_offset
        if signature and data[start:start + len(signature)] != signature:
            return {"valid": False, "detail": "declared signature does not match"}
        if len(data) < self.spec.minimum_length:
            return {"valid": False, "detail": f"requires {self.spec.minimum_length} bytes; found {len(data)}"}
        _, records, damage, _ = self._decode(data)
        structural = [d for d in damage if any(marker in d.reason.lower() for marker in
                      ("out of range", "truncated", "outside safe bound", "validator failed",
                       "invalid encoding", "invalid length", "checksum mismatch"))]
        return {"valid": not structural, "detail": f"decoded {len(records)} fixed records; {len(damage)} diagnostic(s)"}

    def checksum_valid(self, data: bytes) -> bool:
        if not self.spec.blocks:
            return False
        _, _, damage, blocks = self._decode(data)
        checksum_blocks = [block for block in blocks if block.get("checksum") is not None]
        return bool(checksum_blocks) and all(block.get("valid", False) and block["checksum"].get("valid", False) for block in checksum_blocks) and not any(
            "checksum" in item.field.lower() and "mismatch" in item.reason for item in damage)

    def decode(self, data: bytes) -> Result:
        header, records, damage, blocks = self._decode(data)
        result = Result(format=self.name, status="recovered")
        if self.spec.records:
            result.data = {**header, self.spec.records.get("name", "records"): records}
            result.records = [dict(record) for record in records]
        else:
            result.data = header
            result.records = [dict(header)] if header else []
        if blocks:
            result.data = {**(result.data if isinstance(result.data, dict) else {"value": result.data}), "blocks": blocks}
        result.damage = [item.to_dict() for item in damage]
        if damage:
            result.status = "partial" if result.records else "damaged"
        return result
