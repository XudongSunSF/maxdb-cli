"""
Display: all terminal rendering for udb-cli.
Uses ANSI escape codes for colour; respects NO_COLOR env var.
"""

from __future__ import annotations

import os
import shutil
import textwrap
from typing import Optional

from .backend.base import StopEvent, Breakpoint

_NO_COLOR = bool(os.environ.get("NO_COLOR") or not os.isatty(1))


def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def _bold(t: str)     -> str: return _c("1", t)
def _dim(t: str)      -> str: return _c("2", t)
def _red(t: str)      -> str: return _c("1;31", t)
def _yellow(t: str)   -> str: return _c("1;33", t)
def _green(t: str)    -> str: return _c("1;32", t)
def _blue(t: str)     -> str: return _c("1;34", t)
def _cyan(t: str)     -> str: return _c("1;36", t)
def _magenta(t: str)  -> str: return _c("1;35", t)


# syntax-highlight a line of C++ source (very simple tokeniser)
_CPP_KEYWORDS = frozenset([
    "alignas","alignof","and","and_eq","asm","auto","bitand","bitor","bool",
    "break","case","catch","char","char8_t","char16_t","char32_t","class",
    "compl","concept","const","consteval","constexpr","constinit","const_cast",
    "continue","co_await","co_return","co_yield","decltype","default","delete",
    "do","double","dynamic_cast","else","enum","explicit","export","extern",
    "false","float","for","friend","goto","if","inline","int","long","mutable",
    "namespace","new","noexcept","not","not_eq","nullptr","operator","or",
    "or_eq","private","protected","public","register","reinterpret_cast",
    "requires","return","short","signed","sizeof","static","static_assert",
    "static_cast","struct","switch","template","this","thread_local","throw",
    "true","try","typedef","typeid","typename","union","unsigned","using",
    "virtual","void","volatile","wchar_t","while","xor","xor_eq",
])

import re as _re

_TOKEN_RE = _re.compile(
    r'(//[^\n]*)'             # line comment
    r'|("(?:[^"\\]|\\.)*")'  # string literal
    r"|('(?:[^'\\]|\\.)*')"  # char literal
    r'|(#\w+)'               # preprocessor
    r'|(<[^>]+>)'            # angle-bracket include
    r'|(\b[A-Za-z_]\w*\b)'  # identifier / keyword
    r'|(\b\d+\.?\d*\b)'     # number
)


def _highlight_cpp(line: str) -> str:
    if _NO_COLOR:
        return line
    result = []
    last = 0
    for m in _TOKEN_RE.finditer(line):
        start, end = m.span()
        result.append(line[last:start])
        tok = m.group(0)
        if m.group(1):                       # comment
            result.append(_dim(_c("32", tok)))
        elif m.group(2) or m.group(3):      # string / char
            result.append(_c("33", tok))
        elif m.group(4):                     # preprocessor
            result.append(_c("35", tok))
        elif m.group(5):                     # angle-bracket
            result.append(_c("33", tok))
        elif m.group(6):                     # identifier
            if tok in _CPP_KEYWORDS:
                result.append(_c("34", tok))
            elif tok[0].isupper():
                result.append(_c("36", tok))
            else:
                result.append(tok)
        elif m.group(7):                     # number
            result.append(_c("32", tok))
        else:
            result.append(tok)
        last = end
    result.append(line[last:])
    return "".join(result)


class Display:
    def __init__(self, config):
        self.config = config
        self._width = shutil.get_terminal_size().columns

    def _rule(self, char: str = "─") -> str:
        return _dim(char * min(self._width, 72))

    # ── basics ─────────────────────────────────────────────────────────────

    def banner(self, text: str):
        print(_cyan(text))

    def info(self, msg: str):
        print(f"  {_blue('ℹ')}  {msg}")

    def success(self, msg: str):
        print(f"  {_green('✔')}  {msg}")

    def warn(self, msg: str):
        print(f"  {_yellow('⚠')}  {msg}")

    def error(self, msg: str):
        print(f"  {_red('✖')}  {msg}")

    # ── stop event ─────────────────────────────────────────────────────────

    def show_stop(self, ev: StopEvent):
        if ev.is_crash:
            print()
            print(f"  {_red('●')} {_red(_bold('SIGNAL RECEIVED'))}: {_red(ev.signal)}")
            print(f"     {ev.func}()  at  {_bold(ev.file)}:{_yellow(str(ev.line))}")
            print(f"  {_dim('tip:')} type {_green('explain')} for AI root-cause analysis.")
        elif ev.reason == "exited":
            code = ev.exit_code or 0
            col = _green if code == 0 else _red
            print(f"  {col('●')} Program exited with code {col(str(code))}.")
        elif ev.reason == "breakpoint-hit":
            print(f"  {_yellow('●')} Breakpoint hit — {_bold(ev.func)}() at {ev.file}:{_yellow(str(ev.line))}")
        else:
            if ev.func or ev.line:
                print(f"  {_dim('▸')} {ev.func}()  at  {ev.file}:{_dim(str(ev.line))}")

    # ── source view ────────────────────────────────────────────────────────

    def show_source(self, lines: list[tuple[int, str]], current: Optional[int]):
        if not lines:
            return
        print()
        gutter = len(str(max(ln for ln, _ in lines)))
        for ln, text in lines:
            is_cur = ln == current
            ln_str = str(ln).rjust(gutter)
            marker = _yellow("▶") if is_cur else " "
            hl = _highlight_cpp(text)
            if is_cur:
                line_out = f"  {_yellow(ln_str)} {marker} {hl}"
                print(_c("100", "") + line_out + "\033[0m")
            else:
                print(f"  {_dim(ln_str)}   {hl}")
        print()

    # ── locals / args ──────────────────────────────────────────────────────

    def show_locals(self, variables: dict[str, str], label: str = "Locals"):
        print(f"\n  {_bold(label)}")
        print("  " + self._rule())
        if not variables:
            print(f"  {_dim('(none)')}")
        else:
            name_w = max((len(k) for k in variables), default=8)
            for name, val in variables.items():
                print(f"  {_cyan(name.ljust(name_w))}  =  {val}")
        print()

    # ── backtrace ──────────────────────────────────────────────────────────

    def show_backtrace(self, frames: list[dict]):
        print(f"\n  {_bold('Call Stack')}")
        print("  " + self._rule())
        if not frames:
            print(f"  {_dim('(empty)')}")
        for f in frames:
            fid   = _dim(f"#{f['id']}")
            func  = _bold(f.get("func", "?"))
            loc   = f"{f.get('file','?')}:{f.get('line','?')}"
            addr  = _dim(f.get("addr", ""))
            print(f"  {fid}  {func}  {_dim('at')}  {loc}  {addr}")
        print()

    # ── breakpoints ────────────────────────────────────────────────────────

    def show_breakpoints(self, bps: list[Breakpoint]):
        print(f"\n  {_bold('Breakpoints / Watchpoints')}")
        print("  " + self._rule())
        if not bps:
            print(f"  {_dim('(none)')}")
        for bp in bps:
            enabled = _green("●") if bp.enabled else _dim("○")
            kind = _dim(f"[{bp.kind}]")
            hits = _dim(f"  hit {bp.hit_count}×") if bp.hit_count else ""
            print(f"  {enabled} #{bp.id}  {kind}  {bp.location}{hits}")
        print()

    # ── registers ─────────────────────────────────────────────────────────

    def show_registers(self, regs: dict[str, str]):
        print(f"\n  {_bold('Registers')}")
        print("  " + self._rule())
        items = list(regs.items())
        col_w = max((len(k) for k, _ in items), default=4) if items else 4
        for name, val in items:
            print(f"  {_cyan(name.ljust(col_w))}  {val}")
        print()

    # ── expression value ───────────────────────────────────────────────────

    def show_value(self, expr: str, value: str):
        print(f"  $1 = {_green(value)}")

    # ── AI response ────────────────────────────────────────────────────────

    def show_ai_response(self, text: str):
        width = min(self._width - 6, 80)
        print()
        print(f"  {_magenta('✦ Claude AI Analysis')}")
        print("  " + self._rule("─"))
        for line in text.splitlines():
            if line.startswith("►"):
                print(f"  {_magenta(_bold(line))}")
            else:
                wrapped = textwrap.fill(line, width=width, subsequent_indent="    ")
                print(f"  {_magenta(wrapped)}" if wrapped else "")
        print("  " + self._rule("─"))
        print()
