import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))
from salvage.reader import ByteReader


class ByteReaderTests(unittest.TestCase):
    def test_exact_read_and_cursor(self):
        reader = ByteReader(b"abcd")
        self.assertEqual(reader.read(2, "tag"), b"ab")
        self.assertEqual(reader.offset, 2)
        self.assertEqual(reader.remaining, 2)
        self.assertEqual(reader.damage, [])

    def test_short_read_returns_available_bytes_and_damage(self):
        reader = ByteReader(b"abc")
        self.assertEqual(reader.read(5, "payload"), b"abc")
        self.assertEqual(reader.damage, [{
            "field": "payload", "offset": 3, "expected": 5, "found": 3,
            "reason": "out of range: insufficient bytes",
        }])
        self.assertEqual(reader.offset, 3)

    def test_read_at_does_not_move_cursor(self):
        reader = ByteReader(b"abc")
        self.assertEqual(reader.read_at(1, 4, "slice"), b"bc")
        self.assertEqual(reader.offset, 0)
        self.assertEqual(reader.damage[0]["offset"], 3)

    def test_endian_aware_integer_reads(self):
        self.assertEqual(ByteReader(b"\x01\x02", "big").read_uint(2, "n"), 258)
        self.assertEqual(ByteReader(b"\x01\x02", "little").read_uint(2, "n"), 513)

    def test_short_integer_read_and_empty_integer(self):
        reader = ByteReader(b"\x12")
        self.assertEqual(reader.read_uint(2, "version"), 0x12)
        self.assertEqual(reader.damage[0]["found"], 1)
        self.assertIsNone(reader.read_uint(1, "next"))

    def test_invalid_ranges_never_raise(self):
        reader = ByteReader(b"abc")
        self.assertEqual(reader.read(-1, "negative"), b"")
        self.assertEqual(reader.read_at(-2, 3, "negative-offset"), b"")
        self.assertFalse(reader.seek(99))
        self.assertGreaterEqual(len(reader.damage), 3)

    def test_invalid_endian_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ByteReader(b"x", "middle")


if __name__ == "__main__":
    unittest.main()
