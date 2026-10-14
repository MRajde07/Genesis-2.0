# SALVAGE Format Specification

## 1. Scope

This document describes the fictional STUD format used to test the SALVAGE prototype. It is not an official hackathon format.

## 2. STUD Binary Layout

| Offset | Size | Field | Description |
|---:|---:|---|---|
| 0 | 4 bytes | Signature | ASCII bytes `STUD` |
| 4 | 1 byte | Version | Unsigned byte representing the demo version |
| 5 | 1 byte | Name length | Number of bytes declared for the name |
| 6 | Variable | Name | UTF-8 text in the demo implementation |

All offsets are zero-based. The current implementation treats the name length as a byte count.

## 3. Example

The sample byte sequence is:

```text
53 54 55 44 01 03 41 6E 75
```

Interpretation:

- `53 54 55 44` — `STUD` signature
- `01` — version 1
- `03` — name length of 3 bytes
- `41 6E 75` — text `Anu`

## 4. Validation and Recovery

- A missing or unrecognized signature results in `unsupported`.
- A recognized signature with an incomplete header results in `damaged`.
- A declared name length exceeding the available bytes results in `partially_recovered`.
- A complete demo record results in `success`.

Recovered text is decoded with replacement characters for invalid UTF-8 sequences. This behavior is specific to the demonstration implementation.

## 5. Known Limitations

This toy format has no checksum, archive index, compression, or official schema. No assumptions in this document should be applied to actual challenge formats without evidence from their samples or specifications.

## 6. Official Challenge Formats

Complete this section after the organizers release the official samples and specifications. Record confirmed field offsets, sizes, byte order, validation rules, and recovery behavior separately for each format.