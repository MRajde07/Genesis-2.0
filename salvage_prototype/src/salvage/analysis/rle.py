"""Conservative count/value RLE detector and decoder hypothesis."""
from __future__ import annotations


def decode_count_value(data: bytes, *, zero_means_256: bool = False, max_output: int = 1_000_000) -> dict:
    output = bytearray(); damage = []
    usable = len(data) - len(data) % 2
    if usable != len(data):
        damage.append({"field": "rle_pair", "offset": usable, "expected": 2, "found": 1,
                       "reason": "truncated count/value pair", "byte_range": {"start": usable, "end": len(data)}})
    for offset in range(0, usable, 2):
        count, value = data[offset], data[offset + 1]
        count = 256 if count == 0 and zero_means_256 else count
        if count == 0: continue
        if len(output) + count > max_output:
            damage.append({"field": "rle_output", "offset": offset, "expected": count,
                           "found": max(0, max_output - len(output)), "reason": "decoded output limit exceeded",
                           "byte_range": {"start": offset, "end": offset + 2}})
            break
        output.extend(bytes((value,)) * count)
    return {"decoded_hex": bytes(output).hex(), "decoded_size": len(output), "damage": damage,
            "confidence": round(0.65 + (0.25 if usable == len(data) and data else 0.0), 4), "verified": False}


def detect_rle(data: bytes, min_pairs: int = 3) -> dict:
    if len(data) < min_pairs * 2:
        return {"analysis": "rle", "findings": [], "confidence": 0.0}
    decoded = decode_count_value(data)
    pairs = len(data) // 2
    repeated = sum(1 for i in range(0, len(data) - 1, 2) if data[i] > 1)
    compression_ratio = decoded["decoded_size"] / max(1, len(data))
    confidence = min(0.95, 0.45 + 0.08 * min(repeated, 5) + (0.1 if compression_ratio > 1.2 else 0.0))
    if pairs < min_pairs or repeated == 0: return {"analysis": "rle", "findings": [], "confidence": 0.0}
    return {"analysis": "rle", "findings": [{"scheme": "count_value_pairs", "pair_count": pairs,
            "decoded_size": decoded["decoded_size"], "compression_ratio": round(compression_ratio, 4),
            "decoded_hex_preview": decoded["decoded_hex"][:128], "damage": decoded["damage"],
            "confidence": round(confidence, 4), "verified": False}], "confidence": round(confidence, 4)}


def analyze(data: bytes, **kwargs) -> dict:
    return detect_rle(data, **kwargs)


# Explicit alias for callers that prefer an imperative decoder name.
def decode_rle(data: bytes, **kwargs) -> dict:
    return decode_count_value(data, **kwargs)
