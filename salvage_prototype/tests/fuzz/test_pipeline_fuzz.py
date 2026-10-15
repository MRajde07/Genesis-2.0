"""Seeded mutation tests for the full CLI pipeline and no-fabrication checks."""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from tools.corrupt import generate, mutate
from tools.gen_samples import generate as generate_samples

IGNORED = {"raw_hex", "payload_raw_hex", "packed_hex", "complete"}


def flatten(value, prefix=""):
    result = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in IGNORED:
                continue
            path = f"{prefix}.{key}" if prefix else key
            result.update(flatten(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.update(flatten(item, f"{prefix}[{index}]"))
    else:
        result[prefix] = value
    return result


def field_ranges(format_name, data: bytes, truth: dict) -> dict[str, list[tuple[int, int]]]:
    """Byte provenance for truth fields, including dependencies of derived fields."""
    ranges = {}
    def put(path, start, end):
        ranges[path] = [(start, end)]
    if format_name == "ASTER":
        put("version", 4, 6); put("record_count", 6, 8)
        for i, record in enumerate(truth["expected"]["records"]):
            start = 8 + i * 12
            for key, a, b in (("item_id",0,2),("kind",2,3),("nominal_span",3,5),
                              ("quantity",5,7),("score",7,9),("code",9,12)):
                put(f"records[{i}].{key}", start+a, start+b)
    elif format_name == "CRC_BLOCKS":
        put("version", 4, 5); put("block_count", 5, 7)
        cursor = 7
        for i, block in enumerate(truth["expected"]["blocks"]):
            length = int.from_bytes(data[cursor:cursor+2], "little")
            payload = cursor + 2; crc = payload + length; end = crc + 4
            put(f"blocks[{i}].length", cursor, cursor+2)
            put(f"blocks[{i}].sequence", payload, payload+2)
            put(f"blocks[{i}].reading", payload+2, payload+6)
            put(f"blocks[{i}].label", payload+7, payload+length)
            put(f"blocks[{i}].stored_crc32", crc, end)
            ranges[f"blocks[{i}].crc32_valid"] = [(payload, crc), (crc, end)]
            ranges[f"blocks[{i}].complete"] = [(cursor, end)]
            # All later block boundaries depend on every preceding length prefix.
            prefix_dependencies = []
            prior_cursor = 7
            for prior_index in range(i + 1):
                prior_len = int.from_bytes(data[prior_cursor:prior_cursor+2], "little")
                prefix_dependencies.append((prior_cursor, prior_cursor + 2))
                prior_cursor += 2 + prior_len + 4
            for field_path in [key for key in ranges if key.startswith(f"blocks[{i}].")]:
                ranges[field_path] = list(ranges[field_path]) + prefix_dependencies
            cursor = end
    elif format_name == "XIDX":
        put("version", 4, 5); put("blob_count", 5, 6); put("index_offset", 6, 8)
        for i, entry in enumerate(truth["expected"]["entries"]):
            p = truth["expected"]["index_offset"] + i * 10
            for key, a, b in (("blob_offset",0,2),("packed_length",2,4),("decoded_length",4,6),
                              ("label_offset",6,8),("label_length",8,9),("xor_key",9,10)):
                put(f"entries[{i}].{key}", p+a, p+b)
            blob_start = entry["blob_offset"]
            blob_end = blob_start + entry["packed_length"]
            label_start = entry["label_offset"]
            label_end = label_start + entry["label_length"]
            ranges[f"entries[{i}].blob_hex"] = [(blob_start, blob_end), (p+4, p+6)]
            ranges[f"entries[{i}].blob_bytes"] = [(blob_start, blob_end), (p+4, p+6)]
            ranges[f"entries[{i}].label"] = [(label_start, label_end), (p+8, p+10)]
            ranges[f"entries[{i}].rle_valid"] = [(blob_start, blob_end), (p+4, p+6)]
            ranges[f"entries[{i}].complete"] = [(blob_start, blob_end), (label_start, label_end), (p, p+10)]
    return ranges


def overlaps(ranges, start, end):
    # Empty truncation ranges do not affect bytes; a suffix truncation has a
    # non-empty [start,end) interval extending through the original EOF.
    return any(a < end and start < b for a, b in ranges)


class PipelineFuzzTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.samples = self.root / "samples"
        generate_samples(self.samples, seed=41027)

    def tearDown(self):
        self.temp.cleanup()

    def test_mutator_is_seeded_and_supports_all_four_mutations(self):
        source = (self.samples / "aster_records.bin").read_bytes()
        kinds = ("truncate", "bit-flip", "zero-block", "swap-bytes")
        for kind in kinds:
            with self.subTest(kind=kind):
                a, meta_a = mutate(source, kind, __import__("random").Random(12))
                b, meta_b = mutate(source, kind, __import__("random").Random(12))
                self.assertEqual(a, b)
                self.assertEqual(meta_a, meta_b)

    def test_full_pipeline_survives_seeded_mutations_and_preserves_unaffected_truth(self):
        mutated_dir = self.root / "mutated"
        generate(self.samples, mutated_dir, seed=9201, per_type=1)
        manifest = json.loads((mutated_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["mutations"]), 12)
        for mutation in manifest["mutations"]:
            if "error" in mutation:
                self.fail(mutation["error"])
            with self.subTest(file=mutation["file"]):
                source_path = self.samples / mutation["source"]
                truth = json.loads((self.samples / (mutation["source"] + ".truth.json")).read_text(encoding="utf-8"))
                original = source_path.read_bytes()
                mutated = (mutated_dir / mutation["file"]).read_bytes()
                input_dir = self.root / "input-one"
                output_dir = self.root / "output-one"
                if input_dir.exists(): shutil.rmtree(input_dir)
                if output_dir.exists(): shutil.rmtree(output_dir)
                input_dir.mkdir()
                (input_dir / mutation["file"]).write_bytes(mutated)
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "salvage"), str(input_dir), str(output_dir)],
                    cwd=ROOT, capture_output=True, text=True, timeout=15,
                    env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                per_file = output_dir / f"{mutation['file']}.json"
                report_file = output_dir / "report.json"
                self.assertTrue(per_file.is_file())
                self.assertTrue(report_file.is_file())
                result = json.loads(per_file.read_text(encoding="utf-8"))
                report = json.loads(report_file.read_text(encoding="utf-8"))
                self.assertIsInstance(result, dict)
                self.assertIsInstance(report, dict)
                self.assertEqual(result.get("file_name"), mutation["file"])
                self.assertIn(result.get("status"), {"recovered", "partial", "damaged", "unsupported", "error"})
                self.assertTrue(report.get("files"))
                self.assertEqual(report["files"][0]["file_name"], mutation["file"])

                # Every field whose source bytes were not touched must still
                # equal its ground truth. Fields whose source/dependencies were
                # mutated are excluded: without a checksum or redundancy, a
                # bit flip in an otherwise-valid field is not distinguishable
                # from a legitimate value and must not be falsely called known.
                actual = flatten(result.get("data") or {})
                expected = flatten(truth["expected"])
                ranges = field_ranges(truth["format"], original, truth)
                start, end = mutation["start"], mutation["end"]
                for path, expected_value in expected.items():
                    source_ranges = ranges.get(path, [])
                    if not source_ranges:
                        parents = [key for key in ranges if path.startswith(key + "[")]
                        if parents:
                            source_ranges = ranges[max(parents, key=len)]
                    if source_ranges and overlaps(source_ranges, start, end):
                        continue
                    if path in actual and actual[path] is not None:
                        self.assertEqual(actual[path], expected_value,
                                         f"unaffected field {path} diverged from ground truth")

                # No JSON NaN/Infinity or unserializable object can slip through
                # the writer: strict re-serialization must succeed.
                json.dumps(result, allow_nan=False, sort_keys=True)

    def test_corruption_manifest_and_outputs_are_deterministic(self):
        a, b = self.root / "mut-a", self.root / "mut-b"
        generate(self.samples, a, seed=77, per_type=1)
        generate(self.samples, b, seed=77, per_type=1)
        self.assertEqual((a / "manifest.json").read_bytes(), (b / "manifest.json").read_bytes())
        for path in sorted(a.glob("*.bin.*")):
            self.assertEqual(path.read_bytes(), (b / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
