import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "src"))
from salvage.cli import main
from salvage.formats.base import FormatPlugin, Result
from salvage.formats.generic import GenericPlugin
from salvage.formats.registry import PluginRegistry
from salvage.pipeline import inspect_bytes


class RaisingPlugin(FormatPlugin):
    name = "RAISER"

    def detect(self, data):
        return 1.0

    def decode(self, data):
        raise RuntimeError("deliberate decoder failure")


class FailureHandlingTests(unittest.TestCase):
    def test_missing_input_directory_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "out"
            self.assertEqual(main([str(Path(temp) / "missing"), str(output)]), 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["failures"][0]["stage"], "validate_input_dir")

    def test_subdirectory_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "in"; output = root / "out"
            source.mkdir(); (source / "nested").mkdir()
            self.assertEqual(main([str(source), str(output)]), 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["failures"][0]["stage"], "inspect_entry")

    def test_zero_byte_file_is_processed_without_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "in"; output = root / "out"
            source.mkdir(); (source / "empty.bin").write_bytes(b"")
            self.assertEqual(main([str(source), str(output)]), 0)
            result = json.loads((output / "empty.bin.json").read_text(encoding="utf-8"))
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(report["files_processed"], 1)

    def test_unreadable_file_result_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "in"; output = root / "out"
            source.mkdir(); target = source / "blocked.bin"; target.write_bytes(b"data")
            with patch("salvage.pipeline.Path.read_bytes", side_effect=PermissionError("denied")):
                self.assertEqual(main([str(source), str(output)]), 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(any(f["stage"] == "process_file" for f in report["failures"]))
            result = json.loads((output / "blocked.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "error")

    def test_raising_plugin_is_caught_and_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "in"; output = root / "out"
            source.mkdir(); (source / "sample.bin").write_bytes(b"payload")
            registry = PluginRegistry([RaisingPlugin(), GenericPlugin()])
            self.assertEqual(main([str(source), str(output)], registry=registry), 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertTrue(any(f["stage"] == "process_file" for f in report["failures"]))
            result = json.loads((output / "sample.bin.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "error")
            self.assertIn("deliberate decoder failure", " ".join(result["errors"]))

    def test_run_level_exception_still_returns_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / "in"; output = root / "out"
            source.mkdir()
            with patch("salvage.cli.build_report", side_effect=RuntimeError("report crash")):
                self.assertEqual(main([str(source), str(output)]), 0)

    def test_pipeline_catches_raising_plugin(self):
        result = inspect_bytes("x.bin", b"x", PluginRegistry([RaisingPlugin()]))
        self.assertEqual(result["status"], "error")
        self.assertIn("deliberate decoder failure", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
