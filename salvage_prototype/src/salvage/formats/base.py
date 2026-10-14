"""Format plugin contracts and declarative binary field-spec decoder.

All offsets are zero-based and byte ranges are half-open. The decoder is
stdlib-only and returns partial values plus structured damage on short input.
"""
from __future__ import annotations

import datetime as _dt
import struct
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence


@dataclass
class Damage:
    """Structured diagnostic for damaged or undecodable bytes."""
    field: str
    offset: int
    expected: int
    found: int
    reason: str
    byte_range: tuple[int, int] | None = None
    raw_hex: str | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {"field": self.field, "offset": self.offset,
            "expected": self.expected, "found": self.found, "reason": self.reason}
        if self.byte_range is not None:
            item["byte_range"] = {"start": self.byte_range[0], "end": self.byte_range[1]}
        if self.raw_hex is not None:
            item["raw_hex"] = self.raw_hex
        return item


@dataclass
class Result:
    """Decoded records and any structured damage found while decoding."""
    records: list[dict[str, Any]] = field(default_factory=list)
    damage: list[Damage | dict[str, Any]] = field(default_factory=list)
    format: str = "UNKNOWN"
    status: str = "unsupported"
    data: Any = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FieldSpec:
    """Declarative field description.

    ``length`` is a byte count for fixed strings/bytes, or an array count.
    ``length_source`` names a previously decoded field (for length-prefixed
    strings/arrays), or may be an integer literal. ``count`` is an alternative
    fixed array/index-table count. ``offset_from`` is added to index offsets.
    Validators may be names (``nonzero``, ``positive``, ``min:N``, ``max:N``,
    ``one_of:a,b``) or callables returning bool.
    """
    name: str
    type: str
    endianness: str | None = None
    length_source: str | int | None = None
    encoding: str | None = None
    validators: Sequence[str | Callable[[Any], bool]] = ()
    length: int | None = None
    count: int | str | None = None
    item_type: str | None = None
    item_size: int | None = None
    prefix_type: str = "u8"
    offset_from: int = 0
    target_fields: Sequence["FieldSpec"] = ()
    offset: int | None = None
    strip_nul: bool = False
    minimum: int | float | None = None
    maximum: int | float | None = None
    enum_values: Sequence[Any] | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class BlockSpec:
    """Bounds and optional checksum contract for a byte block.

    Offsets are absolute, zero-based file offsets. The checksum field must be
    inside the block. Unless checksum_range is provided, the checksum is
    computed over the block excluding the stored checksum bytes.
    """
    name: str
    offset: int
    length: int
    checksum_offset: int | None = None
    checksum_type: str = "crc32"
    checksum_length: int = 4
    checksum_endianness: str = "little"
    checksum_range: tuple[int, int] | None = None


@dataclass
class FieldDecode:
    values: dict[str, Any] = field(default_factory=dict)
    damage: list[Damage] = field(default_factory=list)
    consumed: int = 0
    blocks: list[dict[str, Any]] = field(default_factory=list)


_NUMERIC = {
    "u8": (1, False, False), "u16": (2, False, False), "u32": (4, False, False),
    "i8": (1, True, False), "i16": (2, True, False), "i32": (4, True, False),
    "f32": (4, True, True), "float32": (4, True, True), "float": (4, True, True),
    "f64": (8, True, True), "float64": (8, True, True), "double": (8, True, True),
}


def _damage(name: str, offset: int, expected: int, found: int, reason: str,
            affected: tuple[int, int] | None = None) -> Damage:
    return Damage(name, offset, expected, found, reason, affected)


def _size_for_type(kind: str) -> int | None:
    return _NUMERIC.get(kind.lower(), (None, False, False))[0]


def _read_value(data: bytes, offset: int, spec: FieldSpec, endian: str,
                prior: Mapping[str, Any], damage: list[Damage], *, limit: int | None = None) -> tuple[Any, int]:
    """Decode one field at an absolute offset; return value and bytes consumed."""
    kind = spec.type.lower().replace("-", "_")
    kind = {
        "string_fixed": "fixed_string", "fixed_text": "fixed_string",
        "string_length_prefixed": "length_prefixed_string", "length_prefixed": "length_prefixed_string",
        "dos_date_time": "dos_datetime", "unix_timestamp32": "unix_timestamp",
        "byte_array": "array", "offset_table": "index_table",
    }.get(kind, kind)
    order = spec.endianness or endian
    if order not in ("big", "little"):
        damage.append(_damage(spec.name, offset, 0, 0, f"invalid endianness: {order}"))
        return None, 0

    local_cursor = offset
    def take(n: int) -> bytes:
        nonlocal local_cursor
        if n < 0:
            damage.append(_damage(spec.name, local_cursor, n, 0, "negative field length"))
            return b""
        here = local_cursor
        if here < 0:
            damage.append(_damage(spec.name, here, n, 0, "offset out of range: negative offset", (here, 0)))
            local_cursor = 0
            return b""
        available = max(0, min(n, len(data) - here)) if here < len(data) else 0
        raw = data[here:here + available]
        if available < n:
            missing_start = min(len(data), here + available)
            damage.append(_damage(spec.name, missing_start, n, available,
                "out of range: insufficient bytes", (missing_start, max(missing_start, here + n))))
        local_cursor += available
        return raw

    if kind in _NUMERIC:
        size, signed, floating = _NUMERIC[kind]
        raw = take(size)
        if not raw:
            return None, len(raw)
        if len(raw) < size:
            # Preserve the available portion rather than fabricating a full value.
            return None, len(raw)
        if floating:
            value = struct.unpack(("<" if order == "little" else ">") + ("f" if size == 4 else "d"), raw)[0]
        else:
            value = int.from_bytes(raw, order, signed=signed)
        _validate(spec, value, offset, size, damage, raw)
        return value, size

    if kind in ("fixed_bytes", "bytes", "signature"):
        n = spec.length if spec.length is not None else (int(spec.length_source) if isinstance(spec.length_source, int) else 0)
        raw = take(n)
        value: Any = raw.hex() if kind == "signature" else raw.hex()
        _validate(spec, value, offset, n, damage, raw)
        return value, len(raw)

    if kind in ("fixed_string", "string", "length_prefixed_string", "lp_string"):
        prefix = 0
        if kind in ("length_prefixed_string", "lp_string"):
            psize = _size_for_type(spec.prefix_type)
            if psize is None:
                damage.append(_damage(spec.name, offset, 0, 0, f"unsupported prefix type: {spec.prefix_type}"))
                return None, 0
            p_raw = take(psize)
            prefix = len(p_raw)
            if len(p_raw) < psize:
                return {"text": None, "raw_hex": p_raw.hex()}, prefix
            p_signed = spec.prefix_type.startswith("i")
            n = int.from_bytes(p_raw, order, signed=p_signed)
        elif spec.length_source is not None:
            source = prior.get(spec.length_source) if isinstance(spec.length_source, str) else spec.length_source
            try: n = int(source)
            except (TypeError, ValueError, OverflowError):
                damage.append(_damage(spec.name, offset, 0, 0, f"invalid length source: {spec.length_source}"))
                return None, prefix
        else:
            n = spec.length or 0
        if n < 0:
            damage.append(_damage(spec.name, offset + prefix, n, 0, "invalid length: negative value", (offset + prefix, offset + prefix)))
            return {"text": None, "raw_hex": "", "length_error": "negative length"}, prefix
        if spec.max_length is not None and n > spec.max_length:
            damage.append(_damage(spec.name, offset + prefix, spec.max_length, n,
                "length exceeds configured maximum", (offset + prefix, offset + prefix + min(n, max(0, len(data) - (offset + prefix))))))
        raw = take(n)
        enc = spec.encoding or "utf-8"
        try:
            text = raw.decode(enc, errors="strict")
            if spec.strip_nul:
                text = text.rstrip("\x00")
            value = text
        except (UnicodeDecodeError, LookupError) as exc:
            reason = "invalid encoding" if isinstance(exc, UnicodeDecodeError) else f"unknown encoding: {enc}"
            damage.append(_damage(spec.name, offset + prefix, len(raw), len(raw), reason,
                                  (offset + prefix, offset + prefix + len(raw))))
            value = {"text": None, "raw_hex": raw.hex(), "encoding_error": reason}
        _validate(spec, value, offset, prefix + len(raw), damage, raw)
        return value, prefix + len(raw)

    if kind in ("dos_date", "dos_time", "dos_datetime"):
        sizes = {"dos_date": 2, "dos_time": 2, "dos_datetime": 4}
        size = sizes[kind]
        raw = take(size)
        if len(raw) < size: return None, len(raw)
        if kind == "dos_datetime":
            date_num = int.from_bytes(raw[:2], order); time_num = int.from_bytes(raw[2:], order)
        elif kind == "dos_date": date_num, time_num = int.from_bytes(raw, order), None
        else: date_num, time_num = None, int.from_bytes(raw, order)
        try:
            out: dict[str, Any] = {}
            if date_num is not None:
                year, month, day = 1980 + ((date_num >> 9) & 0x7f), (date_num >> 5) & 0xf, date_num & 0x1f
                out["date"] = _dt.date(year, month, day).isoformat()
            if time_num is not None:
                hour, minute, second = (time_num >> 11) & 0x1f, (time_num >> 5) & 0x3f, (time_num & 0x1f) * 2
                if hour > 23 or minute > 59 or second > 59: raise ValueError("invalid DOS time")
                out["time"] = f"{hour:02d}:{minute:02d}:{second:02d}"
            value = out["date"] if kind == "dos_date" else out["time"] if kind == "dos_time" else out
        except ValueError as exc:
            damage.append(_damage(spec.name, offset, size, size, f"invalid DOS date/time: {exc}", (offset, offset + size)))
            value = None
        _validate(spec, value, offset, size, damage, raw)
        return value, size

    if kind in ("unix_timestamp", "unix_time"):
        size = spec.length or 4
        raw = take(size)
        if len(raw) < size: return None, len(raw)
        value = int.from_bytes(raw, order, signed=False)
        try: rendered = _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError): rendered = None
        result = {"seconds": value, "utc": rendered}
        _validate(spec, value, offset, size, damage, raw)
        return result, size

    if kind == "bcd":
        n = spec.length or 1
        raw = take(n)
        digits = ""
        valid = True
        for byte in raw:
            hi, lo = byte >> 4, byte & 0xf
            if hi > 9 or lo > 9: valid = False
            digits += f"{hi:x}{lo:x}"
        if not valid:
            damage.append(_damage(spec.name, offset, n, len(raw), "invalid BCD nibble", (offset, offset + len(raw))))
            value = {"raw_hex": raw.hex(), "digits": None}
        else:
            value = int(digits) if digits else 0
        _validate(spec, value, offset, n, damage, raw)
        return value, len(raw)

    if kind in ("julian_date", "jdn"):
        size = spec.length or 4
        raw = take(size)
        if len(raw) < size: return None, len(raw)
        jdn = int.from_bytes(raw, order, signed=False)
        try:
            # Integer JDN convention: map midnight-based day number to Gregorian date.
            value = (_dt.date(1, 1, 1) + _dt.timedelta(days=jdn - 1721426)).isoformat()
        except (OverflowError, ValueError):
            value = None
            damage.append(_damage(spec.name, offset, size, size, "Julian day outside supported date range", (offset, offset + size)))
        _validate(spec, value, offset, size, damage, raw)
        return value, size

    if kind == "array":
        count_source = spec.count if spec.count is not None else spec.length_source
        if isinstance(count_source, str): count_source = prior.get(count_source)
        try: count = max(0, int(count_source if count_source is not None else 0))
        except (TypeError, ValueError, OverflowError):
            damage.append(_damage(spec.name, offset, 0, 0, "invalid array count")); return [], 0
        item_type = spec.item_type or "u8"
        item_size = spec.item_size or _size_for_type(item_type) or (spec.length or 1)
        values, consumed = [], 0
        for index in range(count):
            sub = FieldSpec(f"{spec.name}[{index}]", item_type, spec.endianness, length=item_size,
                            encoding=spec.encoding, validators=spec.validators)
            before = len(damage)
            value, used = _read_value(data, offset + consumed, sub, endian, prior, damage)
            values.append(value); consumed += used
            if used < item_size or len(damage) > before and used == 0: break
        return values, consumed

    if kind in ("index_table", "indices"):
        count_source = spec.count if spec.count is not None else spec.length_source
        if isinstance(count_source, str): count_source = prior.get(count_source)
        try: count = max(0, int(count_source if count_source is not None else 0))
        except (TypeError, ValueError, OverflowError):
            damage.append(_damage(spec.name, offset, 0, 0, "invalid index-table count")); return [], 0
        item_size = spec.item_size or _size_for_type(spec.item_type or "u32") or 4
        offsets: list[dict[str, Any]] = []; consumed = 0
        for index in range(count):
            sub = FieldSpec(f"{spec.name}[{index}]", spec.item_type or "u32", spec.endianness)
            val, used = _read_value(data, offset + consumed, sub, endian, prior, damage)
            if val is None: break
            target = int(val) + spec.offset_from
            entry: dict[str, Any] = {"index": index, "offset": target, "valid": 0 <= target < len(data)}
            if not entry["valid"]:
                damage.append(_damage(f"{spec.name}[{index}]", offset + consumed, item_size, used,
                                      "index offset outside file", (offset + consumed, offset + consumed + used)))
            elif spec.target_fields:
                decoded = decode_fields(data, spec.target_fields, endian=endian, start_offset=target, _prior=prior)
                entry["record"] = decoded.values
                damage.extend(decoded.damage)
            offsets.append(entry); consumed += used
            if used < item_size: break
        return offsets, consumed

    damage.append(_damage(spec.name, offset, 0, 0, f"unsupported field type: {spec.type}"))
    return None, 0


def _validate(spec: FieldSpec, value: Any, offset: int, size: int, damage: list[Damage],
              raw: bytes | None = None) -> None:
    """Apply explicit range/enum checks and legacy validator expressions."""
    checks: list[tuple[str, Callable[[Any], bool]]] = []
    if spec.minimum is not None:
        checks.append((f"minimum:{spec.minimum}", lambda v, minimum=spec.minimum: v >= minimum))
    if spec.maximum is not None:
        checks.append((f"maximum:{spec.maximum}", lambda v, maximum=spec.maximum: v <= maximum))
    if spec.enum_values is not None:
        allowed = tuple(spec.enum_values)
        checks.append((f"enum:{list(allowed)}", lambda v, allowed=allowed: v in allowed))
    for validator in spec.validators:
        description = getattr(validator, "__name__", str(validator))
        if callable(validator):
            check = validator
        elif validator == "nonzero":
            check = lambda v: v != 0
        elif validator == "positive":
            check = lambda v: v > 0
        elif validator.startswith("min:"):
            limit = float(validator.split(":", 1)[1]); check = lambda v, limit=limit: v >= limit
        elif validator.startswith("max:"):
            limit = float(validator.split(":", 1)[1]); check = lambda v, limit=limit: v <= limit
        elif validator.startswith("one_of:"):
            allowed = validator.split(":", 1)[1].split(","); check = lambda v, allowed=allowed: str(v) in allowed
        else:
            continue
        checks.append((description, check))
    for description, check in checks:
        try:
            ok = bool(check(value))
        except Exception:
            ok = False
        if not ok:
            damage.append(Damage(spec.name, offset, size, size,
                f"validator failed: {description}", (offset, offset + size),
                raw.hex() if raw is not None else None))


def _checksum_value(kind: str, payload: bytes) -> int:
    """Compute supported checksum candidates using only the standard library."""
    import zlib
    name = kind.lower().replace("-", "").replace("_", "")
    if name in ("crc32", "crc32ieee"):
        return zlib.crc32(payload) & 0xffffffff
    if name in ("sum8", "add8"):
        return sum(payload) & 0xff
    if name in ("sum16", "add16"):
        return sum(payload) & 0xffff
    if name in ("xor", "xor8"):
        value = 0
        for byte in payload: value ^= byte
        return value
    if name in ("fletcher16", "fletcher"):
        a = b = 0
        for byte in payload:
            a = (a + byte) % 255
            b = (b + a) % 255
        return (b << 8) | a
    if name in ("crc16", "crc16modbus", "modbus"):
        crc = 0xffff
        for byte in payload:
            crc ^= byte
            for _ in range(8): crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc & 0xffff
    if name in ("crc16ccitt", "ccitt"):
        crc = 0xffff
        for byte in payload:
            crc ^= byte << 8
            for _ in range(8): crc = ((crc << 1) ^ 0x1021) & 0xffff if crc & 0x8000 else (crc << 1) & 0xffff
        return crc
    raise ValueError(f"unsupported checksum algorithm: {kind}")


def _verify_blocks(data: bytes, blocks: Sequence[BlockSpec | Mapping[str, Any]], result: FieldDecode) -> None:
    for raw_spec in blocks:
        block = raw_spec if isinstance(raw_spec, BlockSpec) else BlockSpec(**dict(raw_spec))
        start, length = int(block.offset), int(block.length)
        end = start + length
        available_start = max(0, min(len(data), start))
        available_end = max(available_start, min(len(data), end))
        raw_block = data[available_start:available_end]
        block_report: dict[str, Any] = {"name": block.name, "offset": start, "length": length,
                                        "found_length": len(raw_block), "raw_hex": raw_block.hex(),
                                        "checksum": None, "valid": True}
        if start < 0 or length < 0 or end > len(data) or start > len(data):
            reason = "block bounds out of range"
            result.damage.append(Damage(block.name, start, max(0, length), len(raw_block), reason,
                                        (available_end, max(available_end, end)), raw_block.hex()))
            block_report["valid"] = False
            block_report["reason"] = reason
        if block.checksum_offset is not None:
            cstart = int(block.checksum_offset)
            cend = cstart + int(block.checksum_length)
            if block.checksum_length <= 0 or cstart < start or cend > end or cstart < 0 or cend > len(data):
                reason = "checksum field bounds out of range"
                available_cstart = max(0, min(len(data), cstart))
                checksum_raw = data[available_cstart:max(available_cstart, min(len(data), cend))]
                result.damage.append(Damage(f"{block.name}.checksum", cstart, block.checksum_length,
                    len(checksum_raw), reason, (available_cstart, max(available_cstart, cend)), checksum_raw.hex()))
                block_report["valid"] = False
                block_report["reason"] = reason
            else:
                checksum_raw = data[cstart:cend]
                order = block.checksum_endianness
                if order not in ("little", "big"):
                    reason = f"invalid checksum endianness: {order}"
                    result.damage.append(Damage(f"{block.name}.checksum", cstart, block.checksum_length,
                        len(checksum_raw), reason, (cstart, cend), checksum_raw.hex()))
                    block_report["valid"] = False
                    block_report["reason"] = reason
                else:
                    if block.checksum_range is not None:
                        rstart, rend = map(int, block.checksum_range)
                        if rstart < 0 or rend < rstart or rend > len(data):
                            result.damage.append(Damage(f"{block.name}.checksum", rstart, max(0, rend-rstart),
                                max(0, min(len(data), rend)-max(0, rstart)), "checksum coverage range out of bounds",
                                (max(0, min(len(data), rstart)), max(0, min(len(data), rend))), data[max(0,rstart):max(0,min(len(data),rend))].hex()))
                            block_report["valid"] = False
                            block_report["reason"] = "checksum coverage range out of bounds"
                            payload = b""
                        else:
                            payload = data[rstart:rend]
                    else:
                        payload = data[start:cstart] + data[cend:end]
                    try:
                        calculated = _checksum_value(block.checksum_type, payload)
                        stored = int.from_bytes(checksum_raw, order)
                        checksum_ok = calculated == stored
                        block_report["checksum"] = {"algorithm": block.checksum_type, "stored": stored,
                            "calculated": calculated, "valid": checksum_ok, "offset": cstart,
                            "length": block.checksum_length, "raw_hex": checksum_raw.hex()}
                        if not checksum_ok:
                            reason = f"checksum mismatch ({block.checksum_type}): stored={stored}, calculated={calculated}"
                            result.damage.append(Damage(f"{block.name}.checksum", cstart, calculated, stored,
                                reason, (cstart, cend), (raw_block + checksum_raw).hex()))
                            block_report["valid"] = False
                            block_report["reason"] = reason
                    except ValueError as exc:
                        result.damage.append(Damage(f"{block.name}.checksum", cstart, block.checksum_length,
                            len(checksum_raw), str(exc), (cstart, cend), checksum_raw.hex()))
                        block_report["valid"] = False
                        block_report["reason"] = str(exc)
        result.blocks.append(block_report)


def decode_fields(data: bytes, fields: Sequence[FieldSpec | Mapping[str, Any]], *, endian: str = "little",
                  start_offset: int = 0, _prior: Mapping[str, Any] | None = None,
                  blocks: Sequence[BlockSpec | Mapping[str, Any]] = ()) -> FieldDecode:
    """Decode sequential field specs into values plus diagnostics.

    A field's explicit ``offset`` is relative to ``start_offset``; otherwise
    fields are laid out consecutively. Later fields still decode after a short
    field using the available bytes consumed, so partial records are retained.
    """
    source = bytes(data); result = FieldDecode(); prior: dict[str, Any] = dict(_prior or {})
    cursor = start_offset
    for raw_spec in fields:
        spec = raw_spec if isinstance(raw_spec, FieldSpec) else FieldSpec(**dict(raw_spec))
        field_offset = start_offset + spec.offset if spec.offset is not None else cursor
        if field_offset < 0 or field_offset > len(source):
            result.damage.append(Damage(spec.name, field_offset, _size_for_type(spec.type) or (spec.length or 0), 0,
                "field offset out of range", (max(0, min(len(source), field_offset)), max(0, min(len(source), field_offset))), ""))
            value, used = None, 0
        else:
            value, used = _read_value(source, field_offset, spec, endian, prior, result.damage)
        result.values[spec.name] = value
        prior[spec.name] = value
        if spec.offset is None:
            cursor = field_offset + used
        result.consumed = max(result.consumed, cursor - start_offset, field_offset + used - start_offset)
    _verify_blocks(source, blocks, result)
    return result


class FormatPlugin:
    """Base class for offline format decoders, including declarative formats."""
    name = "UNKNOWN"

    def detect(self, data: bytes) -> float:
        raise NotImplementedError

    def decode(self, data: bytes) -> Result:
        raise NotImplementedError

    def decode_spec(self, data: bytes, fields: Sequence[FieldSpec], *, endian: str = "little",
                    format_name: str | None = None, record_name: str = "record",
                    blocks: Sequence[BlockSpec | Mapping[str, Any]] = ()) -> Result:
        decoded = decode_fields(data, fields, endian=endian, blocks=blocks)
        result = Result(format=format_name or self.name, status="recovered")
        result.data = decoded.values
        result.records = [dict(decoded.values)] if decoded.values else []
        result.damage = decoded.damage
        if decoded.blocks:
            result.data = {"fields": decoded.values, "blocks": decoded.blocks}
            result.records = [dict(result.data)] if decoded.values or decoded.blocks else []
        if decoded.damage:
            result.status = "partial" if result.records else "damaged"
        return result
