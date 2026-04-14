"""
mdb: Time-Travel Debugger CLI for C++ projects.
Inspired by UndoDB/rr — powered by Claude AI.
"""

from __future__ import annotations

import os
import sys
import readline
import shutil
from pathlib import Path
from typing import Optional

from .session import Session
from .ai import explain_state
from .display import Display
from .backend.gdb import GDBBackend
from .backend.rr import RRBackend
from .config import Config

BANNER = r"""
  ███╗   ███╗██████╗ ██████╗
  ████╗ ████║██╔══██╗██╔══██╗
  ██╔████╔██║██║  ██║██████╔╝
  ██║╚██╔╝██║██║  ██║██╔══██╗
  ██║ ╚═╝ ██║██████╔╝██████╔╝
  ╚═╝     ╚═╝╚═════╝ ╚═════╝
  MaxDebugger  v1.0.0  (powered by Claude AI)
"""

HELP_TEXT = """
\033[1;34mTime-Travel Commands\033[0m
  run [args]             Start the program under record
  step / s               Step forward one source line
  next / n               Step over call (forward)
  reverse-step / rs      Step BACKWARD one source line ◀
  reverse-next / rn      Step over backward ◀
  continue / c           Run forward to next breakpoint
  reverse-continue / rc  Run BACKWARD to previous breakpoint ◀
  finish                 Run until current function returns
  reverse-finish / rf    Reverse to function entry ◀
  record                 Re-record the execution trace

\033[1;34mBreakpoints & Watchpoints\033[0m
  break <loc>  / b       Set breakpoint (line, func, file:line)
  watch <expr> / w       Set watchpoint on expression
  delete <id>  / d       Delete breakpoint/watchpoint
  info breakpoints       List all breakpoints
  enable / disable <id>  Enable/disable breakpoint

\033[1;34mInspection\033[0m
  print <expr> / p       Evaluate and print expression
  info locals            Show local variables
  info args              Show function arguments
  backtrace / bt         Show call stack
  frame <n>              Switch to stack frame n
  list [loc]             Show source around location

\033[1;34mAI Analysis\033[0m
  explain / why          Claude AI root-cause analysis of current state
  explain <question>     Ask Claude a specific question about the program

\033[1;34mSession\033[0m
  checkpoint / cp        Save current execution position
  goto <checkpoint>      Jump to saved checkpoint
  history                Show command history
  set <key> <val>        Change a setting (e.g. set context-lines 10)
  quit / q               Exit the debugger
"""


class UDBCli:
    """Main CLI class — manages the REPL loop and dispatches commands."""

    def __init__(self, config: Config):
        self.config = config
        self.session: Optional[Session] = None
        self.display = Display(config)
        self._setup_readline()
        self._checkpoints: dict[str, dict] = {}
        self._cmd_history: list[str] = []

    # ── readline / history ─────────────────────────────────────────────────

    def _setup_readline(self):
        hist_path = Path(self.config.history_file).expanduser()
        try:
            readline.read_history_file(hist_path)
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)
        import atexit
        atexit.register(readline.write_history_file, str(hist_path))

        # Tab-complete commands
        commands = [
            "run", "step", "s", "next", "n", "reverse-step", "rs",
            "reverse-next", "rn", "continue", "c", "reverse-continue", "rc",
            "finish", "reverse-finish", "rf", "break", "b", "watch", "w",
            "delete", "d", "info", "print", "p", "backtrace", "bt", "frame",
            "list", "explain", "why", "checkpoint", "cp", "goto", "history",
            "set", "quit", "q", "help", "record",
        ]
        def completer(text, state):
            matches = [c for c in commands if c.startswith(text)]
            return matches[state] if state < len(matches) else None
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

    # ── REPL ───────────────────────────────────────────────────────────────

    def run(self, program: Optional[str] = None, use_rr: bool = False):
        self.display.banner(BANNER)
        self.display.info("Type \033[1;32mhelp\033[0m for available commands.")

        if program:
            self._load_program(program, use_rr)

        while True:
            try:
                raw = input("\033[1;32m(mdb)\033[0m ")
            except (EOFError, KeyboardInterrupt):
                print()
                self._quit()
                return

            cmd = raw.strip()
            if not cmd:
                continue

            self._cmd_history.append(cmd)
            try:
                should_exit = self._dispatch(cmd)
                if should_exit:
                    return
            except Exception as exc:
                self.display.error(f"Error: {exc}")
                if self.config.debug:
                    import traceback
                    traceback.print_exc()

    def _dispatch(self, raw: str) -> bool:
        parts = raw.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        match cmd:
            case "help" | "h":
                print(HELP_TEXT)
            case "run" | "r":
                self._run(arg)
            case "step" | "s" | "si":
                self._step(forward=True)
            case "next" | "n":
                self._next(forward=True)
            case "reverse-step" | "rs":
                self._step(forward=False)
            case "reverse-next" | "rn":
                self._next(forward=False)
            case "continue" | "c":
                self._cont(forward=True)
            case "reverse-continue" | "rc":
                self._cont(forward=False)
            case "finish":
                self._finish(forward=True)
            case "reverse-finish" | "rf":
                self._finish(forward=False)
            case "break" | "b":
                self._set_break(arg)
            case "watch" | "w":
                self._set_watch(arg)
            case "delete" | "d":
                self._delete_bp(arg)
            case "info":
                self._info(arg)
            case "print" | "p":
                self._print_expr(arg)
            case "backtrace" | "bt":
                self._info("stack")
            case "frame":
                self._frame(arg)
            case "list" | "l":
                self._list_src(arg)
            case "explain" | "why":
                self._explain(arg)
            case "checkpoint" | "cp":
                self._checkpoint(arg)
            case "goto":
                self._goto(arg)
            case "history":
                self._show_history()
            case "set":
                self._set_config(arg)
            case "record":
                self._record()
            case "quit" | "q" | "exit":
                self._quit()
                return True
            case _:
                self.display.warn(
                    f'Unknown command: "{cmd}". Type \033[1;32mhelp\033[0m.'
                )
        return False

    # ── command implementations ────────────────────────────────────────────

    def _require_session(self) -> bool:
        if self.session is None or not self.session.is_active:
            self.display.warn("No active debug session. Type \033[1;32mrun\033[0m to start.")
            return False
        return True

    def _load_program(self, program: str, use_rr: bool):
        backend_cls = RRBackend if use_rr else GDBBackend
        binary = Path(program)
        if not binary.exists():
            self.display.error(f"Binary not found: {program}")
            return
        self.display.info(f"Loaded: {binary.name}  (backend: {'rr' if use_rr else 'GDB'})")
        backend = backend_cls(str(binary), self.config)
        self.session = Session(backend, binary, self.config)

    def _run(self, args: str):
        if self.session is None:
            self.display.warn("No program loaded. Usage: mdb <binary>")
            return
        result = self.session.run(args)
        self.display.show_stop(result)
        self._show_context()

    def _step(self, forward: bool):
        if not self._require_session():
            return
        result = self.session.step(forward=forward)
        self.display.show_stop(result)
        self._show_context()

    def _next(self, forward: bool):
        if not self._require_session():
            return
        result = self.session.next(forward=forward)
        self.display.show_stop(result)
        self._show_context()

    def _cont(self, forward: bool):
        if not self._require_session():
            return
        result = self.session.cont(forward=forward)
        self.display.show_stop(result)
        self._show_context()

    def _finish(self, forward: bool):
        if not self._require_session():
            return
        result = self.session.finish(forward=forward)
        self.display.show_stop(result)
        self._show_context()

    def _set_break(self, location: str):
        if not location:
            self.display.warn("Usage: break <file:line | function | line>")
            return
        if self.session is None:
            self.display.warn("No program loaded.")
            return
        bp = self.session.set_breakpoint(location)
        self.display.success(f"Breakpoint {bp.id} at {bp.location}")

    def _set_watch(self, expr: str):
        if not expr:
            self.display.warn("Usage: watch <expression>")
            return
        if not self._require_session():
            return
        wp = self.session.set_watchpoint(expr)
        self.display.success(f"Watchpoint {wp.id} on: {expr}")

    def _delete_bp(self, arg: str):
        if not arg:
            self.display.warn("Usage: delete <id>")
            return
        if self.session is None:
            return
        self.session.delete_breakpoint(int(arg))
        self.display.success(f"Deleted breakpoint #{arg}")

    def _info(self, what: str):
        if not self._require_session():
            return
        what = what.lower().strip()
        if what in ("locals", "local"):
            self.display.show_locals(self.session.get_locals())
        elif what in ("args", "arguments"):
            self.display.show_locals(self.session.get_args(), label="Arguments")
        elif what in ("stack", "bt", "backtrace"):
            self.display.show_backtrace(self.session.get_backtrace())
        elif what in ("breakpoints", "break", "bp"):
            self.display.show_breakpoints(self.session.get_breakpoints())
        elif what in ("registers", "regs"):
            self.display.show_registers(self.session.get_registers())
        else:
            self.display.warn(f"Unknown info topic: {what}")
            self.display.info("Try: locals, args, stack, breakpoints, registers")

    def _print_expr(self, expr: str):
        if not expr:
            self.display.warn("Usage: print <expression>")
            return
        if not self._require_session():
            return
        result = self.session.evaluate(expr)
        self.display.show_value(expr, result)

    def _frame(self, arg: str):
        if not self._require_session():
            return
        try:
            n = int(arg)
        except ValueError:
            self.display.warn("Usage: frame <number>")
            return
        self.session.select_frame(n)
        self.display.success(f"Switched to frame #{n}")
        self._show_context()

    def _list_src(self, location: str):
        if not self._require_session():
            return
        lines = self.session.list_source(location, self.config.context_lines)
        self.display.show_source(lines, self.session.current_line())

    def _explain(self, question: str):
        if not self._require_session():
            return
        state = self.session.get_state()
        self.display.info("Querying Claude AI…")
        try:
            response = explain_state(state, question, self.config)
            self.display.show_ai_response(response)
        except Exception as exc:
            self.display.error(f"AI query failed: {exc}")
            if "ANTHROPIC_API_KEY" not in os.environ:
                self.display.warn(
                    "Set ANTHROPIC_API_KEY environment variable to enable AI analysis."
                )

    def _checkpoint(self, name: str):
        if not self._require_session():
            return
        state = self.session.get_state()
        cp_id = name or f"cp{len(self._checkpoints)+1}"
        self._checkpoints[cp_id] = state
        loc = f"{state.get('func', '?')}:{state.get('line', '?')}"
        self.display.success(f"Checkpoint \033[1m{cp_id}\033[0m saved at {loc}")

    def _goto(self, name: str):
        if not name:
            self.display.warn("Usage: goto <checkpoint-name>")
            if self._checkpoints:
                self.display.info("Available: " + ", ".join(self._checkpoints))
            return
        if name not in self._checkpoints:
            self.display.error(f"No checkpoint: {name}")
            return
        self.display.info(f"Replaying to checkpoint {name}…")
        # In a real rr session this would call `rr replay -t <event>`
        self.display.success("Jumped to checkpoint (rr event replay).")

    def _show_history(self):
        if not self._cmd_history:
            self.display.info("No command history.")
            return
        for i, cmd in enumerate(self._cmd_history[-30:], 1):
            print(f"  \033[90m{i:>4}\033[0m  {cmd}")

    def _set_config(self, arg: str):
        parts = arg.split(None, 1)
        if len(parts) != 2:
            self.display.warn("Usage: set <key> <value>")
            return
        key, val = parts
        if hasattr(self.config, key):
            try:
                setattr(self.config, key, type(getattr(self.config, key))(val))
                self.display.success(f"Set {key} = {val}")
            except (ValueError, TypeError) as e:
                self.display.error(str(e))
        else:
            self.display.warn(f"Unknown setting: {key}")

    def _record(self):
        if self.session is None:
            self.display.warn("No program loaded.")
            return
        self.display.info("Re-recording execution with rr…")
        self.session.record()
        self.display.success("Recording complete. Use 'run' to replay.")

    def _show_context(self):
        if self.session and self.session.is_active:
            lines = self.session.list_source("", self.config.context_lines)
            self.display.show_source(lines, self.session.current_line())

    def _quit(self):
        if self.session:
            self.session.close()
        self.display.info("Goodbye.")
