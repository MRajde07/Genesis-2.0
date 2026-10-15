"""Slim default output: no rejected formats, no analysis noise, per-record counts."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from salvage.output import shape_report, validate_schema, load_schema
from salvage.pipeline import inspect_bytes


def wks_with_housekeeping(extra_truncate=0):
    bof = b"\x00\x00\x02\x00\x04\x04"
    housekeeping = b"\x03\x00\x01\x00\x00"          # opcode 3, one body byte
    cell = b"\x0d\x00\x07\x00\xff\x00\x00\x00\x00\x01\x00"  # INTEGER, col0 row0 value 1
    eof = b"\x01\x00\x00\x00"
    data = bof + housekeeping + cell + eof
    return data[: len(data) - extra_truncate] if extra_truncate else data


class SlimOutputTests(unittest.TestCase):
    def test_default_result_has_no_rejected_formats_or_byte_ranges(self):
        result = inspect_bytes("a.bin", b"STUD\x01\x03Ana")
        self.assertNotIn("identification", result)
        self.assertNotIn("byte_ranges", result)
        self.assertEqual(result["confidence"], 1.0)
        validate_schema(result, load_schema("result.schema.json"))

    def test_unknown_file_gets_short_summary(self):
        data = bytes(range(256)) * 16
        result = inspect_bytes("blob.bin", data)
        self.assertEqual(result["format"], "UNKNOWN")
        self.assertNotIn("integer_candidates", result["data"])
        self.assertNotIn("_full_analysis", result["data"])
        self.assertLess(len(json.dumps(result)), 3000)
        debug = inspect_bytes("blob.bin", data, debug=True)
        self.assertIn("integer_candidates", debug["data"]["debug"]["full_analysis"])
        self.assertIn("identification", debug)

    def test_empty_file_is_minimal(self):
        result = inspect_bytes("empty.bin", b"")
        self.assertEqual(result["data"]["content_guess"], "empty")
        self.assertLess(len(json.dumps(result)), 1500)

    def test_report_has_no_duplicated_results(self):
        results = [inspect_bytes("a.bin", b"STUD\x01\x03Ana"), inspect_bytes("b.bin", b"zzzzzz")]
        report = shape_report(results)
        self.assertNotIn("results", report)
        self.assertEqual([f["file_name"] for f in report["files"]], ["a.bin", "b.bin"])
        validate_schema(report, load_schema("report.schema.json"))

    def test_partial_file_does_not_make_intact_records_damaged(self):
        # Housekeeping opcode 3 is not interpreted, but nothing is damaged.
        result = inspect_bytes("ok.wks", wks_with_housekeeping())
        self.assertEqual(result["damage"], [])
        self.assertEqual(result["counts"]["records_damaged"], 0)
        self.assertEqual(result["counts"]["records_recovered"], len(result["records"]))

    def test_truncation_damages_only_the_cut_record(self):
        result = inspect_bytes("cut.wks", wks_with_housekeeping(extra_truncate=6))
        counts = result["counts"]
        self.assertGreaterEqual(counts["records_damaged"], 1)
        self.assertLess(counts["records_damaged"], len(result["records"]) + 1)
        self.assertEqual(counts["records_recovered"] + counts["records_damaged"], len(result["records"]))


if __name__ == "__main__":
    unittest.main()
