import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from salvage.analysis.entropy import analyze_entropy, byte_histogram, shannon_entropy
from salvage.analysis.strings import extract_strings
from salvage.analysis.ints import scan_integers, find_length_fields
from salvage.analysis.records import detect_fixed_records
from salvage.analysis.checksums import guess_checksums, _crc32
from salvage.analysis.xor import detect_single_byte_xor, detect_repeating_key_xor
from salvage.analysis.rle import decode_count_value, detect_rle
from salvage.formats.generic import GenericPlugin
from salvage.tools.probe import probe
from salvage.tools.hexview import render


class AnalysisTests(unittest.TestCase):
    def test_entropy_and_histogram(self):
        self.assertEqual(shannon_entropy(b"AAAA"), 0.0)
        self.assertEqual(shannon_entropy(bytes(range(256))), 8.0)
        result = analyze_entropy(b"A" * 300, window_size=128, step=64)
        self.assertTrue(result["regions"])
        hist = byte_histogram(b"ABA")
        self.assertEqual(hist["counts"][65], 2)
        self.assertEqual(hist["counts"][66], 1)

    def test_string_encodings_have_offsets(self):
        data = b"\x00HELLO\x00 " + "WIDE".encode("utf-16le") + b"\x00\x00"
        result = extract_strings(data, min_length=4)
        self.assertTrue(any(x["text"] == "HELLO" and x["offset"] == 1 for x in result["findings"]))
        self.assertTrue(any(x["text"] == "WIDE" and x["encoding"] == "UTF-16LE" for x in result["findings"]))
        self.assertTrue(all("confidence" in x for x in result["findings"]))
        wide = "BEAM".encode("utf-16be")
        be_result = extract_strings(b"xx\x00\x00" + wide + b"\x00\x00", min_length=4)
        self.assertTrue(any(x["text"] == "BEAM" and x["encoding"] == "UTF-16BE" and x["offset"] == 4
                            for x in be_result["findings"]))
        cp_result = extract_strings(bytes([0x82, 0x82, 0x82, 0x82]), min_length=4)
        self.assertTrue(any(x["encoding"] == "cp437" for x in cp_result["findings"]))

    def test_integer_scan_and_length_fields(self):
        data = b"\x00\x08ABCDEF"
        ints = scan_integers(data, widths=(2,), endians=("big",))
        self.assertTrue(any(x["offset"] == 0 and x["value"] == 8 for x in ints["findings"]))
        lengths = find_length_fields(data, widths=(1, 2), endians=("big",))
        self.assertTrue(any("file_size" in x["matches"] for x in lengths["findings"]))

    def test_fixed_record_detector(self):
        result = detect_fixed_records(b"ABCD" * 5, min_record_size=4, max_record_size=4)
        self.assertEqual(result["findings"][0]["record_size"], 4)
        self.assertEqual(result["findings"][0]["record_count"], 5)
        self.assertFalse(result["findings"][0]["verified"])

    def test_checksum_guessing_finds_sum8(self):
        data = b"ABC" + bytes([sum(b"ABC") & 255])
        result = guess_checksums(data)
        self.assertTrue(any(x["algorithm"] == "sum8" and x["offset"] == 3 for x in result["findings"]))
        payload = b"CRC32 payload"
        crc_data = payload + _crc32(payload).to_bytes(4, "little")
        crc_result = guess_checksums(crc_data)
        self.assertTrue(any(x["algorithm"] == "crc32" and x["offset"] == len(payload)
                            and x["endian"] == "little" for x in crc_result["findings"]))

    def test_xor_detection(self):
        plain = b"this is a readable text string with spaces and words"
        cipher = bytes(b ^ 0x42 for b in plain)
        result = detect_single_byte_xor(cipher)
        self.assertTrue(any(x["key"] == 0x42 for x in result["findings"]))
        repeat = bytes(b ^ b"KEY"[i % 3] for i, b in enumerate(plain * 3))
        repeated = detect_repeating_key_xor(repeat, min_key_size=3, max_key_size=3)
        self.assertEqual(repeated["findings"][0]["key_size"], 3)
        self.assertEqual(repeated["findings"][0]["key_hex"], b"KEY".hex())
        self.assertFalse(repeated["findings"][0]["verified"])

    def test_rle_detection_and_decode(self):
        data = bytes([4, 65, 3, 66, 2, 67])
        decoded = decode_count_value(data)
        self.assertEqual(bytes.fromhex(decoded["decoded_hex"]), b"AAAABBBCC")
        self.assertTrue(detect_rle(data)["findings"])
        damaged = decode_count_value(b"\x03A\x02")
        self.assertTrue(damaged["damage"])

    def test_generic_plugin_outputs_unverified_findings(self):
        result = GenericPlugin().decode(b"unknown string\x00\x04\x00\x00")
        self.assertEqual(result.status, "unsupported")
        self.assertTrue(result.data["unverified"])
        # Default summary is short; the full toolkit output sits under a debug-only key.
        self.assertIn("ascii_strings", result.data)
        self.assertIn("entropy_bits_per_byte", result.data)
        self.assertNotIn("fixed_record_candidates", result.data)
        full = result.data["_full_analysis"]
        self.assertIn("strings", full)
        self.assertIn("entropy", full)
        self.assertIn("fixed_record_candidates", full)
        json.dumps(result.data)

    def test_probe_and_hexview(self):
        findings = probe(b"Hello there!\x00\x01\x02")
        self.assertTrue(findings["unverified"])
        self.assertIn("Hello", json.dumps(findings))
        view = render(b"Hello there!")
        self.assertIn("00000000", view)
        self.assertIn("string@0x0", view)


if __name__ == "__main__":
    unittest.main()
