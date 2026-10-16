# SALVAGE Format Specifications

This document describes parser behaviour, not a guarantee that every file matching a signature is authentic. **Confirmed** means the layout is established by the local prototype/generator and covered by tests, or explicitly supported by the parser's synthetic fixtures. For Lotus WKS, parser mechanics are synthetically tested but real-file interoperability is not yet confirmed. **Unverified** means the interpretation is heuristic, raw-only, convention-dependent, or has not been validated against independent real samples.

## Status vocabulary and byte ranges

Statuses are `recovered`, `partial`, `damaged`, `unsupported`, and `error`. Byte offsets and ranges are zero-based; ranges are half-open (`[start, end)`). Damage diagnostics do not repair or overwrite source bytes. Unknown-format findings are leads, not decoded facts.

## STUD

The original prototype format. The structural signature is omitted from the valid result data for compatibility.

| Field | Layout / interpretation | Evidence status | Notes |
|---|---|---|---|
| `signature` | Offset 0, 4 bytes, ASCII `STUD` | Confirmed | Required for detection; structural field, not emitted in `data`. |
| `version` | Offset 4, unsigned 8-bit integer | Confirmed | Positive values pass the declarative validator. |
| `name_length` | Offset 5, unsigned 8-bit byte count | Confirmed | Must be positive; counts encoded bytes, not Unicode characters. |
| `name` | Offset 6, `name_length` bytes, strict UTF-8 | Confirmed | Valid text returned as `name`; invalid UTF-8 yields `name: null`, `name_raw_hex`, and damage. |
| Valid result shape | `data: {version, name}` | Confirmed | Canonical sample `53 54 55 44 01 03 41 6e 75` yields version 1 and `Anu`. |

## ASTER (`ARCF`) — invented test format

The generator and golden tests define this local synthetic format; it is not a claim about an external format.

| Field | Layout / interpretation | Evidence status | Notes |
|---|---|---|---|
| `magic` | Offset 0, 4 bytes `ARCF` | Confirmed | Local generator and decoder agree. |
| `version` | Offset 4, unsigned 16-bit big-endian | Confirmed | Synthetic fixture contract. |
| `record_count` | Offset 6, unsigned 16-bit big-endian | Confirmed | Declares number of fixed-size records. |
| Record size | 12 bytes per record | Confirmed | Record boundaries use fixed size, not `nominal_span`. |
| `item_id` | Record +0, unsigned 16-bit big-endian | Confirmed | Synthetic fixture field. |
| `kind` | Record +2, unsigned 8-bit | Confirmed | Meaning beyond stored category is fixture-defined. |
| `nominal_span` | Record +3, unsigned 16-bit big-endian | Confirmed | Deliberately misleading length-looking value; not a record length. |
| `quantity` | Record +5, unsigned 16-bit big-endian | Confirmed | Synthetic fixture field. |
| `score` | Record +7, signed 16-bit big-endian | Confirmed | Synthetic fixture field. |
| `code` | Record +9, 3-byte ASCII | Confirmed | Invalid/partial bytes are handled by decoder diagnostics. |

## CRC_BLOCKS (`CRCB`) — invented test format

The generator and golden tests define this local synthetic format.

| Field | Layout / interpretation | Evidence status | Notes |
|---|---|---|---|
| `magic` | Offset 0, 4 bytes `CRCB` | Confirmed | Local fixture contract. |
| `version` | Offset 4, unsigned 8-bit | Confirmed | Synthetic fixture field. |
| `block_count` | Offset 5, unsigned 16-bit little-endian | Confirmed | Declares block count. |
| `payload_length` | Each block begins with unsigned 16-bit little-endian length | Confirmed | Length of payload only. |
| `payload.sequence` | Payload +0, unsigned 16-bit little-endian | Confirmed | Requires sufficient payload bytes. |
| `payload.reading` | Payload +2, signed 32-bit little-endian | Confirmed | Requires sufficient payload bytes. |
| `payload.label_length` | Payload +6, unsigned 8-bit | Confirmed | Byte count for UTF-8 label. |
| `payload.label` | Payload +7, declared number of UTF-8 bytes | Confirmed | Synthetic fixture contract; malformed/truncated labels are damaged. |
| `stored_crc32` | Four bytes after payload, little-endian CRC32 | Confirmed | Computed over payload bytes; mismatch is diagnostic only. |

## XIDX (`XIDX`) — invented test format

The generator and golden tests define this local synthetic format.

| Field | Layout / interpretation | Evidence status | Notes |
|---|---|---|---|
| `magic` | Offset 0, 4 bytes `XIDX` | Confirmed | Local fixture contract. |
| `version` | Offset 4, unsigned 8-bit | Confirmed | Generator emits version 1. |
| `entry_count` | Offset 5, unsigned 8-bit | Confirmed | Number of 10-byte index entries. |
| `index_offset` | Offset 6, unsigned 16-bit big-endian | Confirmed | Absolute file offset. |
| `blob_offset` | Entry +0, unsigned 16-bit big-endian | Confirmed | Absolute offset to packed RLE bytes. |
| `packed_length` | Entry +2, unsigned 16-bit big-endian | Confirmed | Length of packed blob. |
| `decoded_length` | Entry +4, unsigned 16-bit big-endian | Confirmed | Required RLE output length. |
| `label_offset` | Entry +6, unsigned 16-bit big-endian | Confirmed | Absolute offset to XOR-encoded label. |
| `label_length` | Entry +8, unsigned 8-bit | Confirmed | Encoded label byte count. |
| `xor_key` | Entry +9, unsigned 8-bit | Confirmed | Each encoded label byte is XORed with this value. |
| Blob encoding | Count/value RLE byte pairs | Confirmed | Zero count, odd packed length, overflow and length mismatch are errors. |
| Label text | XOR-decoded bytes interpreted as strict UTF-8 | Confirmed | Confirmed for the invented fixture contract only. |

## Lotus 1-2-3 Release 1A `.WKS`

The parser targets the BOF revision `0x0404`. Synthetic parser tests pass, but the integration test skips when no real `.wks` sample is available. Accordingly, the record framing and decoded byte operations below are **implementation-confirmed**; compatibility with arbitrary real-world files remains unverified.

| Field / record | Layout / interpretation | Evidence status | Notes |
|---|---|---|---|
| BOF opcode | Offset 0, unsigned 16-bit little-endian, value `0x0000` | Confirmed in implementation; real-file validation unverified | First record only is accepted as the supported signature. |
| BOF body length | Offset 2, unsigned 16-bit little-endian, value 2 | Confirmed in implementation; real-file validation unverified | Signature checks the exact six-byte prefix. |
| BOF revision | Offset 4, unsigned 16-bit little-endian, value `0x0404` | Confirmed in implementation; real-file validation unverified | Other revisions are not claimed as supported. |
| Record envelope | 16-bit LE opcode, 16-bit LE body length, then body | Confirmed in implementation; real-file validation unverified | Truncation yields structured damage. |
| INTEGER cell header | Body byte 0 format; bytes 1–2 column; bytes 3–4 row, both unsigned LE 16-bit | Confirmed in implementation; real-file validation unverified | Coordinates are retained and rendered as one-based `R#C#` addresses. |
| INTEGER value | Body bytes 5–6, signed LE 16-bit | Confirmed in implementation; real-file validation unverified | Body minimum is 7 bytes. |
| NUMBER value | Body bytes 5–12, LE IEEE-754 binary64 | Confirmed in implementation; real-file validation unverified | Body minimum is 13 bytes. |
| LABEL text | Body byte 5 prefix, remaining bytes text; CP437 decode | Implementation behaviour confirmed; prefix semantics unverified | Raw bytes and prefix are retained. Prefix/alignment interpretation is not a general guarantee. |
| FORMULA cached value | Body bytes 5–12, LE IEEE-754 binary64 | Confirmed in implementation; real-file validation unverified | Body minimum is 15 bytes. |
| FORMULA token length and stream | Token length and remaining token bytes are preserved by the parser | Raw preservation confirmed; token semantics unverified | No formula translation or evaluation; `formula_text` is null. |
| Cell format byte | Body byte 0 | Confirmed as raw byte; meaning unverified | Display/date/currency semantics are not inferred. |
| RANGE | First 8 body bytes parsed as four LE 16-bit coordinate values | Raw parse confirmed; coordinate meaning unverified | Output explicitly labels the interpretation unverified. |
| EOF | Opcode `0x0001`; parser expects empty body | Confirmed in implementation; real-file validation unverified | Missing EOF or trailing bytes produce diagnostics. |
| Unknown records | Opcode, declared length and body hex | Raw preservation confirmed; meaning unverified | Unknown records cause partial status and are never semantically decoded. |

## Generic / unknown files

There is no universal field layout for unknown files. The generic fallback does not claim to decode a schema.

| Finding | Method / interpretation | Evidence status | Notes |
|---|---|---|---|
| Byte histogram | Counts of byte values | Confirmed computation | Descriptive statistics only. |
| Windowed entropy | Shannon entropy over bounded windows | Confirmed computation | Does not prove encryption or compression. |
| Printable strings | ASCII, UTF-16LE/BE and CP437 candidates with offsets | Heuristic / unverified | False positives are expected. |
| Integer candidates | Endian-aware numeric scans | Heuristic / unverified | Candidate values are not field definitions. |
| Length fields / record sizes | Plausible lengths and repeated-size hypotheses | Heuristic / unverified | Require independent structural confirmation. |
| Checksums | CRC16/CRC32, sum, XOR and Fletcher candidates | Heuristic / unverified | Coincidental matches are possible. |
| XOR / RLE | Single/repeating-key XOR and count/value RLE candidates | Heuristic / unverified | Transformations are not trusted without validation. |

## Shared declarative field engine (not a file format)

These are parser capabilities, not evidence that a target format uses a given convention.

| Capability / field type | Behaviour | Evidence status | Notes |
|---|---|---|---|
| Integer and float types | Signed/unsigned 8/16/32-bit integers and IEEE-754 `f32`/`f64` | Confirmed implementation | Endianness is explicit/configurable. |
| Fixed bytes / strings | Fixed-length bytes or decoded string | Confirmed implementation | Encoding must be selected for the target format. |
| Length-prefixed string | Prefix type defaults to `u8` | Default confirmed; format convention unverified | Target format must define prefix width and encoding. |
| DOS date/time | Packed DOS date and time | Implementation convention confirmed; target convention unverified | Must be validated per format. |
| Unix timestamp | Unsigned seconds from epoch, rendered UTC | Implementation convention confirmed; target convention unverified | Other units/epochs are possible. |
| BCD / Julian date | BCD decoding / integer Julian Day Number conversion | Implementation convention confirmed; target convention unverified | Formats may use alternate conventions. |
| Arrays / index tables | Configurable count/item type and offsets | Implementation confirmed; target layout unverified | Index entries are decoded only according to supplied specs. |
| Field validators | Range, enum and predicate checks | Confirmed implementation | Diagnostic only; values are not repaired. |
| Block checksums | CRC32, CRC16/Modbus, CRC16-CCITT, sum8/sum16, XOR8, Fletcher16 | Confirmed implementation | Algorithm parameters and coverage must match the target specification. |

## Official challenge formats

No official hidden challenge format has been independently confirmed in this repository yet. Add a format section only after testing field offsets, lengths, endianness, checksum rules and recovery behaviour against an authoritative specification or representative samples.

## Declarative learned-spec interpreter

The interpreter under `src/salvage/learned/` consumes JSON-only specs. It supports a fixed header field list, an optional fixed-stride record section (`count_field`, `offset`, `stride`, and field specs), and optional checksum blocks using the shared `FieldSpec` / `BlockSpec` engine. The signature and minimum file length contribute to identification; structural bounds and declared checksums are validated when present. Invalid or truncated bytes are diagnosed and never repaired. The interpreter imposes a maximum declared record count of 1,000,000 and only iterates records that could fit in the input.

The current `tools/train.py` is intentionally conservative: it infers only flat fixed-width scalar fields that are uniquely located across multiple samples and verifies the final sorted sample as a holdout. It refuses nested data, transformations, and ambiguous field layouts. A rejected training set is not evidence that the format is unsupported; it means the current inference method cannot justify a safe spec.

The checked-in `LEARNED_STUD` and `LEARNED_ASTER` specs are demonstrations of declarative interpretation on synthetic fixture formats. They are not claims about external file formats and are not yet substitutes for the legacy decoders' complete output shapes.
