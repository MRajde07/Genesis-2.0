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
