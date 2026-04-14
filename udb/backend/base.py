"""Abstract backend interface for debugger backends (GDB, rr)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StopEvent:
    """Represents a point where execution has stopped."""
    reason: str          # "breakpoint-hit", "end-stepping-range", "signal-received", "exited", etc.
    file: str = ""
    line: Optional[int] = None
    func: str = ""
    signal: str = ""     # e.g. "SIGSEGV"
    exit_code: Optional[int] = None
    alive: bool = True
    raw: str = ""        # raw GDB/rr output for debugging

    @property
    def is_crash(self) -> bool:
        return self.reason == "signal-received" and self.signal in (
            "SIGSEGV", "SIGABRT", "SIGFPE", "SIGBUS", "SIGILL"
        )

    @property
    def label(self) -> str:
        if self.is_crash:
            return f"\033[1;31m{self.signal}\033[0m — {self.func}() at {self.file}:{self.line}"
        if self.reason == "exited":
            return f"Program exited with code {self.exit_code}"
        if self.file and self.line:
            return f"{self.func}() at {self.file}:{self.line}"
        return self.reason


@dataclass
class Breakpoint:
    id: int
    location: str
    kind: str = "break"   # "break" | "watch"
    enabled: bool = True
    hit_count: int = 0


class Backend(ABC):
    """Abstract base class for debugger backends."""

    def __init__(self, binary: str, config):
        self.binary = binary
        self.config = config

    # ── lifecycle ──────────────────────────────────────────────────────────

    @abstractmethod
    def start(self, args: str = "") -> None:
        """Launch the program (begin replay for rr)."""

    @abstractmethod
    def record(self) -> None:
        """Record a fresh execution trace (rr record)."""

    @abstractmethod
    def terminate(self) -> None:
        """Kill the inferior and clean up resources."""

    @abstractmethod
    def wait_for_stop(self) -> StopEvent:
        """Block until the inferior stops, return the stop reason."""

    # ── time-travel execution ──────────────────────────────────────────────

    @abstractmethod
    def step(self, forward: bool = True) -> StopEvent:
        """Step one source line (forward or backward)."""

    @abstractmethod
    def next(self, forward: bool = True) -> StopEvent:
        """Step over (forward or backward)."""

    @abstractmethod
    def cont(self, forward: bool = True) -> StopEvent:
        """Continue to next breakpoint (forward or backward)."""

    @abstractmethod
    def finish(self, forward: bool = True) -> StopEvent:
        """Run until the current function returns (forward or backward)."""

    # ── breakpoints ────────────────────────────────────────────────────────

    @abstractmethod
    def set_breakpoint(self, location: str) -> Breakpoint:
        """Set a breakpoint at a location string."""

    @abstractmethod
    def set_watchpoint(self, expr: str) -> Breakpoint:
        """Set a watchpoint on an expression."""

    @abstractmethod
    def delete_breakpoint(self, bp_id: int) -> None:
        """Remove a breakpoint or watchpoint."""

    # ── inspection ────────────────────────────────────────────────────────

    @abstractmethod
    def get_locals(self, frame: int = 0) -> dict[str, str]:
        """Return {name: value_str} for local variables in frame."""

    @abstractmethod
    def get_args(self, frame: int = 0) -> dict[str, str]:
        """Return {name: value_str} for function arguments in frame."""

    @abstractmethod
    def get_backtrace(self) -> list[dict]:
        """Return list of frame dicts: {id, func, file, line, addr}."""

    @abstractmethod
    def get_registers(self) -> dict[str, str]:
        """Return {register_name: value_str}."""

    @abstractmethod
    def evaluate(self, expr: str) -> str:
        """Evaluate an expression in the current frame, return string."""

    @abstractmethod
    def select_frame(self, n: int) -> None:
        """Switch to stack frame n."""

    @abstractmethod
    def current_line(self) -> Optional[int]:
        """Return the current source line number, or None."""

    @abstractmethod
    def list_source(self, location: str, n_lines: int) -> list[tuple[int, str]]:
        """Return [(line_no, source_text)] around location."""
