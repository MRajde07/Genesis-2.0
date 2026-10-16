import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))
from salvage.formats.stud import STUDPlugin
from salvage.output import shape_result


class OutputShapeTests(unittest.TestCase):
    def test_stud_incomplete_name_has_structured_damage_and_counts(self):
        decoded = STUDPlugin().decode(b"STUD\x01\x05Al")
        shaped = shape_result("student.bin", decoded, fallback_format="STUD")
        self.assertEqual(shaped["status"], "partial")
        self.assertEqual(shaped["counts"], {
            "records_recovered": 0, "records_damaged": 1, "records_lost": 0
        })
        damage = shaped["damage"][0]
        self.assertTrue({"kind", "offset", "detail", "lossy", "field", "expected", "found", "reason", "byte_range"}.issubset(damage))
        self.assertEqual(damage["byte_range"], {"start": 8, "end": 11})

    def test_invalid_utf8_keeps_raw_hex_without_replacement_character(self):
        # One invalid UTF-8 byte, with a complete name field.
        decoded = STUDPlugin().decode(b"STUD\x01\x01\xff")
        shaped = shape_result("bad-name.bin", decoded, fallback_format="STUD")
        self.assertEqual(shaped["status"], "partial")
        self.assertIsNone(shaped["metadata"]["name"])
        self.assertEqual(shaped["metadata"]["name_raw_hex"], "ff")
        self.assertNotIn("\ufffd", repr(shaped["metadata"]))
        self.assertEqual(shaped["damage"][0]["byte_range"], {"start": 6, "end": 7})
        self.assertEqual(shaped["counts"]["records_damaged"], 1)
        self.assertEqual(shaped["counts"]["records_recovered"], 0)

    def test_complete_stud_has_recovered_status_and_zero_damage(self):
        shaped = shape_result("ok.bin", STUDPlugin().decode(b"STUD\x01\x03Anu"), fallback_format="STUD")
        self.assertEqual(shaped["status"], "ok")
        self.assertEqual(shaped["counts"]["records_recovered"], 1)
        self.assertEqual(shaped["counts"]["records_damaged"], 0)
        self.assertEqual(shaped["counts"]["records_lost"], 0)
        self.assertEqual(shaped["damage"], [])


if __name__ == "__main__":
    unittest.main()
