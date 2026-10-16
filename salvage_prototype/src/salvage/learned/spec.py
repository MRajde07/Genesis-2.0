"""Validated, JSON-serializable declarative format specifications."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..formats.base import BlockSpec, FieldSpec

_ALLOWED_TOP = {"name", "public_format", "description", "signature_hex", "signature_offset",
                "minimum_length", "endianness", "fields", "records", "blocks", "confidence"}


def _field(raw: dict[str, Any]) -> FieldSpec:
    allowed = set(FieldSpec.__dataclass_fields__)
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unknown field-spec keys: {sorted(unknown)}")
    if "name" not in raw or "type" not in raw:
        raise ValueError("each field needs name and type")
    # JSON specs must never contain executable validators/callables.
    validators = raw.get("validators", ())
    if not isinstance(validators, (list, tuple)) or not all(isinstance(v, str) for v in validators):
        raise ValueError("spec validators must be a list of strings")
    return FieldSpec(**raw)


@dataclass(frozen=True)
class PluginSpec:
    name: str
    public_format: str = "UNKNOWN"
    description: str = ""
    signature_hex: str = ""
    signature_offset: int = 0
    minimum_length: int = 0
    endianness: str = "little"
    fields: tuple[FieldSpec, ...] = ()
    records: dict[str, Any] | None = None
    blocks: tuple[BlockSpec, ...] = ()
    confidence: float = 0.9

    @property
    def signature(self) -> bytes:
        try:
            return bytes.fromhex(self.signature_hex)
        except ValueError as exc:
            raise ValueError("signature_hex must be valid hexadecimal") from exc

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PluginSpec":
        unknown = set(raw) - _ALLOWED_TOP
        if unknown:
            raise ValueError(f"unknown spec keys: {sorted(unknown)}")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("spec name must be a non-empty string")
        endian = raw.get("endianness", "little")
        if endian not in ("little", "big"):
            raise ValueError("endianness must be little or big")
        signature_hex = raw.get("signature_hex", "")
        if not isinstance(signature_hex, str):
            raise ValueError("signature_hex must be a string")
        try:
            bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise ValueError("signature_hex must be valid hexadecimal") from exc
        sig_offset = raw.get("signature_offset", 0)
        min_len = raw.get("minimum_length", 0)
        confidence = raw.get("confidence", 0.9)
        if not isinstance(sig_offset, int) or sig_offset < 0 or not isinstance(min_len, int) or min_len < 0:
            raise ValueError("signature_offset and minimum_length must be non-negative integers")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        fields_raw = raw.get("fields", [])
        blocks_raw = raw.get("blocks", [])
        if not isinstance(fields_raw, list) or not isinstance(blocks_raw, list):
            raise ValueError("fields and blocks must be lists")
        fields = tuple(_field(item) for item in fields_raw)
        block_allowed = set(BlockSpec.__dataclass_fields__)
        blocks = []
        for item in blocks_raw:
            if not isinstance(item, dict) or set(item) - block_allowed:
                raise ValueError("invalid block spec")
            blocks.append(BlockSpec(**item))
        records = raw.get("records")
        if records is not None:
            if not isinstance(records, dict):
                raise ValueError("records must be an object")
            if set(records) - {"name", "count_field", "offset", "stride", "fields"}:
                raise ValueError("unknown records configuration keys")
            if not isinstance(records.get("name", "records"), str):
                raise ValueError("records.name must be a string")
            if not isinstance(records.get("offset"), int) or records["offset"] < 0:
                raise ValueError("records.offset must be a non-negative integer")
            if not isinstance(records.get("stride"), int) or records["stride"] <= 0:
                raise ValueError("records.stride must be a positive integer")
            if not isinstance(records.get("count_field"), str):
                raise ValueError("records.count_field must name a header field")
            if not isinstance(records.get("fields"), list):
                raise ValueError("records.fields must be a list")
            records = dict(records)
            records["fields"] = [_field(item) for item in records["fields"]]
        return cls(name=name, public_format=str(raw.get("public_format", "UNKNOWN")),
                   description=str(raw.get("description", "")), signature_hex=signature_hex,
                   signature_offset=sig_offset, minimum_length=min_len, endianness=endian,
                   fields=fields, records=records, blocks=tuple(blocks), confidence=float(confidence))

    @classmethod
    def load(cls, path: str | Path) -> "PluginSpec":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("plugin spec must be a JSON object")
        return cls.from_dict(raw)

    def to_dict(self) -> dict[str, Any]:
        def field_dict(field: FieldSpec) -> dict[str, Any]:
            return {key: value for key, value in vars(field).items()
                    if value not in (None, (), [])}
        out: dict[str, Any] = {
            "name": self.name, "public_format": self.public_format,
            "description": self.description, "signature_hex": self.signature_hex,
            "signature_offset": self.signature_offset, "minimum_length": self.minimum_length,
            "endianness": self.endianness, "fields": [field_dict(f) for f in self.fields],
            "confidence": self.confidence,
        }
        if self.records:
            out["records"] = {**self.records, "fields": [field_dict(f) for f in self.records["fields"]]}
        if self.blocks:
            out["blocks"] = [vars(block) for block in self.blocks]
        return out
