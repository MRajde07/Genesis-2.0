"""Byte coverage map: totals must add up, ranges are clamped, plugins and the CLI stay safe."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from salvage.bytemap import build_bytemap, render_html, span
from salvage.cli import main
from salvage.pipeline import inspect_bytes

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "samples" / "generated"


def _map(name, data=None):
    data = data if data is not None else (GEN / name).read_bytes()
    sink = {}
    inspect_bytes(name, data, bytemap_sink=sink)
    return data, sink


class ByteMapTests(unittest.TestCase):
    def test_totals_always_add_up_to_file_size_even_when_truncated(self):
        for name in ("aster_records.bin", "crc_blocks.bin", "xidx_archive.bin"):
            full = (GEN / name).read_bytes()
            for n in range(len(full) + 1):
                _, bm = _map(name, full[:n])
                if not bm:
                    continue
                self.assertEqual(sum(bm["totals"].values()), n, (name, n))
                covered = sum(s["end"] - s["start"] for s in bm["spans"])
                self.assertEqual(covered, n, (name, n))
                for a, b in zip(bm["spans"], bm["spans"][1:]):
                    self.assertEqual(a["end"], b["start"])

    def test_clean_file_is_fully_explained_and_hashed(self):
        data, bm = _map("crc_blocks.bin")
        self.assertEqual(bm["explained_pct"], 100.0)
        self.assertEqual(bm["totals"]["damaged"], 0)
        self.assertEqual(bm["sha256"], hashlib.sha256(data).hexdigest())

    def test_corrupted_crc_bytes_are_marked_damaged(self):
        data = bytearray((GEN / "crc_blocks.bin").read_bytes())
        data[-3] ^= 0xFF
        _, bm = _map("x", bytes(data))
        self.assertEqual(bm["totals"]["damaged"], 4)
        last = [s for s in bm["spans"] if s["kind"] == "damaged"][0]
        self.assertEqual((last["start"], last["end"]), (len(data) - 4, len(data)))

    def test_unknown_file_is_entirely_unclaimed_not_guessed(self):
        _, bm = _map("junk.bin", bytes(range(200)))
        self.assertEqual(bm["totals"]["unclaimed"], 200)
        self.assertEqual(bm["explained_pct"], 0.0)

    def test_truncation_reports_bytes_expected_beyond_eof(self):
        data = (GEN / "aster_records.bin").read_bytes()[:30]
        _, bm = _map("t", data)
        self.assertGreater(bm["bytes_expected_beyond_eof"], 0)

    def test_hostile_ranges_are_clamped_and_overlap_prefers_damage(self):
        data = bytes(10)
        bm = build_bytemap(data, plugin_spans=[span(-5, 4, "decoded"), span(2, 99, "verified"),
                                               {"start": "x"}, "junk", span(3, 3, "decoded")],
                           damage=[{"byte_range": {"start": 3, "end": 5}, "field": "f", "reason": "r"}])
        self.assertEqual(sum(bm["totals"].values()), 10)
        self.assertEqual(bm["totals"]["damaged"], 2)

    def test_empty_file(self):
        bm = build_bytemap(b"")
        self.assertEqual(bm["size"], 0)
        self.assertEqual(bm["spans"], [])

    def test_record_inference_fallback_for_plugins_without_spans(self):
        data = b"HEAD" + b"\x01\x02\x03\x04" + b"\x05\x06\x07\x08"
        records = [{"index": 0, "raw_hex": "01020304", "complete": True},
                   {"index": 1, "raw_hex": "05060708", "complete": True}]
        bm = build_bytemap(data, records=records, header_length=4)
        self.assertEqual(bm["method"], "inferred-from-records")
        self.assertEqual(bm["totals"]["decoded"], 8)
        self.assertEqual(bm["totals"]["header"], 4)

    def test_html_is_offline_self_contained_and_escapes_names(self):
        data, bm = _map("crc_blocks.bin")
        page = render_html([{"file_name": "<b>x</b>.bin", "format": "F", "status": "s", "bytemap": bm}],
                           {"<b>x</b>.bin": data})
        self.assertNotIn("http://", page.replace("http://www.w3.org", ""))
        self.assertNotIn("https://", page)
        self.assertNotIn("<b>x</b>.bin", page.split('id="bytemap-data"')[0])
        self.assertIn("&lt;b&gt;x&lt;/b&gt;.bin", page)

    def test_cli_writes_report_html_and_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in").mkdir()
            for name in ("aster_records.bin", "crc_blocks.bin", "xidx_archive.bin"):
                (tmp / "in" / name).write_bytes((GEN / name).read_bytes())
            self.assertEqual(main([str(tmp / "in"), str(tmp / "a")]), 0)
            self.assertEqual(main([str(tmp / "in"), str(tmp / "b")]), 0)
            self.assertTrue((tmp / "a" / "report.html").exists())
            self.assertEqual((tmp / "a" / "report.html").read_bytes(), (tmp / "b" / "report.html").read_bytes())
            self.assertEqual(main([str(tmp / "in"), str(tmp / "c"), "--no-bytemap"]), 0)
            self.assertFalse((tmp / "c" / "report.html").exists())
            # per-file JSON must be unchanged by the feature
            self.assertEqual((tmp / "a" / "crc_blocks.bin.json").read_bytes(),
                             (tmp / "c" / "crc_blocks.bin.json").read_bytes())

    def test_report_json_byte_ranges_cover_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in").mkdir()
            (tmp / "in" / "crc_blocks.bin").write_bytes((GEN / "crc_blocks.bin").read_bytes())
            (tmp / "in" / "junk.bin").write_bytes(bytes(range(50)))
            main([str(tmp / "in"), str(tmp / "out")])
            files = {f["file"]: f for f in json.loads((tmp / "out" / "report.json").read_text())["files"]}
            for name, size in (("crc_blocks.bin", 63), ("junk.bin", 50)):
                ranges = files[name]["byte_ranges"]
                self.assertTrue(ranges)
                self.assertEqual(ranges[0]["start"], 0)
                self.assertEqual(ranges[-1]["end"], size)
                for a, b in zip(ranges, ranges[1:]):
                    self.assertEqual(a["end"], b["start"])
            self.assertEqual(files["junk.bin"]["byte_ranges"][0]["kind"], "unclaimed")


if __name__ == "__main__":
    unittest.main()
