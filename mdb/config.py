"""Configuration for mdb."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # AI
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    ai_model: str = "claude-sonnet-4-20250514"

    # Display
    context_lines: int = 10      # source lines shown around current position
    syntax_highlight: bool = True

    # Session
    history_file: str = "~/.mdb_history"
    debug: bool = False          # verbose GDB/MI logging

    # Backend
    use_rr: bool = False         # prefer rr over plain GDB

    @classmethod
    def from_env(cls) -> "Config":
        cfg = cls()
        if os.environ.get("MDB_DEBUG"):
            cfg.debug = True
        if os.environ.get("MDB_USE_RR"):
            cfg.use_rr = True
        if cl := os.environ.get("MDB_CONTEXT_LINES"):
            try:
                cfg.context_lines = int(cl)
            except ValueError:
                pass
        return cfg
