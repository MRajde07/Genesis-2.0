"""Print all SALVAGE analysis findings for one file as deterministic JSON."""
from __future__ import annotations
import json
import sys
from pathlib import Path

try:
    from ..analysis.entropy import analyze_entropy, byte_histogram
    from ..analysis.strings import extract_strings
    from ..analysis.ints import scan_integers, find_length_fields
    from ..analysis.records import detect_fixed_records
    from ..analysis.checksums import guess_checksums
    from ..analysis.xor import detect_single_byte_xor, detect_repeating_key_xor
    from ..analysis.rle import detect_rle
except ImportError:  # direct script execution with src/salvage on sys.path
    from salvage.analysis.entropy import analyze_entropy, byte_histogram
    from salvage.analysis.strings import extract_strings
    from salvage.analysis.ints import scan_integers, find_length_fields
    from salvage.analysis.records import detect_fixed_records
    from salvage.analysis.checksums import guess_checksums
    from salvage.analysis.xor import detect_single_byte_xor, detect_repeating_key_xor
    from salvage.analysis.rle import detect_rle


def probe(data: bytes) -> dict:
    sample = data[:65536]
    return {
        "source_size": len(data), "analysis_size": len(sample), "analysis_truncated": len(sample) < len(data),
        "strings": extract_strings(sample, max_strings=1000),
        "entropy": analyze_entropy(sample), "byte_histogram": byte_histogram(sample),
        "integers": scan_integers(sample), "length_fields": find_length_fields(sample),
        "fixed_records": detect_fixed_records(sample), "checksums": guess_checksums(sample[:4096]),
        "xor_single_byte": detect_single_byte_xor(sample[:8192]),
        "xor_repeating_key": detect_repeating_key_xor(sample[:8192]), "rle": detect_rle(sample),
        "unverified": True,
    }


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: probe.py FILE", file=sys.stderr); return 0
    try:
        data = Path(args[0]).read_bytes()
        print(json.dumps(probe(data), indent=2, sort_keys=True, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"status": "error", "path": args[0], "error": f"{type(exc).__name__}: {exc}"},
                         indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
