import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from salvage.output import (SchemaValidationError, load_schema, validate_schema,
                            shape_report, shape_result, write_json)
from salvage.formats.stud import STUDPlugin


class JSONWriterTests(unittest.TestCase):
    def test_valid_result_and_report_against_bundled_schemas(self):
        result = shape_result('sample.bin', STUDPlugin().decode(b'STUD\x01\x03Anu'),
                              fallback_format='STUD', identification=[{'selected': True, 'confidence': 0.9}])
        report = shape_report([result])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            write_json(out / 'sample.bin.json', result)
            write_json(out / 'report.json', report)
            self.assertEqual(json.loads((out / 'report.json').read_text()), report)
            self.assertEqual(report['files'][0]['confidence'], 0.9)
            self.assertEqual(report['files'][0]['counts']['records_recovered'], 1)
            self.assertEqual(report['files'][0]['warnings'], [])

    def test_rejects_invalid_output_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            with self.assertRaises(SchemaValidationError):
                write_json(path, {'file_name': 'bad'})
            self.assertFalse(path.exists())

    def test_rejects_bool_as_integer_and_extra_damage_fields(self):
        with self.assertRaises(SchemaValidationError):
            validate_schema(True, {'type': 'integer'})
        with self.assertRaises(SchemaValidationError):
            validate_schema({'x': 1}, {'type': 'object', 'additionalProperties': False})
        with self.assertRaises(SchemaValidationError):
            validate_schema({}, {'$ref': 'https://example.com/schema'})

    def test_byte_identical_across_order_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a.json'
            b = Path(tmp) / 'b.json'
            payload = {'file_name': 'x', 'format': 'UNKNOWN', 'status': 'unsupported',
                       'data': {'z': 1, 'a': 2}, 'records': [],
                       'counts': {'records_lost': 0, 'records_recovered': 0, 'records_damaged': 0},
                       'damage': [], 'byte_ranges': [], 'errors': []}
            write_json(a, payload)
            write_json(b, dict(reversed(list(payload.items()))))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertNotIn(b'\\r\\n', a.read_bytes())

    def test_report_stable_file_order_and_warnings(self):
        a = shape_result('a.bin', STUDPlugin().decode(b'STUD\x01\x03A'), fallback_format='STUD')
        b = shape_result('b.bin', STUDPlugin().decode(b'STUD\x01\x01B'), fallback_format='STUD')
        report = shape_report([b, a])
        self.assertEqual([f['file_name'] for f in report['files']], ['a.bin', 'b.bin'])
        self.assertTrue(report['files'][0]['warnings'])
        validate_schema(report, load_schema('report.schema.json'))

if __name__ == '__main__':
    unittest.main()
