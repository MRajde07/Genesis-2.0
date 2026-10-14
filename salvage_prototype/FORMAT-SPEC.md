# SALVAGE Format Specification

## Scope

This document describes the fictional STUD format used to test the initial plugin architecture. It is not an official hackathon format.

## STUD binary layout

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 4 bytes | Signature | ASCII bytes `STUD` |
| 4 | 1 byte | Version | Unsigned byte |
| 5 | 1 byte | Name length | Number of bytes declared for the name |
| 6 | Variable | Name | Name bytes; the prototype decodes as UTF-8 with replacement |

Offsets are zero-based. The name length is a byte count. The valid sample `53 54 55 44 01 03 41 6E 75` contains version 1 and name `Anu`.

## Status rules

- Unrecognized signature: `unsupported`.
- `STUD` signature but fewer than six bytes: `damaged`.
- Declared name length larger than available bytes: `partially_recovered`.
- Complete name: `success`.

For truncation, byte ranges are zero-based and half-open. No checksum, compression, or archive index is defined by this toy format. Do not apply these assumptions to challenge formats without evidence.

## Plugin contract

A `FormatPlugin` provides `detect(data) -> confidence` in the range 0..1 and `decode(data) -> Result`. A `Result` contains records, damage, format, status, data and errors. The registry evaluates plugins deterministically in registration order and selects the highest valid confidence. The generic fallback has low nonzero confidence and returns unsupported without fabricating content.

## Official challenge formats

Add format descriptions only after validating field offsets, lengths, endianness, checksums and recovery behaviour against official samples or specifications.
