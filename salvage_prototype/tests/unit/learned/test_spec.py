from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from salvage.learned import PluginSpec, SpecPlugin, load_specs
from salvage.formats.registry import default_registry


class LearnedSpecTests(unittest.TestCase):
    def test_builtin_specs_load_and_register(self):
        plugins = load_specs()
        self.assertEqual({plugin.name for plugin in plugins}, {"LEARNED_STUD", "LEARNED_ASTER"})
        names = {plugin.name for plugin in default_registry().plugins}
        self.assertTrue({"LEARNED_STUD", "LEARNED_ASTER"}.issubset(names))

    def test_stud_spec_decodes_header_and_string(self):
        plugin = next(p for p in load_specs() if p.name == "LEARNED_STUD")
        result = plugin.decode(b"STUD\x01\x03Anu")
        self.assertEqual(result.data["version"], 1)
        self.assertEqual(result.data["name"], "Anu")
        self.assertEqual(result.status, "recovered")

    def test_aster_spec_decodes_fixed_stride_without_using_nominal_span(self):
        plugin = next(p for p in load_specs() if p.name == "LEARNED_ASTER")
        record = (7).to_bytes(2, "big") + b"\x01" + b"\xff\xff" + (4).to_bytes(2, "big") + (3).to_bytes(2, "big", signed=True) + b"ABC"
        data = b"ARCF" + (1).to_bytes(2, "big") + (1).to_bytes(2, "big") + record
        result = plugin.decode(data)
        self.assertEqual(result.data["records"][0]["nominal_span"], 65535)
        self.assertEqual(result.data["records"][0]["item_id"], 7)

    def test_declared_checksum_is_checked_without_repair(self):
        import zlib
        spec = PluginSpec.from_dict({
            "name": "CHECKED", "signature_hex": "414243", "minimum_length": 7,
            "endianness": "little", "fields": [
                {"name": "tag", "type": "fixed_string", "length": 3, "offset": 0}
            ], "blocks": [{"name": "body", "offset": 0, "length": 7,
                            "checksum_offset": 3, "checksum_type": "crc32", "checksum_length": 4,
                            "checksum_endianness": "little"}]
        })
        plugin = SpecPlugin(spec)
        good = b"ABC" + (zlib.crc32(b"ABC") & 0xffffffff).to_bytes(4, "little")
        self.assertTrue(plugin.checksum_valid(good))
        damaged = bytearray(good)
        damaged[0] ^= 1
        self.assertFalse(plugin.checksum_valid(bytes(damaged)))
        self.assertEqual(damaged[0], good[0] ^ 1)

    def test_bad_spec_is_rejected(self):
        with self.assertRaises(ValueError):
            PluginSpec.from_dict({"name": "X", "surprise": True})
        with self.assertRaises(ValueError):
            PluginSpec.from_dict({"name": "X", "endianness": "middle"})

    def test_interpreter_handles_truncation_without_raising(self):
        plugin = next(p for p in load_specs() if p.name == "LEARNED_ASTER")
        result = plugin.decode(b"ARCF\x00\x01\x00\x02\x00")
        self.assertIn(result.status, {"partial", "damaged"})
        self.assertTrue(result.damage)


if __name__ == "__main__":
    unittest.main()
