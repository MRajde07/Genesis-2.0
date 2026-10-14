"""STUD decoder expressed with the declarative field-spec engine."""
from __future__ import annotations

from .base import Damage, FieldSpec, FormatPlugin, Result, decode_fields


STUD_FIELDS = (
    FieldSpec("signature", "fixed_bytes", length=4, validators=(lambda value: value == "53545544",)),
    FieldSpec("version", "u8", validators=("positive",)),
    FieldSpec("name_length", "u8", validators=("positive",)),
    FieldSpec("name", "fixed_string", length_source="name_length", encoding="utf-8"),
)


class STUDPlugin(FormatPlugin):
    name = "STUD"
    signature = b"STUD"
    header_length = 6

    def detect(self, data: bytes) -> float:
        return 1.0 if data.startswith(self.signature) else 0.0

    def plausible_fields(self, data: bytes) -> dict[str, object]:
        if len(data) < self.header_length:
            return {"valid": False, "detail": "STUD header is truncated"}
        version, name_length = data[4], data[5]
        available = len(data) - self.header_length
        valid = version > 0 and name_length > 0
        detail = (f"version={version}, name_length={name_length}, "
                  f"available_name_bytes={available}; name "
                  f"{'fits' if name_length <= available else 'is truncated'}")
        return {"valid": valid, "detail": detail}

    def decode(self, data: bytes) -> Result:
        result = Result(format="STUD", status="recovered")
        # Keep the legacy output shape exactly: signature is structural only;
        # name is strictly decoded and invalid bytes are preserved as hex.
        decoded = decode_fields(data, STUD_FIELDS, endian="big")
        values = decoded.values
        if len(data) < 6:
            result.status = "damaged"
            result.damage.extend(item.to_dict() for item in decoded.damage)
            return result
        version = values.get("version")
        name_length = values.get("name_length")
        raw_name = data[6:min(len(data), 6 + (name_length or 0))]
        name_value = values.get("name")
        if isinstance(name_value, dict) and name_value.get("encoding_error"):
            result.data = {"version": version, "name": None, "name_raw_hex": raw_name.hex(),
                           "name_decode_error": "invalid UTF-8"}
            # Declarative decoder already reported invalid encoding; refine to legacy wording/range.
            invalid = [d for d in decoded.damage if d.field == "name" and "invalid encoding" in d.reason]
            for item in invalid:
                item.reason = "invalid UTF-8; raw bytes preserved as hex"
            result.status = "damaged"
        else:
            result.data = {"version": version, "name": name_value}
        result.records.append(dict(result.data))
        result.damage.extend(item.to_dict() for item in decoded.damage)
        if result.damage and result.status == "recovered":
            result.status = "partial"
        return result
