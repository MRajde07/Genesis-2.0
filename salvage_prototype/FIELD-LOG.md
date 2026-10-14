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
