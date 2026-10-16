"""Conservative reader for Lotus 1-2-3 Release 1A (.WKS) record streams.

The implementation intentionally does not evaluate formula token streams or
infer semantics from cell-format bytes. Unknown records and formula tokens are
preserved as raw hex and explicitly marked unverified.
"""
from __future__ import annotations

import math
import struct
from typing import Any

from ..base import Damage, FormatPlugin, Result

# WKS Release 1A begins with BOF (opcode 0, body length 2), revision 0x0404.
BOF_SIGNATURE = b"\x00\x00\x02\x00\x04\x04"
BOF = 0x0000
EOF = 0x0001
RANGE = 0x0006
INTEGER = 0x000D
NUMBER = 0x000E
LABEL = 0x000F
FORMULA = 0x0010

_RECORD_NAMES = {
    BOF: "BOF", EOF: "EOF", RANGE: "RANGE", INTEGER: "INTEGER",
    NUMBER: "NUMBER", LABEL: "LABEL", FORMULA: "FORMULA",
}
_LABEL_PREFIXES = {ord("'"), ord('"'), ord("^"), ord("\\"), ord("|")}


def _damage(field: str, offset: int, expected: int, found: int, reason: str,
            start: int | None = None, end: int | None = None, raw: bytes = b"") -> Damage:
    if start is None:
        start = offset
    if end is None:
        end = max(start, offset + max(0, expected - found))
    return Damage(field, max(0, offset), expected, found, reason,
                  (max(0, start), max(max(0, start), end)), raw.hex() if raw else None)


class LotusWKSPlugin(FormatPlugin):
    """Decode WKS cells without pretending to understand formula opcodes."""

    name = "LOTUS_WKS"
    public_format = "WKS"
    signature = BOF_SIGNATURE
    header_length = len(BOF_SIGNATURE)

    def detect(self, data: bytes) -> float:
        if data.startswith(BOF_SIGNATURE):
            return 0.99
        # Partial BOF prefix is weak evidence only; this helps rank truncated
        # files without confidently claiming an unrelated zero-prefixed file.
        if data and BOF_SIGNATURE.startswith(data):
            return 0.25
        if len(data) >= 4 and data[:4] == b"\x00\x00\x02\x00":
            return 0.45
        return 0.0

    def plausible_fields(self, data: bytes) -> dict[str, object]:
        if len(data) < 4:
            return {"valid": False, "detail": "WKS BOF record header is truncated"}
        opcode = int.from_bytes(data[0:2], "little")
        length = int.from_bytes(data[2:4], "little")
        if opcode != BOF:
            return {"valid": False, "detail": f"first record opcode is 0x{opcode:04x}, not BOF"}
        if length != 2:
            return {"valid": False, "detail": f"BOF body length is {length}, expected 2"}
        if len(data) < 6:
            return {"valid": False, "detail": "WKS BOF revision bytes are truncated"}
        revision = int.from_bytes(data[4:6], "little")
        return {"valid": revision == 0x0404,
                "detail": f"BOF revision=0x{revision:04x}; expected Lotus 1-2-3 Release 1A 0x0404"}

    def decode(self, data: bytes) -> Result:
        result = Result(format=self.name, status="recovered")
        if not data.startswith(BOF_SIGNATURE):
            result.status = "unsupported"
            result.data = {"version": None, "cells": [], "unrecognized_records": [],
                           "format_claim": "Lotus 1-2-3 WKS Release 1A", "verified": False}
            return result

        version = int.from_bytes(data[4:6], "little")
        cells: list[dict[str, Any]] = []
        unrecognized: list[dict[str, Any]] = []
        record_summaries: list[dict[str, Any]] = []
        cursor = 0
        eof_seen = False
        record_index = 0

        while cursor < len(data):
            record_start = cursor
            if len(data) - cursor < 4:
                raw = data[cursor:]
                result.damage.append(_damage("record_header", cursor, 4, len(raw),
                    "truncated WKS record header", cursor, cursor + 4, raw))
                break
            opcode = int.from_bytes(data[cursor:cursor + 2], "little")
            body_length = int.from_bytes(data[cursor + 2:cursor + 4], "little")
            body_start = cursor + 4
            body_end = body_start + body_length
            body = data[body_start:min(body_end, len(data))]
            record_complete = len(body) == body_length
            record_summaries.append({"index": record_index, "offset": record_start,
                "opcode": opcode, "opcode_hex": f"0x{opcode:04x}",
                "name": _RECORD_NAMES.get(opcode), "declared_length": body_length,
                "raw_body_hex": body.hex(), "complete": record_complete,
                "verified": opcode in _RECORD_NAMES and record_complete})

            if not record_complete:
                result.damage.append(_damage(f"record[{record_index}].body", body_start + len(body),
                    body_length, len(body), "truncated WKS record body", body_start + len(body), body_end, body))

            if opcode == BOF:
                # The opening BOF has already been validated. Any later BOF is preserved,
                # but flagged because nested/restarted streams are not interpreted.
                if record_start != 0:
                    result.damage.append(_damage(f"record[{record_index}].bof", record_start, 1, 1,
                        "unexpected BOF record inside worksheet", record_start, body_end, body))
            elif opcode == EOF:
                eof_seen = True
                if body_length != 0:
                    result.damage.append(_damage(f"record[{record_index}].eof", body_start, 0, body_length,
                        "EOF record has a non-empty body", body_start, body_end, body))
                cursor = body_end
                record_index += 1
                if cursor < len(data):
                    extra = data[cursor:]
                    result.damage.append(_damage("trailing_bytes", cursor, 0, len(extra),
                        "bytes follow WKS EOF record", cursor, len(data), extra))
                break
            elif opcode in (INTEGER, NUMBER, LABEL, FORMULA):
                cell, cell_damage = self._decode_cell(opcode, body, body_start, record_index)
                cells.append(cell)
                result.damage.extend(cell_damage)
            elif opcode == RANGE:
                if len(body) >= 8:
                    # Coordinates are represented exactly as unsigned little-endian words.
                    record_summaries[-1]["range"] = {
                        "start_column": int.from_bytes(body[0:2], "little"),
                        "start_row": int.from_bytes(body[2:4], "little"),
                        "end_column": int.from_bytes(body[4:6], "little"),
                        "end_row": int.from_bytes(body[6:8], "little"),
                        "interpretation": "unverified coordinate interpretation",
                    }
                else:
                    result.damage.append(_damage(f"record[{record_index}].range", body_start, 8, len(body),
                        "RANGE body shorter than the documented 8-byte coordinate payload",
                        body_start + len(body), body_start + 8, body))
            elif opcode not in (BOF, EOF):
                unrecognized.append({"record_index": record_index, "offset": record_start,
                    "opcode": opcode, "opcode_hex": f"0x{opcode:04x}",
                    "declared_length": body_length, "raw_body_hex": body.hex(),
                    "interpretation": "unrecognized record; raw body preserved", "verified": False})
                result.errors.append(f"Unrecognized WKS record opcode 0x{opcode:04x} at offset {record_start}; raw body preserved")

            cursor = min(body_end, len(data))
            record_index += 1
            if not record_complete:
                break

        if not eof_seen:
            result.damage.append(_damage("eof_record", len(data), 4, 0,
                "WKS EOF record not found", len(data), len(data)))

        result.data = {
            "format_claim": "Lotus 1-2-3 WKS Release 1A",
            "version": version,
            "version_hex": f"0x{version:04x}",
            "cells": cells,
            "unrecognized_records": unrecognized,
            "_record_log": record_summaries,
            "eof_seen": eof_seen,
            "formula_policy": "formula token streams are preserved as raw hex; no formula evaluation or token translation attempted",
            "verified": not result.damage and not unrecognized,
        }
        result.records = [dict(cell) for cell in cells]
        if result.damage:
            result.status = "partial" if cells else "damaged"
        elif unrecognized:
            result.status = "partial"
        return result

    def _decode_cell(self, opcode: int, body: bytes, body_offset: int,
                     record_index: int) -> tuple[dict[str, Any], list[Damage]]:
        name = _RECORD_NAMES[opcode]
        damage: list[Damage] = []
        cell: dict[str, Any] = {
            "record_index": record_index,
            "record_type": name,
            "record_type_code": opcode,
            "offset": body_offset - 4,
            "complete": True,
            "verified": True,
        }
        minimum = {INTEGER: 7, NUMBER: 13, LABEL: 6, FORMULA: 15}[opcode]
        if len(body) < 5:
            damage.append(_damage(f"{name.lower()}.cell_header", body_offset, 5, len(body),
                "cell record lacks format/column/row fields", body_offset + len(body), body_offset + 5, body))
            cell.update({"format_byte": body[0] if body else None, "column": None, "row": None,
                         "raw_body_hex": body.hex(), "complete": False, "verified": False})
            return cell, damage

        fmt = body[0]
        column = int.from_bytes(body[1:3], "little")
        row = int.from_bytes(body[3:5], "little")
        cell.update({"format_byte": fmt, "column": column, "row": row,
                     "cell_address": f"R{row + 1}C{column + 1}",
                     "format_byte_interpretation": "raw only; display semantics not inferred"})
        if len(body) < minimum:
            damage.append(_damage(f"{name.lower()}.value", body_offset + len(body), minimum - 5,
                max(0, len(body) - 5), f"{name} cell value is truncated", body_offset + len(body),
                body_offset + minimum, body[5:]))
            cell.update({"raw_value_hex": body[5:].hex(), "complete": False, "verified": False})
            return cell, damage

        if opcode == INTEGER:
            raw = body[5:7]
            cell.update({"value": int.from_bytes(raw, "little", signed=True), "raw_value_hex": raw.hex()})
            if len(body) > 7:
                extra = body[7:]
                damage.append(_damage("integer.extra_bytes", body_offset + 7, 0, len(extra),
                    "unexpected bytes after INTEGER value", body_offset + 7, body_offset + len(body), extra))
                cell["extra_bytes_hex"] = extra.hex()
                cell["verified"] = False
        elif opcode == NUMBER:
            raw = body[5:13]
            value = struct.unpack("<d", raw)[0]
            cell.update({"value": value if math.isfinite(value) else None, "raw_value_hex": raw.hex()})
            if not math.isfinite(value):
                damage.append(_damage("number.value", body_offset + 5, 8, 8,
                    "NUMBER contains non-finite IEEE-754 value", body_offset + 5, body_offset + 13, raw))
                cell["value_unverified"] = True
                cell["verified"] = False
            if len(body) > 13:
                extra = body[13:]
                damage.append(_damage("number.extra_bytes", body_offset + 13, 0, len(extra),
                    "unexpected bytes after NUMBER value", body_offset + 13, body_offset + len(body), extra))
                cell["extra_bytes_hex"] = extra.hex()
                cell["verified"] = False
        elif opcode == LABEL:
            raw = body[5:]
            nul = raw.find(b"\x00")
            if nul < 0:
                label_raw = raw
                damage.append(_damage("label.terminator", body_offset + len(body), 1, 0,
                    "LABEL is missing its NUL terminator", body_offset + len(body), body_offset + len(body) + 1, raw))
                cell["complete"] = False
                cell["verified"] = False
            else:
                label_raw = raw[:nul]
                tail = raw[nul + 1:]
                if tail:
                    damage.append(_damage("label.trailing_bytes", body_offset + 6 + nul, 0, len(tail),
                        "bytes follow LABEL terminator", body_offset + 6 + nul, body_offset + len(body), tail))
                    cell["trailing_bytes_hex"] = tail.hex()
                    cell["verified"] = False
            if label_raw:
                prefix = label_raw[0]
                text_raw = label_raw[1:]
                cell["label_prefix_byte"] = prefix
                if prefix in _LABEL_PREFIXES:
                    cell["alignment"] = {ord("'"): "left", ord('"'): "right", ord("^"): "center",
                                          ord("\\"): "repeat", ord("|"): "printer_command"}[prefix]
                else:
                    cell["alignment"] = None
                    cell["interpretation_warnings"] = ["unknown LABEL prefix; preserved as raw byte"]
                    cell["verified"] = False
            else:
                text_raw = b""
                cell["label_prefix_byte"] = None
                cell["alignment"] = None
                cell["verified"] = False
            # CP437 maps every byte; raw bytes are kept for exact recovery.
            cell.update({"value": text_raw.decode("cp437"), "raw_value_hex": label_raw.hex(),
                         "text_raw_hex": text_raw.hex(), "encoding": "cp437"})
        elif opcode == FORMULA:
            cached_raw = body[5:13]
            cached = struct.unpack("<d", cached_raw)[0]
            token_length = int.from_bytes(body[13:15], "little")
            tokens = body[15:]
            if len(tokens) < token_length:
                damage.append(_damage("formula.tokens", body_offset + len(body), token_length, len(tokens),
                    "FORMULA token stream is truncated", body_offset + len(body), body_offset + 15 + token_length, tokens))
                cell["complete"] = False
                cell["verified"] = False
            elif len(tokens) > token_length:
                extra = tokens[token_length:]
                damage.append(_damage("formula.extra_bytes", body_offset + 15 + token_length, 0, len(extra),
                    "unexpected bytes after FORMULA token stream", body_offset + 15 + token_length,
                    body_offset + len(body), extra))
                cell["extra_bytes_hex"] = extra.hex()
                cell["verified"] = False
            cell.update({
                "cached_value": cached if math.isfinite(cached) else None,
                "cached_value_raw_hex": cached_raw.hex(),
                "formula_raw": {"encoding": "hex", "text": tokens[:token_length].hex(),
                                "raw_hex": tokens[:token_length].hex(), "verified": False},
                "formula_text": None,
                "formula_evaluated": False,
                "declared_token_length": token_length,
            })
            if not math.isfinite(cached):
                damage.append(_damage("formula.cached_value", body_offset + 5, 8, 8,
                    "FORMULA cached value is non-finite", body_offset + 5, body_offset + 13, cached_raw))
                cell["verified"] = False
        return cell, damage
