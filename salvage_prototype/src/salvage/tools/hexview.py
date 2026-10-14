"""Annotated deterministic hex dump with printable ASCII and entropy labels."""
from __future__ import annotations
import sys
from pathlib import Path

try:
    from ..analysis.entropy import analyze_entropy
    from ..analysis.strings import extract_strings
except ImportError:
    from salvage.analysis.entropy import analyze_entropy
    from salvage.analysis.strings import extract_strings


def render(data: bytes, width: int = 16) -> str:
    if width < 1: raise ValueError("width must be positive")
    strings = extract_strings(data, min_length=4, max_strings=1000)["findings"]
    starts = {item["offset"]: item["text"] for item in strings}
    entropy = analyze_entropy(data, window_size=256, step=256)["regions"]
    region_by_start = {item["offset"]: item for item in entropy}
    lines = []
    for offset in range(0, len(data), width):
        chunk = data[offset:offset + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk).ljust(width * 3 - 1)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        annotations = []
        if offset in region_by_start:
            item = region_by_start[offset]
            annotations.append(f"entropy={item['entropy_bits_per_byte']:.3f}")
        for start, text in sorted(starts.items()):
            if offset <= start < offset + width:
                annotations.append(f"string@0x{start:x}={text!r}")
        suffix = "  ; " + ", ".join(annotations) if annotations else ""
        lines.append(f"{offset:08x}  {hex_part}  |{ascii_part}|{suffix}")
    if not lines: lines.append("00000000  <empty file>")
    return "\n".join(lines)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (1, 2):
        print("usage: hexview.py FILE [WIDTH]", file=sys.stderr); return 0
    try:
        data = Path(args[0]).read_bytes()
        width = int(args[1]) if len(args) == 2 else 16
        print(render(data, width))
    except Exception as exc:
        print(f"hexview: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
