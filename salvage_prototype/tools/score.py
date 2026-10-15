#!/usr/bin/env python3
"""Score SALVAGE JSON against adjacent *.truth.json fixtures.

Usage: python tools/score.py TRUTH_DIR RESULTS_DIR
RESULTS_DIR contains per-file JSON written by SALVAGE (for example
``aster_records.bin.json``) and optionally ``report.json``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

IGNORED_KEYS = {"raw_hex", "payload_raw_hex", "packed_hex", "complete"}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            if key in IGNORED_KEYS:
                continue
            path = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten(value[key], path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            out.update(_flatten(item, path))
    else:
        out[prefix] = value
    return out


def _equivalent(expected: Any, actual: Any) -> bool:
    # JSON booleans are not numeric ground-truth integers despite Python's
    # bool subclassing int.
    if isinstance(expected, bool) != isinstance(actual, bool):
        return False
    return expected == actual


def score(truth_dir: Path, results_dir: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    true_positive = false_positive = false_negative = 0
    total_fields = correct_fields = 0
    predicted_formats: list[str] = []
    expected_formats: list[str] = []

    for truth_path in sorted(truth_dir.glob("*.truth.json"), key=lambda p: p.name):
        source_name = truth_path.name[:-len(".truth.json")]
        result_path = results_dir / f"{source_name}.json"
        try:
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            expected_format = str(truth.get("format", "UNKNOWN"))
            expected = truth.get("expected", {})
            result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
            actual = result.get("data") if isinstance(result, dict) else None
            actual_format = str(result.get("format", "UNKNOWN")) if isinstance(result, dict) else "UNKNOWN"
        except (OSError, ValueError, TypeError):
            expected_format = "UNKNOWN"
            expected = {}
            actual = None
            actual_format = "UNKNOWN"
        expected_formats.append(expected_format)
        predicted_formats.append(actual_format)
        is_tp = actual_format == expected_format
        if is_tp:
            true_positive += 1
        else:
            false_positive += 1
            false_negative += 1
        expected_flat = _flatten(expected)
        actual_flat = _flatten(actual) if actual is not None else {}
        matches = sum(1 for key, value in expected_flat.items()
                      if key in actual_flat and _equivalent(value, actual_flat[key]))
        total_fields += len(expected_flat)
        correct_fields += matches
        files.append({"file": source_name, "expected_format": expected_format,
                      "detected_format": actual_format, "format_correct": is_tp,
                      "fields_correct": matches, "fields_expected": len(expected_flat),
                      "field_accuracy": matches / len(expected_flat) if expected_flat else 1.0,
                      "status": result.get("status", "missing") if isinstance(result, dict) else "missing"})

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    return {"files": files, "field_accuracy": correct_fields / total_fields if total_fields else 1.0,
            "fields_correct": correct_fields, "fields_total": total_fields,
            "format_precision": precision, "format_recall": recall,
            "format_true_positive": true_positive, "format_false_positive": false_positive,
            "format_false_negative": false_negative}


def print_table(summary: dict[str, Any]) -> None:
    rows = [("File", "Expected", "Detected", "Fields", "Accuracy", "Status")]
    for item in summary["files"]:
        rows.append((item["file"], item["expected_format"], item["detected_format"],
                     f"{item['fields_correct']}/{item['fields_expected']}",
                     f"{item['field_accuracy']:.1%}", item["status"]))
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
    print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(rows[0])))
    print("-+-".join("-" * width for width in widths))
    for row in rows[1:]:
        print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    print()
    print(f"Field accuracy: {summary['fields_correct']}/{summary['fields_total']} = {summary['field_accuracy']:.1%}")
    print(f"Format detection precision: {summary['format_precision']:.1%}")
    print(f"Format detection recall:    {summary['format_recall']:.1%}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("truth_dir", type=Path, help="directory containing *.truth.json files")
    parser.add_argument("results_dir", type=Path, help="directory containing per-file result JSON")
    parser.add_argument("--json", type=Path, help="also write machine-readable score summary")
    args = parser.parse_args(argv)
    summary = score(args.truth_dir, args.results_dir)
    print_table(summary)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
