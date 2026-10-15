"""Extract printable string runs with source byte offsets; no replacement decoding."""
from __future__ import annotations


def _printable(ch: str) -> bool:
    return ch.isprintable() and ch not in "\x0b\x0c"


def _runs_ascii(data: bytes, encoding: str, min_length: int, max_strings: int) -> list[dict]:
    if max_strings <= 0: return []
    found, start, chars = [], None, []
    for offset, byte in enumerate(data):
        try:
            char = bytes((byte,)).decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            char = ""
        if char and _printable(char):
            if start is None: start = offset
            chars.append(char)
        else:
            if start is not None and len(chars) >= min_length:
                found.append({"text": "".join(chars), "encoding": encoding, "offset": start,
                              "length": offset - start, "confidence": round(min(1.0, len(chars) / 12), 4), "verified": False})
                if len(found) >= max_strings: return found
            start, chars = None, []
    if start is not None and len(chars) >= min_length and len(found) < max_strings:
        found.append({"text": "".join(chars), "encoding": encoding, "offset": start,
                      "length": len(data) - start, "confidence": round(min(1.0, len(chars) / 12), 4), "verified": False})
    return found


def _runs_utf16(data: bytes, endian: str, min_length: int, max_strings: int) -> list[dict]:
    if max_strings <= 0: return []
    enc = "utf-16-le" if endian == "little" else "utf-16-be"
    found = []
    # Examine both possible byte alignments, which is useful for embedded strings.
    for alignment in (0, 1):
        start, chars = None, []
        limit = len(data) - ((len(data) - alignment) % 2)
        for offset in range(alignment, limit, 2):
            pair = data[offset:offset + 2]
            try: char = pair.decode(enc, errors="strict")
            except UnicodeDecodeError: char = ""
            if char and _printable(char):
                if start is None: start = offset
                chars.append(char)
            else:
                if start is not None and len(chars) >= min_length:
                    found.append({"text": "".join(chars), "encoding": "UTF-16LE" if endian == "little" else "UTF-16BE",
                                  "offset": start, "length": offset - start,
                                  "confidence": round(min(1.0, len(chars) / 12), 4), "verified": False})
                start, chars = None, []
                if len(found) >= max_strings: return found
        if start is not None and len(chars) >= min_length:
            found.append({"text": "".join(chars), "encoding": "UTF-16LE" if endian == "little" else "UTF-16BE",
                          "offset": start, "length": len(chars) * 2,
                          "confidence": round(min(1.0, len(chars) / 12), 4), "verified": False})
        if len(found) >= max_strings: break
    return found[:max_strings]


def extract_strings(data: bytes, min_length: int = 4, max_strings: int = 1000) -> dict:
    if min_length < 1 or max_strings < 1: raise ValueError("min_length and max_strings must be positive")
    findings = []
    findings.extend(_runs_ascii(data, "ascii", min_length, max_strings))
    findings.extend(_runs_utf16(data, "little", min_length, max_strings - len(findings)))
    findings.extend(_runs_utf16(data, "big", min_length, max_strings - len(findings)))
    findings.extend(_runs_ascii(data, "cp437", min_length, max_strings - len(findings)))
    # Stable ordering and exact duplicate removal (CP437 commonly duplicates ASCII).
    unique = {}
    for item in findings:
        key = (item["offset"], item["length"], item["encoding"], item["text"])
        unique[key] = item
    results = sorted(unique.values(), key=lambda item: (item["offset"], item["encoding"], item["text"]))[:max_strings]
    return {"analysis": "strings", "findings": results, "count": len(results),
            "confidence": round(sum(x["confidence"] for x in results) / len(results), 4) if results else 0.0}


def analyze(data: bytes, min_length: int = 4, max_strings: int = 1000) -> dict:
    return extract_strings(data, min_length, max_strings)
