# SALVAGE Field Log

## 2026-10-15 — Plugin architecture refactor

### Goal

Move the single-file prototype into a standard-library-only package while preserving observable STUD output behaviour.

### Confirmed from the prototype

- STUD signature: four bytes `STUD`.
- Version: one byte at offset 4.
- Name length: one byte at offset 5.
- Name bytes begin at offset 6.
- Valid STUD files return `success`; short headers return `damaged`; truncated names return `partially_recovered`.
- Unknown signatures return `UNKNOWN` / `unsupported`.
- The original STUD decoder uses UTF-8 replacement decoding. This was retained for behavioural compatibility in this refactor.

### Architecture added

- `FormatPlugin` base class and `Result` / `Damage` data structures.
- Deterministic `PluginRegistry` with STUD and generic fallback plugins.
- CLI, pipeline, output and report modules.
- POSIX `salvage` and Windows `salvage.cmd` launchers.
- Tests for registry selection, STUD damage ranges and missing input directory.

### Assumptions / unverified

- Plugin selection uses the highest valid confidence; ties go to the first registered plugin.
- Generic fallback intentionally returns no extracted content because no structure is supported by evidence.
- The full hidden hackathon format set is not available yet.
- Cross-platform Windows execution and Docker image build must be verified in their target environments.


## 2026-10-15 — Structured damage and output shaping

### Implemented

- STUD parsing now uses `ByteReader` for bounds-checked header and name reads. Reader diagnostics are retained as structured damage entries instead of being flattened into error strings.
- Output shaping is centralized in `src/salvage/output.py`; the pipeline and report module delegate to it.
- Adopted the status vocabulary `recovered`, `partial`, `damaged`, `unsupported`, and `error`.
- Per-file output includes `counts.records_recovered`, `counts.records_damaged`, `counts.records_lost`, structured `damage`, and normalized `byte_ranges`. The batch report aggregates statuses and record counts.
- Invalid UTF-8 names are not decoded with replacement. The name is `null`, exact bytes are returned in `name_raw_hex`, and the damaged byte range is reported.
- Added output-shaping tests for complete STUD, truncated names, invalid UTF-8 and counts.

### Counting assumptions

- Counts are mutually exclusive: complete records increment recovered; records with any byte or text-decoding damage increment damaged; a known damaged record that could not be reconstructed at all increments lost.
- Unsupported files do not increment record-lost counts because the number or structure of their records is unknown.
- Byte ranges are zero-based and half-open. For missing bytes, the range represents the absent interval; for invalid UTF-8, it identifies the invalid sequence.
- Windows execution and the Docker build have not been verified in this run.


## Generic analysis modules

Implemented pure-function analysis helpers for windowed Shannon entropy and histograms; ASCII, UTF-16LE/BE and CP437 strings with offsets; endian-aware integer scans; candidate length fields; fixed-size record hypotheses; CRC16/CRC32, sum8/sum16, XOR and Fletcher checksum guesses; single-byte and repeating-key XOR hypotheses; and count/value RLE detection/decoding. Added `tools/probe.py` and `tools/hexview.py`. The generic fallback includes bounded findings and explicitly labels inferred structures as unverified. Heuristics can produce false positives, especially for CP437 strings, record sizes, checksum coincidences, XOR and RLE.

## 2026-10-15 — Declarative field-spec engine

### Implemented

- Added `FieldSpec`, `FieldDecode`, `decode_fields`, and `FormatPlugin.decode_spec` in `formats/base.py`.
- Added endian-aware signed/unsigned integers, IEEE-754 floats, fixed and length-prefixed strings, fixed bytes/signatures, packed DOS date/time, UTC Unix timestamps, BCD, Julian Day Number conversion, arrays, and index tables with optional offset-based target record decoding.
- Added declarative validators (`nonzero`, `positive`, `min:N`, `max:N`, `one_of:...`, or callable predicates).
- Short reads preserve available data and emit structured damage entries with zero-based half-open byte ranges. Partial record data remains available.
- Re-expressed STUD using `FieldSpec` declarations while preserving valid output shape and strict UTF-8 behavior.
- Added field-spec tests for types, endianness, truncated strings, dates/timestamps, BCD, arrays/index tables, validators, and STUD compatibility.

### Assumptions / unverified

- Float fields are IEEE-754 binary32/binary64.
- DOS datetime bytes are packed date then packed time, using the configured endianness.
- Unix timestamps are unsigned seconds from the Unix epoch and are displayed in UTC.
- `julian_date` treats the integer as a Julian Day Number and maps it to an ISO date; challenge formats may use a different epoch or fractional convention.
- Length-prefixed strings use an integer prefix specified by `prefix_type` (default `u8`).
- Index tables default to unsigned 32-bit entries; `offset_from` adjusts offsets, and target records are decoded only when `target_fields` are supplied.
- The field engine is standard-library-only. Platform-specific Windows and Docker verification remains outstanding.
