"""
CycleLogger — records every metacognitive cycle to a JSON Lines file (AC #4).

Each line in the output file is a self-contained JSON object representing one
complete observe → evaluate → reflect → update cycle, suitable for offline
analysis or visualisation.

Author: Eduardo Arana
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .models import MetacognitiveLog


class CycleLogger:
    """
    Appends MetacognitiveLog entries to a JSON Lines file.

    Usage
    -----
    logger = CycleLogger("results/cycles_20260415T120000.jsonl")
    logger.log(cycle_log)   # called by MetaAgent after every run
    logger.close()          # flush and close the file handle
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")
        self._count = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def log(self, cycle: MetacognitiveLog) -> None:
        """Append *cycle* as a single JSON line."""
        self._file.write(json.dumps(cycle.to_dict(), ensure_ascii=False) + "\n")
        self._file.flush()
        self._count += 1

    def close(self) -> None:
        """Flush and close the underlying file."""
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def cycle_count(self) -> int:
        """Number of cycles logged in this session."""
        return self._count

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "CycleLogger":
        return self

    def __exit__(self, *_) -> None:
        self.close()
