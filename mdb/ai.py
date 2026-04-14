"""
AI module: uses the Anthropic API to explain debugger state and crashes.

The `explain_state` function takes the current session state dict and an
optional user question, then returns a structured root-cause analysis.
"""

from __future__ import annotations

import os
import json
import textwrap
from typing import Optional

try:
    import anthropic
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False

SYSTEM_PROMPT = """\
You are an expert C++ debugging assistant embedded in a time-travel debugger \
(similar to UndoDB or Mozilla rr). You have access to the current execution \
state: call stack, local variables, function arguments, and the precise source \
location where execution stopped.

Your job is to:
1. Identify the root cause of crashes, hangs, or incorrect behaviour.
2. Explain *why* the bug occurred — not just *what* crashed.
3. Leverage time-travel context (e.g. "three steps back, variable X was valid").
4. Suggest a minimal, correct fix.

Respond using these exact section headers (with the ► symbol):
  ► CRASH SITE
  ► ROOT CAUSE
  ► TIME-TRAVEL INSIGHT
  ► RECOMMENDED FIX

Be concise and technical. Assume an experienced C++ developer audience. \
Keep the total response under 250 words.\
"""


def explain_state(state: dict, question: str = "", config=None) -> str:
    """
    Call Claude to explain the current debugging state.

    Args:
        state:    Session.get_state() snapshot dict.
        question: Optional follow-up question from the user.
        config:   Config object (for model / api_key overrides).

    Returns:
        Formatted string response from Claude.
    """
    api_key = (
        (config.anthropic_api_key if config else None)
        or os.environ.get("ANTHROPIC_API_KEY", "")
    )
    if not api_key:
        raise RuntimeError(
            "No Anthropic API key found.\n"
            "Set the ANTHROPIC_API_KEY environment variable or pass --api-key."
        )

    model = getattr(config, "ai_model", None) or "claude-sonnet-4-20250514"

    user_content = _build_user_prompt(state, question)

    if _HAS_SDK:
        return _call_via_sdk(api_key, model, user_content)
    else:
        return _call_via_http(api_key, model, user_content)


# ── prompt construction ────────────────────────────────────────────────────────

def _build_user_prompt(state: dict, question: str) -> str:
    bt_text = "\n".join(
        f"  #{f['id']}  {f['func']}() at {f['file']}:{f['line']}"
        for f in state.get("backtrace", [])
    ) or "  (not available)"

    locals_text = "\n".join(
        f"  {name} = {val}"
        for name, val in state.get("locals", {}).items()
    ) or "  (none)"

    args_text = "\n".join(
        f"  {name} = {val}"
        for name, val in state.get("args", {}).items()
    ) or "  (none)"

    bps_text = "\n".join(
        f"  #{bp['id']} at {bp['location']} ({'enabled' if bp['enabled'] else 'disabled'})"
        for bp in state.get("breakpoints", [])
    ) or "  (none)"

    prompt = textwrap.dedent(f"""\
        ## Current debugging state

        Binary  : {state.get('binary', '?')}
        Location: {state.get('func', '?')}() at {state.get('file', '?')}:{state.get('line', '?')}

        ### Call Stack
        {bt_text}

        ### Local Variables
        {locals_text}

        ### Function Arguments
        {args_text}

        ### Active Breakpoints
        {bps_text}
    """)

    if question:
        prompt += f"\n### User Question\n{question}\n"
    else:
        prompt += "\nPlease provide a root-cause analysis of the current state.\n"

    return prompt


# ── API calls ─────────────────────────────────────────────────────────────────

def _call_via_sdk(api_key: str, model: str, user_content: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text


def _call_via_http(api_key: str, model: str, user_content: str) -> str:
    import urllib.request

    payload = json.dumps({
        "model": model,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
    return body["content"][0]["text"]
