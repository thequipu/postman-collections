"""Live dashboard — prints real-time stats every N seconds.

Tracks per-operation: count, errors, latency p50/p95/p99, ops/sec.
"""

import statistics
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone


class Dashboard:
    """Thread-safe stats collector with periodic console output."""

    def __init__(self, interval: int = 10):
        self.interval = interval
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._ops = defaultdict(lambda: {"count": 0, "errors": 0, "latencies": []})
        self._total = {"count": 0, "errors": 0}
        self._running = False
        self._thread = None

    def record(self, op: str, status: int, latency_ms: float):
        """Record one operation."""
        with self._lock:
            entry = self._ops[op]
            entry["count"] += 1
            entry["latencies"].append(latency_ms)
            self._total["count"] += 1
            if status >= 400:
                entry["errors"] += 1
                self._total["errors"] += 1

    def start(self):
        """Start background thread that prints stats periodically."""
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop and print final summary."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._print_final()

    def _loop(self):
        while self._running:
            time.sleep(self.interval)
            if self._running:
                self._print_live()

    def _print_live(self):
        with self._lock:
            elapsed = time.time() - self._start_time
            total = self._total["count"]
            errors = self._total["errors"]
            ops_sec = total / elapsed if elapsed > 0 else 0

            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            lines = []
            lines.append("")
            lines.append(f"\033[1;36m  ┌─── NEURO-SIM DASHBOARD [{now}] ── {elapsed:.0f}s elapsed ───\033[0m")
            lines.append(f"\033[1;36m  │ Total: {total} ops  │  {ops_sec:.1f} ops/sec  │  Errors: {errors}  │  Rate: {errors/total*100:.1f}%\033[0m" if total else f"\033[1;36m  │ Total: 0 ops\033[0m")
            lines.append(f"\033[1;36m  ├{'─'*70}\033[0m")
            lines.append(f"\033[1;36m  │ {'Operation':<22s} {'Count':>6s} {'Err':>4s} {'ops/s':>6s} {'p50':>7s} {'p95':>7s} {'p99':>7s}\033[0m")
            lines.append(f"\033[1;36m  ├{'─'*70}\033[0m")

            for op in sorted(self._ops.keys()):
                entry = self._ops[op]
                count = entry["count"]
                errs = entry["errors"]
                lats = entry["latencies"]
                op_sec = count / elapsed if elapsed > 0 else 0

                if lats:
                    p50 = statistics.median(lats)
                    p95 = self._percentile(lats, 95)
                    p99 = self._percentile(lats, 99)
                else:
                    p50 = p95 = p99 = 0

                color = "\033[0;32m" if errs == 0 else "\033[0;31m"
                lines.append(f"  {color}│ {op:<22s} {count:>6d} {errs:>4d} {op_sec:>6.1f} {p50:>6.0f}ms {p95:>6.0f}ms {p99:>6.0f}ms\033[0m")

            lines.append(f"\033[1;36m  └{'─'*70}\033[0m")

            print("\n".join(lines), file=sys.stderr)

    def _print_final(self):
        with self._lock:
            elapsed = time.time() - self._start_time
            total = self._total["count"]
            errors = self._total["errors"]
            ops_sec = total / elapsed if elapsed > 0 else 0

            lines = []
            lines.append("")
            lines.append(f"\033[1;33m  ╔══════════════════════════════════════════════════════════════════╗\033[0m")
            lines.append(f"\033[1;33m  ║  FINAL SUMMARY — {elapsed:.0f}s total                                     ║\033[0m")
            lines.append(f"\033[1;33m  ╠══════════════════════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;33m  ║  Total ops:    {total:<8d}                                        ║\033[0m")
            lines.append(f"\033[1;33m  ║  Throughput:   {ops_sec:<8.1f} ops/sec                                ║\033[0m")
            lines.append(f"\033[1;33m  ║  Errors:       {errors:<8d} ({errors/total*100:.1f}%)                                  ║\033[0m" if total else f"\033[1;33m  ║  Errors:       0                                              ║\033[0m")
            lines.append(f"\033[1;33m  ╠══════════════════════════════════════════════════════════════════╣\033[0m")
            lines.append(f"\033[1;33m  ║ {'Operation':<22s} {'Count':>6s} {'Err':>4s} {'ops/s':>6s} {'p50':>7s} {'p95':>7s} {'p99':>7s} ║\033[0m")
            lines.append(f"\033[1;33m  ╠══════════════════════════════════════════════════════════════════╣\033[0m")

            for op in sorted(self._ops.keys()):
                entry = self._ops[op]
                count = entry["count"]
                errs = entry["errors"]
                lats = entry["latencies"]
                op_sec = count / elapsed if elapsed > 0 else 0

                if lats:
                    p50 = statistics.median(lats)
                    p95 = self._percentile(lats, 95)
                    p99 = self._percentile(lats, 99)
                else:
                    p50 = p95 = p99 = 0

                mark = "\033[0;32m✓" if errs == 0 else "\033[0;31m✗"
                lines.append(f"  {mark} {op:<22s} {count:>6d} {errs:>4d} {op_sec:>6.1f} {p50:>6.0f}ms {p95:>6.0f}ms {p99:>6.0f}ms\033[0m")

            lines.append(f"\033[1;33m  ╚══════════════════════════════════════════════════════════════════╝\033[0m")
            print("\n".join(lines), file=sys.stderr)

    @staticmethod
    def _percentile(data: list[float], pct: int) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * pct / 100)
        return sorted_data[min(idx, len(sorted_data) - 1)]
