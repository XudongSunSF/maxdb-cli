"""
GDB backend using the GDB Machine Interface (MI) protocol.

GDB's reverse debugging is enabled via:
  (gdb) target record-full
  (gdb) reverse-step / reverse-next / reverse-continue / reverse-finish

This backend drives GDB as a subprocess, communicating over stdin/stdout
using the GDB/MI protocol for structured, parseable output.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import queue
import time
from pathlib import Path
from typing import Optional

from .base import Backend, StopEvent, Breakpoint


_MI_RESULT_RE  = re.compile(r'^(\d*)\^(done|running|error|exit)(,(.*))?$')
_MI_ASYNC_RE   = re.compile(r'^(\d*)([*=~@&])(.+)$')
_BP_ID_RE      = re.compile(r'number="(\d+)"')
_ADDR_RE       = re.compile(r'addr="(0x[0-9a-fA-F]+)"')


def _parse_mi_record(line: str) -> dict:
    """Very lightweight GDB/MI record parser (sufficient for our needs)."""
    result: dict = {"raw": line}

    m = _MI_RESULT_RE.match(line)
    if m:
        result["token"] = m.group(1)
        result["class"] = m.group(2)
        result["payload"] = m.group(4) or ""
        result["type"] = "result"
        return result

    m = _MI_ASYNC_RE.match(line)
    if m:
        result["token"] = m.group(1)
        result["kind"] = m.group(2)
        result["payload"] = m.group(3)
        result["type"] = "async"
        return result

    result["type"] = "other"
    return result


def _extract_kv(payload: str, key: str) -> str:
    """Extract value of key="..." from a GDB/MI payload string."""
    pattern = rf'{re.escape(key)}="([^"]*)"'
    m = re.search(pattern, payload)
    return m.group(1) if m else ""


class GDBBackend(Backend):
    """Controls GDB via the MI protocol for time-travel debugging."""

    def __init__(self, binary: str, config):
        super().__init__(binary, config)
        self._proc: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._output_q: queue.Queue = queue.Queue()
        self._token = 0
        self._bp_counter = 0
        self._source_cache: dict[str, list[str]] = {}
        self._current_file: str = ""
        self._current_line: Optional[int] = None

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self, args: str = "") -> None:
        if self._proc and self._proc.poll() is None:
            self.terminate()

        gdb_cmd = ["gdb", "--interpreter=mi3", "--quiet", self.binary]
        self._proc = subprocess.Popen(
            gdb_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

        # Wait for GDB prompt
        self._drain(timeout=3.0)

        # Enable record-full for reverse debugging
        self._cmd("-gdb-set target-async off")
        self._cmd("target record-full")

        # Set args and run
        if args:
            self._cmd(f"-exec-arguments {args}")
        self._cmd("-exec-run")

    def record(self) -> None:
        """Re-record via rr (if available) or reset GDB record-full."""
        rr = self._find_rr()
        if rr:
            subprocess.run([rr, "record", self.binary], check=False)
        else:
            self._cmd("record stop")
            self._cmd("run")
            self._cmd("target record-full")

    def terminate(self) -> None:
        if self._proc:
            try:
                self._cmd("-gdb-exit")
                self._proc.wait(timeout=3)
            except Exception:
                self._proc.kill()
            self._proc = None

    def wait_for_stop(self) -> StopEvent:
        return self._collect_stop()

    # ── time-travel execution ──────────────────────────────────────────────

    def step(self, forward: bool = True) -> StopEvent:
        cmd = "-exec-step" if forward else "reverse-step"
        self._cmd(cmd)
        return self._collect_stop()

    def next(self, forward: bool = True) -> StopEvent:
        cmd = "-exec-next" if forward else "reverse-next"
        self._cmd(cmd)
        return self._collect_stop()

    def cont(self, forward: bool = True) -> StopEvent:
        cmd = "-exec-continue" if forward else "reverse-continue"
        self._cmd(cmd)
        return self._collect_stop()

    def finish(self, forward: bool = True) -> StopEvent:
        cmd = "-exec-finish" if forward else "reverse-finish"
        self._cmd(cmd)
        return self._collect_stop()

    # ── breakpoints ────────────────────────────────────────────────────────

    def set_breakpoint(self, location: str) -> Breakpoint:
        self._bp_counter += 1
        out = self._cmd(f"-break-insert {location}")
        bp_id = int(_extract_kv(out, "number") or self._bp_counter)
        return Breakpoint(id=bp_id, location=location)

    def set_watchpoint(self, expr: str) -> Breakpoint:
        self._bp_counter += 1
        out = self._cmd(f"-break-watch {expr}")
        wp_id = int(_extract_kv(out, "number") or self._bp_counter)
        return Breakpoint(id=wp_id, location=expr, kind="watch")

    def delete_breakpoint(self, bp_id: int) -> None:
        self._cmd(f"-break-delete {bp_id}")

    # ── inspection ────────────────────────────────────────────────────────

    def get_locals(self, frame: int = 0) -> dict[str, str]:
        out = self._cmd("-stack-list-locals --simple-values")
        return self._parse_variable_list(out)

    def get_args(self, frame: int = 0) -> dict[str, str]:
        out = self._cmd(f"-stack-list-arguments --simple-values {frame} {frame}")
        return self._parse_variable_list(out)

    def get_backtrace(self) -> list[dict]:
        out = self._cmd("-stack-list-frames")
        frames = []
        for m in re.finditer(
            r'frame=\{level="(\d+)",addr="([^"]*)",func="([^"]*)"(?:,file="([^"]*)")?(?:,line="([^"]*)")?',
            out,
        ):
            frames.append({
                "id":   int(m.group(1)),
                "addr": m.group(2),
                "func": m.group(3),
                "file": m.group(4) or "",
                "line": int(m.group(5)) if m.group(5) else None,
            })
        return frames

    def get_registers(self) -> dict[str, str]:
        out = self._cmd("-data-list-register-values x")
        result = {}
        for m in re.finditer(r'number="(\d+)",value="([^"]*)"', out):
            result[f"r{m.group(1)}"] = m.group(2)
        return result

    def evaluate(self, expr: str) -> str:
        out = self._cmd(f"-data-evaluate-expression {expr}")
        m = re.search(r'value="((?:[^"\\]|\\.)*)"', out)
        return m.group(1) if m else out

    def select_frame(self, n: int) -> None:
        self._cmd(f"-stack-select-frame {n}")

    def current_line(self) -> Optional[int]:
        return self._current_line

    def list_source(self, location: str, n_lines: int) -> list[tuple[int, str]]:
        if not self._current_file:
            return []
        src_path = Path(self._current_file)
        if not src_path.exists():
            # Try relative to binary
            src_path = Path(self.binary).parent / src_path.name
        if not src_path.exists():
            return []

        if str(src_path) not in self._source_cache:
            try:
                self._source_cache[str(src_path)] = src_path.read_text().splitlines()
            except OSError:
                return []

        lines = self._source_cache[str(src_path)]
        center = (self._current_line or 1) - 1  # 0-indexed
        half = n_lines // 2
        start = max(0, center - half)
        end = min(len(lines), center + half + 1)
        return [(i + 1, lines[i]) for i in range(start, end)]

    # ── internal helpers ───────────────────────────────────────────────────

    def _next_token(self) -> str:
        self._token += 1
        return str(self._token)

    def _cmd(self, mi_cmd: str, timeout: float = 10.0) -> str:
        """Send a GDB/MI command, return the result payload string."""
        if not self._proc or self._proc.poll() is not None:
            return ""
        tok = self._next_token()
        full_cmd = f"{tok}{mi_cmd}\n"
        try:
            self._proc.stdin.write(full_cmd)
            self._proc.stdin.flush()
        except BrokenPipeError:
            return ""
        return self._drain(token=tok, timeout=timeout)

    def _drain(self, token: str = "", timeout: float = 5.0) -> str:
        """Read output until we see a result record matching token (or timeout)."""
        result_payload = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self._output_q.get(timeout=0.1)
            except queue.Empty:
                continue
            rec = _parse_mi_record(line)
            if rec["type"] == "result":
                if not token or rec.get("token") == token:
                    result_payload = rec.get("payload", "")
                    break
        return result_payload

    def _reader_loop(self):
        """Background thread that reads GDB output line-by-line."""
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.rstrip("\n")
            self._output_q.put(line)

    def _collect_stop(self) -> StopEvent:
        """
        Collect asynchronous stop notification from GDB output.
        GDB emits: *stopped,reason="...",frame={...} ...
        """
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            try:
                line = self._output_q.get(timeout=0.5)
            except queue.Empty:
                # Check if process died
                if self._proc and self._proc.poll() is not None:
                    return StopEvent(reason="exited", exit_code=self._proc.returncode, alive=False)
                continue

            if line.startswith("*stopped"):
                payload = line[len("*stopped,"):]
                reason = _extract_kv(payload, "reason") or "unknown"
                func   = _extract_kv(payload, "func")
                file_  = _extract_kv(payload, "fullname") or _extract_kv(payload, "file")
                line_s = _extract_kv(payload, "line")
                signal = _extract_kv(payload, "signal-name")
                ln = int(line_s) if line_s.isdigit() else None

                if file_:
                    self._current_file = file_
                if ln:
                    self._current_line = ln

                return StopEvent(
                    reason=reason, file=file_, line=ln,
                    func=func, signal=signal, alive=True, raw=line,
                )

            if line.startswith("*running"):
                continue  # still going, keep waiting

            if "exited" in line:
                exit_code = 0
                m = re.search(r"exit-code=\"(\d+)\"", line)
                if m:
                    exit_code = int(m.group(1), 16)
                return StopEvent(reason="exited", exit_code=exit_code, alive=False)

        return StopEvent(reason="timeout", alive=True)

    def _parse_variable_list(self, payload: str) -> dict[str, str]:
        """Parse GDB/MI variable list into {name: value}."""
        result = {}
        for m in re.finditer(r'\{name="([^"]*)",(?:type="[^"]*",)?value="((?:[^"\\]|\\.)*)"\}', payload):
            result[m.group(1)] = m.group(2)
        return result

    @staticmethod
    def _find_rr() -> Optional[str]:
        return shutil.which("rr")
