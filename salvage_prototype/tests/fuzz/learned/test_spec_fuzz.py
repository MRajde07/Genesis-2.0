from __future__ import annotations
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from salvage.learned import load_specs
from salvage.formats.real import AsterRecordsPlugin
from tools.gen_samples import generate


class LearnedSpecFuzzTests(unittest.TestCase):
    def test_seeded_mutations_never_raise_and_are_deterministic(self):
        plugins = load_specs()
        rng = random.Random(4921)
        with __import__("tempfile").TemporaryDirectory() as temp:
            generate(Path(temp), seed=4921)
            data = (Path(temp) / "aster_records.bin").read_bytes()
        cases = [data, data[:4], data[:9], b"", data + b"trailing"]
        for _ in range(80):
            mutant = bytearray(data)
            pos = rng.randrange(len(mutant))
            mutant[pos] ^= 1 << rng.randrange(8)
            if rng.random() < 0.25:
                del mutant[rng.randrange(len(mutant)):]
            cases.append(bytes(mutant))
        for payload in cases:
            for plugin in plugins:
                with self.subTest(plugin=plugin.name, length=len(payload)):
                    first = plugin.decode(payload)
                    second = plugin.decode(payload)
                    self.assertEqual(first.data, second.data)
                    self.assertEqual(first.damage, second.damage)
                    self.assertIn(first.status, {"recovered", "partial", "damaged"})

    def test_learned_aster_fields_agree_with_legacy_decoder(self):
        with __import__("tempfile").TemporaryDirectory() as temp:
            generate(Path(temp), seed=991)
            data = (Path(temp) / "aster_records.bin").read_bytes()
        old = AsterRecordsPlugin().decode(data).data
        learned = next(p for p in load_specs() if p.name == "LEARNED_ASTER").decode(data).data
        for key in ("version", "record_count"):
            self.assertEqual(learned[key], old[key])
        self.assertEqual(len(learned["records"]), len(old["records"]))
        for left, right in zip(learned["records"], old["records"]):
            for key in ("item_id", "kind", "nominal_span", "quantity", "score", "code"):
                self.assertEqual(left[key], right[key])


if __name__ == "__main__":
    unittest.main()
