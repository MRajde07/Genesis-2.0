"""Synthetic tests for the conservative Lotus 1-2-3 Release 1A WKS reader."""
from __future__ import annotations
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from salvage.formats.real.lotus_wks import LotusWKSPlugin, BOF_SIGNATURE
from salvage.formats.registry import default_registry
from salvage.pipeline import inspect_bytes


def record(opcode: int, body: bytes = b"") -> bytes:
    return opcode.to_bytes(2, "little") + len(body).to_bytes(2, "little") + body


def cell_prefix(column: int = 0, row: int = 0, fmt: int = 0) -> bytes:
    return bytes([fmt]) + column.to_bytes(2, "little") + row.to_bytes(2, "little")


def wks(*records: bytes) -> bytes:
    return BOF_SIGNATURE + b"".join(records) if records and records[0].startswith(b"\x00\x00\x02\x00") else BOF_SIGNATURE + b"".join(records)


class LotusWKSTests(unittest.TestCase):
    def setUp(self):
        self.plugin = LotusWKSPlugin()

    def test_detects_release_1a_not_arbitrary_zero_prefix(self):
        self.assertGreaterEqual(self.plugin.detect(BOF_SIGNATURE), 0.9)
        self.assertEqual(self.plugin.detect(b"ordinary data"), 0.0)
        self.assertEqual(default_registry().select(BOF_SIGNATURE).name, "LOTUS_WKS")

    def test_integer_number_and_label_cells(self):
        data = BOF_SIGNATURE + b"".join([
            record(0x000D, cell_prefix(1, 2, 0) + (-17).to_bytes(2, "little", signed=True)),
            record(0x000E, cell_prefix(2, 3, 0) + struct.pack("<d", 12.5)),
            record(0x000F, cell_prefix(3, 4, 0) + b"'Hello\x00"),
            record(0x0001),
        ])
        result = self.plugin.decode(data)
        self.assertEqual(result.status, "recovered")
        self.assertEqual([c["record_type"] for c in result.data["cells"]], ["INTEGER", "NUMBER", "LABEL"])
        self.assertEqual(result.data["cells"][0]["value"], -17)
        self.assertEqual(result.data["cells"][1]["value"], 12.5)
        self.assertEqual(result.data["cells"][2]["value"], "Hello")
        self.assertEqual(result.data["cells"][2]["alignment"], "left")
        self.assertTrue(result.data["eof_seen"])

    def test_formula_tokens_are_preserved_not_evaluated(self):
        tokens = b"\x01\xA7\x00"
        body = cell_prefix(0, 0) + struct.pack("<d", 7.0) + len(tokens).to_bytes(2, "little") + tokens
        result = self.plugin.decode(BOF_SIGNATURE + record(0x0010, body) + record(0x0001))
        cell = result.data["cells"][0]
        self.assertEqual(cell["cached_value"], 7.0)
        self.assertEqual(cell["formula_raw"]["text"], tokens.hex())
        self.assertIsNone(cell["formula_text"])
        self.assertFalse(cell["formula_evaluated"])

    def test_truncated_cell_and_missing_eof_report_damage_ranges(self):
        truncated = record(0x000E, cell_prefix(0, 0) + b"\x00\x01")
        result = self.plugin.decode(BOF_SIGNATURE + truncated)
        self.assertIn(result.status, ("partial", "damaged"))
        reasons = [d.reason for d in result.damage]
        self.assertTrue(any("truncated" in reason for reason in reasons))
        self.assertTrue(any("EOF record not found" in reason for reason in reasons))
        self.assertTrue(all(d.byte_range is not None for d in result.damage))

    def test_unknown_record_preserves_raw_payload_and_flags_uncertainty(self):
        payload = b"\xde\xad\xbe\xef"
        result = self.plugin.decode(BOF_SIGNATURE + record(0x0077, payload) + record(0x0001))
        unknown = result.data["unrecognized_records"][0]
        self.assertEqual(unknown["raw_body_hex"], payload.hex())
        self.assertFalse(unknown["verified"])
        self.assertEqual(result.status, "partial")
        self.assertTrue(result.errors)

    def test_invalid_or_unrecognized_input_does_not_claim_wks(self):
        result = self.plugin.decode(b"not a WKS file")
        self.assertEqual(result.status, "unsupported")
        shaped = inspect_bytes("unknown.bin", b"not a WKS file")
        self.assertNotEqual(shaped["format"], "LOTUS_WKS")


if __name__ == "__main__":
    unittest.main()
