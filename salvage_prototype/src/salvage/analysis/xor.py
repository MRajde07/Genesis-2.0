"""Single-byte and repeating-key XOR hypotheses, never treated as decoded truth."""
from __future__ import annotations


def _english_score(data: bytes) -> float:
    if not data: return 0.0
    printable = sum(1 for b in data if b in (9, 10, 13) or 32 <= b <= 126)
    common = sum(1 for b in data if b in b" etaoinshrdluETAOINSHRDLU0123456789.,'\"-_")
    return 0.75 * printable / len(data) + 0.25 * common / len(data)


def detect_single_byte_xor(data: bytes, min_score: float = 0.75, max_findings: int = 8) -> dict:
    findings = []
    if not data: return {"analysis": "xor_single_byte", "findings": [], "confidence": 0.0}
    for key in range(256):
        decoded = bytes(byte ^ key for byte in data[:65536])
        score = _english_score(decoded)
        if score >= min_score:
            findings.append({"key": key, "key_hex": f"{key:02x}", "sample_hex": decoded[:64].hex(),
                             "sample_text": decoded[:64].decode("ascii", errors="ignore"),
                             "confidence": round(score, 4), "verified": False})
    findings.sort(key=lambda x: (-x["confidence"], x["key"]))
    return {"analysis": "xor_single_byte", "findings": findings[:max_findings],
            "confidence": findings[0]["confidence"] if findings else 0.0}


def detect_repeating_key_xor(data: bytes, min_key_size: int = 2, max_key_size: int = 16,
                             max_findings: int = 8) -> dict:
    if min_key_size < 1 or max_key_size < min_key_size: raise ValueError("invalid key size bounds")
    findings = []
    sample = data[:65536]
    for size in range(min_key_size, min(max_key_size, len(sample) // 2) + 1):
        blocks = [sample[i:i + size] for i in range(0, min(len(sample), size * 8), size)]
        distances = []
        for a, b in zip(blocks, blocks[1:]):
            if len(a) == len(b): distances.append(sum((x ^ y).bit_count() for x, y in zip(a, b)) / size)
        if not distances: continue
        normalized = sum(distances) / len(distances)
        columns = [bytes(sample[i] for i in range(col, min(len(sample), 8192), size)) for col in range(size)]
        key = bytes(max(range(256), key=lambda k: _english_score(bytes(v ^ k for v in col[:256]))) for col in columns)
        decoded = bytes(value ^ key[i % size] for i, value in enumerate(sample))
        score = _english_score(decoded)
        # Distance suggests a candidate key length; language score tests the inferred key.
        confidence = max(0.0, min(1.0, 0.55 * score + 0.45 * max(0.0, 1.0 - normalized)))
        findings.append({"key_size": size, "normalized_hamming_distance": round(normalized, 4),
                         "key_hex": key.hex(), "sample_hex": decoded[:64].hex(),
                         "sample_text": decoded[:64].decode("ascii", errors="ignore"),
                         "confidence": round(confidence, 4), "verified": False})
    findings.sort(key=lambda x: (-x["confidence"], x["key_size"]))
    return {"analysis": "xor_repeating_key", "findings": findings[:max_findings],
            "confidence": findings[0]["confidence"] if findings else 0.0}


def analyze(data: bytes, **kwargs) -> dict:
    return {"single_byte": detect_single_byte_xor(data), "repeating_key": detect_repeating_key_xor(data)}


def detect_xor(data: bytes, **kwargs) -> dict:
    return analyze(data, **kwargs)
