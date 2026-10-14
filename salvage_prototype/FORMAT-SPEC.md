# SALVAGE Format Specification

## Scope

This document describes the fictional STUD format used to test the initial plugin architecture. It is not an official hackathon format.

## STUD binary layout

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 4 bytes | Signature | ASCII bytes `STUD` |
| 4 | 1 byte | Version | Unsigned byte |
| 5 | 1 byte | Name length | Number of bytes declared for the name |
| 6 | Variable | Name | Name bytes; decoded strictly as UTF-8, with raw hex preserved if invalid |

Offsets are zero-based. The name length is a byte count. The valid sample `53 54 55 44 01 03 41 6E 75` contains version 1 and name `Anu`.

## Status rules

- Unrecognized signature: `unsupported`.
- `STUD` signature but fewer than six bytes: `damaged`.
- Declared name length larger than available bytes: `partial` when available bytes decode, otherwise `damaged`.
- Invalid UTF-8 name bytes: `damaged`; `name` is `null`, `name_raw_hex` preserves the exact bytes, and no replacement characters are inserted.
- Complete valid name: `recovered`.

The output status vocabulary is exactly `recovered`, `partial`, `damaged`, `unsupported`, and `error`. Damage entries contain `field`, `offset`, `expected`, `found`, and `reason`; output shaping adds a zero-based, half-open `byte_range`. Per-file `counts` separates complete records recovered, records damaged, and records lost. Counts do not guess the number of records in unsupported files.

For truncation, byte ranges are zero-based and half-open. No checksum, compression, or archive index is defined by this toy format. Do not apply these assumptions to challenge formats without evidence.

## Plugin contract

A `FormatPlugin` provides `detect(data) -> confidence` in the range 0..1 and `decode(data) -> Result`. A `Result` contains records, damage, format, status, data and errors. The registry evaluates plugins deterministically in registration order and selects the highest valid confidence. The generic fallback has low nonzero confidence and returns unsupported without fabricating content.

## Official challenge formats

Add format descriptions only after validating field offsets, lengths, endianness, checksums and recovery behaviour against official samples or specifications.

## Declarative field-spec engine

`src/salvage/formats/base.py` provides `FieldSpec`, `decode_fields`, and `FormatPlugin.decode_spec`. Field specs are decoded in order; optional absolute offsets are relative to the record's starting offset. A short field yields the bytes/value available plus a structured `Damage` entry, and decoding continues where possible. The engine accepts `FieldSpec` instances or dictionaries with matching keys.

Supported field types include `u8/u16/u32`, `i8/i16/i32`, `f32/f64` (also `float`/`double` aliases), `fixed_bytes`, `fixed_string`, `length_prefixed_string`, `dos_date`, `dos_time`, `dos_datetime`, `unix_timestamp`, `bcd`, `julian_date`, `array`, and `index_table`. Fields can specify `endianness`, `length`, `length_source`, `encoding`, `validators`, array `count` / `item_type` / `item_size`, and index-table `offset_from` / `target_fields`. Validators support `nonzero`, `positive`, `min:N`, `max:N`, `one_of:a,b`, and callables.

The STUD plugin now declares its signature, version, name length and UTF-8 name using this engine. Its externally visible `data` and `records` shape for valid files remains `{ "version": 1, "name": "Anu" }` for the canonical sample; the signature remains structural and is not added to the result object. Invalid UTF-8 is preserved as hex, not replacement text.

Date conventions: DOS date/time use the conventional packed 16-bit DOS fields; Unix timestamps are unsigned seconds rendered in UTC; `julian_date` interprets an unsigned integer as a Julian Day Number and returns an ISO Gregorian date. These conventions must be checked against the target format's actual specification before use.


### Field bounds, validators, and block checksums

`FieldSpec` also accepts `minimum`, `maximum`, `enum_values`, and `max_length`. Failed checks add structured damage and preserve the observed decoded value; they never clamp, replace, or repair the source bytes. A configured `max_length` is a validation limit only: the reader still attempts a bounded read of the declared field and reports truncation or the limit violation.

`BlockSpec` can be passed to `decode_fields(..., blocks=[...])` or `FormatPlugin.decode_spec(..., blocks=[...])`. It defines an absolute `offset`, `length`, and optionally a `checksum_offset`, `checksum_type`, `checksum_length`, `checksum_endianness`, and explicit `checksum_range`. Supported checksum algorithms are `crc32`, `crc16` (Modbus/IBM reflected), `crc16_ccitt`, `sum8`, `sum16`, `xor8`, and `fletcher16`. With no explicit coverage range, the checksum is calculated across the block excluding its stored checksum bytes. Block and checksum bounds are validated before verification. A failed check records the reason, affected byte range, stored/calculated values where available, and raw hexadecimal bytes; the input is never corrected.

Validator failures for ranges and enumerations preserve raw field bytes as `raw_hex` in damage diagnostics. The `minimum`/`maximum` checks are inclusive, and `enum_values` is an explicit set/list of allowed decoded values. All byte offsets and ranges remain zero-based and half-open.

## Invented golden-test formats

`tools/gen_samples.py` generates three fictional formats using only the Python standard library. The generator accepts `--seed` and writes a `.truth.json` file beside each binary fixture. These formats are local test fixtures, not claims about real-world legacy formats.

### ASTER (`ARCF`)

- Header: ASCII magic `ARCF`, 16-bit big-endian version, 16-bit big-endian record count.
- Records: fixed 12-byte records, big-endian numeric fields: `item_id:u16`, `kind:u8`, `nominal_span:u16`, `quantity:u16`, `score:i16`, and a three-byte ASCII `code`.
- `nominal_span` is intentionally a misleading length-looking category value. It is never used to calculate record boundaries; record boundaries are determined by the fixed 12-byte record size.

### CRC_BLOCKS (`CRCB`)

- Header: magic `CRCB`, one-byte version, 16-bit little-endian block count.
- Each block: 16-bit little-endian payload length, payload, and little-endian CRC32 of the payload.
- Payload: little-endian `sequence:u16`, little-endian signed `reading:i32`, one-byte UTF-8 label length, then label bytes.

### XIDX (`XIDX`)

- Header: magic `XIDX`, one-byte version, one-byte entry count, 16-bit big-endian index-table offset.
- Index entries are 10 bytes: big-endian blob offset, packed length, decoded length, and label offset (each `u16`), then label length and XOR key (`u8` each).
- Blobs use count/value RLE pairs. Labels are UTF-8 bytes XOR-obfuscated with the entry's single-byte key.
- Offsets are absolute from the beginning of the file. Table and target bounds are validated before interpretation.

Generate fixtures with:

```sh
python tools/gen_samples.py --output-dir samples/generated --seed 1337
```

Each `.bin.truth.json` is the fixture's expected decoded data and is used by `tests/golden/test_real_format_golden.py` to check decoder results exactly.

## Corruption and scoring utilities

`tools/corrupt.py INPUT_DIR OUTPUT_DIR --seed N --per-type K` generates deterministic mutated copies using four operations: suffix truncation at a seeded random offset, a single-bit flip, zeroing a contiguous block, and swapping adjacent bytes. It writes `manifest.json` containing the source file, output filename, mutation kind, byte range, seed and original/mutated lengths. The ground-truth sidecars are not copied into the mutation corpus.

`tools/score.py TRUTH_DIR RESULTS_DIR` compares per-file output JSON against `*.truth.json` fixtures and prints a table with exact field matches and format decisions. `--json PATH` additionally writes a machine-readable summary. Field accuracy counts exact leaf-value matches over expected leaves; format detection precision and recall use exact format-name matches across the fixture set.

The fuzz tests execute the actual CLI subprocess for every seeded mutation and require exit code zero, parseable per-file JSON and `report.json`, and ground-truth equality for non-null fields whose source bytes and framing dependencies were not mutated. This distinction is intentional: in a format without checksums, parity, or redundant data, a bit-flipped value may remain structurally valid and cannot be identified as corrupt from the bytes alone.
