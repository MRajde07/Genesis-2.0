# SALVAGE

SALVAGE is an offline, standard-library-only Python CLI for identifying and conservatively inspecting binary files. It preserves uncertain bytes and reports structural damage rather than silently repairing data.

## Run

```sh
./salvage <input_dir> <output_dir>
./salvage <input_dir> <output_dir> --debug
```

The public result/report JSON schemas are in `schema/`. Internal decoder names are not necessarily public format names; only confirmed organiser-vocabulary mappings are exposed as public format labels.

## Learned declarative specs

`src/salvage/learned/specs/*.json` contains data-only format descriptions interpreted by `src/salvage/learned/interpreter.py`. Specs may define a signature, fixed fields, fixed-stride records, field validators and checksum-protected blocks. They cannot execute Python code. The interpreter bounds record counts and retains diagnostics for truncated or invalid data.

The checked-in `LEARNED_STUD` and `LEARNED_ASTER` specs are demonstrations based on the repository's synthetic fixtures. They are registered alongside legacy decoders for comparison; they do not replace the legacy decoders, and their internal names are not advertised as public formats.

### Training a simple fixed-field spec

The developer-only trainer accepts a directory of at least three `*.bin` samples. Each binary must have a sidecar named exactly `<sample>.bin.expected.json`, for example `one.bin.expected.json`:

```json
{
  "format": "DEMO",
  "expected": {
    "serial": 513,
    "label": "ABCD"
  }
}
```

Run:

```sh
python tools/train.py samples/training --output src/salvage/learned/specs/demo.json
```

The final sample in filename order is held out. The trainer currently supports only flat scalar fields whose fixed-width encoding and offset are uniquely inferable from the training samples. It rejects ambiguity, overlapping fields, missing/contradictory values, short corpora, and nested/transformed data rather than guessing. It does not yet infer variable-length records, compression, XOR transforms, or general checksum layouts. Validate any generated spec on independent real files and corruption cases before trusting it.

## Tests

```sh
python -m unittest discover -s tests -p "test_*.py" -v
```

The real Lotus WKS sample integration test is skipped when no real `.WKS` sample is present under `samples/`.
