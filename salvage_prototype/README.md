# SALVAGE — Offline Binary Recovery CLI

SALVAGE is a standard-library-only Python 3.10+ CLI prototype for identifying binary formats, decoding known structures through plugins, and reporting recovered data as deterministic JSON. It is designed to run without network access and does not install third-party Python packages.

## One-command Docker build

With Docker installed and the selected base image already present in the local image cache, build the image with:

```sh
make build
```

The default base is `python:3.12-slim`. Configure the Python version or image tag with:

```sh
make build PYTHON_VERSION=3.11
# or
make build PYTHON_VERSION=3.10 IMAGE_NAME=salvage:py310
```

**Offline-build note:** Docker must already have `python:<PYTHON_VERSION>-slim` cached locally. `--network=none` prevents network access during the build, and `--pull=false` prevents an intentional base-image refresh. If the base image is not cached, first obtain it in an environment with access and transfer/load it into the offline Docker host. SALVAGE itself has no package-install or runtime network dependency.

Run the container with an input directory mounted read-only and an output directory mounted read/write (POSIX shell example):

```sh
mkdir -p input_dir output_dir
docker run --rm --network=none \
  -v "$PWD/input_dir:/data/in:ro" \
  -v "$PWD/output_dir:/data/out" \
  salvage:local /data/in /data/out
```

The image entrypoint is `./salvage`; the two arguments are input and output directory paths. No network is required at runtime.

## Run directly with Python

Python 3.10 or newer is the only runtime requirement.

Linux/macOS:

```sh
./salvage ./input_dir ./output_dir
```

Windows Command Prompt or PowerShell:

```powershell
.\salvage.cmd .\input_dir .\output_dir
```

The tool makes no network requests. It always returns process exit code `0`, including when the input directory is missing or processing fails; inspect `report.json` and per-file results for the outcome.

## Tests

```sh
make test
```

Or invoke the standard-library test runner directly:

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

Tests require no third-party packages and do not need network access. The optional real Lotus `.WKS` integration test skips if no sample is present.

## Quick STUD sample

```sh
python -c "from pathlib import Path; Path('input_dir').mkdir(exist_ok=True); Path('input_dir/student.bin').write_bytes(b'STUD\\x01\\x03Anu')"
./salvage ./input_dir ./output_dir
```

The STUD layout is a four-byte `STUD` signature, one version byte, one name-length byte, and that many name bytes. Damage ranges are zero-based, half-open byte offsets.

## Output

Each input gets `<input-name>.json`; the batch also gets `report.json`. JSON uses stable key order, indentation, ASCII escaping, and LF newlines. Unknown formats remain `UNKNOWN` with `unsupported` status. The status vocabulary is `recovered`, `partial`, `damaged`, `unsupported`, and `error`. Unsupported files do not receive invented fields. The CLI attempts to contain errors, although operating-system failures can still prevent output files from being written.

## Supported and experimental formats

- **STUD** — original prototype format; compatibility behaviour is covered by tests.
- **ASTER (`ARCF`), CRC_BLOCKS (`CRCB`), XIDX (`XIDX`)** — deliberately invented local fixtures for testing fixed records, checksums, index tables, RLE and XOR. These are not real-world format claims.
- **Lotus 1-2-3 Release 1A `.WKS`** — conservative subset decoder for BOF revision `0x0404`, INTEGER, NUMBER, LABEL and FORMULA cell records. Formula tokens are preserved as raw hex and are not evaluated or translated. Real-sample verification is pending unless a sample is supplied.
- **Unknown formats** — bounded heuristic findings are labelled `unverified`; they are not asserted as decoded fields.

See [FORMAT-SPEC.md](FORMAT-SPEC.md) for per-format fields and confidence status, and [FIELD-LOG.md](FIELD-LOG.md) for dated experiments and evidence.

## Generate invented fixtures

```sh
python tools/gen_samples.py --output-dir samples/generated --seed 1337
```

Each generated binary has an adjacent `.truth.json` used by golden tests.

## Unknown-format analysis

The generic fallback performs bounded heuristic analysis of up to the first 64 KiB: windowed Shannon entropy, byte histogram, printable strings (ASCII, UTF-16LE/BE and CP437), endian-aware integer candidates, candidate length fields, fixed-size record hypotheses, checksum matches (CRC16/CRC32, sum, XOR and Fletcher), XOR hypotheses, and count/value RLE hypotheses. These can produce false positives. Findings are evidence for investigation, not proof of structure.

```sh
python tools/probe.py path/to/file.bin
python tools/hexview.py path/to/file.bin
```

## Plugin API

Implement `FormatPlugin` from `src/salvage/formats/base.py`:

- `detect(data: bytes) -> float`: confidence in `[0.0, 1.0]`.
- `decode(data: bytes) -> Result`: decoded data plus structured damage diagnostics.

Register plugins with `PluginRegistry`. Selection is deterministic; decoder failures are isolated to the affected file. Plugins should only claim interpretations supported by evidence.

## Corruption and scoring utilities

```sh
python tools/corrupt.py samples/generated samples/mutated --seed 1337 --per-type 1
python salvage samples/mutated output/mutated
python tools/score.py samples/generated output/mutated --json output/mutation-score.json
```

The score utility reports field-level exact-match accuracy and format-detection precision/recall. Corruption tests compare unaffected recoverable fields; they do not claim that arbitrary changes to unchecksummed fields can always be detected.

## Repository layout

```text
salvage                 POSIX launcher / Docker entrypoint
salvage.cmd             Windows launcher
src/salvage/            CLI, pipeline, identification, reporting and format plugins
tests/                  Unit, integration, fuzz and golden tests
tools/                  Sample, corruption, scoring and analysis utilities
schema/                 Output schemas
Dockerfile              Offline-oriented, configurable Python image
Makefile                build, test, run, clean targets
FORMAT-SPEC.md          Per-format field layouts and evidence status
FIELD-LOG.md            Dated hypothesis/test/result/conclusion log
```
