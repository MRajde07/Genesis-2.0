"""The single boundary for shaping SALVAGE output and report JSON.

Keep schema-specific JSON decisions here so an official schema can replace
this module's shaping without changing parsers or orchestration.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

STATUS_VOCABULARY = ("recovered", "partial", "damaged", "unsupported", "error")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, sort_keys=False) + "\n", encoding="utf-8", newline="\n")


def _damage_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        raw = item.to_dict()
    elif isinstance(item, dict):
        raw = dict(item)
    else:
        raw = {"field": "unknown", "offset": 0, "expected": 0, "found": 0,
               "reason": f"invalid damage entry type: {type(item).__name__}"}
    # Normalize the reader's structured contract and derive a missing-byte
    # range when a plugin has not supplied a more precise affected-byte range.
    field = str(raw.get("field", "unknown"))
    offset = _nonnegative_int(raw.get("offset"), 0)
    expected = _nonnegative_int(raw.get("expected"), 0)
    found = _nonnegative_int(raw.get("found"), 0)
    reason = str(raw.get("reason", "unspecified damage"))
    shaped = {"field": field, "offset": offset, "expected": expected,
              "found": found, "reason": reason}
    byte_range = raw.get("byte_range")
    if isinstance(byte_range, dict) and "start" in byte_range and "end" in byte_range:
        start = _nonnegative_int(byte_range.get("start"), offset)
        end = max(start, _nonnegative_int(byte_range.get("end"), start))
    elif isinstance(byte_range, (tuple, list)) and len(byte_range) == 2:
        start = _nonnegative_int(byte_range[0], offset)
        end = max(start, _nonnegative_int(byte_range[1], start))
    elif expected > found:
        start, end = offset, offset + (expected - found)
    elif found > 0:
        start, end = offset, offset + found
    else:
        start = end = offset
    shaped["byte_range"] = {"start": start, "end": end}
    return shaped


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        number = int(value)
        return max(0, number)
    except (TypeError, ValueError, OverflowError):
        return default


def _status(status: Any) -> str:
    aliases = {"success": "recovered", "partially_recovered": "partial",
               "partially-recovered": "partial"}
    normalized = aliases.get(str(status), str(status))
    return normalized if normalized in STATUS_VOCABULARY else "error"


def shape_result(file_name: str, decoded: Any, *, fallback_format: str = "UNKNOWN") -> dict[str, Any]:
    """Convert an internal plugin Result to the stable per-file JSON schema."""
    raw_damage = list(getattr(decoded, "damage", []) or [])
    damage = [_damage_dict(item) for item in raw_damage]
    records = list(getattr(decoded, "records", []) or [])
    data = getattr(decoded, "data", None)
    status = _status(getattr(decoded, "status", "unsupported"))
    if damage and status == "recovered":
        status = "damaged"
    # Counts are mutually exclusive: complete records are recovered, records
    # with byte/decoding damage are damaged, and a known record that could not
    # be reconstructed at all is lost. Unknown files are not guessed to contain
    # a particular number of records.
    if damage or status in ("partial", "damaged"):
        records_recovered = 0
        records_damaged = len(records) if records else 0
        records_lost = 1 if not records and status in ("partial", "damaged") else 0
    else:
        records_recovered = len(records)
        records_damaged = 0
        records_lost = 0
    result = {
        "file_name": str(file_name),
        "format": str(getattr(decoded, "format", "") or fallback_format),
        "status": status,
        "data": data,
        "records": records,
        "counts": {
            "records_recovered": records_recovered,
            "records_damaged": records_damaged,
            "records_lost": records_lost,
        },
        "damage": damage,
        "byte_ranges": [item["byte_range"] for item in damage],
        "errors": [str(item) for item in (getattr(decoded, "errors", []) or [])],
    }
    return result


def shape_failure(file_name: str, format_name: str, message: str, *, field: str = "file") -> dict[str, Any]:
    damage = _damage_dict({"field": field, "offset": 0, "expected": 0, "found": 0,
                           "reason": message, "byte_range": {"start": 0, "end": 0}})
    return {
        "file_name": str(file_name), "format": str(format_name), "status": "error",
        "data": None, "records": [],
        "counts": {"records_recovered": 0, "records_damaged": 0, "records_lost": 0},
        "damage": [damage], "byte_ranges": [damage["byte_range"]], "errors": [str(message)],
    }


def shape_failure_entry(path: str, stage: str, error: BaseException | str) -> dict[str, Any]:
    detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    return {"path": str(path), "status": "error", "stage": stage, "error": detail}


def shape_report(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    failures = list(failures or [])
    counts = Counter(item.get("status", "error") for item in results)
    return {
        "tool": "SALVAGE",
        "files_processed": len(results),
        "status_vocabulary": list(STATUS_VOCABULARY),
        "status_counts": {key: counts.get(key, 0) for key in STATUS_VOCABULARY},
        "records_recovered": sum(item.get("counts", {}).get("records_recovered", 0) for item in results),
        "records_damaged": sum(item.get("counts", {}).get("records_damaged", 0) for item in results),
        "records_lost": sum(item.get("counts", {}).get("records_lost", 0) for item in results),
        "output_errors": [],
        "failures": failures,
        "results": results,
    }
