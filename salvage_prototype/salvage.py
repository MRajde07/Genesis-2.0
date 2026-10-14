
import argparse
import json
from pathlib import Path


def inspect_file(file_path):
    """Identify and recover data from the demo STUD format."""
    data = file_path.read_bytes()

    result = {
        "file_name": file_path.name,
        "format": "UNKNOWN",
        "status": "unsupported",
        "data": None,
        "errors": [],
    }

    # Identify the demo format using its four-byte signature.
    if not data.startswith(b"STUD"):
        result["errors"].append("Unrecognized file signature")
        return result

    result["format"] = "STUD"

    # Header: 4-byte signature, 1-byte version, 1-byte name length.
    if len(data) < 6:
        result["status"] = "damaged"
        result["errors"].append("File is too short to contain its header")
        return result

    version = data[4]
    name_length = data[5]
    available_bytes = len(data) - 6

    actual_length = min(name_length, available_bytes)
    name_bytes = data[6:6 + actual_length]

    result["data"] = {
        "version": version,
        "name": name_bytes.decode("utf-8", errors="replace"),
    }

    if name_length > available_bytes:
        result["status"] = "partially_recovered"
        result["errors"].append(
            f"Name was truncated: expected {name_length} bytes, "
            f"found {available_bytes}"
        )
    else:
        result["status"] = "success"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="SALVAGE - Offline binary recovery prototype"
    )
    parser.add_argument("input_dir", help="Folder containing input files")
    parser.add_argument("output_dir", help="Folder for JSON output")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        parser.error(f"Input directory does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "tool": "SALVAGE",
        "files_processed": 0,
        "status_counts": {
            "success": 0,
            "partially_recovered": 0,
            "damaged": 0,
            "unsupported": 0,
            "error": 0,
        },
        "output_errors": [],
        "results": [],
    }

    for file_path in sorted(input_dir.iterdir()):
        if not file_path.is_file():
            continue

        try:
            result = inspect_file(file_path)
        except (OSError, ValueError) as error:
            result = {
                "file_name": file_path.name,
                "format": "UNKNOWN",
                "status": "error",
                "data": None,
                "errors": [str(error)],
            }

        output_file = output_dir / f"{file_path.name}.json"
        output_file.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        report["files_processed"] += 1
        status = result["status"]
        report["status_counts"][status] += 1
        report["results"].append(result)

        print(f"{file_path.name}: {result['status']}")

    report_file = output_dir / "report.json"
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"\nDone! Processed {report['files_processed']} file(s).")
    print(f"Report saved to: {report_file.resolve()}")


if __name__ == "__main__":
    main()
