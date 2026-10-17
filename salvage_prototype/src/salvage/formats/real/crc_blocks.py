"""CRCB: little-endian variable-length blocks protected by CRC32."""
from __future__ import annotations
import zlib
from ..base import Damage, FormatPlugin, Result
from ...bytemap import span

MAGIC = b"CRCB"
HEADER_SIZE = 7


class CRCBlocksPlugin(FormatPlugin):
    name = "CRC_BLOCKS"
    signature = MAGIC
    header_length = HEADER_SIZE

    def detect(self, data: bytes) -> float:
        return 0.94 if data.startswith(MAGIC) else 0.0

    def plausible_fields(self, data: bytes) -> dict[str, object]:
        if len(data) < HEADER_SIZE:
            return {"valid": False, "detail": "CRCB header is truncated"}
        version = data[4]
        count = int.from_bytes(data[5:7], "little")
        return {"valid": version == 1 and count <= (len(data) - HEADER_SIZE) // 6,
                "detail": f"version={version}, block_count={count}, little-endian length and CRC fields"}

    def decode(self, data: bytes) -> Result:
        result = Result(format=self.name, status="recovered")
        if not data.startswith(MAGIC):
            result.status = "unsupported"
            return result
        if len(data) < HEADER_SIZE:
            result.status = "damaged"
            result.damage.append(Damage("header", len(data), HEADER_SIZE, len(data),
                "truncated CRCB header", (len(data), HEADER_SIZE), data.hex()))
            result.data = {"version": None, "block_count": None, "blocks": []}
            return result
        version = data[4]
        count = int.from_bytes(data[5:7], "little")
        blocks = []
        spans = [span(0, HEADER_SIZE, "header", "magic, version, block count")]
        cursor = HEADER_SIZE
        for index in range(count):
            if cursor + 2 > len(data):
                result.damage.append(Damage(f"blocks[{index}].length", cursor, 2, max(0, len(data)-cursor),
                    "truncated block length", (len(data), cursor + 2), data[cursor:].hex()))
                break
            payload_len = int.from_bytes(data[cursor:cursor+2], "little")
            length_offset = cursor
            spans.append(span(cursor, cursor + 2, "decoded", f"blocks[{index}].length"))
            payload_offset = cursor + 2
            payload_end = payload_offset + payload_len
            crc_offset = payload_end
            block_end = crc_offset + 4
            payload = data[payload_offset:min(payload_end, len(data))]
            if len(payload) < payload_len:
                spans.append(span(payload_offset, payload_offset + len(payload), "damaged", f"blocks[{index}] truncated payload"))
                result.damage.append(Damage(f"blocks[{index}].payload", payload_offset + len(payload), payload_len, len(payload),
                    "truncated CRCB block payload", (payload_offset + len(payload), payload_end), payload.hex()))
                blocks.append({"index": index, "length": payload_len, "payload_raw_hex": payload.hex(),
                    "sequence": None, "reading": None, "label": None, "crc32_valid": None, "complete": False})
                break
            if crc_offset + 4 > len(data):
                result.damage.append(Damage(f"blocks[{index}].crc32", len(data), 4, max(0, len(data)-crc_offset),
                    "truncated CRC32 field", (len(data), block_end), data[crc_offset:].hex()))
                stored_crc = None
                crc_valid = None
            else:
                stored_crc = int.from_bytes(data[crc_offset:block_end], "little")
                calculated = zlib.crc32(payload) & 0xffffffff
                crc_valid = stored_crc == calculated
                if not crc_valid:
                    result.damage.append(Damage(f"blocks[{index}].crc32", crc_offset, 4, 4,
                        f"CRC32 mismatch: stored={stored_crc}, calculated={calculated}",
                        (crc_offset, block_end), data[crc_offset:block_end].hex()))
            spans.append(span(payload_offset, payload_end, "verified" if crc_valid else "decoded", f"blocks[{index}].payload"))
            if crc_valid is not None:
                spans.append(span(crc_offset, block_end, "verified" if crc_valid else "decoded", f"blocks[{index}].crc32"))
            sequence = int.from_bytes(payload[0:2], "little") if len(payload) >= 2 else None
            reading = int.from_bytes(payload[2:6], "little", signed=True) if len(payload) >= 6 else None
            label_len = payload[6] if len(payload) >= 7 else None
            label = None
            if label_len is not None:
                label_raw = payload[7:7+label_len]
                if len(label_raw) == label_len:
                    try:
                        label = label_raw.decode("utf-8", errors="strict")
                    except UnicodeDecodeError:
                        result.damage.append(Damage(f"blocks[{index}].label", payload_offset+7, label_len, label_len,
                            "invalid UTF-8 in block label", (payload_offset+7, payload_offset+7+label_len), label_raw.hex()))
                else:
                    result.damage.append(Damage(f"blocks[{index}].label", payload_offset+7+len(label_raw), label_len, len(label_raw),
                        "truncated block label", (payload_offset+7+len(label_raw), payload_offset+7+label_len), label_raw.hex()))
            if len(payload) < 7:
                result.damage.append(Damage(f"blocks[{index}].record", payload_offset, 7, len(payload),
                    "block payload is too short for record fields", (payload_offset+len(payload), payload_offset+7), payload.hex()))
            blocks.append({"index": index, "length": payload_len, "sequence": sequence, "reading": reading,
                "label": label, "crc32_valid": crc_valid, "stored_crc32": stored_crc,
                "payload_raw_hex": payload.hex(), "complete": crc_valid is not None and len(payload) == payload_len})
            cursor = min(block_end, len(data))
            if crc_valid is None:
                break
        if cursor < len(data) and len(blocks) == count:
            result.damage.append(Damage("trailing_bytes", cursor, 0, len(data)-cursor,
                "bytes remain after declared blocks", (cursor, len(data)), data[cursor:].hex()))
        result.data = {"version": version, "block_count": count, "blocks": blocks, "_spans": spans}
        result.records = [dict(block) for block in blocks]
        if result.damage:
            result.status = "partial" if blocks else "damaged"
        return result
