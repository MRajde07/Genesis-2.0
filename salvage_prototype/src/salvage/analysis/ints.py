"""Endian-aware integer scanning and candidate length-field analysis."""
from __future__ import annotations


def scan_integers(data: bytes, widths=(1, 2, 4, 8), endians=("little", "big"), max_findings: int = 2000) -> dict:
    if any(width not in (1, 2, 4, 8) for width in widths): raise ValueError("widths must be 1, 2, 4, or 8")
    findings = []
    for width in widths:
        if len(data) < width: continue
        for offset in range(0, len(data) - width + 1):
            raw = data[offset:offset + width]
            for endian in endians:
                value = int.from_bytes(raw, endian, signed=False)
                max_value = (1 << (8 * width)) - 1
                confidence = 0.35
                if value in (len(data), len(data) - offset, len(data) - offset - width): confidence = 0.95
                elif value <= max(len(data) * 16, 4096): confidence = 0.6
                findings.append({"offset": offset, "width": width, "endian": endian, "signed": False,
                                 "value": value, "raw_hex": raw.hex(), "confidence": confidence, "verified": False})
                if len(findings) >= max_findings:
                    return {"analysis": "integers", "findings": findings, "truncated": True,
                            "confidence": 0.5 if findings else 0.0}
    findings.sort(key=lambda item: (-item["confidence"], item["offset"], item["width"], item["endian"]))
    return {"analysis": "integers", "findings": findings, "truncated": False,
            "confidence": round(sum(x["confidence"] for x in findings) / len(findings), 4) if findings else 0.0}


def find_length_fields(data: bytes, widths=(1, 2, 4), endians=("little", "big"), max_findings: int = 500) -> dict:
    n = len(data); findings = []
    for width in widths:
        if width not in (1, 2, 4, 8): continue
        for offset in range(0, max(0, n - width + 1)):
            value_bytes = data[offset:offset + width]
            for endian in endians:
                value = int.from_bytes(value_bytes, endian)
                matches = []
                if value == n: matches.append("file_size")
                if value == n - offset: matches.append("remaining_bytes_from_field")
                if value == n - (offset + width): matches.append("bytes_after_field")
                if value == offset: matches.append("distance_to_file_start")
                if value == n - offset: matches.append("distance_to_file_end")
                for boundary in (offset, offset + width, n):
                    if value == boundary - offset and boundary != offset:
                        matches.append(f"distance_to_boundary_{boundary}")
                if matches:
                    findings.append({"offset": offset, "width": width, "endian": endian, "value": value,
                                     "matches": sorted(set(matches)), "confidence": min(0.99, 0.65 + 0.1 * (len(set(matches)) - 1)), "verified": False})
                    if len(findings) >= max_findings:
                        return {"analysis": "length_fields", "findings": findings, "truncated": True,
                                "confidence": max(x["confidence"] for x in findings)}
    findings.sort(key=lambda x: (-x["confidence"], x["offset"], x["width"], x["endian"]))
    return {"analysis": "length_fields", "findings": findings, "truncated": False,
            "confidence": max((x["confidence"] for x in findings), default=0.0)}


def analyze(data: bytes, **kwargs) -> dict:
    return scan_integers(data, **kwargs)
