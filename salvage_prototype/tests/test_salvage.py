
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


# Locate salvage.py in the project root.
PROJECT_DIR = Path(__file__).resolve().parent.parent
SALVAGE_SCRIPT = PROJECT_DIR / "salvage.py"


class SalvageTests(unittest.TestCase):

    def run_salvage(self, input_dir, output_dir):
        return subprocess.run(
            [
                sys.executable,
                str(SALVAGE_SCRIPT),
                str(input_dir),
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_valid_stud_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()

            (input_dir / "student.bin").write_bytes(
                b"STUD\x01\x03Anu"
            )

            process = self.run_salvage(input_dir, output_dir)

            self.assertEqual(process.returncode, 0, process.stderr)

            result = json.loads(
                (output_dir / "student.bin.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result["format"], "STUD")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"]["name"], "Anu")

    def test_unknown_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()

            (input_dir / "unknown.bin").write_bytes(b"HELLO")

            process = self.run_salvage(input_dir, output_dir)

            self.assertEqual(process.returncode, 0, process.stderr)

            result = json.loads(
                (output_dir / "unknown.bin.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result["format"], "UNKNOWN")
            self.assertEqual(result["status"], "unsupported")

    def test_truncated_stud_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()

            (input_dir / "damaged.bin").write_bytes(
                b"STUD\x01\x05Al"
            )

            process = self.run_salvage(input_dir, output_dir)

            self.assertEqual(process.returncode, 0, process.stderr)

            result = json.loads(
                (output_dir / "damaged.bin.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result["format"], "STUD")
            self.assertEqual(result["status"], "partially_recovered")
            self.assertTrue(result["errors"])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()

            (input_dir / "empty.bin").write_bytes(b"")

            process = self.run_salvage(input_dir, output_dir)

            self.assertEqual(process.returncode, 0, process.stderr)

            result = json.loads(
                (output_dir / "empty.bin.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(result["status"], "unsupported")

    def test_batch_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()

            (input_dir / "good.bin").write_bytes(
                b"STUD\x01\x03Anu"
            )
            (input_dir / "unknown.bin").write_bytes(b"OTHER")

            process = self.run_salvage(input_dir, output_dir)

            self.assertEqual(process.returncode, 0, process.stderr)

            report = json.loads(
                (output_dir / "report.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(report["files_processed"], 2)
            self.assertEqual(len(report["results"]), 2)


if __name__ == "__main__":
    unittest.main()
