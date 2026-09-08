"""Per-user JSONL audit trail for Neuro simulation."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


class UserAudit:
    """Writes one JSONL file per simulated user, logging every operation."""

    def __init__(self, user_id: str, report_dir: str):
        self.user_id = user_id
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.report_dir / f"{user_id}.jsonl"
        self._file = open(self._path, "a", encoding="utf-8")
        self._seq = 0

    def log(self, operation: str, details: dict,
            status_code: int = 0, latency_ms: float = 0.0,
            error: str = ""):
        """Append one audit record."""
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "user": self.user_id,
            "op": operation,
            "status": status_code,
            "latency_ms": round(latency_ms, 1),
            "error": error,
            **details,
        }
        self._file.write(json.dumps(record, default=str) + "\n")
        self._file.flush()

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()
