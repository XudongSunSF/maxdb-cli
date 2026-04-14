"""
MCP (Model Context Protocol) server for mdb.

Exposes mdb's time-travel debugging capabilities as tools that VS Code
Copilot (or any MCP-compatible client) can invoke in agent mode.

Usage — VS Code (.vscode/mcp.json):
  {
    "servers": {
      "mdb": {
        "command": "python",
        "args": ["-m", "mdb.mcp_server"]
      }
    }
  }

Then in Copilot agent mode:
  "Load ./my_program, run it, and explain the crash."

No ANTHROPIC_API_KEY needed — the host LLM (Copilot) does the reasoning.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .config import Config
from .session import Session
from .backend.gdb import GDBBackend
from .backend.rr import RRBackend
from .backend.base import StopEvent

# ── server instance ──────────────────────────────────────────────────────────

mcp = FastMCP(
    "mdb",
    instructions=(
        "mdb is a time-travel debugger for C++ programs. It wraps GDB/rr "
        "to provide full reverse execution (step backward, continue backward, "
        "etc.). Use these tools to load a binary, set breakpoints, step through "
        "execution forwards and backwards, inspect variables and call stacks, "
        "and diagnose crashes like use-after-free or buffer overflows. "
        "Start by loading a binary with mdb_load, then run it with mdb_run."
    ),
)

# ── global session state ─────────────────────────────────────────────────────

_session: Optional[Session] = None
_config: Config = Config.from_env()


def _require_session() -> Session:
    if _session is None or not _session.is_active:
        raise RuntimeError(
            "No active debug session. Call mdb_load first to load a binary, "
            "then mdb_run to start it."
        )
    return _session


def _stop_event_to_dict(ev: StopEvent) -> dict:
    """Serialize a StopEvent for JSON output."""
    return {
        "reason": ev.reason,
        "file": ev.file,
        "line": ev.line,
        "func": ev.func,
        "signal": ev.signal,
        "exit_code": ev.exit_code,
        "alive": ev.alive,
        "is_crash": ev.is_crash,
    }


# ── lifecycle tools ──────────────────────────────────────────────────────────

@mcp.tool()
def mdb_load(binary: str, use_rr: bool = False) -> str:
    """Load a C++ binary for debugging.

    Args:
        binary: Path to the compiled binary (must be built with -g -O0).
        use_rr: If True, use Mozilla rr backend instead of GDB record-full.
                rr gives much better performance on real codebases.

    Returns:
        Confirmation message with binary name and backend.
    """
    global _session, _config

    path = Path(binary).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Binary not found: {binary}")

    backend_cls = RRBackend if use_rr else GDBBackend
    backend = backend_cls(str(path), _config)
    _session = Session(backend, path, _config)

    backend_name = "rr" if use_rr else "GDB"
    return f"Loaded {path.name} (backend: {backend_name}). Call mdb_run to start."


@mcp.tool()
def mdb_run(args: str = "") -> dict:
    """Start (or restart) the loaded program under the time-travel recorder.

    Args:
        args: Optional command-line arguments to pass to the program.

    Returns:
        Stop event dict describing where execution first stopped.
    """
    if _session is None:
        raise RuntimeError("No binary loaded. Call mdb_load first.")
    ev = _session.run(args)
    return _stop_event_to_dict(ev)


# ── time-travel execution ────────────────────────────────────────────────────

@mcp.tool()
def mdb_step(forward: bool = True) -> dict:
    """Step one source line, entering function calls.

    Args:
        forward: True to step forward, False to step BACKWARD in time.

    Returns:
        Stop event dict describing the new execution position.
    """
    session = _require_session()
    ev = session.step(forward=forward)
    return _stop_event_to_dict(ev)


@mcp.tool()
def mdb_next(forward: bool = True) -> dict:
    """Step one source line, stepping OVER function calls.

    Args:
        forward: True to step forward, False to step BACKWARD in time.

    Returns:
        Stop event dict describing the new execution position.
    """
    session = _require_session()
    ev = session.next(forward=forward)
    return _stop_event_to_dict(ev)


@mcp.tool()
def mdb_continue(forward: bool = True) -> dict:
    """Continue execution until the next breakpoint or crash.

    Args:
        forward: True to continue forward, False to REVERSE-CONTINUE
                 backward to the previous breakpoint.

    Returns:
        Stop event dict describing where execution stopped.
    """
    session = _require_session()
    ev = session.cont(forward=forward)
    return _stop_event_to_dict(ev)


@mcp.tool()
def mdb_finish(forward: bool = True) -> dict:
    """Run until the current function returns (or, in reverse, until entry).

    Args:
        forward: True for finish, False for reverse-finish (back to entry).

    Returns:
        Stop event dict describing where execution stopped.
    """
    session = _require_session()
    ev = session.finish(forward=forward)
    return _stop_event_to_dict(ev)


# ── breakpoints ──────────────────────────────────────────────────────────────

@mcp.tool()
def mdb_set_breakpoint(location: str) -> dict:
    """Set a breakpoint at a source location.

    Args:
        location: Where to break. Can be:
                  - a function name: "main", "delete_list"
                  - a file:line:    "use_after_free.cpp:20"
                  - a line number:  "42" (current file)

    Returns:
        Dict with breakpoint id and location.
    """
    session = _require_session()
    bp = session.set_breakpoint(location)
    return {"id": bp.id, "location": bp.location, "kind": bp.kind}


@mcp.tool()
def mdb_set_watchpoint(expr: str) -> dict:
    """Set a data watchpoint that triggers when an expression's value changes.

    Args:
        expr: C++ expression to watch, e.g. "ptr->next" or "counter".

    Returns:
        Dict with watchpoint id and expression.
    """
    session = _require_session()
    wp = session.set_watchpoint(expr)
    return {"id": wp.id, "location": wp.location, "kind": wp.kind}


@mcp.tool()
def mdb_delete_breakpoint(bp_id: int) -> str:
    """Delete a breakpoint or watchpoint by its ID.

    Args:
        bp_id: The breakpoint/watchpoint ID to delete.

    Returns:
        Confirmation message.
    """
    session = _require_session()
    session.delete_breakpoint(bp_id)
    return f"Deleted breakpoint #{bp_id}"


@mcp.tool()
def mdb_get_breakpoints() -> list[dict]:
    """List all active breakpoints and watchpoints.

    Returns:
        List of dicts with id, location, kind, enabled, hit_count.
    """
    session = _require_session()
    return [
        {
            "id": bp.id,
            "location": bp.location,
            "kind": bp.kind,
            "enabled": bp.enabled,
            "hit_count": bp.hit_count,
        }
        for bp in session.get_breakpoints()
    ]


# ── inspection ───────────────────────────────────────────────────────────────

@mcp.tool()
def mdb_get_locals() -> dict[str, str]:
    """Get all local variables in the current stack frame.

    Returns:
        Dict mapping variable names to their string values.
    """
    session = _require_session()
    return session.get_locals()


@mcp.tool()
def mdb_get_args() -> dict[str, str]:
    """Get all function arguments in the current stack frame.

    Returns:
        Dict mapping argument names to their string values.
    """
    session = _require_session()
    return session.get_args()


@mcp.tool()
def mdb_backtrace() -> list[dict]:
    """Get the full call stack (backtrace).

    Returns:
        List of stack frames, each with id, func, file, line, addr.
        Frame 0 is the innermost (current) frame.
    """
    session = _require_session()
    return session.get_backtrace()


@mcp.tool()
def mdb_evaluate(expr: str) -> str:
    """Evaluate a C++ expression in the current stack frame.

    Args:
        expr: Any valid C++ expression, e.g. "head->next", "*ptr",
              "sizeof(Node)", "arr[3]".

    Returns:
        The expression's value as a string.
    """
    session = _require_session()
    return session.evaluate(expr)


@mcp.tool()
def mdb_select_frame(frame_number: int) -> str:
    """Switch to a different stack frame for inspection.

    Args:
        frame_number: Frame index (0 = innermost/current frame).

    Returns:
        Confirmation message.
    """
    session = _require_session()
    session.select_frame(frame_number)
    return f"Switched to frame #{frame_number}"


@mcp.tool()
def mdb_list_source(location: str = "", context_lines: int = 15) -> list[dict]:
    """Show source code around the current execution point.

    Args:
        location: Optional location to list (default: current position).
        context_lines: Number of lines to show around the current line.

    Returns:
        List of dicts with line_number, text, and is_current fields.
    """
    session = _require_session()
    lines = session.list_source(location, context_lines)
    current = session.current_line()
    return [
        {
            "line_number": ln,
            "text": text,
            "is_current": ln == current,
        }
        for ln, text in lines
    ]


@mcp.tool()
def mdb_get_state() -> dict:
    """Get a full snapshot of the current debugging state.

    This includes: binary name, current location (function, file, line),
    the full call stack, all local variables, function arguments, and
    active breakpoints.

    This is the best tool to call when you need to analyze a crash or
    understand the current program state.

    Returns:
        Complete state dict suitable for root-cause analysis.
    """
    session = _require_session()
    return session.get_state()


# ── prompts ──────────────────────────────────────────────────────────────────

@mcp.prompt()
def analyze_crash() -> str:
    """Generate a prompt for AI root-cause analysis of the current crash.

    Call this after the program has crashed (SIGSEGV, SIGABRT, etc.)
    to get a structured analysis prompt. The host LLM will then use
    mdb_get_state and other inspection tools to diagnose the bug.
    """
    return (
        "The program being debugged has stopped. Please:\n"
        "1. Call mdb_get_state to get the full debugging context.\n"
        "2. Call mdb_list_source to see the source code around the crash.\n"
        "3. If the crash involves a pointer, call mdb_evaluate on the "
        "   relevant pointer expressions.\n"
        "4. Use mdb_step with forward=False (reverse-step) to go back in "
        "   time and trace how the corrupted state was reached.\n"
        "5. Provide your analysis using these sections:\n"
        "   ► CRASH SITE — where exactly execution stopped and what failed\n"
        "   ► ROOT CAUSE — why the bug occurred (not just what crashed)\n"
        "   ► TIME-TRAVEL INSIGHT — what reverse execution revealed\n"
        "   ► RECOMMENDED FIX — a minimal, correct code fix\n"
    )


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
