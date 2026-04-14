# udb-cli — Time-Travel Debugger for C++

> Debug large-scale C++ projects with full reverse execution and AI-powered root-cause analysis.

```
  ██╗   ██╗██████╗ ██████╗
  ██║   ██║██╔══██╗██╔══██╗
  ██║   ██║██║  ██║██████╔╝
  ██║   ██║██║  ██║██╔══██╗
  ╚██████╔╝██████╔╝██████╔╝
   ╚═════╝ ╚═════╝ ╚═════╝
  Time-Travel Debugger  v1.0.0  (powered by Claude AI)
```

**udb-cli** is an open-source command-line debugger inspired by [UndoDB](https://undo.io/)
and [Mozilla rr](https://rr-project.org/). It wraps GDB (or rr) to give you full
reverse-execution of any C++ program, and integrates the **Claude AI** API to
automatically explain crashes, use-after-free bugs, buffer overflows, and more.

---

## Features

| Feature | Detail |
|---|---|
| **Time-travel execution** | `step`, `next`, `continue` — all reversible |
| **Reverse commands** | `reverse-step`, `reverse-next`, `reverse-continue`, `reverse-finish` |
| **GDB backend** | Uses GDB `record-full` for reverse debugging (no extra install) |
| **rr backend** | Uses Mozilla `rr` for efficient, low-overhead recording |
| **AI root-cause** | `explain` / `why` calls Claude to analyse crashes in context |
| **Checkpoints** | Save and restore arbitrary execution positions |
| **Source view** | Syntax-highlighted C++ with current-line indicator |
| **Tab completion** | All commands completable with Tab |
| **Readline history** | Arrow-key history, persistent across sessions |

---

## Requirements

- Python 3.11+
- GDB 9+ (for reverse debugging via `record-full`)
- [Mozilla rr](https://rr-project.org/) *(optional but recommended for large projects)*
- An Anthropic API key (for `explain` / `why` commands)

Install GDB:
```bash
# Ubuntu / Debian
sudo apt install gdb

# macOS (via Homebrew)
brew install gdb
```

Install rr (optional):
```bash
# Ubuntu / Debian
sudo apt install rr

# macOS
brew install rr
```

---

## Installation

```bash
pip install udb-cli
```

Or from source:
```bash
git clone https://github.com/XudongSunSF/udb-cli
cd udb-cli
pip install -e .
```

---

## Quick Start

```bash
# Compile your binary with debug symbols (no optimisation)
g++ -g -O0 -o my_program my_program.cpp

# Start udb
export ANTHROPIC_API_KEY=sk-ant-...
udb ./my_program
```

### Example session

```
(udb) run
  ● Breakpoint 1, main() at my_program.cpp:42

(udb) break delete_list
  ✔ Breakpoint 2 at delete_list

(udb) continue
  ● Breakpoint hit — delete_list() at use_after_free.cpp:20

(udb) step
  ▸ delete_list() at use_after_free.cpp:21

(udb) step
  ● SIGNAL RECEIVED: SIGSEGV
     delete_list() at use_after_free.cpp:21
  tip: type explain for AI root-cause analysis.

(udb) explain

  ✦ Claude AI Analysis
  ──────────────────────────────────────
  ► CRASH SITE
  delete_list() at use_after_free.cpp:21 — reading head->next after free.

  ► ROOT CAUSE
  The loop calls `delete head` on line 20, freeing the Node object.
  Line 21 then dereferences `head->next` on the now-freed memory.
  This is undefined behaviour (use-after-free), causing SIGSEGV.

  ► TIME-TRAVEL INSIGHT
  One step back (line 20) shows head = 0x5562a0 with a valid ->next = 0x556280.
  The fix must save ->next before the delete.

  ► RECOMMENDED FIX
  Node* next = head->next;   // save first
  delete head;
  head = next;
  ──────────────────────────────────────

(udb) reverse-step
  ◀ delete_list() at use_after_free.cpp:20

(udb) info locals
  Locals
  ──────────────────────────────────
  head  =  0x5562a0
```

---

## Commands

### Time-Travel Execution

| Command | Alias | Description |
|---|---|---|
| `run [args]` | `r` | Start the program under record |
| `step` | `s` | Step **forward** one source line |
| `next` | `n` | Step over (forward) |
| `reverse-step` | `rs` | Step **backward** one source line ◀ |
| `reverse-next` | `rn` | Step over (backward) ◀ |
| `continue` | `c` | Run forward to next breakpoint |
| `reverse-continue` | `rc` | Run **backward** to previous breakpoint ◀ |
| `finish` | | Run until current function returns |
| `reverse-finish` | `rf` | Reverse to function entry ◀ |

### Breakpoints & Watchpoints

| Command | Description |
|---|---|
| `break <loc>` | Set breakpoint (`file:line`, function name, or line number) |
| `watch <expr>` | Set data watchpoint on an expression |
| `delete <id>` | Remove breakpoint/watchpoint |
| `info breakpoints` | List all active breakpoints |

### Inspection

| Command | Description |
|---|---|
| `info locals` | Show local variables in current frame |
| `info args` | Show function arguments |
| `backtrace` / `bt` | Show call stack |
| `frame <n>` | Switch to stack frame n |
| `print <expr>` / `p` | Evaluate and print an expression |
| `list [loc]` | Show source around current/given location |

### AI Analysis

| Command | Description |
|---|---|
| `explain` | Claude AI root-cause analysis of current state |
| `explain <question>` | Ask Claude a specific question about the program |
| `why` | Alias for `explain` |

### Session

| Command | Description |
|---|---|
| `checkpoint [name]` | Save current execution position |
| `goto <name>` | Jump to saved checkpoint (rr only) |
| `record` | Re-record the execution trace |
| `set <key> <val>` | Change a setting (e.g. `set context-lines 15`) |
| `history` | Show recent command history |
| `quit` / `q` | Exit the debugger |

---

## Using rr (recommended for large projects)

[Mozilla rr](https://rr-project.org/) records execution with very low overhead
and supports perfect replay. Enable it with `--rr`:

```bash
udb ./my_program --rr
```

Or set the environment variable:
```bash
export UDB_USE_RR=1
udb ./my_program
```

rr is significantly faster than GDB `record-full` for long-running programs and
supports multi-threaded recording.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for AI `explain` commands |
| `UDB_USE_RR` | Set to `1` to use rr instead of GDB record-full |
| `UDB_CONTEXT_LINES` | Number of source lines to display (default `10`) |
| `UDB_DEBUG` | Set to `1` to log raw GDB/MI protocol traffic |
| `NO_COLOR` | Disable ANSI colour output |

---

## Architecture

```
udb-cli/
├── udb/
│   ├── __main__.py      CLI entry point & argument parsing
│   ├── cli.py           REPL loop & command dispatch
│   ├── session.py       Session state (owns the backend)
│   ├── ai.py            Claude API integration
│   ├── display.py       Terminal rendering & syntax highlighting
│   ├── config.py        Configuration dataclass
│   └── backend/
│       ├── base.py      Abstract Backend interface
│       ├── gdb.py       GDB/MI backend (record-full)
│       └── rr.py        Mozilla rr backend
└── examples/
    ├── use_after_free.cpp
    └── buffer_overflow.cpp
```

The **backend abstraction** makes it straightforward to add new backends
(e.g. [Pernosco](https://pernos.co/), LLDB, Windows TTD).

---

## License

MIT — see [LICENSE](LICENSE).
