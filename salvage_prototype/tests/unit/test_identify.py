import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from salvage.identify import identify
from salvage.pipeline import inspect_bytes
from salvage.formats.base import FormatPlugin, Result
from salvage.formats.generic import GenericPlugin
from salvage.formats.registry import PluginRegistry, default_registry
from salvage.formats.stud import STUDPlugin


class FormatA(FormatPlugin):
    name = "FORMAT_A"
    signature = b"ABCD"
    header_length = 6

    def detect(self, data):
        return 0.8 if data.startswith(self.signature) else 0.0

    def plausible_fields(self, data):
        return {"valid": len(data) >= 6 and data[4] == 1,
                "detail": "version byte must be 1"}

    def decode(self, data):
        return Result(format=self.name)


class FormatB(FormatPlugin):
    name = "FORMAT_B"
    signature = b"ABCD"
    header_length = 8

    def detect(self, data):
        return 0.75 if data.startswith(self.signature) else 0.0

    def plausible_fields(self, data):
        return {"valid": len(data) >= 8 and data[4] == 2,
                "detail": "version byte must be 2"}

    def decode(self, data):
        return Result(format=self.name)


class ChecksumPlugin(FormatPlugin):
    name = "CHECKSUMMED"
    signature = b"SUM!"
    header_length = 4

    def detect(self, data):
        return 0.6 if data.startswith(self.signature) else 0.0

    def checksum_valid(self, data):
        return len(data) >= 5 and sum(data[:-1]) % 256 == data[-1]

    def decode(self, data):
        return Result(format=self.name)


class IdentifyTests(unittest.TestCase):
    def test_returns_ranked_candidates_with_evidence(self):
        candidates = identify(b"STUD\x01\x03Ana", default_registry())
        self.assertEqual(candidates[0]["name"], "STUD")
        self.assertGreaterEqual(candidates[0]["confidence"], 0.55)
        self.assertTrue(any(item["clue"] == "signature_at_start"
                            for item in candidates[0]["evidence"]))
        self.assertTrue(any(item["clue"] == "plausible_fields"
                            for item in candidates[0]["evidence"]))

    def test_nearly_matching_formats_are_ranked_by_structure(self):
        registry = PluginRegistry([FormatB(), FormatA(), GenericPlugin()])
        candidates = identify(b"ABCD\x01\x03xy", registry)
        self.assertEqual(candidates[0]["name"], "FORMAT_A")
        self.assertTrue(candidates[0]["selected"])
        format_b = next(item for item in candidates if item["name"] == "FORMAT_B")
        self.assertTrue(any(item["contradiction"] for item in format_b["evidence"]))

    def test_signature_coincidence_at_nonzero_offset_falls_back(self):
        # The signature exists, but only as an embedded byte sequence and the
        # bytes at the candidate header positions are not structurally plausible.
        registry = PluginRegistry([FormatA(), GenericPlugin()])
        candidates = identify(b"noiseABCD\x00\x00trailing", registry)
        format_a = next(item for item in candidates if item["name"] == "FORMAT_A")
        self.assertFalse(format_a["selected"])
        selected = next(item for item in candidates if item["selected"])
        self.assertEqual(selected["name"], "UNKNOWN")
        self.assertTrue(any(item["clue"] == "signature_at_offset"
                            for item in format_a["evidence"]))

    def test_checksum_validity_changes_rank(self):
        plugin = ChecksumPlugin()
        valid = b"SUM!\x01"  # 83 + 85 + 77 + 33 == 278; remainder 22, not 1
        valid = b"SUM!" + bytes([sum(b"SUM!") % 256])
        candidates = identify(valid, PluginRegistry([plugin, GenericPlugin()]))
        candidate = next(item for item in candidates if item["name"] == "CHECKSUMMED")
        self.assertTrue(any(item["clue"] == "checksum" and item["matched"] is True
                            for item in candidate["evidence"]))
        invalid_candidates = identify(b"SUM!\x00", PluginRegistry([plugin, GenericPlugin()]))
        invalid = next(item for item in invalid_candidates if item["name"] == "CHECKSUMMED")
        self.assertTrue(any(item["clue"] == "checksum" and item["matched"] is False
                            for item in invalid["evidence"]))
        self.assertLess(invalid["confidence"], candidate["confidence"])


    def test_pipeline_exposes_serializable_candidate_evidence(self):
        result = inspect_bytes("sample.bin", b"STUD\x01\x03Ana")
        self.assertIn("identification", result)
        self.assertEqual(result["identification"][0]["name"], "STUD")
        self.assertTrue(result["identification"][0]["selected"])
        self.assertTrue(all("plugin" not in candidate for candidate in result["identification"]))

    def test_signature_by_coincidence_does_not_select_stud(self):
        data = b"junkSTUD\x00\x00random"
        candidates = identify(data, default_registry())
        self.assertFalse(next(item for item in candidates if item["name"] == "STUD")["selected"])
        self.assertEqual(default_registry().select(data).name, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
