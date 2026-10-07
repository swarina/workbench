"""One-line Claude Code status line: context size, session cost, handoff hint.

Claude Code passes a JSON object on stdin. Only transcript_path is relied on; the other
fields are used when present and skipped when not, so a changed payload degrades to
a shorter line instead of an error.
"""
from typing import Dict

from .live import latest_context, status_band

HINT = {"ok": "", "soon": "handoff soon", "now": "HANDOFF"}


def render(payload: Dict) -> str:
    parts = []
    context = latest_context(payload.get("transcript_path") or "")
    if context is not None:
        ctx = f"ctx {round(context / 1000)}k"
        window = (payload.get("context_window") or {}).get("context_window_size")
        if isinstance(window, (int, float)) and window:
            ctx += f" ({context / window:.0%})"
        parts.append(ctx)
    cost = (payload.get("cost") or {}).get("total_cost_usd")
    if isinstance(cost, (int, float)):
        parts.append(f"${cost:.2f}")
    if context is not None and HINT[status_band(context)]:
        parts.append(HINT[status_band(context)])
    return " | ".join(parts)
