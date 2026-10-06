"""Claude Code transcripts: ~/.claude/projects/<project>/<session>.jsonl"""
import glob
import json
import os
from typing import Dict, List, Optional

from ..model import Session, ToolCall, Turn

NAME = "claude"
DEFAULT_ROOT = "~/.claude/projects"


def discover(root: Optional[str] = None) -> List[str]:
    root = os.path.expanduser(root or DEFAULT_ROOT)
    return sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True))


def _result_chars(content) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get("text", "")) for b in content if isinstance(b, dict))
    return 0


def parse(path: str) -> Optional[Session]:
    s = Session(
        source=NAME,
        id=os.path.splitext(os.path.basename(path))[0],
        path=path,
        kind="subagent" if os.sep + "subagents" + os.sep in path else "main",
    )
    seen_messages = set()
    by_id: Dict[str, ToolCall] = {}
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not s.project and rec.get("cwd"):
                s.project = os.path.basename(rec["cwd"])
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if rec.get("type") == "assistant":
                # One API response is written as several records, each repeating its usage.
                if msg.get("id") not in seen_messages:
                    seen_messages.add(msg.get("id"))
                    u = msg.get("usage") or {}
                    s.turns.append(Turn(
                        fresh_in=u.get("input_tokens", 0),
                        cache_write=u.get("cache_creation_input_tokens", 0),
                        cache_read=u.get("cache_read_input_tokens", 0),
                        out=u.get("output_tokens", 0),
                        model=msg.get("model", ""),
                        timestamp=rec.get("timestamp", ""),
                    ))
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        call = ToolCall(
                            name=block.get("name", "?"),
                            turn=len(s.turns) - 1,
                            input=block.get("input") or {},
                        )
                        s.calls.append(call)
                        by_id[block.get("id")] = call
            elif rec.get("type") == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        call = by_id.get(block.get("tool_use_id"))
                        if call:
                            call.output_chars = _result_chars(block.get("content"))
    return s if s.turns else None
