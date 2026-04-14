"""Session: owns the backend and all mutable debugging state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .backend.base import Backend, StopEvent, Breakpoint


@dataclass
class Session:
    backend: Backend
    binary: Path
    config: Any
    is_active: bool = False
    _breakpoints: dict[int, Breakpoint] = field(default_factory=dict)
    _current_frame: int = 0
    _started_at: float = field(default_factory=time.time)

    # ── lifecycle ──────────────────────────────────────────────────────────

    def run(self, args: str = "") -> StopEvent:
        self.backend.start(args)
        self.is_active = True
        return self.backend.wait_for_stop()

    def record(self):
        self.backend.record()

    def close(self):
        self.backend.terminate()
        self.is_active = False

    # ── time-travel execution ──────────────────────────────────────────────

    def step(self, forward: bool = True) -> StopEvent:
        ev = self.backend.step(forward=forward)
        self.is_active = ev.alive
        return ev

    def next(self, forward: bool = True) -> StopEvent:
        ev = self.backend.next(forward=forward)
        self.is_active = ev.alive
        return ev

    def cont(self, forward: bool = True) -> StopEvent:
        ev = self.backend.cont(forward=forward)
        self.is_active = ev.alive
        return ev

    def finish(self, forward: bool = True) -> StopEvent:
        ev = self.backend.finish(forward=forward)
        self.is_active = ev.alive
        return ev

    # ── breakpoints / watchpoints ──────────────────────────────────────────

    def set_breakpoint(self, location: str) -> Breakpoint:
        bp = self.backend.set_breakpoint(location)
        self._breakpoints[bp.id] = bp
        return bp

    def set_watchpoint(self, expr: str) -> Breakpoint:
        wp = self.backend.set_watchpoint(expr)
        self._breakpoints[wp.id] = wp
        return wp

    def delete_breakpoint(self, bp_id: int):
        self.backend.delete_breakpoint(bp_id)
        self._breakpoints.pop(bp_id, None)

    def get_breakpoints(self) -> list[Breakpoint]:
        return list(self._breakpoints.values())

    # ── inspection ────────────────────────────────────────────────────────

    def get_locals(self) -> dict[str, str]:
        return self.backend.get_locals(self._current_frame)

    def get_args(self) -> dict[str, str]:
        return self.backend.get_args(self._current_frame)

    def get_backtrace(self) -> list[dict]:
        return self.backend.get_backtrace()

    def get_registers(self) -> dict[str, str]:
        return self.backend.get_registers()

    def evaluate(self, expr: str) -> str:
        return self.backend.evaluate(expr)

    def select_frame(self, n: int):
        self._current_frame = n
        self.backend.select_frame(n)

    def current_line(self) -> Optional[int]:
        return self.backend.current_line()

    def list_source(self, location: str, n_lines: int) -> list[tuple[int, str]]:
        return self.backend.list_source(location, n_lines)

    # ── state snapshot for AI ─────────────────────────────────────────────

    def get_state(self) -> dict:
        try:
            bt = self.get_backtrace()
            locals_ = self.get_locals()
            args = self.get_args()
            line = self.current_line()
            func = bt[0].get("func", "?") if bt else "?"
            file_ = bt[0].get("file", str(self.binary)) if bt else str(self.binary)
        except Exception:
            bt, locals_, args, line, func, file_ = [], {}, {}, None, "?", str(self.binary)

        return {
            "binary": str(self.binary),
            "func": func,
            "file": file_,
            "line": line,
            "backtrace": bt,
            "locals": locals_,
            "args": args,
            "breakpoints": [
                {"id": bp.id, "location": bp.location, "enabled": bp.enabled}
                for bp in self._breakpoints.values()
            ],
        }
