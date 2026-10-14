"""Evidence-based, deterministic format identification.

``identify`` returns ranked candidate dictionaries.  Each candidate contains a
plugin reference for internal use, a confidence score in [0, 1], and an
explanation of every clue considered.  The plugin reference is intentionally
excluded from serialized output by callers.
"""
from __future__ import annotations

from typing import Any, Iterable

from .formats.base import FormatPlugin
from .formats.generic import GenericPlugin
from .formats.registry import PluginRegistry, default_registry

DEFAULT_THRESHOLD = 0.55

# Weighted evidence contributions. Contradictions are also reported and apply
# a penalty, so a matching signature alone cannot dominate structural evidence.
_WEIGHTS = {
    "detect": 0.55,
    "signature_at_start": 0.25,
    "signature_at_offset": 0.08,
    "header_length": 0.10,
    "plausible_fields": 0.15,
    "checksum": 0.20,
}
_CONTRADICTION_PENALTY = 0.20


def _clue(name: str, matched: bool | None, detail: str, score: float = 0.0,
          weight: float = 0.0, contradiction: bool = False) -> dict[str, Any]:
    return {
        "clue": name,
        "matched": matched,
        "score": round(max(0.0, min(1.0, score)), 4),
        "weight": round(weight, 4),
        "contradiction": contradiction,
        "detail": detail,
    }


def _signature_clues(plugin: FormatPlugin, data: bytes) -> list[dict[str, Any]]:
    signatures: list[bytes] = []
    one = getattr(plugin, "signature", None)
    if isinstance(one, bytes) and one:
        signatures.append(one)
    many = getattr(plugin, "signatures", ())
    if isinstance(many, (list, tuple, set)):
        signatures.extend(value for value in many if isinstance(value, bytes) and value)
    # Preserve declaration order while avoiding duplicate evidence.
    signatures = list(dict.fromkeys(signatures))
    if not signatures:
        return []

    matches: list[tuple[int, bytes]] = []
    for signature in signatures:
        offset = data.find(signature)
        if offset >= 0:
            matches.append((offset, signature))
    if not matches:
        return [_clue("signature", False, "No declared signature found", 0.0, 0.0)]

    offset, signature = min(matches, key=lambda item: (item[0], item[1]))
    if offset == 0:
        return [_clue("signature_at_start", True,
                      f"Signature {signature.hex()} found at offset 0", 1.0,
                      _WEIGHTS["signature_at_start"])]
    return [_clue("signature_at_offset", True,
                  f"Signature {signature.hex()} found at offset {offset}, not at file start",
                  1.0, _WEIGHTS["signature_at_offset"])]


def _collect_evidence(plugin: FormatPlugin, data: bytes) -> tuple[float, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    contradiction_count = 0
    score_total = 0.0

    try:
        raw_detect = float(plugin.detect(data))
        detect_score = raw_detect if 0.0 <= raw_detect <= 1.0 else 0.0
        evidence.append(_clue("detect", 0.0 <= raw_detect <= 1.0,
                              f"Plugin detect() returned {raw_detect!r}", detect_score,
                              _WEIGHTS["detect"], contradiction=not 0.0 <= raw_detect <= 1.0))
        score_total += detect_score * _WEIGHTS["detect"]
        if not 0.0 <= raw_detect <= 1.0:
            contradiction_count += 1
    except Exception as error:
        evidence.append(_clue("detect", False,
                              f"Plugin detect() raised {type(error).__name__}", 0.0,
                              _WEIGHTS["detect"], contradiction=True))
        contradiction_count += 1

    for item in _signature_clues(plugin, data):
        evidence.append(item)
        score_total += item["score"] * item["weight"]

    header_length = getattr(plugin, "header_length", None)
    if isinstance(header_length, int) and header_length >= 0:
        enough = len(data) >= header_length
        clue_score = 1.0 if enough else (len(data) / header_length if header_length else 1.0)
        evidence.append(_clue(
            "header_length", enough,
            f"Header requires {header_length} bytes; file has {len(data)} bytes",
            clue_score, _WEIGHTS["header_length"], contradiction=not enough,
        ))
        score_total += clue_score * _WEIGHTS["header_length"]
        if not enough:
            contradiction_count += 1

    # A plugin can expose plausible_fields(data) -> bool or a detail dictionary
    # with {valid: bool, detail: str}. This is deliberately optional.
    validator = getattr(plugin, "plausible_fields", None)
    if callable(validator):
        try:
            validation = validator(data)
            if isinstance(validation, dict):
                valid = bool(validation.get("valid", False))
                detail = str(validation.get("detail", "Plugin field plausibility check"))
            else:
                valid = bool(validation)
                detail = "Plugin field plausibility check passed" if valid else "Plugin field plausibility check failed"
            evidence.append(_clue("plausible_fields", valid, detail, 1.0 if valid else 0.0,
                                  _WEIGHTS["plausible_fields"], contradiction=not valid))
            if valid:
                score_total += _WEIGHTS["plausible_fields"]
            else:
                contradiction_count += 1
        except Exception as error:
            evidence.append(_clue("plausible_fields", False,
                                  f"Field check raised {type(error).__name__}", 0.0,
                                  _WEIGHTS["plausible_fields"], contradiction=True))
            contradiction_count += 1

    # Optional checksum_valid(data) -> bool. False is meaningful contrary evidence;
    # absence of a checksum checker is reported as not applicable, not a failure.
    checksum_validator = getattr(plugin, "checksum_valid", None)
    if callable(checksum_validator):
        try:
            valid = bool(checksum_validator(data))
            evidence.append(_clue("checksum", valid,
                                  "Checksum is valid" if valid else "Checksum validation failed",
                                  1.0 if valid else 0.0, _WEIGHTS["checksum"],
                                  contradiction=not valid))
            if valid:
                score_total += _WEIGHTS["checksum"]
            else:
                contradiction_count += 1
        except Exception as error:
            evidence.append(_clue("checksum", False,
                                  f"Checksum check raised {type(error).__name__}", 0.0,
                                  _WEIGHTS["checksum"], contradiction=True))
            contradiction_count += 1
    else:
        evidence.append(_clue("checksum", None, "No checksum rule declared by this plugin"))

    confidence = max(0.0, min(1.0, score_total - contradiction_count * _CONTRADICTION_PENALTY))
    evidence.append(_clue("combined_score", None,
                          f"Weighted evidence {score_total:.4f}; contradiction penalty "
                          f"{contradiction_count * _CONTRADICTION_PENALTY:.4f}; "
                          f"final confidence {confidence:.4f}"))
    return confidence, evidence


def identify(data: bytes, registry: PluginRegistry | None = None,
             threshold: float = DEFAULT_THRESHOLD) -> list[dict[str, Any]]:
    """Return ranked plugin candidates with confidence and evidence.

    The returned list is sorted by descending confidence and then original
    registration order. If the best non-generic candidate is below ``threshold``,
    the generic plugin is marked selected as the conservative fallback.
    Candidate dictionaries include ``plugin`` for internal dispatch; do not
    serialize that object directly.
    """
    registry = registry or default_registry()
    threshold = float(threshold)
    if not 0.0 <= threshold <= 1.0:
        threshold = DEFAULT_THRESHOLD

    plugins = list(registry.plugins)
    if not any(isinstance(plugin, GenericPlugin) for plugin in plugins):
        plugins.append(GenericPlugin())

    candidates: list[dict[str, Any]] = []
    for order, plugin in enumerate(plugins):
        confidence, evidence = _collect_evidence(plugin, data)
        candidates.append({
            "name": str(getattr(plugin, "name", type(plugin).__name__)),
            "confidence": round(confidence, 4),
            "evidence": evidence,
            "plugin": plugin,
            "_order": order,
            "selected": False,
        })

    candidates.sort(key=lambda item: (-item["confidence"], item["_order"]))
    generic_candidate = next((item for item in candidates if isinstance(item["plugin"], GenericPlugin)), None)
    best_known = next((item for item in candidates if not isinstance(item["plugin"], GenericPlugin)), None)
    if best_known is not None and best_known["confidence"] >= threshold:
        selected = best_known
    else:
        selected = generic_candidate
    if selected is not None:
        selected["selected"] = True
        if selected is generic_candidate and best_known is not None:
            selected["fallback_reason"] = (
                f"Best known-format confidence {best_known['confidence']:.4f} "
                f"is below threshold {threshold:.4f}"
            )
    for item in candidates:
        item.pop("_order", None)
    return candidates


def select_plugin(data: bytes, registry: PluginRegistry | None = None,
                  threshold: float = DEFAULT_THRESHOLD) -> FormatPlugin:
    """Select the identified plugin, applying the generic fallback threshold."""
    candidates = identify(data, registry=registry, threshold=threshold)
    for candidate in candidates:
        if candidate["selected"]:
            return candidate["plugin"]
    return GenericPlugin()
