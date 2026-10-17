"""Golden tests for the three invented, seeded real-format fixtures."""
from __future__ import annotations
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from salvage.formats.real import AsterRecordsPlugin, CRCBlocksPlugin, XIDXPlugin
from salvage.formats.registry import default_registry
from salvage.identify import select_plugin
from salvage.pipeline import inspect_bytes
from tools.gen_samples import generate


class RealFormatGoldenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        generate(self.directory, seed=8675309)

    def tearDown(self):
        self.temp.cleanup()

    def test_each_plugin_matches_adjacent_ground_truth(self):
        cases = [
            ("aster_records.bin", AsterRecordsPlugin()),
            ("crc_blocks.bin", CRCBlocksPlugin()),
            ("xidx_archive.bin", XIDXPlugin()),
        ]
        for filename, plugin in cases:
            with self.subTest(filename=filename):
                data = (self.directory / filename).read_bytes()
                truth = json.loads((self.directory / (filename + ".truth.json")).read_text(encoding="utf-8"))
                result = plugin.decode(data)
                self.assertEqual(result.format, truth["format"])
                self.assertEqual(result.status, "recovered")
                self.assertEqual(result.damage, [])
                # "_"-prefixed keys (e.g. "_spans" for the byte map) are internal, not part of the schema
                public = {k: v for k, v in result.data.items() if not str(k).startswith("_")}
                self.assertEqual(public, truth["expected"])

    def test_registry_identifies_and_pipeline_decodes_all_three(self):
        expected = {"aster_records.bin": "ASTER", "crc_blocks.bin": "CRC_BLOCKS", "xidx_archive.bin": "XIDX"}
        registry = default_registry()
        for filename, format_name in expected.items():
            with self.subTest(filename=filename):
                data = (self.directory / filename).read_bytes()
                self.assertEqual(select_plugin(data, registry).name, format_name)
                shaped = inspect_bytes(filename, data, registry)
                self.assertEqual(shaped["format"], format_name)
                self.assertEqual(shaped["status"], "recovered")

    def test_aster_nominal_span_is_not_used_as_a_length(self):
        path = self.directory / "aster_records.bin"
        data = bytearray(path.read_bytes())
        # First record's nominal_span is bytes 11..12 in the file. Change it to
        # 0xFFFF; the decoder must still step by the fixed 12-byte record size.
        data[11:13] = b"\xff\xff"
        result = AsterRecordsPlugin().decode(bytes(data))
        self.assertEqual(len(result.data["records"]), 3)
        self.assertEqual(result.data["records"][0]["nominal_span"], 65535)
        self.assertEqual(result.data["records"][1]["item_id"], int.from_bytes(data[20:22], "big"))
        self.assertEqual(result.status, "recovered")

    def test_crc_block_corruption_is_reported_not_repaired(self):
        data = bytearray((self.directory / "crc_blocks.bin").read_bytes())
        # First payload starts after 7-byte header + 2-byte block length.
        data[9] ^= 0x01
        result = CRCBlocksPlugin().decode(bytes(data))
        self.assertEqual(result.data["blocks"][0]["crc32_valid"], False)
        self.assertTrue(any("CRC32 mismatch" in damage.reason for damage in result.damage))
        self.assertEqual(result.status, "partial")
        self.assertEqual(data[9], (self.directory / "crc_blocks.bin").read_bytes()[9] ^ 1)

    def test_seeded_generation_is_byte_deterministic(self):
        second = self.directory / "second"
        generate(second, seed=8675309)
        names = ["aster_records.bin", "crc_blocks.bin", "xidx_archive.bin"]
        for name in names:
            self.assertEqual((self.directory / name).read_bytes(), (second / name).read_bytes())
            self.assertEqual((self.directory / (name + ".truth.json")).read_bytes(),
                             (second / (name + ".truth.json")).read_bytes())


if __name__ == "__main__":
    unittest.main()
