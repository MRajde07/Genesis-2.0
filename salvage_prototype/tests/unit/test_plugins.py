import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))
from salvage.formats.base import FormatPlugin, Result
from salvage.formats.generic import GenericPlugin
from salvage.formats.registry import PluginRegistry, default_registry
from salvage.formats.stud import STUDPlugin


class PluginTests(unittest.TestCase):
    def test_default_registry_selects_stud(self):
        self.assertIsInstance(default_registry().select(b"STUD\x01\x03Anu"), STUDPlugin)

    def test_default_registry_falls_back(self):
        self.assertIsInstance(default_registry().select(b"not a known format"), GenericPlugin)

    def test_confidence_out_of_range_is_ignored(self):
        class BadPlugin(FormatPlugin):
            name = "BAD"
            def detect(self, data): return 5.0
            def decode(self, data): return Result(format="BAD")
        registry = PluginRegistry([BadPlugin(), GenericPlugin()])
        self.assertIsInstance(registry.select(b"x"), GenericPlugin)

    def test_stud_damage_has_byte_range(self):
        result = STUDPlugin().decode(b"STUD\x01\x05Al")
        self.assertEqual(result.status, "partially_recovered")
        self.assertEqual(result.damage[0].start, 8)
        self.assertEqual(result.damage[0].end, 11)


if __name__ == "__main__":
    unittest.main()
