# mdb — Time-Travel Debugger for C++

> Debug large-scale C++ projects with full reverse execution and AI-powered root-cause analysis.

```
  ███╗   ███╗██████╗ ██████╗
  ████╗ ████║██╔══██╗██╔══██╗
  ██╔████╔██║██║  ██║██████╔╝
  ██║╚██╔╝██║██║  ██║██╔══██╗
  ██║ ╚═╝ ██║██████╔╝██████╔╝
  ╚═╝     ╚═╝╚═════╝ ╚═════╝
  MaxDebugger  v1.0.0  (powered by Claude AI)
```

**mdb** is an open-source command-line debugger inspired by [UndoDB](https://undo.io/)
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
| **MCP server** | Integrates with VS Code Copilot — no API key needed |
| **Checkpoints** | Save and restore arbitrary execution positions |
| **Source view** | Syntax-highlighted C++ with current-line indicator |
| **Tab completion** | All commands completable with Tab |
| **Readline history** | Arrow-key history, persistent across sessions |

---

## Requirements

- Python 3.11+
- GDB 9+ (for reverse debugging via `record-full`)
- [Mozilla rr](https://rr-project.org/) — **strongly recommended** for large projects (see below)
- An Anthropic API key (for CLI `explain` / `why` commands) **— not needed in MCP mode**

Install GDB:
```bash
# Ubuntu / Debian
sudo apt install gdb

# macOS (via Homebrew)
brew install gdb
```

---

## Installing rr — why it matters

GDB's built-in `record-full` works out of the box but is unsuitable for real
codebases. rr is the right choice for any non-trivial program:

| | GDB `record-full` | Mozilla rr |
|---|---|---|
| Extra install | No | Yes |
| Slowdown | 50–100× | ~1.2× |
| Multi-threaded programs | ❌ Unreliable | ✅ Full support |
| Large traces | Runs out of memory | Gigabytes, no problem |
| Reverse-continue speed | Very slow | Instant |

### Quick install (with sudo)

```bash
# Ubuntu / Debian
sudo apt install rr

# macOS
brew install rr

# RHEL / CentOS (package manager)
sudo dnf install rr
```

### Building rr from source on RHEL 8 — no sudo required

If you are on a shared RHEL 8 server without root access, build rr entirely
inside your home directory. The steps below install every dependency locally
and place the final `rr` binary at `~/.local/bin/rr`.

#### 1. Check hardware support

rr requires a modern Intel or AMD CPU with hardware performance counters.
Verify before building:

```bash
# Must print a number > 0
grep -c 'pmu\|perf' /proc/cpuinfo

# Check perf_event_paranoid — must be ≤ 1
cat /proc/sys/kernel/perf_event_paranoid
```

If `perf_event_paranoid` is 2 or higher and you cannot change it (requires
root), ask your sysadmin to run:

```bash
sudo sysctl -w kernel.perf_event_paranoid=1
# Make it permanent:
echo 'kernel.perf_event_paranoid=1' | sudo tee /etc/sysctl.d/99-rr.conf
```

#### 2. Install a local CMake (if system CMake < 3.11)

```bash
# Check version — rr needs 3.11+
cmake --version

# If too old, install a local copy:
cd ~
wget https://github.com/Kitware/CMake/releases/download/v3.29.3/cmake-3.29.3-linux-x86_64.tar.gz
tar -xf cmake-3.29.3-linux-x86_64.tar.gz
export PATH="$HOME/cmake-3.29.3-linux-x86_64/bin:$PATH"
# Add to ~/.bashrc to persist:
echo 'export PATH="$HOME/cmake-3.29.3-linux-x86_64/bin:$PATH"' >> ~/.bashrc
```

#### 3. Install capnproto locally (rr dependency)

rr requires [Cap'n Proto](https://capnproto.org/) 0.9+. Build it from source
into `~/.local`:

```bash
cd ~
wget https://capnproto.org/capnproto-c++-1.0.2.tar.gz
tar -xf capnproto-c++-1.0.2.tar.gz
cd capnproto-c++-1.0.2

./configure --prefix=$HOME/.local
make -j$(nproc)
make install

# Make the compiler and pkg-config find it:
export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:$PKG_CONFIG_PATH"
export PATH="$HOME/.local/bin:$PATH"
echo 'export PKG_CONFIG_PATH="$HOME/.local/lib/pkgconfig:$PKG_CONFIG_PATH"' >> ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

#### 4. Install zstd locally (optional but recommended)

```bash
cd ~
wget https://github.com/facebook/zstd/releases/download/v1.5.6/zstd-1.5.6.tar.gz
tar -xf zstd-1.5.6.tar.gz
cd zstd-1.5.6/build/cmake

cmake -DCMAKE_INSTALL_PREFIX=$HOME/.local \
      -DCMAKE_BUILD_TYPE=Release \
      -DZSTD_BUILD_PROGRAMS=OFF .
make -j$(nproc)
make install
```

#### 5. Build rr itself

```bash
cd ~
git clone https://github.com/rr-debugger/rr.git
cd rr
mkdir build && cd build

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$HOME/.local \
  -DCapnProto_DIR=$HOME/.local/lib/cmake/CapnProto \
  -DCMAKE_PREFIX_PATH=$HOME/.local

make -j$(nproc)
make install
```

#### 6. Verify the install

```bash
# Should print rr version
~/.local/bin/rr --version

# If ~/.local/bin is already in your PATH (step 3 above), just:
rr --version

# Quick smoke test — record and replay ls
rr record ls
rr replay
```

#### 7. Tell mdb to use your local rr

```bash
# If ~/.local/bin is in PATH, --rr just works:
mdb ./my_binary --rr

# Or point explicitly to the binary:
RR=/home/yourname/.local/bin/rr mdb ./my_binary --rr
```

#### Troubleshooting

**`CPUID faulting` error on VM** — rr needs bare-metal CPU features. If you are
inside a VM, ask your admin to enable CPU passthrough / hardware virtualisation
extensions.

**`perf_event_open` permission denied** — `perf_event_paranoid` is too high.
You need your sysadmin to set it to 1 (see step 1 above).

**`capnp: not found` during cmake** — re-run step 3 and make sure
`PKG_CONFIG_PATH` is exported in your current shell before running cmake.

**Old GCC on RHEL 8** — rr requires GCC 7+ or Clang 6+. Enable the SCL
toolset if needed:

```bash
# Install (requires sudo — ask sysadmin once)
sudo dnf install gcc-toolset-13

# Then in your build shell (no sudo needed after install):
scl enable gcc-toolset-13 bash
# Now rebuild rr inside this shell
```

---

## Installation

```bash
pip install mdb
```

Or from source:
```bash
git clone https://github.com/XudongSunSF/mdb
cd mdb
pip install -e .
```

---

## Quick Start

```bash
# Compile your binary with debug symbols (no optimisation)
g++ -g -O0 -o my_program my_program.cpp

# Start mdb
export ANTHROPIC_API_KEY=sk-ant-...
mdb ./my_program
```

### Example session

```
(mdb) run
  ● Breakpoint 1, main() at my_program.cpp:42

(mdb) break delete_list
  ✔ Breakpoint 2 at delete_list

(mdb) continue
  ● Breakpoint hit — delete_list() at use_after_free.cpp:20

(mdb) step
  ▸ delete_list() at use_after_free.cpp:21

(mdb) step
  ● SIGNAL RECEIVED: SIGSEGV
     delete_list() at use_after_free.cpp:21
  tip: type explain for AI root-cause analysis.

(mdb) explain

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

(mdb) reverse-step
  ◀ delete_list() at use_after_free.cpp:20

(mdb) info locals
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

## Using rr with mdb

Once rr is installed (see above), enable it with `--rr`:

```bash
mdb ./my_program --rr
```

Or set the environment variable permanently:
```bash
export MDB_USE_RR=1
mdb ./my_program
```

Inside the session, reverse commands run at full speed — `reverse-continue`
jumps back to the previous breakpoint instantly with zero replay overhead.

---

## VS Code Copilot Integration (MCP Server)

mdb ships with a built-in [MCP (Model Context Protocol)](https://modelcontextprotocol.io/)
server that lets **VS Code Copilot** (or any MCP-compatible client) drive the
debugger directly. No `ANTHROPIC_API_KEY` required — Copilot's own LLM does
the reasoning while mdb provides the debugging tools.

### Setup

**1. Install mdb with MCP support:**
```bash
pip install -e .
# or just: pip install mdb
```

**2. Add to your VS Code workspace** (`.vscode/mcp.json`):
```json
{
  "servers": {
    "mdb": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "mdb.mcp_server"]
    }
  }
}
```

**3. Use in Copilot agent mode.** Just ask naturally:

> *"Load `./my_program`, run it, and explain why it crashes."*

> *"Set a breakpoint at `delete_list`, continue to it, then step backward
>  to find when the pointer was freed."*

> *"Show me the backtrace and local variables, then reverse-step 3 times
>  to trace how `head` became dangling."*

Copilot will call mdb's tools automatically — loading the binary, setting
breakpoints, stepping, inspecting state, and synthesising a root-cause
analysis, all without you writing a single debugger command.

### Available MCP Tools

| Tool | Description |
|---|---|
| `mdb_load` | Load a C++ binary for debugging (GDB or rr backend) |
| `mdb_run` | Start/restart the program under time-travel recording |
| `mdb_step` | Step one source line (forward or **backward**) |
| `mdb_next` | Step over a call (forward or **backward**) |
| `mdb_continue` | Continue to next breakpoint (forward or **reverse**) |
| `mdb_finish` | Run until function returns (or reverse to entry) |
| `mdb_set_breakpoint` | Set breakpoint at function, file:line, or line number |
| `mdb_set_watchpoint` | Set data watchpoint on an expression |
| `mdb_delete_breakpoint` | Remove a breakpoint/watchpoint by ID |
| `mdb_get_breakpoints` | List all active breakpoints/watchpoints |
| `mdb_get_locals` | Inspect local variables in the current frame |
| `mdb_get_args` | Inspect function arguments in the current frame |
| `mdb_backtrace` | Get the full call stack |
| `mdb_evaluate` | Evaluate any C++ expression (`ptr->next`, `*arr`, etc.) |
| `mdb_select_frame` | Switch to a different stack frame |
| `mdb_list_source` | Show source code around the current position |
| `mdb_get_state` | Full state snapshot (best for crash analysis) |

### MCP Prompt

The server also provides an `analyze_crash` prompt that guides Copilot through
a structured root-cause analysis workflow: get state → read source → evaluate
pointers → reverse-step to trace corruption → produce a fix.

### Using rr with MCP

To use the rr backend instead of GDB `record-full`, ask Copilot:

> *"Load `./my_program` with rr and run it."*

Or pass `use_rr=True` when calling `mdb_load`.

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key for CLI `explain` commands (not needed in MCP mode) |
| `MDB_USE_RR` | Set to `1` to use rr instead of GDB record-full |
| `MDB_CONTEXT_LINES` | Number of source lines to display (default `10`) |
| `MDB_DEBUG` | Set to `1` to log raw GDB/MI protocol traffic |
| `NO_COLOR` | Disable ANSI colour output |

---

## Architecture

```
mdb/
├── mdb/
│   ├── __main__.py      CLI entry point & argument parsing
│   ├── cli.py           REPL loop & command dispatch
│   ├── session.py       Session state (owns the backend)
│   ├── ai.py            Claude API integration (standalone CLI)
│   ├── mcp_server.py    ← MCP server for VS Code Copilot
│   ├── display.py       Terminal rendering & syntax highlighting
│   ├── config.py        Configuration dataclass
│   └── backend/
│       ├── base.py      Abstract Backend interface
│       ├── gdb.py       GDB/MI backend (record-full)
│       └── rr.py        Mozilla rr backend
├── .vscode/
│   └── mcp.json         Example MCP config for VS Code
└── examples/
    ├── use_after_free.cpp
    └── buffer_overflow.cpp
```

Two ways to use mdb:

```
┌─────────────────────────────────────────────────────────────┐
│  Option A: Standalone CLI                                   │
│  mdb ./binary  →  REPL  →  explain  →  Anthropic API       │
│                                         (needs API key)     │
├─────────────────────────────────────────────────────────────┤
│  Option B: VS Code Copilot (MCP)                            │
│  Copilot agent  →  mcp_server.py  →  session  →  GDB/rr    │
│  (LLM reasoning)   (tools)          (state)    (execution)  │
│                     No API key needed!                      │
└─────────────────────────────────────────────────────────────┘
```

The **backend abstraction** makes it straightforward to add new backends
(e.g. [Pernosco](https://pernos.co/), LLDB, Windows TTD).

---

## License

MIT — see [LICENSE](LICENSE).
