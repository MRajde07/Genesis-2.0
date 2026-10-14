#!/usr/bin/env python3
"""Create deterministic corrupted copies of binary samples.

Usage: python tools/corrupt.py INPUT_DIR OUTPUT_DIR [--seed 1337] [--per-type 1]
The output contains mutated ``.bin`` files and a manifest.json describing each
mutation. Ground-truth sidecars are deliberately not copied into the corpus.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

KINDS = ("truncate", "bit-flip", "zero-block", "swap-bytes")


def mutate(data: bytes, kind: str, rng: random.Random) -> tuple[bytes, dict[str, Any]]:
    """Mutate bytes and return (mutated bytes, reproducible mutation metadata)."""
    raw = bytearray(data)
    original_length = len(raw)
    if kind == "truncate":
        # Preserve a real truncation whenever possible; empty files remain empty.
        cut = rng.randrange(0, original_length) if original_length else 0
        mutated = bytes(raw[:cut])
        details = {"offset": cut, "start": cut, "end": original_length,
                   "reason": "truncated suffix", "original_length": original_length,
                   "mutated_length": len(mutated)}
    elif kind == "bit-flip":
        if not raw:
            offset, mask = 0, 1
            mutated = bytes(raw)
            reason = "empty input; no byte available to flip"
            end = 0
        else:
            offset = rng.randrange(len(raw))
            mask = 1 << rng.randrange(8)
            raw[offset] ^= mask
            mutated = bytes(raw)
            reason = "one bit flipped"
            end = offset + 1
        details = {"offset": offset, "start": offset, "end": end,
                   "mask": mask, "reason": reason,
                   "original_length": original_length, "mutated_length": len(mutated)}
    elif kind == "zero-block":
        if not raw:
            start, end = 0, 0
        else:
            start = rng.randrange(len(raw))
            max_size = min(16, len(raw) - start)
            size = rng.randrange(1, max_size + 1)
            end = start + size
            raw[start:end] = b"\x00" * size
        mutated = bytes(raw)
        details = {"offset": start, "start": start, "end": end,
                   "reason": "contiguous byte block zeroed",
                   "original_length": original_length, "mutated_length": len(mutated)}
    elif kind == "swap-bytes":
        if len(raw) < 2:
            first = second = 0
            mutated = bytes(raw)
            reason = "fewer than two bytes; no swap possible"
            start, end = 0, len(raw)
        else:
            first = rng.randrange(len(raw) - 1)
            second = first + 1
            raw[first], raw[second] = raw[second], raw[first]
            mutated = bytes(raw)
            reason = "adjacent bytes swapped"
            start, end = first, second + 1
        details = {"offset": first, "other_offset": second, "start": start, "end": end,
                   "reason": reason, "original_length": original_length,
                   "mutated_length": len(mutated)}
    else:
        raise ValueError(f"unsupported mutation kind: {kind}")
    return mutated, {"kind": kind, **details}


def generate(input_dir: Path, output_dir: Path, seed: int = 1337,
             per_type: int = 1) -> list[Path]:
    """Generate seeded mutations for each regular file in *input_dir*."""
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted((p for p in input_dir.iterdir()
                      if p.is_file() and not p.name.endswith(".truth.json")
                      and not p.name.endswith(".mutation.json")
                      and p.name != "manifest.json"), key=lambda p: p.name)
    manifest: dict[str, Any] = {"seed": seed, "mutations": []}
    written: list[Path] = []
    for source in sources:
        try:
            original = source.read_bytes()
        except OSError as exc:
            manifest["mutations"].append({"source": source.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for kind in KINDS:
            for index in range(max(1, per_type)):
                mutated, details = mutate(original, kind, rng)
                suffix = f"{kind}-{index:02d}"
                destination = output_dir / f"{source.name}.{suffix}"
                destination.write_bytes(mutated)
                entry = {"source": source.name, "file": destination.name,
                         "seed": seed, **details}
                manifest["mutations"].append(entry)
                written.append(destination)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                             encoding="utf-8", newline="\n")
    written.append(manifest_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--per-type", type=int, default=1, help="mutations of each kind per source (minimum 1)")
    args = parser.parse_args(argv)
    if not args.input_dir.is_dir():
        parser.error(f"input directory does not exist: {args.input_dir}")
    for path in generate(args.input_dir, args.output_dir, args.seed, args.per_type):
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
