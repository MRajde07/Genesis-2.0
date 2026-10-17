"""Byte coverage map: which bytes of an input were decoded, verified, damaged or left unexplained.

Every input byte ends up in exactly one class, so the map answers "what did
SALVAGE actually account for?" without trusting a plugin's own summary.

Classes (highest priority first; a higher class wins where claims overlap):
    damaged    bytes a plugin reported as damaged, truncated or failing validation
    verified   bytes decoded AND confirmed by a checksum/validator that passed
    decoded    bytes decoded into fields/records but not independently verified
    header     bytes of the format's fixed header
    unclaimed  bytes nobody explained (never guessed: shown with a hex preview)

Where the claims come from:
    1. ``plugin-declared``  - a plugin put ``_spans`` in ``Result.data`` (exact).
    2. ``inferred-from-records`` - fallback for plugins without ``_spans``: each
       record's raw bytes are located in the input by offset hint or content
       match. Content matching can pick the wrong copy of repeated bytes, so it
       is labelled as inferred in the output.

Stdlib only. Nothing here may raise into the pipeline: callers wrap it, and the
builder itself clamps every range to the file instead of trusting plugins.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from collections import Counter
from typing import Any, Iterable

KINDS = ("damaged", "verified", "decoded", "header", "unclaimed")
_PRIORITY = {"unclaimed": 0, "header": 1, "decoded": 2, "verified": 3, "damaged": 4}
_PLUGIN_KINDS = {"header", "decoded", "verified", "damaged"}
_MAX_SPANS = 20000
_MAX_UNCLAIMED_LISTED = 200


def span(start: int, end: int, kind: str, label: str = "") -> dict[str, Any]:
    """Helper for plugins: declare that bytes [start, end) belong to ``kind``."""
    return {"start": int(start), "end": int(end), "kind": kind, "label": label}


# --------------------------------------------------------------------------- claims

def _entropy(sample: bytes) -> float:
    if not sample:
        return 0.0
    total = len(sample)
    return -sum(c / total * math.log2(c / total) for c in Counter(sample).values())


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _hex_bytes(value: Any) -> bytes | None:
    if not isinstance(value, str) or len(value) < 2 or len(value) % 2:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


def _claims_from_plugin(spans: Iterable[Any], size: int) -> list[dict[str, Any]]:
    claims = []
    for item in spans:
        if not isinstance(item, dict):
            continue
        start, end = _as_int(item.get("start")), _as_int(item.get("end"))
        kind = item.get("kind")
        if start is None or end is None or kind not in _PLUGIN_KINDS:
            continue
        claims.append({"start": start, "end": end, "kind": kind,
                       "label": str(item.get("label", "")), "source": "plugin-declared"})
    return claims


def _claims_from_records(data: bytes, records: list[Any]) -> list[dict[str, Any]]:
    """Locate each record's raw bytes in the input. Best effort, labelled inferred."""
    claims: list[dict[str, Any]] = []
    cursor = 0
    for position, rec in enumerate(records):
        if not isinstance(rec, dict):
            continue
        index = rec.get("index", position)
        validity = [v for k, v in rec.items() if k.endswith("_valid") and isinstance(v, bool)]
        kind = "verified" if validity and all(validity) else "decoded"
        if rec.get("complete") is False:
            kind = "damaged"
        located = False
        for key, value in rec.items():
            if not (key.endswith("raw_hex") or key.endswith("packed_hex")):
                continue
            raw = _hex_bytes(value)
            if not raw:
                continue
            hints = [_as_int(rec.get("offset")), _as_int(rec.get("blob_offset")) if key == "packed_hex" else None]
            start, source = -1, "content-match"
            for hint in hints:
                if hint is not None and 0 <= hint and data[hint:hint + len(raw)] == raw:
                    start, source = hint, "offset-hint"
                    break
            if start < 0:
                start = data.find(raw, cursor)
            if start < 0:
                continue
            claims.append({"start": start, "end": start + len(raw), "kind": kind,
                           "label": f"record[{index}] {key}", "source": f"inferred ({source})"})
            cursor = max(cursor, start + len(raw))
            located = True
        # offset + length field pairs reported by the plugin itself
        for key, value in rec.items():
            offset = _as_int(value)
            if offset is None or not key.endswith("_offset"):
                continue
            prefix = key[:-len("_offset")]
            length = _as_int(rec.get(prefix + "_length"))
            if length is None and prefix == "blob":
                length = _as_int(rec.get("packed_length"))
            if length and offset >= 0:
                claims.append({"start": offset, "end": offset + length, "kind": kind,
                               "label": f"record[{index}] {prefix}", "source": "inferred (offset+length fields)"})
                located = True
        if not located:
            claims.append({"start": -1, "end": -1, "kind": kind, "label": f"record[{index}]",
                           "source": "unlocated"})
    return claims


def _claims_from_damage(damage: list[Any]) -> list[dict[str, Any]]:
    claims = []
    for item in damage:
        if not isinstance(item, dict):
            continue
        rng = item.get("byte_range")
        if isinstance(rng, dict):
            start, end = _as_int(rng.get("start")), _as_int(rng.get("end"))
        else:
            start = end = None
        if start is None or end is None:
            continue
        claims.append({"start": start, "end": end, "kind": "damaged",
                       "label": f"{item.get('field', 'damage')}: {item.get('reason', '')}".strip(": "),
                       "source": "damage-report"})
    return claims


# --------------------------------------------------------------------------- sweep

def _sweep(claims: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Resolve overlapping claims into non-overlapping, gap-free spans."""
    points = {0, size}
    for c in claims:
        points.add(c["start"])
        points.add(c["end"])
    bounds = sorted(points)
    starts: dict[int, list[int]] = {}
    ends: dict[int, list[int]] = {}
    for i, c in enumerate(claims):
        starts.setdefault(c["start"], []).append(i)
        ends.setdefault(c["end"], []).append(i)
    active: set[int] = set()
    spans: list[dict[str, Any]] = []
    for a, b in zip(bounds, bounds[1:]):
        active.difference_update(ends.get(a, ()))
        active.update(starts.get(a, ()))
        if active:
            best = claims[max(active, key=lambda i: (_PRIORITY[claims[i]["kind"]], i))]
            piece = {"start": a, "end": b, "kind": best["kind"], "label": best["label"], "source": best["source"]}
        else:
            piece = {"start": a, "end": b, "kind": "unclaimed", "label": "", "source": "none"}
        prev = spans[-1] if spans else None
        if prev and prev["kind"] == "unclaimed" and piece["kind"] == "unclaimed":
            prev["end"] = b
        else:
            spans.append(piece)
    return spans


def _merge_if_huge(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(spans) <= _MAX_SPANS:
        return spans
    merged: list[dict[str, Any]] = []
    for s in spans:
        if merged and merged[-1]["kind"] == s["kind"]:
            merged[-1]["end"] = s["end"]
            merged[-1]["label"], merged[-1]["source"] = "merged spans", "merged"
        else:
            merged.append(dict(s))
    return merged


# --------------------------------------------------------------------------- build

def build_bytemap(data: bytes, *, plugin_spans: Iterable[Any] | None = None,
                  records: list[Any] | None = None, damage: list[Any] | None = None,
                  header_length: int | None = None) -> dict[str, Any]:
    """Return the coverage map for ``data``. Pure function, never trusts ranges."""
    size = len(data)
    damage_claims = _claims_from_damage(list(damage or []))
    if plugin_spans is not None:
        method = "plugin-declared"
        claims = _claims_from_plugin(plugin_spans, size)
    elif records:
        method = "inferred-from-records"
        claims = _claims_from_records(data, list(records))
        if isinstance(header_length, int) and 0 < header_length:
            claims.append({"start": 0, "end": header_length, "kind": "header",
                           "label": "header (length declared by plugin)", "source": "plugin header_length"})
    else:
        method = "none"
        claims = []
        if isinstance(header_length, int) and 0 < header_length:
            claims.append({"start": 0, "end": header_length, "kind": "header",
                           "label": "header (length declared by plugin)", "source": "plugin header_length"})
    claims += damage_claims

    # Clamp to the file. Bytes a format expected beyond EOF are reported, not painted.
    beyond = 0
    unlocated = 0
    usable = []
    for c in claims:
        if c["start"] < 0:
            unlocated += 1
            continue
        lo, hi = max(0, c["start"]), min(size, c["end"])
        if c["kind"] == "damaged" and c["end"] > size:
            beyond += c["end"] - max(size, c["start"])
        if lo < hi:
            usable.append({**c, "start": lo, "end": hi})
    spans = _merge_if_huge(_sweep(usable, size)) if size else []

    totals = {k: 0 for k in KINDS}
    for s in spans:
        totals[s["kind"]] += s["end"] - s["start"]
    explained = totals["verified"] + totals["decoded"] + totals["header"]
    unclaimed = []
    for s in spans:
        if s["kind"] == "unclaimed" and len(unclaimed) < _MAX_UNCLAIMED_LISTED:
            chunk = data[s["start"]:s["end"]]
            unclaimed.append({"start": s["start"], "end": s["end"], "length": s["end"] - s["start"],
                              "hex_preview": chunk[:32].hex(),
                              "entropy_bits_per_byte": round(_entropy(chunk[:4096]), 3)})
    return {
        "size": size,
        "sha256": hashlib.sha256(data).hexdigest(),
        "method": method,
        "totals": totals,
        "explained_pct": round(100.0 * explained / size, 2) if size else 0.0,
        "damaged_pct": round(100.0 * totals["damaged"] / size, 2) if size else 0.0,
        "unclaimed_pct": round(100.0 * totals["unclaimed"] / size, 2) if size else 0.0,
        "bytes_expected_beyond_eof": beyond,
        "unlocated_records": unlocated,
        "spans": spans,
        "unclaimed": unclaimed,
    }


def report_ranges(bytemap: dict[str, Any]) -> list[dict[str, Any]]:
    """Whole-file coverage as [{start, end, kind}] for report.json (adjacent same-kind spans merged)."""
    merged: list[dict[str, Any]] = []
    for s in bytemap.get("spans", []):
        if merged and merged[-1]["kind"] == s["kind"] and merged[-1]["end"] == s["start"]:
            merged[-1]["end"] = s["end"]
        else:
            merged.append({"start": s["start"], "end": s["end"], "kind": s["kind"]})
    return merged


# --------------------------------------------------------------------------- html

_CSS = """
:root{--bg:#fafaf7;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#dcdcd4;
--verified:#2e7d32;--decoded:#8bc34a;--header:#4f7cac;--damaged:#c62828;--unclaimed:#9e9e9e;--on:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e8e8e3;--mut:#9a9a94;--card:#1f1f1e;--line:#33332f;
--verified:#43a047;--decoded:#7cb342;--header:#5b8fc7;--damaged:#ef5350;--unclaimed:#6f6f6a}}
body{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,Segoe UI,Arial,sans-serif}
main{max-width:1000px;margin:0 auto}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 18px}
section{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:0 0 18px}
h2{font-size:16px;margin:0 0 2px}.meta{color:var(--mut);font-size:13px;word-break:break-all}
.bar{display:flex;height:22px;border-radius:4px;overflow:hidden;margin:10px 0;background:var(--unclaimed)}
.bar i{display:block;min-width:1px}.k-verified{background:var(--verified)}.k-decoded{background:var(--decoded)}
.k-header{background:var(--header)}.k-damaged{background:var(--damaged)}.k-unclaimed{background:var(--unclaimed)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;margin:4px 0 8px}
.legend b{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:-1px}
pre.hex{font:12px/1.5 ui-monospace,Consolas,monospace;overflow-x:auto;margin:8px 0;padding:8px;border:1px solid var(--line);border-radius:6px}
pre.hex .o{color:var(--mut)}pre.hex .a{color:var(--mut)}
pre.hex .k-verified,pre.hex .k-decoded,pre.hex .k-header,pre.hex .k-damaged,pre.hex .k-unclaimed{background:none}
pre.hex .k-verified{color:var(--verified);font-weight:600}pre.hex .k-decoded{color:var(--decoded);font-weight:600}
pre.hex .k-header{color:var(--header);font-weight:600}
pre.hex .k-damaged{color:var(--damaged);font-weight:700;text-decoration:underline}pre.hex .k-unclaimed{color:var(--unclaimed)}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;padding:4px 8px;border-top:1px solid var(--line);vertical-align:top}
td.m{font-family:ui-monospace,Consolas,monospace}.note{color:var(--mut);font-size:13px}
"""

_HEX_LIMIT = 8192
_LABELS = {"verified": "verified (checksum/validator passed)", "decoded": "decoded", "header": "header",
           "damaged": "damaged / failed validation", "unclaimed": "unclaimed (unexplained)"}


def _hex_dump(data: bytes, spans: list[dict[str, Any]]) -> str:
    shown = data[:_HEX_LIMIT]
    kind_at = bytearray(len(shown))
    code = {k: i for i, k in enumerate(KINDS)}
    for s in spans:
        if s["start"] >= len(shown):
            break
        e = min(s["end"], len(shown))
        kind_at[s["start"]:e] = bytes([code[s["kind"]]]) * (e - s["start"])
    rows = []
    for off in range(0, len(shown), 16):
        parts, run_kind, run = [], None, []
        for i in range(off, min(off + 16, len(shown))):
            k = KINDS[kind_at[i]]
            if k != run_kind and run:
                parts.append(f'<span class="k-{run_kind}">{" ".join(run)}</span>')
                run = []
            run_kind = k
            run.append(f"{shown[i]:02x}")
        if run:
            parts.append(f'<span class="k-{run_kind}">{" ".join(run)}</span>')
        ascii_ = "".join(chr(b) if 32 <= b < 127 else "." for b in shown[off:off + 16])
        rows.append(f'<span class="o">{off:08x}</span>  {" ".join(parts)}  <span class="a">|{html.escape(ascii_)}|</span>')
    return "\n".join(rows)


def render_html(entries: list[dict[str, Any]], inputs: dict[str, bytes] | None = None) -> str:
    """Single offline report.html. ``inputs`` maps file name -> bytes for the hex view."""
    inputs = inputs or {}
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>SALVAGE byte coverage report</title><style>{_CSS}</style></head><body><main>',
           "<h1>SALVAGE byte coverage report</h1>",
           '<p class="sub">Every byte of each input is placed in one class. Nothing is guessed: '
           "bytes no decoder could explain stay <b>unclaimed</b>.</p>",
           '<div class="legend">' + "".join(
               f'<span><b class="k-{k}"></b>{html.escape(_LABELS[k])}</span>' for k in KINDS) + "</div>"]
    for entry in entries:
        bm = entry["bytemap"]
        name = str(entry.get("file_name", ""))
        size = bm["size"]
        out.append(f"<section><h2>{html.escape(name)}</h2>")
        out.append(f'<div class="meta">{html.escape(str(entry.get("format", "")))} · status '
                   f'{html.escape(str(entry.get("status", "")))} · {size} bytes · '
                   f'sha256 {bm["sha256"]}</div>')
        out.append(f'<div class="meta">explained {bm["explained_pct"]}% · damaged {bm["damaged_pct"]}% · '
                   f'unclaimed {bm["unclaimed_pct"]}% · map method: {html.escape(bm["method"])}</div>')
        if bm["bytes_expected_beyond_eof"]:
            out.append(f'<div class="note">The format expected {bm["bytes_expected_beyond_eof"]} more byte(s) '
                       "past the end of this file (truncation).</div>")
        if bm["unlocated_records"]:
            out.append(f'<div class="note">{bm["unlocated_records"]} record(s) could not be located '
                       "in the file bytes and are not painted.</div>")
        if size:
            out.append('<div class="bar" role="img" aria-label="byte coverage bar">')
            for s in bm["spans"]:
                width = 100.0 * (s["end"] - s["start"]) / size
                tip = f'0x{s["start"]:x}-0x{s["end"]:x} {s["kind"]} {s["label"]}'.strip()
                out.append(f'<i class="k-{s["kind"]}" style="width:{width:.4f}%" title="{html.escape(tip)}"></i>')
            out.append("</div>")
        raw = inputs.get(name)
        if raw:
            out.append(f'<pre class="hex">{_hex_dump(raw, bm["spans"])}</pre>')
            if len(raw) > _HEX_LIMIT:
                out.append(f'<div class="note">Hex view shows the first {_HEX_LIMIT} of {len(raw)} bytes; '
                           "the bar and tables cover the whole file.</div>")
        interesting = [s for s in bm["spans"] if s["kind"] in ("damaged", "unclaimed")][:60]
        if interesting:
            out.append("<table><tr><th>Range</th><th>Class</th><th>Detail</th></tr>")
            for s in interesting:
                out.append(f'<tr><td class="m">0x{s["start"]:x}–0x{s["end"]:x} ({s["end"] - s["start"]} B)</td>'
                           f'<td>{s["kind"]}</td><td>{html.escape(s["label"] or "no decoder claimed these bytes")}</td></tr>')
            out.append("</table>")
        out.append("</section>")
    payload = json.dumps([{"file_name": e.get("file_name"), "format": e.get("format"),
                           "status": e.get("status"), "bytemap": e["bytemap"]} for e in entries],
                         sort_keys=True).replace("</", "<\\/")
    out.append(f'<script type="application/json" id="bytemap-data">{payload}</script>')
    out.append("</main></body></html>")
    return "\n".join(out)
