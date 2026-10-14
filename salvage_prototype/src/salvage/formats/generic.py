"""Conservative generic analysis for unknown files; all inferred structures are unverified."""
from __future__ import annotations
from .base import FormatPlugin, Result
from ..analysis.entropy import analyze_entropy, byte_histogram
from ..analysis.strings import extract_strings
from ..analysis.ints import scan_integers, find_length_fields
from ..analysis.records import detect_fixed_records
from ..analysis.checksums import guess_checksums
from ..analysis.xor import detect_single_byte_xor, detect_repeating_key_xor
from ..analysis.rle import detect_rle

ANALYSIS_LIMIT = 65536


class GenericPlugin(FormatPlugin):
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        # Fallback is eligible for every input, but has no format evidence.
        return 0.01

    def decode(self, data: bytes) -> Result:
        sample = data[:ANALYSIS_LIMIT]
        truncated = len(data) > len(sample)
        findings = {
            "unverified": True,
            "analysis_bytes": len(sample),
            "source_bytes": len(data),
            "analysis_truncated": truncated,
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
        return Result(format="UNKNOWN", status="unsupported", data=findings,
                      errors=["Generic analysis is heuristic; all candidate structures are unverified"])
