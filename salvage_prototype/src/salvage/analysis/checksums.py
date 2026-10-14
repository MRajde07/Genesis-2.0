"""Heuristic checksum matching over candidate byte ranges."""
from __future__ import annotations


def _crc16(data: bytes, poly: int, init: int, refin: bool = False) -> int:
    crc = init & 0xffff
    if refin:
        for byte in data:
            crc ^= byte
            for _ in range(8): crc = (crc >> 1) ^ (poly if crc & 1 else 0)
    else:
        for byte in data:
            crc ^= byte << 8
            for _ in range(8): crc = ((crc << 1) ^ poly) & 0xffff if crc & 0x8000 else (crc << 1) & 0xffff
    return crc & 0xffff


def _fletcher16(data: bytes) -> int:
    a = b = 0
    for byte in data: a = (a + byte) % 255; b = (b + a) % 255
    return (b << 8) | a


def _sum16(data: bytes, endian: str) -> int:
    if len(data) % 2: data += b"\x00"
    return sum(int.from_bytes(data[i:i + 2], endian) for i in range(0, len(data), 2)) & 0xffff


def guess_checksums(data: bytes, max_candidates: int = 500) -> dict:
    n = len(data); found = []
    if n < 2: return {"analysis": "checksums", "findings": [], "confidence": 0.0}
    # Check likely stored checksum fields near the beginning/end and internal offsets for small files.
    positions = set(range(max(0, n - 8), n)) | set(range(0, min(n, 8))) | {max(0, n // 2)}
    if n <= 256: positions.update(range(n))
    for offset in sorted(positions):
        for width in (1, 2, 4):
            if offset + width > n: continue
            stored_bytes = data[offset:offset + width]
            before, after = data[:offset], data[offset + width:]
            ranges = [("before_field", before), ("after_field", after), ("whole_file_zeroed_field", before + bytes(width) + after)]
            for range_name, payload in ranges:
                algorithms = []
                if width == 1:
                    algorithms.extend([("sum8", sum(payload) & 0xff), ("xor8", _xor(payload) )])
                if width >= 2:
                    for endian in ("little", "big"):
                        algorithms.extend([(f"sum16_{endian}", _sum16(payload, endian)),
                                          (f"fletcher16_{endian}", _fletcher16(payload))])
                    algorithms.extend([("crc16_modbus", _crc16(payload, 0xA001, 0xFFFF, True)),
                                       ("crc16_ccitt_false", _crc16(payload, 0x1021, 0xFFFF))])
                if width >= 4: algorithms.append(("crc32", _crc32(payload)))
                for algorithm, computed in algorithms:
                    for endian in (("little", "big") if width > 1 else ("little",)):
                        if int.from_bytes(stored_bytes, endian) == computed:
                            found.append({"offset": offset, "width": width, "endian": endian, "algorithm": algorithm,
                                          "range": range_name, "stored": int.from_bytes(stored_bytes, endian),
                                          "computed": computed, "confidence": 0.85, "verified": False})
                            if len(found) >= max_candidates:
                                return {"analysis": "checksums", "findings": found, "truncated": True, "confidence": 0.85}
    found.sort(key=lambda x: (x["offset"], x["width"], x["algorithm"], x["range"], x["endian"]))
    return {"analysis": "checksums", "findings": found, "truncated": False,
            "confidence": max((x["confidence"] for x in found), default=0.0)}


def _xor(data: bytes) -> int:
    value = 0
    for byte in data: value ^= byte
    return value


def _crc32(data: bytes) -> int:
    import zlib
    return zlib.crc32(data) & 0xffffffff


def analyze(data: bytes, **kwargs) -> dict:
    return guess_checksums(data, **kwargs)
