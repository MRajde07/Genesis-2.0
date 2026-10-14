"""Windowed Shannon entropy and byte histograms (pure, deterministic functions)."""
from __future__ import annotations
import math
from collections import Counter


def byte_histogram(data: bytes) -> dict:
    counts = [0] * 256
    for value in data:
        counts[value] += 1
    return {"analysis": "byte_histogram", "size": len(data), "counts": counts,
            "confidence": 1.0 if data else 0.0}


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    total = len(data)
    return -sum((n / total) * math.log2(n / total) for n in Counter(data).values())


def analyze_entropy(data: bytes, window_size: int = 256, step: int | None = None) -> dict:
    if window_size < 1:
        raise ValueError("window_size must be positive")
    step = window_size if step is None else step
    if step < 1:
        raise ValueError("step must be positive")
    regions = []
    for offset in range(0, len(data), step):
        chunk = data[offset:offset + window_size]
        if not chunk:
            continue
        value = shannon_entropy(chunk)
        regions.append({"offset": offset, "length": len(chunk), "entropy_bits_per_byte": round(value, 6),
                        "confidence": round(min(1.0, len(chunk) / min(window_size, 32)), 4),
                        "classification": "high_entropy" if value >= 7.2 else "low_entropy" if value <= 3.0 else "mixed"})
    return {"analysis": "entropy", "size": len(data), "window_size": window_size, "step": step,
            "regions": regions, "confidence": 1.0 if data else 0.0}


def analyze(data: bytes, window_size: int = 256, step: int | None = None) -> dict:
    return {"entropy": analyze_entropy(data, window_size, step), "histogram": byte_histogram(data)}
