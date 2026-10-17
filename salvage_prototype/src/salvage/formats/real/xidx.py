"""XIDX: big-endian offset table, count/value RLE blobs and XOR strings."""
from __future__ import annotations
from ..base import Damage, FormatPlugin, Result
from ...bytemap import span

MAGIC = b"XIDX"
HEADER_SIZE = 8
ENTRY_SIZE = 10


def decode_rle(packed: bytes, expected_length: int) -> tuple[bytes, str | None]:
    if len(packed) % 2:
        return b"" , "RLE data has an incomplete count/value pair"
    output = bytearray()
    for pos in range(0, len(packed), 2):
        count, value = packed[pos], packed[pos + 1]
        if count == 0:
            return bytes(output), "RLE run has zero count"
        if len(output) + count > expected_length:
            return bytes(output), "RLE output exceeds declared decoded length"
        output.extend(bytes((value,)) * count)
    if len(output) != expected_length:
        return bytes(output), f"RLE output length mismatch: expected={expected_length}, found={len(output)}"
    return bytes(output), None


class XIDXPlugin(FormatPlugin):
    name = "XIDX"
    signature = MAGIC
    header_length = HEADER_SIZE

    def detect(self, data: bytes) -> float:
        return 0.93 if data.startswith(MAGIC) else 0.0

    def plausible_fields(self, data: bytes) -> dict[str, object]:
        if len(data) < HEADER_SIZE:
            return {"valid": False, "detail": "XIDX header is truncated"}
        version, count = data[4], data[5]
        index_offset = int.from_bytes(data[6:8], "big")
        table_end = index_offset + count * ENTRY_SIZE
        return {"valid": version == 1 and index_offset >= HEADER_SIZE and table_end <= len(data),
                "detail": f"version={version}, entries={count}, index_offset={index_offset}, table_end={table_end}"}

    def decode(self, data: bytes) -> Result:
        result = Result(format=self.name, status="recovered")
        if not data.startswith(MAGIC):
            result.status = "unsupported"
            return result
        if len(data) < HEADER_SIZE:
            result.status = "damaged"
            result.damage.append(Damage("header", len(data), HEADER_SIZE, len(data),
                "truncated XIDX header", (len(data), HEADER_SIZE), data.hex()))
            result.data = {"version": None, "blob_count": None, "index_offset": None, "entries": []}
            return result
        version, count = data[4], data[5]
        table_offset = int.from_bytes(data[6:8], "big")
        entries = []
        spans = [span(0, HEADER_SIZE, "header", "magic, version, entry count, index offset")]
        table_end = table_offset + count * ENTRY_SIZE
        if table_offset < HEADER_SIZE or table_end > len(data):
            found = max(0, min(len(data), table_end) - max(0, table_offset))
            result.damage.append(Damage("index_table", table_offset, count * ENTRY_SIZE, found,
                "index table bounds out of range", (max(0, min(len(data), table_offset)), max(0, min(len(data), table_end))),
                data[max(0, table_offset):max(0, min(len(data), table_end))].hex()))
        for index in range(count):
            pos = table_offset + index * ENTRY_SIZE
            if pos < 0 or pos + ENTRY_SIZE > len(data):
                break
            blob_offset = int.from_bytes(data[pos:pos+2], "big")
            packed_len = int.from_bytes(data[pos+2:pos+4], "big")
            raw_len = int.from_bytes(data[pos+4:pos+6], "big")
            string_offset = int.from_bytes(data[pos+6:pos+8], "big")
            string_len, key = data[pos+8], data[pos+9]
            blob_end = blob_offset + packed_len
            spans.append(span(pos, pos + ENTRY_SIZE, "decoded", f"entries[{index}] index entry"))
            packed = data[blob_offset:min(blob_end, len(data))] if blob_offset <= len(data) else b""
            if blob_offset < table_end or blob_offset < 0 or blob_end > len(data):
                result.damage.append(Damage(f"entries[{index}].blob", blob_offset, packed_len, len(packed),
                    "blob offset/length out of bounds or overlaps index table", (max(0, min(len(data), blob_offset)), max(0, min(len(data), blob_end))), packed.hex()))
            decoded, rle_error = decode_rle(packed, raw_len)
            if rle_error:
                result.damage.append(Damage(f"entries[{index}].rle", blob_offset, raw_len, len(decoded),
                    rle_error, (max(0, min(len(data), blob_offset)), max(0, min(len(data), blob_end))), packed.hex()))
            string_end = string_offset + string_len
            encoded = data[string_offset:min(string_end, len(data))] if string_offset <= len(data) else b""
            if string_offset < table_end or string_end > len(data):
                result.damage.append(Damage(f"entries[{index}].string", string_offset, string_len, len(encoded),
                    "XOR string offset/length out of bounds or overlaps index table",
                    (max(0, min(len(data), string_offset)), max(0, min(len(data), string_end))), encoded.hex()))
            plain = bytes(byte ^ key for byte in encoded)
            try:
                label = plain.decode("utf-8", errors="strict") if len(encoded) == string_len else None
            except UnicodeDecodeError:
                label = None
                result.damage.append(Damage(f"entries[{index}].string", string_offset, string_len, len(encoded),
                    "XOR-decoded string is invalid UTF-8", (string_offset, string_end), encoded.hex()))
            spans.append(span(blob_offset, blob_end, "verified" if rle_error is None else "decoded", f"entries[{index}].blob (RLE)"))
            spans.append(span(string_offset, string_end, "decoded", f"entries[{index}].label (XOR key {key})"))
            entries.append({"index": index, "blob_offset": blob_offset, "packed_length": packed_len,
                "decoded_length": raw_len, "packed_hex": packed.hex(), "blob_hex": decoded.hex(),
                "blob_bytes": list(decoded), "label_offset": string_offset, "label_length": string_len,
                "xor_key": key, "label": label, "rle_valid": rle_error is None,
                "complete": rle_error is None and len(packed) == packed_len and label is not None})
        result.data = {"version": version, "blob_count": count, "index_offset": table_offset, "entries": entries, "_spans": spans}
        result.records = [dict(entry) for entry in entries]
        if result.damage:
            result.status = "partial" if entries else "damaged"
        return result
