# SALVAGE — Offline Binary Recovery CLI

SALVAGE is a standard-library-only Python 3.10+ CLI prototype for identifying file formats, decoding known structures through plugins, and reporting recovered data as deterministic JSON. The first decoder is the fictional `STUD` format from the original prototype. Unknown files use a conservative generic fallback and are not assigned invented content.

## Run

POSIX / Linux:

```sh
chmod +x ./salvage
./salvage ./input_dir ./output_dir
```

Windows Command Prompt or PowerShell:

```powershell
.\salvage.cmd .\input_dir .\output_dir
```

Python is the only runtime dependency. The tool makes no network requests. It always returns process exit code `0`, including when the input directory is missing or processing fails; inspect `report.json` and per-file results to determine the outcome.

## STUD sample

```sh
python -c "from pathlib import Path; Path('input_dir').mkdir(exist_ok=True); Path('input_dir/student.bin').write_bytes(b'STUD\\x01\\x03Anu')"
./salvage ./input_dir ./output_dir
```

The STUD layout is a 4-byte `STUD` signature, one version byte, one name-length byte, and that many name bytes. Existing prototype behaviour is retained, including replacement decoding for invalid UTF-8 in STUD names. Damage ranges are zero-based, half-open byte offsets.

## Output

Each input gets `<input-name>.json`; the batch also gets `report.json`. JSON uses stable key order, indentation, ASCII escaping, and LF newlines. Unknown formats remain `UNKNOWN` with `unsupported` status. STUD results preserve the original `format`, `status`, `data`, and `errors` fields; the plugin pipeline may add a `damage` array when a byte range is known.


## Unknown-format analysis

The generic fallback performs bounded, heuristic analysis of up to the first 64 KiB: windowed Shannon entropy, a 256-bin byte histogram, printable strings (ASCII, UTF-16LE/BE and CP437), endian-aware integer candidates, candidate length fields, fixed-size record hypotheses, checksum matches (CRC16/CRC32, sum, XOR and Fletcher), XOR hypotheses, and count/value RLE hypotheses. Candidate interpretations are marked `unverified`; they are evidence for further investigation, not a claim that the file format has been decoded. Expensive checksum and XOR searches use smaller bounded samples.

Inspect a file directly with:

```sh
python tools/probe.py path/to/file.bin
python tools/hexview.py path/to/file.bin
```

The analysis helpers are pure functions in `src/salvage/analysis/` and use only the Python standard library. Heuristic confidence values are ranking signals, not calibrated probabilities. RLE and XOR outputs are candidate transformations and should not be trusted without independent structural validation.

## Plugin API

Implement `FormatPlugin` from `src/salvage/formats/base.py`:

- `detect(data: bytes) -> float`: confidence in `[0.0, 1.0]`.
- `decode(data: bytes) -> Result`: return decoded records/data and a list of `Damage` items.

Register plugins with `PluginRegistry`. The default registry checks STUD before the generic fallback. Detection exceptions and invalid confidence values are ignored; decoder exceptions are isolated to that file. Plugins must not claim data without evidence.

## Tests

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

Or use `make test` where Make is available.

## Repository layout

```text
salvage                 POSIX launcher
salvage.cmd             Windows launcher
src/salvage/            CLI, pipeline, identification, reporting and plugins
src/salvage/analysis/   Entropy, strings, integers, records, checksums, XOR and RLE heuristics
src/salvage/formats/    Plugin API, registry, generic and STUD plugins
src/salvage/tools/      Probe and annotated hex-view utilities
tools/                  Sample, corruption, scoring, probe and hex-view utilities
schema/                 Output schema
 tests/                 Unit, integration, fuzz and golden tests
FORMAT-SPEC.md          Format notes
FIELD-LOG.md            Evidence and development log
```

## Limitations and assumptions

- Only STUD is a known format at this stage; the generic fallback deliberately does not infer fields.
- A generic fallback cannot make arbitrary unknown or encrypted data semantically understandable.
- The CLI attempts to handle errors without crashing, but operating-system failures can prevent output files from being written at all.
- STUD's historical invalid-UTF-8 replacement behaviour is intentionally preserved for compatibility; future formats should preserve undecodable bytes instead of replacing them.
