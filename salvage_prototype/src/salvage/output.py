"""The single boundary for shaping SALVAGE output and report JSON.

Keep schema-specific JSON decisions here so an official schema can replace
this module's shaping without changing parsers or orchestration.
"""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from collections import Counter
from pathlib import Path
from typing import Any

STATUS_VOCABULARY = ("recovered", "partial", "damaged", "unsupported", "error")


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"


class SchemaValidationError(ValueError):
    """An output document did not satisfy the supported schema subset."""


@lru_cache(maxsize=8)
def load_schema(name: str = "result.schema.json") -> dict[str, Any]:
    """Load a bundled local schema, without any remote resolution."""
    if name not in ("result.schema.json", "report.schema.json"):
        raise ValueError("unknown bundled schema")
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate a deliberately small JSON Schema subset (no external refs).

    Supported: type, required, properties, items, enum, minimum, maximum,
    additionalProperties, minItems, maxItems, minLength, maxLength.
    Unknown schema keywords are rejected to avoid silently weakening validation.
    """
    allowed = {"$schema", "title", "description", "type", "required", "properties",
               "items", "enum", "minimum", "maximum", "additionalProperties",
               "minItems", "maxItems", "minLength", "maxLength"}
    unsupported = set(schema) - allowed
    if unsupported:
        raise SchemaValidationError(f"{path}: unsupported schema keywords: {sorted(unsupported)}")
    types = {"object": lambda v: isinstance(v, dict),
             "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str),
             "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
             "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v),
             "boolean": lambda v: isinstance(v, bool),
             "null": lambda v: v is None}
    declared = schema.get("type")
    if declared is not None:
        names = [declared] if isinstance(declared, str) else declared
        if not isinstance(names, list) or not names or any(n not in types for n in names):
            raise SchemaValidationError(f"{path}: unsupported type declaration")
        if not any(types[n](value) for n in names):
            raise SchemaValidationError(f"{path}: expected {names}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value not in enum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise SchemaValidationError(f"{path}: missing required key {key!r}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                validate_schema(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties", True) is False:
                raise SchemaValidationError(f"{path}: unexpected key {key!r}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate_schema(item, schema["additionalProperties"], f"{path}.{key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaValidationError(f"{path}: too many items")
        if "items" in schema:
            for i, item in enumerate(value):
                validate_schema(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaValidationError(f"{path}: string too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaValidationError(f"{path}: string too long")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{path}: above maximum")


def write_json(path: Path, value: Any, *, schema_name: str | None = None) -> None:
    """Validate before writing; serialize in a deterministic, portable form."""
    if schema_name is None:
        schema_name = "report.schema.json" if path.name == "report.json" else "result.schema.json"
    validate_schema(value, load_schema(schema_name))
    serialized = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True,
                            allow_nan=False) + "\n"
    path.write_text(serialized, encoding="utf-8", newline="\n")


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
    if raw.get("raw_hex") is not None:
        shaped["raw_hex"] = str(raw["raw_hex"])
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


_REGION_ONLY = re.compile(r"\[(\d+)\]")


def _damaged_record_keys(damage: list[dict[str, Any]]) -> set[int]:
    """Record indexes named by damage fields such as ``blocks[2].crc32``."""
    keys: set[int] = set()
    for item in damage:
        match = _REGION_ONLY.search(str(item.get("field", "")))
        if match:
            keys.add(int(match.group(1)))
    return keys


def _record_counts(records: list[Any], damage: list[dict[str, Any]], status: str) -> dict[str, int]:
    """Count recovered/damaged/lost per record, not per file.

    A record is damaged when the plugin flagged it incomplete, or a damage entry
    names its index. Damage that names no record (header, trailing bytes) does
    not taint other records; with a single record it is attributed to that
    record. A file being ``partial`` never makes intact records damaged.
    """
    if not records:
        lost = 1 if status in ("partial", "damaged") else 0
        return {"records_recovered": 0, "records_damaged": 0, "records_lost": lost}
    named = _damaged_record_keys(damage)
    damaged = 0
    for position, record in enumerate(records):
        key = position
        flagged = False
        if isinstance(record, dict):
            raw_key = record.get("index", record.get("record_index", position))
            key = raw_key if isinstance(raw_key, int) else position
            flagged = record.get("complete") is False
        if flagged or key in named or (len(records) == 1 and damage):
            damaged += 1
    return {"records_recovered": len(records) - damaged, "records_damaged": damaged,
            "records_lost": 0}


def _selected_confidence(identification: list[dict[str, Any]] | None) -> float:
    for candidate in identification or []:
        if candidate.get("selected"):
            try:
                return round(float(candidate.get("confidence", 0.0)), 4)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def shape_result(file_name: str, decoded: Any, *, fallback_format: str = "UNKNOWN",
                 identification: list[dict[str, Any]] | None = None,
                 debug: bool = False) -> dict[str, Any]:
    """Convert a plugin Result to the slim per-file JSON schema.

    The default output carries only what was recovered, what was lost, and the
    selected format with its confidence. Rejected candidates and full analysis
    detail appear only when ``debug`` is true.
    """
    damage = [_damage_dict(item) for item in list(getattr(decoded, "damage", []) or [])]
    records = list(getattr(decoded, "records", []) or [])
    data = getattr(decoded, "data", None)
    status = _status(getattr(decoded, "status", "unsupported"))
    if damage and status == "recovered":
        status = "damaged"
    if isinstance(data, dict):
        # Keys starting with "_" are debug-only detail from a plugin.
        extra = {key: value for key, value in data.items() if str(key).startswith("_")}
        data = {key: value for key, value in data.items() if not str(key).startswith("_")}
        # A data key that just repeats the top-level records list adds nothing.
        data = {key: value for key, value in data.items()
                if not (records and isinstance(value, list) and value == records)}
        if debug and extra:
            data["debug"] = {str(key).lstrip("_"): value for key, value in extra.items()}
    result = {
        "file_name": str(file_name),
        "format": str(getattr(decoded, "format", "") or fallback_format),
        "confidence": _selected_confidence(identification),
        "status": status,
        "data": data,
        "records": records,
        "counts": _record_counts(records, damage, status),
        "damage": damage,
        "errors": [str(item) for item in (getattr(decoded, "errors", []) or [])],
    }
    if debug and identification is not None:
        # Candidate dictionaries may carry a live plugin reference for internal
        # dispatch. Never leak that object into JSON output.
        result["identification"] = [
            {key: value for key, value in candidate.items() if key != "plugin"}
            for candidate in identification
        ]
    return result


def shape_failure(file_name: str, format_name: str, message: str, *, field: str = "file") -> dict[str, Any]:
    damage = _damage_dict({"field": field, "offset": 0, "expected": 0, "found": 0,
                           "reason": message, "byte_range": {"start": 0, "end": 0}})
    return {
        "file_name": str(file_name), "format": str(format_name), "confidence": 0.0,
        "status": "error", "data": None, "records": [],
        "counts": {"records_recovered": 0, "records_damaged": 0, "records_lost": 0},
        "damage": [damage], "errors": [str(message)],
    }


def shape_failure_entry(path: str, stage: str, error: BaseException | str) -> dict[str, Any]:
    detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    return {"path": str(path), "status": "error", "stage": stage, "error": detail}


def shape_report(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Batch summary: one short entry per file, no repeated per-file results."""
    failures = sorted(list(failures or []), key=lambda f: (str(f.get("path", "")), str(f.get("stage", "")), str(f.get("error", ""))))
    results = sorted(results, key=lambda r: str(r.get("file_name", "")))
    counts = Counter(item.get("status", "error") for item in results)
    empty = {"records_recovered": 0, "records_damaged": 0, "records_lost": 0}

    def total(key: str) -> int:
        return sum(item.get("counts", {}).get(key, 0) for item in results)

    return {
        "tool": "SALVAGE",
        "files_processed": len(results),
        "status_counts": {key: counts.get(key, 0) for key in STATUS_VOCABULARY},
        "records_recovered": total("records_recovered"),
        "records_damaged": total("records_damaged"),
        "records_lost": total("records_lost"),
        "failures": failures,
        "files": [
            {
                "file_name": item.get("file_name", ""),
                "format": item.get("format", "UNKNOWN"),
                "confidence": item.get("confidence", _selected_confidence(item.get("identification"))),
                "status": item.get("status", "error"),
                "counts": item.get("counts", dict(empty)),
                "byte_ranges": [d["byte_range"] for d in item.get("damage", []) if "byte_range" in d],
                "warnings": [str(d.get("reason", "")) for d in item.get("damage", [])]
                            + [str(e) for e in item.get("errors", [])],
            }
            for item in results
        ],
    }
