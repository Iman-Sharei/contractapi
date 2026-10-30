"""In-process Prometheus-style metrics for the data plane."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Iterable


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)

    def incr(self, name: str, *, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = (name, tuple(sorted((labels or {}).items())))
        with self._lock:
            bucket = self._histograms[key]
            bucket.append(value)
            # cap samples to keep memory bounded
            if len(bucket) > 2_000:
                del bucket[:1_000]

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(f"{name}{_fmt_labels(labels)} {value}")
            for (name, labels), samples in sorted(self._histograms.items()):
                if not samples:
                    continue
                count = len(samples)
                total = sum(samples)
                lines.append(f"{name}_count{_fmt_labels(labels)} {count}")
                lines.append(f"{name}_sum{_fmt_labels(labels)} {total}")
                # simple quantiles
                ordered = sorted(samples)
                for q in (0.5, 0.95, 0.99):
                    idx = min(int(q * (count - 1)), count - 1)
                    qlabels = labels + (("quantile", str(q)),)
                    lines.append(f"{name}{_fmt_labels(qlabels)} {ordered[idx]}")
        return "\n".join(lines) + ("\n" if lines else "")


def _fmt_labels(labels: Iterable[tuple[str, str]]) -> str:
    pairs = list(labels)
    if not pairs:
        return ""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in pairs)
    return "{" + inner + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


metrics = MetricsRegistry()


class Timer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    def seconds(self) -> float:
        return time.perf_counter() - self._start
