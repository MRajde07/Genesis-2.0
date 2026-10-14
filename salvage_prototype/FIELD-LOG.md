# SALVAGE Field Log

Use this dated template for each new investigation. Separate what was tested from what was inferred; never promote an unverified hypothesis to a confirmed format fact without evidence.

## New-entry template

```markdown
## YYYY-MM-DD — Short experiment title

### Hypothesis
- What is expected, and why?

### Test
- Exact fixture/sample, command, test, or observation used.
- Environment and version details when relevant.

### Result
- Observed output, pass/fail, measurements, and relevant byte offsets.

### Conclusion
- Confirmed findings and remaining unverified assumptions.
- Follow-up work, if any.
```

---

## 2026-10-15 — Plugin architecture refactor

### Hypothesis
The original single-file STUD prototype can be moved into a standard-library-only package without changing its observable valid-file output or its core failure behaviour.

### Test
- Unit tests for registry selection, STUD damage ranges, and missing input directory.
- Compare canonical STUD behaviour and output fields against the existing prototype.

### Result
- Added `FormatPlugin`, `Result`, and `Damage`, a deterministic `PluginRegistry`, CLI/pipeline/output/report modules, and POSIX/Windows launchers.
- STUD uses a four-byte `STUD` signature, version byte at offset 4, name-length byte at offset 5, and name bytes from offset 6.
- Historical prototype behaviour used UTF-8 replacement decoding; later structured-damage work deliberately changed invalid UTF-8 handling to preserve raw bytes.

### Conclusion
The package/plugin architecture and compatibility intent are implemented. Registry ties resolve to the first registered plugin after confidence ranking. The generic fallback does not fabricate decoded fields. The full hidden hackathon format set is unavailable. Windows and Docker behaviour must be verified in their target environments.

## 2026-10-15 — Structured damage and output shaping

### Hypothesis
Centralized output shaping and bounds-checked reads can make corruption diagnosable while keeping output deterministic and preserving recoverable data.

### Test
- Unit tests for complete STUD data, truncated names, invalid UTF-8, damage ranges, and record counts.
- Exercise missing input and per-file failure handling.

### Result
- STUD parsing uses `ByteReader`; reader diagnostics are represented as structured damage.
- Output shaping is centralized in `src/salvage/output.py`.
- Statuses are `recovered`, `partial`, `damaged`, `unsupported`, and `error`.
- Per-file output carries recovered/damaged/lost counts, `damage`, and normalized `byte_ranges`; the batch report aggregates statuses and counts.
- Invalid UTF-8 yields `name: null`, preserves exact bytes in `name_raw_hex`, and reports a damage range.

### Conclusion
Counts are mutually exclusive: complete records count as recovered; records with byte/text damage count as damaged; known records that cannot be reconstructed count as lost. Unsupported files do not increment lost-record counts because their record count is unknown. Byte ranges are zero-based and half-open; a missing-byte range describes the absent interval. Windows and Docker were not verified during this experiment.

## 2026-10-15 — Generic binary analysis helpers

### Hypothesis
Bounded, standard-library-only heuristics can provide useful leads for unknown files without claiming speculative structures as facts.

### Test
- Implement pure helpers and expose them through `tools/probe.py` and `tools/hexview.py`.
- Exercise analysis helpers in unit and pipeline tests.

### Result
Implemented windowed Shannon entropy and histograms; ASCII, UTF-16LE/BE and CP437 string extraction with offsets; endian-aware integer candidates; length and fixed-record hypotheses; CRC16/CRC32, sum, XOR and Fletcher checksum guesses; single/repeating-key XOR hypotheses; and count/value RLE hypotheses. Generic findings are labelled `unverified` and bounded to the first 64 KiB for primary analysis.

### Conclusion
The helpers are investigative heuristics, not format decoders. False positives are expected, especially for CP437 strings, candidate record sizes, checksum coincidences, XOR, and RLE. Any proposed interpretation needs independent structural evidence.

## 2026-10-15 — Declarative field-spec engine

### Hypothesis
A shared field-spec engine can reduce duplicate parsing code while retaining bounds diagnostics and raw evidence.

### Test
- Unit tests for field types, endianness, truncation, dates/timestamps, BCD, arrays/index tables, validators, and STUD compatibility.

### Result
Added `FieldSpec`, `FieldDecode`, `decode_fields`, and `FormatPlugin.decode_spec`. Supported types include signed/unsigned integers, IEEE-754 floats, fixed bytes/strings, length-prefixed strings, DOS date/time, Unix timestamps, BCD, Julian Day Number, arrays, and index tables. Validators include `nonzero`, `positive`, `min:N`, `max:N`, `one_of:...`, and callable predicates. Short reads retain available values and add structured damage. STUD was re-expressed through field declarations.

### Conclusion
The engine is standard-library-only. Its generic conventions are assumptions until confirmed by a target format: floats are IEEE-754; DOS date/time use packed fields; Unix timestamps are unsigned seconds rendered in UTC; Julian dates use an integer Julian Day Number; string prefix type defaults to `u8`; index-table defaults are unsigned 32-bit entries. Format-specific conventions must be checked independently.

## 2026-10-15 — Field and block integrity checks

### Hypothesis
Declarative bounds, enum checks, and optional checksum validation can identify inconsistent fields/blocks without modifying source bytes.

### Test
- Tests for valid/failing CRC32 and other checksums, block bounds, field range/enum failures, raw-byte preservation, and invalid offsets.

### Result
Added `BlockSpec`; checksum algorithms include CRC32, CRC16/Modbus, CRC16-CCITT, sum8/sum16, XOR8, and Fletcher16. `FieldSpec` supports inclusive minimum/maximum, enum values, and maximum length. Failures produce structured damage and preserve raw bytes.

### Conclusion
`crc16` means reflected CRC-16/Modbus with initial value `0xFFFF`; `crc16_ccitt` uses polynomial `0x1021` and initial value `0xFFFF`. Legacy formats may differ. Block/checksum offsets are absolute; default checksum coverage excludes the stored checksum bytes. Diagnostics do not repair data or establish authenticity.

## 2026-10-15 — Invented fixture formats and golden tests

### Hypothesis
Known synthetic formats with deterministic ground truth can exercise endian handling, record framing, checksums, indexes, and transformations.

### Test
Generate fixtures using `tools/gen_samples.py` with a fixed seed; compare decoder output with adjacent `.truth.json` files using golden tests; run generation repeatedly to check determinism.

### Result
Added ASTER (`ARCF`), CRC_BLOCKS (`CRCB`), and XIDX (`XIDX`) synthetic plugins and fixtures. Golden tests check decoded fields, registry selection, ASTER's misleading `nominal_span`, CRC failure reporting without correction, and repeatability.

### Conclusion
These formats are deliberately invented test fixtures, not claims about external file formats. Their layouts are confirmed relative to the local generator and tests only.

## 2026-10-15 — Corruption fuzzing and scoring

### Hypothesis
Seeded mutations and a scoring utility can test crash resistance and quantify field recovery without claiming undetectable corruption is detectable.

### Test
Use `tools/corrupt.py` to generate suffix truncations, bit flips, zeroed ranges, and adjacent-byte swaps. Run the real CLI against mutations and compare unaffected recoverable fields to fixture ground truth. Use `tools/score.py` for exact field accuracy and format precision/recall.

### Result
The mutation manifest records source, mutation kind, affected range, seed, and lengths. Fuzz tests check zero exit status, parseable JSON, report creation, and unaffected fields. Scoring supports stable text and optional JSON output.

### Conclusion
A changed value in an unchecksummed field may remain structurally valid and cannot always be detected from the observed bytes alone. Tests deliberately avoid asserting otherwise.

## 2026-10-15 — Lotus 1-2-3 Release 1A WKS decoder

### Hypothesis
A conservative record-stream parser can recover a useful subset of Release 1A `.WKS` cells while preserving unknown bytes and avoiding guessed formula expressions.

### Test
- Synthetic unit fixtures for the BOF signature, supported cell records, unknown records, and truncation.
- Optional integration test searches `samples/` for real `.wks` files.
- End-to-end CLI test with a synthetic WKS stream.

### Result
Added `LOTUS_WKS` for BOF revision `0x0404`; parses INTEGER, NUMBER, LABEL, FORMULA, RANGE metadata, EOF, and unknown record envelopes. Formula tokens and unknown bodies are preserved as hex. Truncated records and missing EOF generate damage ranges. The optional real-sample test skips when no `.wks` sample exists.

### Conclusion
Synthetic behaviour is tested; real-file interoperability is unverified until representative real `.WKS` samples are available. Formula tokens are not evaluated or translated, display semantics are not inferred from the format byte, and complete formatting/control-record coverage is not claimed.

## 2026-10-15 — Packaging and offline build configuration

### Hypothesis
The CLI can be packaged in a configurable Python container and tested through Make without downloading Python packages or contacting the network during build/run.

### Test
- `make test` runs the standard-library unittest suite.
- `make build` invokes Docker with `--network=none` and `--pull=false`.
- Validate Dockerfile and Makefile syntax/configuration by inspection; Docker runtime verification is pending unless run on a host with Docker and the base image cached.

### Result
The Dockerfile uses `ARG PYTHON_VERSION` (default `3.12`), copies the repository, installs no dependencies, and uses `./salvage` as entrypoint. Make targets include `build`, `test`, `run`, and `clean`.

### Conclusion
The build is offline only when the selected `python:<version>-slim` base image is already cached locally. No claim is made that Docker can create a missing base image without network access. Actual image build/run remains environment-dependent.
