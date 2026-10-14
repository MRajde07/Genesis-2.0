"""Fixed-size record and simple length-field structure heuristics."""
from __future__ import annotations
from .ints import find_length_fields


def detect_fixed_records(data: bytes, min_record_size: int = 2, max_record_size: int = 256) -> dict:
    n = len(data); candidates = []
    if min_record_size < 1 or max_record_size < min_record_size: raise ValueError("invalid record size bounds")
    for size in range(min_record_size, min(max_record_size, n) + 1):
        complete, remainder = divmod(n, size)
        if complete < 2: continue
        # Score divisibility strongly; repeated record prefixes add weak evidence only.
        confidence = 0.65 + (0.25 if remainder == 0 else 0.0)
        samples = [data[i * size:(i + 1) * size] for i in range(min(complete, 8))]
        same_prefix = sum(1 for a, b in zip(samples, samples[1:]) if a[:min(2, size)] == b[:min(2, size)])
        if samples and len(samples) > 1: confidence += 0.1 * same_prefix / (len(samples) - 1)
        candidates.append({"record_size": size, "record_count": complete, "remainder_bytes": remainder,
                           "remainder_offset": complete * size, "confidence": round(min(0.99, confidence), 4),
                           "verified": False})
    candidates.sort(key=lambda x: (-x["confidence"], x["remainder_bytes"], x["record_size"]))
    return {"analysis": "fixed_records", "findings": candidates[:100],
            "confidence": candidates[0]["confidence"] if candidates else 0.0}


def analyze(data: bytes, **kwargs) -> dict:
    fixed = detect_fixed_records(data, **kwargs)
    fixed["length_fields"] = find_length_fields(data)
    return fixed
