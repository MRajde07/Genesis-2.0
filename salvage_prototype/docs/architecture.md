# SALVAGE Architecture

## Processing Pipeline

```text
Command-line arguments
        |
        v
Input directory validation
        |
        v
Deterministic file scan
        |
        v
Binary signature detection
        |
        v
Known-format decoder
        |
        v
Bounds checks and recovery status
        |
        v
Per-file JSON output
        |
        v
Aggregate report.json
```

## Design Principles

- **Offline first:** Processing must not depend on network services.
- **Defensive parsing:** Check available bytes before reading fields.
- **Evidence-based recovery:** Recover only fields supported by the available data.
- **Fault isolation:** A malformed file should not unnecessarily prevent other files from being processed.
- **Traceability:** Report detected formats, status, and errors.
- **Schema compliance:** Adapt the output model to the official challenge schema.

## Current Implementation

The prototype implements a single fictional STUD decoder. The pipeline will be extended with separate decoders after the official challenge formats are available.
