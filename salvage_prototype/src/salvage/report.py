"""Batch report construction."""
from collections import Counter
from typing import Any


def build_report(results: list[dict[str, Any]], failures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    failures = list(failures or [])
    counts = Counter(item.get("status", "error") for item in results)
    keys = ("success", "partially_recovered", "damaged", "unsupported", "error")
    return {
        "tool": "SALVAGE",
        "files_processed": len(results),
        "status_counts": {key: counts.get(key, 0) for key in keys},
        "output_errors": [],
        "failures": failures,
        "results": results,
    }
