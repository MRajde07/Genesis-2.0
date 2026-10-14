import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))
from salvage.formats.base import FieldSpec, FormatPlugin, decode_fields
from salvage.formats.stud import STUDPlugin


class DeclarativeFieldSpecTests(unittest.TestCase):
    def test_stud_output_matches_legacy_shape(self):
        result = STUDPlugin().decode(b"STUD\x01\x03Anu")
        self.assertEqual(result.data, {"version": 1, "name": "Anu"})
        self.assertEqual(result.records, [{"version": 1, "name": "Anu"}])
        self.assertEqual(result.status, "recovered")
        self.assertEqual(result.damage, [])

    def test_integer_types_and_endianness(self):
        data = bytes.fromhex("01 0203 04050607 ff fffe fffffffd")
        fields = [FieldSpec("a", "u8"), FieldSpec("b", "u16"), FieldSpec("c", "u32"),
                  FieldSpec("d", "i8"), FieldSpec("e", "i16"), FieldSpec("f", "i32")]
        result = decode_fields(data, fields, endian="big")
        self.assertEqual(result.values, {"a": 1, "b": 0x0203, "c": 0x04050607,
                                         "d": -1, "e": -2, "f": -3})
        little = decode_fields(b"\x34\x12", [FieldSpec("v", "u16")], endian="little")
        self.assertEqual(little.values["v"], 0x1234)

    def test_float_fixed_and_length_prefixed_strings(self):
        import struct
        data = struct.pack("<f", 1.25) + b"ABC" + b"\x03xyz"
        fields = [FieldSpec("f", "f32"), FieldSpec("fixed", "fixed_string", length=3),
                  FieldSpec("lp", "length_prefixed_string", prefix_type="u8")]
        result = decode_fields(data, fields, endian="little")
        self.assertAlmostEqual(result.values["f"], 1.25)
        self.assertEqual(result.values["fixed"], "ABC")
        self.assertEqual(result.values["lp"], "xyz")

    def test_truncated_length_prefixed_string_returns_partial_and_damage(self):
        class Example(FormatPlugin):
            name = "EXAMPLE"
            def detect(self, data): return 1.0
            def decode(self, data):
                return self.decode_spec(data, [FieldSpec("name", "length_prefixed_string", prefix_type="u8")])
        result = Example().decode(b"\x05ab")
        self.assertEqual(result.data["name"], "ab")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.damage[0].field, "name")
        self.assertEqual(result.damage[0].expected, 5)
        self.assertEqual(result.damage[0].found, 2)

    def test_dos_date_time_timestamp_bcd_and_julian_date(self):
        # DOS date 2024-01-02 and time 03:04:06, followed by BCD 1234 and Unix epoch.
        date_word = ((2024 - 1980) << 9) | (1 << 5) | 2
        time_word = (3 << 11) | (4 << 5) | 3
        data = date_word.to_bytes(2, "little") + time_word.to_bytes(2, "little") + bytes.fromhex("1234") + (0).to_bytes(4, "little")
        fields = [FieldSpec("when", "dos_datetime"), FieldSpec("bcd", "bcd", length=2),
                  FieldSpec("unix", "unix_timestamp", length=4)]
        result = decode_fields(data, fields, endian="little")
        self.assertEqual(result.values["when"], {"date": "2024-01-02", "time": "03:04:06"})
        self.assertEqual(result.values["bcd"], 1234)
        self.assertEqual(result.values["unix"], {"seconds": 0, "utc": "1970-01-01T00:00:00Z"})
        # JDN 2451545 corresponds to 2000-01-01 in this engine's documented integer-day convention.
        jdn = decode_fields((2451545).to_bytes(4, "big"), [FieldSpec("date", "julian_date")], endian="big")
        self.assertEqual(jdn.values["date"], "2000-01-01")

    def test_arrays_and_index_tables(self):
        # two u16 array elements, followed by offsets 8 and 10 pointing at records.
        data = b"\x01\x00\x02\x00\x0c\x00\x00\x00\x0e\x00\x00\x00ABCD"
        fields = [FieldSpec("values", "array", count=2, item_type="u16", item_size=2, offset=0),
                  FieldSpec("indices", "index_table", count=2, item_type="u32", item_size=4, offset=4,
                            target_fields=(FieldSpec("tag", "fixed_string", length=2),))]
        result = decode_fields(data, fields, endian="little")
        self.assertEqual(result.values["values"], [1, 2])
        self.assertEqual([x["offset"] for x in result.values["indices"]], [12, 14])
        self.assertEqual(result.values["indices"][0]["record"]["tag"], "AB")

    def test_validators_report_damage(self):
        result = decode_fields(b"\x00", [FieldSpec("version", "u8", validators=("positive",))])
        self.assertEqual(result.values["version"], 0)
        self.assertIn("validator failed", result.damage[0].reason)


    def test_block_crc32_valid_and_mismatch_preserves_raw_bytes(self):
        import zlib
        from salvage.formats.base import BlockSpec
        payload = b"ABC"
        good = payload + (zlib.crc32(payload) & 0xffffffff).to_bytes(4, "little")
        fields = [FieldSpec("tag", "fixed_string", length=3)]
        ok = decode_fields(good, fields, blocks=[BlockSpec("header", 0, len(good), 3, "crc32", 4)])
        self.assertEqual(ok.damage, [])
        self.assertTrue(ok.blocks[0]["checksum"]["valid"])
        damaged = bytearray(good)
        damaged[0] ^= 1
        bad = decode_fields(bytes(damaged), fields, blocks=[BlockSpec("header", 0, len(good), 3, "crc32", 4)])
        self.assertTrue(any("checksum mismatch" in d.reason for d in bad.damage))
        entry = next(d for d in bad.damage if "checksum mismatch" in d.reason)
        self.assertEqual(entry.byte_range, (3, 7))
        self.assertTrue(entry.raw_hex)
        self.assertEqual(bad.values["tag"], "@BC")  # observed bytes are not silently corrected

    def test_block_and_checksum_bounds_are_checked(self):
        from salvage.formats.base import BlockSpec
        result = decode_fields(b"abc", [], blocks=[BlockSpec("short", 0, 9, 7, "crc32", 4)])
        self.assertTrue(any("block bounds" in d.reason for d in result.damage))
        self.assertTrue(any("checksum field bounds" in d.reason for d in result.damage))

    def test_field_range_and_enum_checks_keep_raw_bytes(self):
        result = decode_fields(b"\x09\x03", [
            FieldSpec("level", "u8", minimum=1, maximum=5),
            FieldSpec("kind", "u8", enum_values=(1, 2)),
        ])
        self.assertEqual(result.values, {"level": 9, "kind": 3})
        self.assertEqual(len(result.damage), 2)
        self.assertEqual(result.damage[0].raw_hex, "09")
        self.assertEqual(result.damage[1].raw_hex, "03")
        self.assertIn("maximum:5", result.damage[0].reason)
        self.assertIn("enum", result.damage[1].reason)

    def test_explicit_field_offset_out_of_bounds_is_damage(self):
        result = decode_fields(b"abc", [FieldSpec("far", "u32", offset=8)])
        self.assertIsNone(result.values["far"])
        self.assertIn("field offset out of range", result.damage[0].reason)


if __name__ == "__main__":
    unittest.main()
