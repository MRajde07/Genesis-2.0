"""Run against real .WKS samples when supplied by the user; skip when absent."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from salvage.formats.real.lotus_wks import LotusWKSPlugin
from salvage.pipeline import inspect_bytes

SAMPLE_DIR = ROOT / "samples"
SAMPLES = sorted(p for p in SAMPLE_DIR.rglob("*") if p.is_file() and p.suffix.lower() == ".wks") if SAMPLE_DIR.exists() else []


@unittest.skipUnless(SAMPLES, "No real .WKS samples present under samples/; add files to enable this integration test")
class RealLotusWKSSampleTests(unittest.TestCase):
    def test_real_samples_parse_without_crashing_and_report_uncertainty(self):
        plugin = LotusWKSPlugin()
        for path in SAMPLES:
            with self.subTest(sample=str(path.relative_to(ROOT))):
                data = path.read_bytes()
                self.assertGreater(plugin.detect(data), 0.5, "sample is not recognized as Lotus 1-2-3 Release 1A WKS")
                decoded = plugin.decode(data)
                self.assertIn(decoded.status, {"recovered", "partial", "damaged"})
                self.assertIsInstance(decoded.data, dict)
                shaped = inspect_bytes(path.name, data)
                self.assertIn(shaped["status"], {"ok", "partial", "failed"})
                self.assertIsInstance(shaped["damage"], list)
                self.assertIsInstance(shaped["errors"], list)


if __name__ == "__main__":
    unittest.main()
