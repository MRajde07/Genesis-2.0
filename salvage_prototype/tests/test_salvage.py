import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_DIR / "salvage"


class SalvageTests(unittest.TestCase):
    def run_salvage(self, input_dir, output_dir):
        # Invoke the same CLI entry point as the launcher; works on Windows and POSIX.
        code = "import sys; sys.path.insert(0, %r); from salvage.cli import main; raise SystemExit(main(sys.argv[1:]))" % str(PROJECT_DIR / "src")
        return subprocess.run(
            [sys.executable, "-c", code, str(input_dir), str(output_dir)],
            capture_output=True, text=True, timeout=10,
        )

    def test_valid_stud_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_dir = root / "input"; output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "student.bin").write_bytes(b"STUD\x01\x03Anu")
            process = self.run_salvage(input_dir, output_dir)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((output_dir / "student.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["format"], "STUD")
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["data"]["name"], "Anu")

    def test_unknown_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_dir = root / "input"; output_dir = root / "output"
            input_dir.mkdir(); (input_dir / "unknown.bin").write_bytes(b"HELLO")
            process = self.run_salvage(input_dir, output_dir)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((output_dir / "unknown.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["format"], "UNKNOWN")
            self.assertEqual(result["status"], "unsupported")

    def test_truncated_stud_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_dir = root / "input"; output_dir = root / "output"
            input_dir.mkdir(); (input_dir / "damaged.bin").write_bytes(b"STUD\x01\x05Al")
            process = self.run_salvage(input_dir, output_dir)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((output_dir / "damaged.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["format"], "STUD")
            self.assertEqual(result["status"], "partially_recovered")
            self.assertTrue(result["errors"])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_dir = root / "input"; output_dir = root / "output"
            input_dir.mkdir(); (input_dir / "empty.bin").write_bytes(b"")
            process = self.run_salvage(input_dir, output_dir)
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads((output_dir / "empty.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "unsupported")

    def test_batch_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); input_dir = root / "input"; output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "good.bin").write_bytes(b"STUD\x01\x03Anu")
            (input_dir / "unknown.bin").write_bytes(b"OTHER")
            process = self.run_salvage(input_dir, output_dir)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["files_processed"], 2)
            self.assertEqual(len(report["results"]), 2)

    def test_missing_input_is_zero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            process = self.run_salvage(Path(temp) / "missing", output)
            self.assertEqual(process.returncode, 0)
            self.assertTrue((output / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
