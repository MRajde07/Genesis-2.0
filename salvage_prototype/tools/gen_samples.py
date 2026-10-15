#!/usr/bin/env python3
"""Generate seeded, invented binary samples and adjacent ground-truth JSON.

Usage: python tools/gen_samples.py [--output-dir samples/generated] [--seed 1337]
Only the Python standard library is required; output bytes are deterministic.
"""
from __future__ import annotations
import argparse
import json
import random
import zlib
from pathlib import Path


def _write_pair(out_dir: Path, filename: str, payload: bytes, truth: dict) -> None:
    (out_dir / filename).write_bytes(payload)
    target = out_dir / (filename + ".truth.json")
    target.write_text(json.dumps(truth, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                      encoding="utf-8", newline="\n")


def _aster(rng: random.Random) -> tuple[bytes, dict]:
    version = 1
    source = []
    records = []
    codes = ["NTH", "QZ7", "LUM"]
    nominal_codes = [24, 36, 48]  # Deliberately resembles a length, but is just a category code.
    for i in range(3):
        item_id = 100 + i * 7 + rng.randrange(0, 5)
        kind = rng.randrange(1, 5)
        nominal_span = nominal_codes[i]
        quantity = rng.randrange(2, 40)
        score = rng.randrange(-120, 121)
        code = codes[i]
        raw = (item_id.to_bytes(2, "big") + bytes([kind]) + nominal_span.to_bytes(2, "big") +
               quantity.to_bytes(2, "big") + score.to_bytes(2, "big", signed=True) + code.encode("ascii"))
        source.append(raw)
        records.append({"index": i, "item_id": item_id, "kind": kind, "nominal_span": nominal_span,
                        "quantity": quantity, "score": score, "code": code, "raw_hex": raw.hex(), "complete": True})
    data = b"ARCF" + version.to_bytes(2, "big") + len(records).to_bytes(2, "big") + b"".join(source)
    return data, {"format": "ASTER", "expected": {"version": version, "record_count": len(records),
            "record_size": 12, "records": records}}


def _crc_blocks(rng: random.Random) -> tuple[bytes, dict]:
    version = 1
    values = [(11, 2301, "amber"), (12, -77, "violet"), (13, rng.randrange(100, 5000), "copper")]
    blocks = []
    encoded_blocks = []
    for index, (sequence, reading, label) in enumerate(values):
        label_raw = label.encode("utf-8")
        payload = sequence.to_bytes(2, "little") + reading.to_bytes(4, "little", signed=True) + bytes([len(label_raw)]) + label_raw
        crc = zlib.crc32(payload) & 0xffffffff
        encoded_blocks.append(len(payload).to_bytes(2, "little") + payload + crc.to_bytes(4, "little"))
        blocks.append({"index": index, "length": len(payload), "sequence": sequence, "reading": reading,
                       "label": label, "crc32_valid": True, "stored_crc32": crc,
                       "payload_raw_hex": payload.hex(), "complete": True})
    data = b"CRCB" + bytes([version]) + len(blocks).to_bytes(2, "little") + b"".join(encoded_blocks)
    return data, {"format": "CRC_BLOCKS", "expected": {"version": version, "block_count": len(blocks), "blocks": blocks}}


def _rle_encode(raw: bytes) -> bytes:
    out = bytearray()
    pos = 0
    while pos < len(raw):
        value = raw[pos]
        count = 1
        while pos + count < len(raw) and raw[pos + count] == value and count < 255:
            count += 1
        out.extend((count, value))
        pos += count
    return bytes(out)


def _xidx(rng: random.Random) -> tuple[bytes, dict]:
    blobs = [bytes([0x41]) * 4 + bytes([0x10, 0x11]) + bytes([0x7E]) * 3,
             bytes([rng.randrange(1, 20)]) * 5 + b"\x01\x02\x03" + b"\xFF" * 2,
             b"\x00\x00\x00" + bytes([rng.randrange(32, 64)]) * 4]
    labels = ["north-cache", "legacy-note", "sector-3"]
    keys = [0x5A, 0xC3, 0x27]
    packed_blobs = [_rle_encode(blob) for blob in blobs]
    table_offset = 8
    table_end = table_offset + len(blobs) * 10
    blob_offsets = []
    cursor = table_end
    for packed in packed_blobs:
        blob_offsets.append(cursor)
        cursor += len(packed)
    string_offsets = []
    encoded_strings = []
    for label, key in zip(labels, keys):
        raw = label.encode("utf-8")
        encoded = bytes(byte ^ key for byte in raw)
        string_offsets.append(cursor)
        encoded_strings.append(encoded)
        cursor += len(encoded)
    table = bytearray()
    expected_entries = []
    for i, (raw, packed, label, key, blob_off, string_off, encoded) in enumerate(
            zip(blobs, packed_blobs, labels, keys, blob_offsets, string_offsets, encoded_strings)):
        table.extend(blob_off.to_bytes(2, "big"))
        table.extend(len(packed).to_bytes(2, "big"))
        table.extend(len(raw).to_bytes(2, "big"))
        table.extend(string_off.to_bytes(2, "big"))
        table.extend(bytes([len(encoded), key]))
        expected_entries.append({"index": i, "blob_offset": blob_off, "packed_length": len(packed),
            "decoded_length": len(raw), "packed_hex": packed.hex(), "blob_hex": raw.hex(),
            "blob_bytes": list(raw), "label_offset": string_off, "label_length": len(encoded),
            "xor_key": key, "label": label, "rle_valid": True, "complete": True})
    data = (b"XIDX" + bytes([1, len(blobs)]) + table_offset.to_bytes(2, "big") + bytes(table) +
            b"".join(packed_blobs) + b"".join(encoded_strings))
    return data, {"format": "XIDX", "expected": {"version": 1, "blob_count": len(blobs),
            "index_offset": table_offset, "entries": expected_entries}}


def generate(output_dir: Path, seed: int = 1337) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    samples = [
        ("aster_records.bin", *_aster(rng)),
        ("crc_blocks.bin", *_crc_blocks(rng)),
        ("xidx_archive.bin", *_xidx(rng)),
    ]
    written = []
    for filename, data, truth in samples:
        truth["seed"] = seed
        _write_pair(output_dir, filename, data, truth)
        written.extend((output_dir / filename, output_dir / (filename + ".truth.json")))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("samples/generated"))
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args(argv)
    for path in generate(args.output_dir, args.seed):
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
