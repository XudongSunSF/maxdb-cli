"""Debugger backends: GDB (record-full) and rr (record-and-replay)."""

from .base import Backend, StopEvent, Breakpoint
from .gdb  import GDBBackend
from .rr   import RRBackend

__all__ = ["Backend", "StopEvent", "Breakpoint", "GDBBackend", "RRBackend"]
