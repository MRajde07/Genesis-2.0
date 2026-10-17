"""ASTER records: fixed-size big-endian records with a deliberately misleading field."""
from __future__ import annotations
from ..base import Damage, FormatPlugin, Result
from ...bytemap import span

MAGIC = b"ARCF"
HEADER_SIZE = 8
RECORD_SIZE = 12


class AsterRecordsPlugin(FormatPlugin):
    name = "ASTER"
    signature = MAGIC
    header_length = HEADER_SIZE

    def detect(self, data: bytes) -> float:
        return 0.92 if data.startswith(MAGIC) else 0.0

    def plausible_fields(self, data: bytes) -> dict[str, object]:
        if len(data) < HEADER_SIZE:
            return {"valid": False, "detail": "ASTER header is truncated"}
        version = int.from_bytes(data[4:6], "big")
        count = int.from_bytes(data[6:8], "big")
        fit = count <= (len(data) - HEADER_SIZE) // RECORD_SIZE
        return {"valid": version in (1, 2) and fit,
                "detail": f"version={version}, count={count}, fixed_record_size={RECORD_SIZE}, records_fit={fit}; nominal_span is a category code, not a length"}

    def decode(self, data: bytes) -> Result:
        result = Result(format=self.name, status="recovered")
        if not data.startswith(MAGIC):
            result.status = "unsupported"
            return result
        if len(data) < HEADER_SIZE:
            result.status = "damaged"
            result.damage.append(Damage("header", len(data), HEADER_SIZE, len(data),
                "truncated ASTER header", (len(data), HEADER_SIZE), data.hex()))
            result.data = {"version": None, "record_count": None, "records": []}
            return result
        version = int.from_bytes(data[4:6], "big")
        count = int.from_bytes(data[6:8], "big")
        records = []
        spans = [span(0, HEADER_SIZE, "header", "magic, version, record count")]
        cursor = HEADER_SIZE
        for index in range(count):
            start, end = cursor, cursor + RECORD_SIZE
            raw = data[start:min(end, len(data))]
            if len(raw) < RECORD_SIZE:
                spans.append(span(start, start + len(raw), "damaged", f"records[{index}] truncated ({len(raw)}/{RECORD_SIZE} bytes)"))
                result.damage.append(Damage(f"records[{index}]", start, RECORD_SIZE, len(raw),
                    "truncated fixed-size ASTER record", (start + len(raw), end), raw.hex()))
                records.append({"index": index, "item_id": None, "kind": None,
                    "nominal_span": None, "quantity": None, "score": None,
                    "code": None, "raw_hex": raw.hex(), "complete": False})
                break
            record = {
                "index": index,
                "item_id": int.from_bytes(raw[0:2], "big"),
                "kind": raw[2],
                # This value is intentionally NOT used to size or seek records.
                "nominal_span": int.from_bytes(raw[3:5], "big"),
                "quantity": int.from_bytes(raw[5:7], "big"),
                "score": int.from_bytes(raw[7:9], "big", signed=True),
                "code": raw[9:12].decode("ascii", errors="strict") if all(32 <= b < 127 for b in raw[9:12]) else None,
                "raw_hex": raw.hex(), "complete": True,
            }
            if record["code"] is None:
                result.damage.append(Damage(f"records[{index}].code", start + 9, 3, 3,
                    "record code contains non-printable/non-ASCII bytes", (start + 9, start + 12), raw[9:12].hex()))
            records.append(record)
            spans.append(span(start, end, "decoded", f"records[{index}]"))
            cursor = end
        if len(data) > cursor:
            extra = data[cursor:]
            result.damage.append(Damage("trailing_bytes", cursor, 0, len(extra),
                "bytes remain after declared fixed records", (cursor, len(data)), extra.hex()))
        result.data = {"version": version, "record_count": count, "record_size": RECORD_SIZE, "records": records, "_spans": spans}
        result.records = [dict(item) for item in records]
        if result.damage:
            result.status = "partial" if records else "damaged"
        return result
