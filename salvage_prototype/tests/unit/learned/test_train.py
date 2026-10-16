from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.train import infer_spec, load_pair


class TrainerTests(unittest.TestCase):
    def test_trainer_infers_unambiguous_scalar_fields_and_checks_holdout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pairs = []
            for index, (number, text) in enumerate(((101, "ALFA"), (309, "BETA"), (517, "GAMM"))):
                binary = root / f"sample{index}.bin"
                binary.write_bytes(b"DEMO" + number.to_bytes(2, "big") + text.encode("ascii"))
                truth = {"format": "DEMO", "expected": {"number": number, "label": text}}
                Path(str(binary) + ".expected.json").write_text(json.dumps(truth), encoding="utf-8")
                data, expected, fmt = load_pair(binary)
                pairs.append((binary, data, expected, fmt))
            spec = infer_spec(pairs)
            self.assertEqual(spec["signature_hex"], "44454d4f")
            self.assertEqual({field["name"] for field in spec["fields"]}, {"number", "label"})

    def test_trainer_refuses_insufficient_samples(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            infer_spec([])

    def test_trainer_refuses_ambiguous_layout(self):
        pairs = []
        for index, value in enumerate((1, 2, 3)):
            data = b"DEMO" + bytes([value, value])
            pairs.append((Path(f"s{index}.bin"), data, {"value": value}, "DEMO"))
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            infer_spec(pairs)


if __name__ == "__main__":
    unittest.main()
