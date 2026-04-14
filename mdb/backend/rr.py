"""
rr (Mozilla record-and-replay) backend.

rr records a complete execution trace of a program and then allows
perfectly deterministic replay with full reverse-execution support.

Workflow:
  rr record ./binary [args]   # one-time recording
  rr replay                   # open GDB over the replay

This backend:
  1. Runs `rr record` to capture the execution trace.
  2. Opens `rr replay` as a subprocess (which itself runs GDB/MI).
  3. Delegates all GDB/MI communication to the GDBBackend base.

rr's GDB extension adds extra commands:
  - when             — print current event number
  - checkpoint       — save event
  - restart <cp>     — jump to event
  - run 0            — jump to start

See: https://rr-project.org/
"""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path
from typing import Optional

from .gdb import GDBBackend
from .base import StopEvent


class RRBackend(GDBBackend):
    """rr record-and-replay backend (superset of GDBBackend)."""

    def __init__(self, binary: str, config):
        super().__init__(binary, config)
        self._rr_path = self._require_rr()
        self._trace_dir: Optional[Path] = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def record(self) -> None:
        """Run `rr record` to capture a fresh execution trace."""
        cmd = [self._rr_path, "record", self.binary]
        trace_root = Path.home() / ".local/share/rr"
        print(f"\033[90m  rr record: {' '.join(cmd)}\033[0m")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"rr record failed:\n{result.stderr}"
            )
        # Find the newest trace directory
        if trace_root.exists():
            traces = sorted(trace_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            if traces:
                self._trace_dir = traces[0]

    def start(self, args: str = "") -> None:
        """
        Launch `rr replay` which opens GDB/MI over the recorded trace.
        If no trace exists yet, record first.
        """
        if not self._has_trace():
            print("\033[33m  No rr trace found — recording first…\033[0m")
            self.record()

        rr_cmd = [self._rr_path, "replay", "--interpreter=mi3"]
        if self._trace_dir:
            rr_cmd += [str(self._trace_dir)]

        import subprocess, threading
        self._proc = subprocess.Popen(
            rr_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        import queue
        self._output_q = queue.Queue()
        import threading
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

        self._drain(timeout=5.0)
        if args:
            self._cmd(f"-exec-arguments {args}")
        self._cmd("-exec-continue")  # rr replay starts at entry; run to main

    # ── rr-specific commands ───────────────────────────────────────────────

    def when(self) -> Optional[int]:
        """Return the current rr event number (for checkpointing)."""
        out = self._cmd("when")
        import re
        m = re.search(r"(\d+)", out)
        return int(m.group(1)) if m else None

    def checkpoint(self, name: str = "") -> int:
        """Create an rr checkpoint, return event number."""
        out = self._cmd("checkpoint")
        import re
        m = re.search(r"Checkpoint (\d+)", out, re.IGNORECASE)
        return int(m.group(1)) if m else -1

    def goto_checkpoint(self, cp_id: int):
        """Jump to a previously saved rr checkpoint."""
        self._cmd(f"restart {cp_id}")

    # ── helpers ────────────────────────────────────────────────────────────

    def _has_trace(self) -> bool:
        if self._trace_dir and self._trace_dir.exists():
            return True
        trace_root = Path.home() / ".local/share/rr"
        if not trace_root.exists():
            return False
        entries = list(trace_root.iterdir())
        return bool(entries)

    @staticmethod
    def _require_rr() -> str:
        path = shutil.which("rr")
        if path is None:
            raise EnvironmentError(
                "rr not found in PATH.\n"
                "Install it from https://rr-project.org/ or via your package manager:\n"
                "  Ubuntu/Debian: sudo apt install rr\n"
                "  macOS:         brew install rr\n"
                "  Arch:          sudo pacman -S rr"
            )
        return path
