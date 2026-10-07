"""Live-session helpers shared by the status line and the nudge hook.

Both run on every prompt or refresh, so they must be fast and must never raise:
a broken helper may not interrupt real work.
"""
import json
import os
import tempfile
from typing import Dict, Optional

LIVE = {
    "tail_bytes": 262_144,   # how much of the transcript end to scan for the latest usage
    "status_soon": 150_000,  # status line starts suggesting a handoff
    "status_now": 300_000,   # status line says to hand off
    "nudge_soon": 200_000,   # hook asks for a handoff at the next boundary
    "nudge_now": 400_000,    # hook asks for a handoff before anything else
    "nudge_every": 10,       # prompts between repeated nudges in the same band
}


def latest_context(transcript_path: str) -> Optional[int]:
    """Context size at the most recent assistant turn, from the end of the transcript."""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as fh:
            fh.seek(max(0, size - LIVE["tail_bytes"]))
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        try:
            rec = json.loads(line)
        except ValueError:
            continue  # first line of the tail may be cut in half
        msg = rec.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) and rec.get("type") == "assistant" else None
        if usage:
            return (usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
                    + usage.get("cache_read_input_tokens", 0))
    return None


def status_band(context: int) -> str:
    if context >= LIVE["status_now"]:
        return "now"
    return "soon" if context >= LIVE["status_soon"] else "ok"


def nudge_band(context: int) -> str:
    if context >= LIVE["nudge_now"]:
        return "now"
    return "soon" if context >= LIVE["nudge_soon"] else "ok"


NUDGE_TEXT = {
    "soon": "Workbench: context is {k}k tokens. At the next natural boundary, run the handoff "
            "skill and continue in a fresh session.",
    "now": "Workbench: context is {k}k tokens and every turn re-reads it. Run the handoff skill "
           "now, before other work, then continue in a fresh session.",
}

_RANK = {"ok": 0, "soon": 1, "now": 2}


def nudge(payload: Dict, state_dir: Optional[str] = None) -> str:
    """Text to inject into the model's context for this prompt, or an empty string.

    Nudges once when a band is entered, again when it escalates, and then every
    `nudge_every` prompts while the context stays large, so the reminder itself
    does not become noise.
    """
    context = latest_context(payload.get("transcript_path") or "")
    if context is None:
        return ""
    band = nudge_band(context)

    state_path = os.path.join(state_dir or tempfile.gettempdir(),
                              "wb-nudge-" + "".join(c for c in str(payload.get("session_id", "x"))
                                                    if c.isalnum() or c in "-_"))
    state = {"prompts": 0, "last_prompt": -10**9, "last_band": "ok"}
    try:
        with open(state_path) as fh:
            state.update(json.load(fh))
    except (OSError, ValueError):
        pass
    state["prompts"] += 1

    escalated = _RANK[band] > _RANK[state["last_band"]]
    due = state["prompts"] - state["last_prompt"] >= LIVE["nudge_every"]
    speak = band != "ok" and (escalated or due)
    if speak:
        state["last_prompt"] = state["prompts"]
    state["last_band"] = band
    try:
        with open(state_path, "w") as fh:
            json.dump(state, fh)
    except OSError:
        pass
    return NUDGE_TEXT[band].format(k=round(context / 1000)) if speak else ""
