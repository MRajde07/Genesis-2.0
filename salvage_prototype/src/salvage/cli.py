"""Command-line interface. The command always exits with status zero."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .output import write_json
from .pipeline import inspect_file
from .report import build_report


def _failure(path: Path | str, stage: str, error: BaseException | str) -> dict[str, Any]:
    detail = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    return {"path": str(path), "status": "error", "stage": stage, "error": detail}


def main(argv: list[str] | None = None, *, registry=None) -> int:
    parser = argparse.ArgumentParser(description="SALVAGE - Offline binary recovery toolkit")
    parser.add_argument("input_dir", help="Folder containing input files")
    parser.add_argument("output_dir", help="Folder for JSON output")
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    output_dir: Path | None = None
    try:
        try:
            args = parser.parse_args(argv)
            input_dir, output_dir = Path(args.input_dir), Path(args.output_dir)
        except BaseException as error:
            # argparse normally raises SystemExit for malformed CLI arguments.
            print(f"SALVAGE: invalid invocation: {type(error).__name__}: {error}")
            return 0

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as error:
            failures.append(_failure(output_dir, "create_output_dir", error))
            print(f"SALVAGE: could not create output directory: {error}")
            return 0

        if not input_dir.is_dir():
            error = "input directory does not exist or is not a directory"
            failures.append(_failure(input_dir, "validate_input_dir", error))
            print(f"SALVAGE: {error}: {input_dir}")
        else:
            try:
                entries = sorted(input_dir.iterdir(), key=lambda p: p.name)
            except Exception as error:
                failures.append(_failure(input_dir, "list_input_dir", error))
                entries = []

            for entry in entries:
                try:
                    is_file = entry.is_file()
                except Exception as error:
                    failures.append(_failure(entry, "inspect_entry", error))
                    continue
                if not is_file:
                    failures.append(_failure(entry, "inspect_entry", "entry is not a regular file (subdirectories are not traversed)"))
                    continue
                try:
                    result = inspect_file(entry, registry)
                    if not isinstance(result, dict):
                        raise TypeError("file processor did not return a result object")
                except Exception as error:
                    result = {
                        "file_name": entry.name,
                        "format": "UNKNOWN",
                        "status": "error",
                        "data": None,
                        "errors": [f"Unexpected file processing failure: {type(error).__name__}: {error}"],
                    }
                    failures.append(_failure(entry, "process_file", error))
                if result.get("status") == "error" and not any(
                    item.get("path") == str(entry) and item.get("stage") == "process_file"
                    for item in failures
                ):
                    failures.append(_failure(entry, "process_file", "; ".join(result.get("errors", [])) or "processing failed"))
                results.append(result)
                try:
                    write_json(output_dir / f"{entry.name}.json", result)
                except Exception as error:
                    message = f"Could not write result: {type(error).__name__}: {error}"
                    result.setdefault("errors", []).append(message)
                    failures.append(_failure(entry, "write_result", error))
                print(f"{entry.name}: {result.get('status', 'error')}")

        # Include per-file failures in the report's results as well as its
        # dedicated failures list, so a report consumer cannot miss them.
        report = build_report(results, failures)
        try:
            write_json(output_dir / "report.json", report)
        except Exception as error:
            print(f"SALVAGE: could not write report: {type(error).__name__}: {error}")
        print(f"\nDone! Processed {len(results)} file(s); recorded {len(failures)} failure(s).")
    except BaseException as error:
        # Final guard to honor the CLI's zero-exit contract even for unexpected
        # run-level failures (including exceptions outside normal processing).
        print(f"SALVAGE: unexpected failure: {type(error).__name__}: {error}")
        if output_dir is not None:
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                failures.append(_failure(output_dir, "run", error))
                write_json(output_dir / "report.json", build_report(results, failures))
            except BaseException as report_error:
                print(f"SALVAGE: could not write failure report: {type(report_error).__name__}: {report_error}")
    return 0
