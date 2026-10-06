"""Codex rollouts: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Status: experimental. Written against a handful of real rollouts; token_count events
give per-request usage, and tool calls arrive as *_call / *_call_output response items.
"""
import glob
import json
import os
from typing import Dict, List, Optional

from ..model import Session, ToolCall, Turn

NAME = "codex"
DEFAULT_ROOT = "~/.codex/sessions"


def discover(root: Optional[str] = None) -> List[str]:
    root = os.path.expanduser(root or DEFAULT_ROOT)
    return sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))


def parse(path: str) -> Optional[Session]:
    s = Session(source=NAME, id=os.path.splitext(os.path.basename(path))[0], path=path)
    by_id: Dict[str, ToolCall] = {}
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            p = rec.get("payload")
            if not isinstance(p, dict):
                continue
            kind = p.get("type") or ""
            if rec.get("type") == "session_meta":
                s.project = os.path.basename(p.get("cwd") or "")
            elif kind == "token_count":
                u = (p.get("info") or {}).get("last_token_usage") or {}
                if not u.get("input_tokens"):
                    continue  # sessions imported from another agent report zero usage
                cached = u.get("cached_input_tokens", 0)
                s.turns.append(Turn(
                    fresh_in=u["input_tokens"] - cached - u.get("cache_write_input_tokens", 0),
                    cache_write=u.get("cache_write_input_tokens", 0),
                    cache_read=cached,
                    out=u.get("output_tokens", 0),
                    timestamp=rec.get("timestamp", ""),
                ))
            elif kind.endswith("_call"):
                raw = p.get("input") if "input" in p else p.get("arguments")
                call = ToolCall(
                    name=p.get("name") or kind,
                    turn=max(len(s.turns) - 1, 0),
                    input=raw if isinstance(raw, dict) else {"raw": str(raw)},
                )
                s.calls.append(call)
                by_id[p.get("call_id")] = call
            elif kind.endswith("_call_output"):
                call = by_id.get(p.get("call_id"))
                if call:
                    out = p.get("output")
                    call.output_chars = len(out if isinstance(out, str) else json.dumps(out))
    return s if s.turns else None
