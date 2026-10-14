# Genesis-2.0
# SALVAGE — Binary File Recovery Toolkit

SALVAGE is an offline command-line prototype designed to identify binary file formats, decode known structures, detect truncated data, and report recovery results as JSON.

> **Prototype notice:** The current implementation supports a fictional demonstration format called STUD. Support for the actual hackathon formats must be implemented after their specifications and sample files are released.

## Features

- **Offline processing:** Runs locally without requiring an internet connection.
- **Signature detection:** Identifies the demo STUD format using its file signature.
- **Structured extraction:** Extracts the version and name fields from valid STUD files.
- **Damage handling:** Detects truncated headers and incomplete name fields.
- **Unknown-format handling:** Reports unsupported files without stopping the entire batch.
- **JSON output:** Generates a JSON result for each input file.
- **Batch report:** Creates a report summarizing the files processed.

## Requirements

- Python 3.10 or newer
- No third-party Python packages required

## Project Structure

```text
salvage_prototype/
├── salvage.py
├── README.md
├── FORMAT_SPEC.md
├── FIELD_LOG.md
├── Dockerfile
├── .gitignore
├── input_dir/
├── output_dir/
├── tests/
│   ├── __init__.py
│   └── test_salvage.py
└── docs/
    ├── architecture.md
    └── demo-notes.md
```

## Run SALVAGE

From the project root, run:

```powershell
python salvage.py ./input_dir ./output_dir
```

The first argument is the input directory. The second argument is the output directory.

SALVAGE processes regular files in the input directory and writes the results to the output directory.

## Try the Demo

Create a sample STUD file:

```powershell
python -c "from pathlib import Path; Path('input_dir/student.bin').write_bytes(b'STUD\x01\x03Anu')"
```

Run the program:

```powershell
python salvage.py ./input_dir ./output_dir
```

The sample contains the STUD signature, version `1`, a name length of `3`, and the name `Anu`.

## Output Files

For an input file named `student.bin`, SALVAGE creates:

- `student.bin.json` — the individual processing result
- `report.json` — the batch report containing results for all processed files

Each individual result includes the filename, detected format, processing status, extracted data, and any reported errors.

Possible statuses include:

- `success` — the demo file was decoded successfully.
- `partially_recovered` — some data was recovered, but a declared field was truncated.
- `damaged` — the file was too short to contain the complete demo header.
- `unsupported` — the signature was not recognized.
- `error` — an input file could not be read or processed.

## Run the Tests

Run the automated test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

The tests cover valid files, unknown formats, truncated files, empty files, and batch reporting.

## Architecture

1. Read command-line arguments.
2. Validate the input directory and prepare the output directory.
3. Scan input files in a deterministic order.
4. Identify supported file signatures.
5. Decode available fields and check field boundaries.
6. Record errors and recovery status.
7. Write per-file JSON results and the aggregate report.

## Limitations

- Only the fictional STUD demonstration format is currently supported.
- The prototype does not yet implement the actual challenge formats.
- It does not yet implement format-specific checksums, archive indexes, compression schemes, or advanced recovery.
- The current output structure is provisional and must be adapted to the official hackathon JSON schema.

## Development Roadmap

1. Inspect official challenge samples and schemas.
2. Implement format detection for each required format.
3. Add format-specific decoders and integrity checks.
4. Implement evidence-based recovery for damaged files.
5. Match the official JSON schema exactly.
6. Expand tests using valid, malformed, and truncated challenge samples.
7. Validate offline execution and packaging.

<!-- ## License

Add the license required by the project or hackathon organizers. -->