"""Conservative generic fallback for unrecognised files.

The default result is a short, heuristic summary. The full analysis toolkit still
runs, but its output is stored under a debug-only key that the output layer
drops unless ``--debug`` is given.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .base import FormatPlugin, Result
from ..analysis.entropy import analyze_entropy, byte_histogram
from ..analysis.strings import extract_strings
from ..analysis.ints import scan_integers, find_length_fields
from ..analysis.records import detect_fixed_records
from ..analysis.checksums import guess_checksums
from ..analysis.xor import detect_single_byte_xor, detect_repeating_key_xor
from ..analysis.rle import detect_rle

ANALYSIS_LIMIT = 65536
_ASCII_RUN = re.compile(rb"[\x20-\x7e]{6,}")
MAX_STRINGS = 10


def _entropy(sample: bytes) -> float:
    if not sample:
        return 0.0
    total = len(sample)
    return -sum((n / total) * math.log2(n / total) for n in Counter(sample).values())


def _content_guess(sample: bytes, entropy: float, printable: float) -> str:
    if not sample:
        return "empty"
    if printable >= 0.85:
        return "text-like"
    if entropy >= 7.2:
        return "high-entropy (compressed or encrypted, or random)"
    return "structured binary"


def summarize(data: bytes) -> dict:
    """Short heuristic summary; every statement here is unverified."""
    sample = data[:ANALYSIS_LIMIT]
    entropy = _entropy(sample)
    printable = (sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13)) / len(sample)) if sample else 0.0
    runs = [(m.start(), m.group().decode("ascii")) for m in _ASCII_RUN.finditer(sample)]
    top = sorted(sorted(runs, key=lambda item: -len(item[1]))[:MAX_STRINGS])
    return {
        "unverified": True,
        "size_bytes": len(data),
        "header_hex": data[:16].hex(),
        "entropy_bits_per_byte": round(entropy, 3),
        "printable_ratio": round(printable, 3),
        "content_guess": _content_guess(sample, entropy, printable),
        "ascii_strings": [{"offset": off, "text": text[:80]} for off, text in top],
        "analysis_truncated": len(data) > len(sample),
    }


class GenericPlugin(FormatPlugin):
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        # Fallback is eligible for every input, but has no format evidence.
        return 0.01

    def decode(self, data: bytes) -> Result:
        summary = summarize(data)
        sample = data[:ANALYSIS_LIMIT]
        # Full toolkit output is kept for --debug only (leading underscore).
        summary["_full_analysis"] = {
            "strings": extract_strings(sample, min_length=4, max_strings=500),
            "entropy": analyze_entropy(sample, window_size=256, step=128),
            "byte_histogram": byte_histogram(sample),
            "integer_candidates": scan_integers(sample, max_findings=500),
            "length_fields": find_length_fields(sample, max_findings=200),
            "fixed_record_candidates": detect_fixed_records(sample, max_record_size=128),
            "checksum_candidates": guess_checksums(sample[:4096], max_candidates=100),
            "xor_single_byte_candidates": detect_single_byte_xor(sample[:8192], max_findings=4),
            "xor_repeating_key_candidates": detect_repeating_key_xor(sample[:8192], max_findings=4),
            "rle_candidates": detect_rle(sample),
        }
        return Result(format="UNKNOWN", status="unsupported", data=summary,
                      errors=["Format not recognised; heuristic summary only, nothing decoded"])
