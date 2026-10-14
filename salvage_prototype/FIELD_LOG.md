# SALVAGE Field Log

## 2026-10-14 — Prototype Development

### Goal

Create an offline command-line prototype for binary file identification, safe field extraction, and JSON reporting.

### Confirmed Observations

- The prototype recognizes the four-byte ASCII signature `STUD`.
- The demonstration header uses a one-byte version and a one-byte name length.
- The name begins at byte offset 6.
- A valid sample containing `Anu` is decoded successfully.
- Unknown signatures are reported as unsupported.
- A truncated name can be partially recovered and reported.
- Individual JSON results and an aggregate report are generated.

### Current Test Coverage

The automated test suite is designed to cover valid STUD data, unknown data, truncated data, empty files, and batch reporting.

Record the actual test outcome after running the test suite.

### Known Limitations

- STUD is a fictional practice format.
- Official challenge schemas and samples have not yet been incorporated.
- Format-specific checksums, archive structures, compression, and advanced recovery remain unimplemented.

### Next Actions

1. Record the official format samples and schemas.
2. Test hypotheses against multiple files.
3. Record confirmed field boundaries and validation rules.
4. Document malformed samples and recovery outcomes.
5. Avoid treating unverified bytes as confirmed fields.