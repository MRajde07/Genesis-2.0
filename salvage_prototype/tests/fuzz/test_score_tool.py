from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.score import score, print_table


class ScoreToolTests(unittest.TestCase):
    def test_field_accuracy_and_format_precision_recall(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            truth = root / "truth"
            results = root / "results"
            truth.mkdir(); results.mkdir()
            (truth / "a.bin.truth.json").write_text(json.dumps({
                "format": "ASTER", "expected": {"value": 10, "stable": "yes"}}), encoding="utf-8")
            (truth / "b.bin.truth.json").write_text(json.dumps({
                "format": "XIDX", "expected": {"value": 20}}), encoding="utf-8")
            (results / "a.bin.json").write_text(json.dumps({
                "format": "ASTER", "status": "recovered", "data": {"value": 10, "stable": "yes"}}), encoding="utf-8")
            (results / "b.bin.json").write_text(json.dumps({
                "format": "UNKNOWN", "status": "unsupported", "data": {"value": None}}), encoding="utf-8")
            result = score(truth, results)
            self.assertEqual(result["fields_correct"], 2)
            self.assertEqual(result["fields_total"], 3)
            self.assertAlmostEqual(result["field_accuracy"], 2 / 3)
            self.assertAlmostEqual(result["format_precision"], 0.5)
            self.assertAlmostEqual(result["format_recall"], 0.5)
            print_table(result)


if __name__ == "__main__":
    unittest.main()
