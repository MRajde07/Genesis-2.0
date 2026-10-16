#!/usr/bin/env python3
"""Conservatively infer flat fixed-field specs from binary/truth pairs.

Pair convention: ``sample.bin`` + ``sample.bin.expected.json``. Each truth file
must be a JSON object with ``format`` and ``expected`` (a flat object of scalar
field names to values). The final sorted sample is held out and is never used
for inference. Ambiguous fields, transformations, nested data, or insufficient
samples cause a non-zero exit and no spec is written.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NUMERIC_TYPES = ((1, False, "u8"), (2, False, "u16"), (4, False, "u32"), (8, False, "u64"),
                 (1, True, "i8"), (2, True, "i16"), (4, True, "i32"), (8, True, "i64"))


def load_pair(path: Path) -> tuple[bytes, dict[str, Any], str]:
    sidecar = Path(str(path) + ".expected.json")
    if not sidecar.is_file():
        raise ValueError(f"missing truth sidecar: {sidecar.name}")
    truth = json.loads(sidecar.read_text(encoding="utf-8"))
    if not isinstance(truth, dict) or not isinstance(truth.get("expected"), dict):
        raise ValueError(f"{sidecar.name}: expected an object with an 'expected' object")
    format_name = truth.get("format")
    if not isinstance(format_name, str) or not format_name:
        raise ValueError(f"{sidecar.name}: 'format' must be a non-empty string")
    expected = truth["expected"]
    if not expected or any(isinstance(v, (dict, list, bool)) or v is None for v in expected.values()):
        raise ValueError(f"{sidecar.name}: only flat string/integer/float scalar values are supported")
    return path.read_bytes(), expected, format_name


def common_signature(samples: list[bytes]) -> bytes:
    limit = min(map(len, samples))
    n = 0
    while n < limit and all(sample[n] == samples[0][n] for sample in samples[1:]):
        n += 1
    if n < 4:
        raise ValueError("could not establish a common signature of at least 4 bytes")
    # Signatures that accidentally include changing fields are avoided by limiting
    # to the first run of common bytes, with a practical upper bound.
    return samples[0][:min(n, 32)]


def occurrences(sample: bytes, raw: bytes) -> list[int]:
    if not raw:
        return []
    found = []
    start = 0
    while True:
        pos = sample.find(raw, start)
        if pos < 0:
            break
        found.append(pos)
        start = pos + 1
    return found


def candidates_for(name: str, values: list[Any], samples: list[bytes]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if all(isinstance(v, str) for v in values):
        encodings = ("utf-8", "ascii", "cp437")
        seen_encodings: set[tuple[int, int, tuple[bytes, ...]]] = set()
        for encoding in encodings:
            try:
                encoded = [v.encode(encoding) for v in values]
            except (UnicodeEncodeError, LookupError):
                continue
            locations = [occurrences(data, raw) for data, raw in zip(samples, encoded)]
            if all(len(loc) == 1 for loc in locations) and len({loc[0] for loc in locations}) == 1:
                identity = (locations[0][0], len(encoded[0]), tuple(encoded))
                if identity not in seen_encodings:
                    seen_encodings.add(identity)
                    candidates.append({"name": name, "type": "fixed_string", "length": len(encoded[0]),
                                       "offset": locations[0][0], "encoding": encoding})
    elif all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        seen_numeric: set[tuple[int, int, str, tuple[bytes, ...]]] = set()
        # Positive-only observations cannot prove signedness; prefer unsigned for
        # non-negative values when byte width/offset/endianness are otherwise equal.
        numeric_types = [item for item in NUMERIC_TYPES if not (all(v >= 0 for v in values) and item[1])]
        for width, signed, type_name in numeric_types:
            for endian in ("little", "big"):
                try:
                    encoded = [v.to_bytes(width, endian, signed=signed) for v in values]
                except OverflowError:
                    continue
                locations = [occurrences(data, raw) for data, raw in zip(samples, encoded)]
                if all(len(loc) == 1 for loc in locations) and len({loc[0] for loc in locations}) == 1:
                    identity = (locations[0][0], width, endian, tuple(encoded))
                    if identity not in seen_numeric:
                        seen_numeric.add(identity)
                        candidates.append({"name": name, "type": type_name, "offset": locations[0][0],
                                           "endianness": endian})
    elif all(isinstance(v, (int, float)) for v in values):
        # Floating-point inference is deliberately not attempted until a training
        # corpus supplies enough independent evidence to distinguish encodings.
        return []
    return candidates


def infer_spec(pairs: list[tuple[Path, bytes, dict[str, Any], str]]) -> dict[str, Any]:
    if len(pairs) < 3:
        raise ValueError("need at least 3 binary/truth pairs (2 training samples plus 1 holdout)")
    names = {item[3] for item in pairs}
    if len(names) != 1:
        raise ValueError("training pairs disagree on format name")
    training = pairs[:-1]
    holdout = pairs[-1]
    key_sets = [set(item[2]) for item in training]
    if any(keys != key_sets[0] for keys in key_sets[1:]) or set(holdout[2]) != key_sets[0]:
        raise ValueError("training/holdout expected fields do not agree")
    data_samples = [item[1] for item in training]
    signature = common_signature(data_samples)
    fields = []
    occupied: set[tuple[int, int]] = set()
    for name in sorted(key_sets[0]):
        values = [item[2][name] for item in training]
        candidates = candidates_for(name, values, data_samples)
        # Remove candidates that merely reinterpret the signature bytes as a field.
        candidates = [c for c in candidates if c["offset"] >= len(signature)]
        if len(candidates) != 1:
            raise ValueError(f"field {name!r}: expected one unambiguous fixed-width location, found {len(candidates)}; refusing to guess")
        candidate = candidates[0]
        size = candidate.get("length", {"u8": 1, "i8": 1, "u16": 2, "i16": 2,
                  "u32": 4, "i32": 4, "u64": 8, "i64": 8}.get(candidate["type"], 0))
        span = (candidate["offset"], candidate["offset"] + size)
        if any(span[0] < end and start < span[1] for start, end in occupied):
            raise ValueError(f"field {name!r}: inferred range overlaps another field; refusing to guess")
        occupied.add(span)
        fields.append(candidate)
    spec = {"name": "LEARNED_" + next(iter(names)).upper(), "public_format": "UNKNOWN",
            "description": "Generated from paired samples; validate against independent real files before production use.",
            "signature_hex": signature.hex(), "signature_offset": 0,
            "minimum_length": max(end for _, end in occupied) if occupied else len(signature),
            "endianness": "little", "fields": fields, "confidence": 0.85}
    # Holdout verification uses the inferred fields, not just signature matching.
    for field in fields:
        value = holdout[2][field["name"]]
        offset = field["offset"]
        if field["type"] == "fixed_string":
            actual = holdout[1][offset:offset + field["length"]].decode(field["encoding"], errors="strict")
        else:
            typ = field["type"]
            width = int(typ[1:]) // 8
            actual = int.from_bytes(holdout[1][offset:offset + width], field.get("endianness", "little"),
                                   signed=typ.startswith("i"))
        if actual != value:
            raise ValueError(f"holdout failed for field {field['name']!r}: decoded {actual!r}, expected {value!r}")
    return spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples_dir", type=Path, help="directory containing *.bin pairs")
    parser.add_argument("--output", type=Path, required=True, help="path for the generated JSON spec")
    args = parser.parse_args(argv)
    try:
        files = sorted(args.samples_dir.glob("*.bin"))
        if len(files) < 3:
            raise ValueError("need at least 3 .bin files with matching .bin.expected.json sidecars")
        pairs = []
        for path in files:
            data, expected, format_name = load_pair(path)
            pairs.append((path, data, expected, format_name))
        spec = infer_spec(pairs)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"train: refusing to emit a spec: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.output} (holdout: {pairs[-1][0].name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
