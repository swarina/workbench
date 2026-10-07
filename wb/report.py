"""Aggregate sessions and findings into a text or JSON report."""
import json
from collections import defaultdict
from typing import Dict, List

from .model import COST_WEIGHTS, Finding, Session


def _k(n: float) -> str:
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return str(int(n))


def _pct(sorted_vals: List[int], p: float) -> int:
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))] if sorted_vals else 0


def summarize(sessions: List[Session], findings: List[Finding]) -> Dict:
    main = [s for s in sessions if s.kind == "main"]
    totals = {k: sum(s.total(k) for s in sessions) for k in COST_WEIGHTS}
    cost = {k: totals[k] * w for k, w in COST_WEIGHTS.items()}
    cost_sum = sum(cost.values()) or 1

    projects = defaultdict(lambda: {"sessions": 0, "subagent_runs": 0, "turns": 0,
                                    "cost_units": 0.0, "startup": []})
    tools = defaultdict(lambda: {"calls": 0, "output_tokens": 0})
    models = defaultdict(float)
    kinds = defaultdict(float)
    branches = defaultdict(lambda: {"turns": 0, "cost_units": 0.0, "peak_context": 0})
    for s in sessions:
        p = projects[s.project or "?"]
        p["sessions" if s.kind == "main" else "subagent_runs"] += 1
        p["turns"] += len(s.turns)
        p["cost_units"] += s.cost_units
        if s.kind == "main":
            p["startup"].append(s.startup_context)
        kinds[s.kind] += s.cost_units
        for t in s.turns:
            models[t.model or "?"] += t.cost_units
            b = branches[(s.project or "?", t.branch or "(none)")]
            b["turns"] += 1
            b["cost_units"] += t.cost_units
            b["peak_context"] = max(b["peak_context"], t.context)
        for c in s.calls:
            t = tools[c.label if c.label.startswith("$") else c.name]
            t["calls"] += 1
            t["output_tokens"] += c.output_tokens

    by_detector = defaultdict(lambda: {"sessions": set(), "est_tokens": 0, "suggestion": ""})
    for f in findings:
        d = by_detector[f.detector]
        d["sessions"].add(f.session)
        d["est_tokens"] += f.est_tokens
        d["suggestion"] = f.suggestion

    turns = sorted(len(s.turns) for s in main)
    peaks = sorted(s.peak_context for s in main)
    for p in projects.values():
        startup = sorted(p.pop("startup"))
        p["startup_p50"], p["startup_max"] = _pct(startup, 0.5), (startup[-1] if startup else 0)
    total_units = sum(kinds.values()) or 1
    return {
        "sessions": len(main),
        "subagent_runs": len(sessions) - len(main),
        "turns": sum(len(s.turns) for s in sessions),
        "cost_units": round(sum(s.cost_units for s in sessions)),
        "tokens": totals,
        "cost_share": {k: round(v / cost_sum, 3) for k, v in cost.items()},
        "turns_per_session": {"p50": _pct(turns, 0.5), "p90": _pct(turns, 0.9)},
        "peak_context": {"p50": _pct(peaks, 0.5), "p90": _pct(peaks, 0.9)},
        "projects": dict(sorted(projects.items(), key=lambda kv: -kv[1]["cost_units"])),
        "cost_by_kind": {k: round(v / total_units, 3) for k, v in sorted(kinds.items())},
        "cost_by_model": {m: round(v / total_units, 3)
                          for m, v in sorted(models.items(), key=lambda kv: -kv[1])},
        "branches": [
            {"project": proj, "branch": br, **vals}
            for (proj, br), vals in sorted(branches.items(), key=lambda kv: -kv[1]["cost_units"])
        ],
        "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1]["output_tokens"])),
        "waste": {
            name: {"sessions": len(d["sessions"]), "est_tokens": d["est_tokens"],
                   "suggestion": d["suggestion"]}
            for name, d in sorted(by_detector.items(), key=lambda kv: -kv[1]["est_tokens"])
        },
    }


def render_summary(summary: Dict, top: int = 10) -> str:
    t, cs = summary["tokens"], summary["cost_share"]
    lines = [
        f"Sessions: {summary['sessions']} main, {summary['subagent_runs']} subagent runs, "
        f"{summary['turns']} turns",
        f"Turns per main session: p50 {summary['turns_per_session']['p50']}, "
        f"p90 {summary['turns_per_session']['p90']}",
        f"Peak context: p50 {_k(summary['peak_context']['p50'])}, "
        f"p90 {_k(summary['peak_context']['p90'])}",
        "",
        "Tokens (share of estimated cost)",
    ]
    for key, label in (("cache_read", "cache read"), ("cache_write", "cache write"),
                       ("out", "output"), ("fresh_in", "fresh input")):
        lines.append(f"  {label:12} {_k(t[key]):>8}  {cs[key]:.0%}")
    lines += ["", "Projects by estimated cost"]
    total_units = sum(p["cost_units"] for p in summary["projects"].values()) or 1
    for name, p in list(summary["projects"].items())[:top]:
        lines.append(f"  {name[:32]:32} {p['cost_units'] / total_units:>4.0%}  "
                     f"{p['sessions']} sessions, {p['subagent_runs']} subagents, {p['turns']} turns, "
                     f"startup context p50 {_k(p['startup_p50'])}")
    kinds = summary["cost_by_kind"]
    lines += ["", "Cost by session kind: " + ", ".join(f"{k} {v:.0%}" for k, v in kinds.items()),
              "Cost by model"]
    for model, share in list(summary["cost_by_model"].items())[:top]:
        lines.append(f"  {model[:32]:32} {share:>4.0%}")
    lines += ["", "Tool output entering context"]
    for name, tl in list(summary["tools"].items())[:top]:
        lines.append(f"  {name[:32]:32} {_k(tl['output_tokens']):>6} tokens  {tl['calls']} calls")
    lines += ["", "Detected waste (rough estimate of avoidable context tokens)"]
    if not summary["waste"]:
        lines.append("  none")
    for name, w in summary["waste"].items():
        lines.append(f"  {name:16} {_k(w['est_tokens']):>7}  in {w['sessions']} sessions")
        lines.append(f"  {'':16} -> {w['suggestion']}")
    return "\n".join(lines)


def render_branches(summary: Dict, top: int = 15) -> str:
    """Cost per (project, branch). Branch is a proxy for task; a branch worked across
    several sessions is combined, and work done on main is lumped together."""
    rows = summary["branches"]
    total = sum(r["cost_units"] for r in rows) or 1
    lines = ["Estimated cost by branch (branch is a proxy for task)"]
    for r in rows[:top]:
        label = f"{r['project']}:{r['branch']}"
        lines.append(f"  {label[:44]:44} {r['cost_units'] / total:>4.0%}  "
                     f"{r['turns']} turns, peak context {_k(r['peak_context'])}")
    if len(rows) > top:
        rest = sum(r["cost_units"] for r in rows[top:])
        lines.append(f"  {'(' + str(len(rows) - top) + ' more)':44} {rest / total:>4.0%}")
    return "\n".join(lines)


def render_session(s: Session, findings: List[Finding]) -> str:
    start = s.turns[0].timestamp[:16].replace("T", " ")
    end = s.turns[-1].timestamp[:16].replace("T", " ")
    files_read = {c.path for c in s.calls if c.name == "Read" and c.path}
    files_changed = {c.path for c in s.calls if c.name in ("Edit", "Write", "NotebookEdit") and c.path}
    lines = [
        f"SESSION {s.id} ({s.source}, {s.project or '?'}, {s.kind})",
        f"  {start} to {end} UTC",
        f"  Turns: {len(s.turns)}   Tool calls: {len(s.calls)}   Peak context: {_k(s.peak_context)}",
        f"  Tokens: {_k(s.total('cache_read'))} cache read, {_k(s.total('cache_write'))} cache write, "
        f"{_k(s.total('fresh_in'))} fresh input, {_k(s.total('out'))} output",
        f"  Files read: {len(files_read)}   Files changed: {len(files_changed)}",
        "  Detected waste:" if findings else "  Detected waste: none",
    ]
    for f in sorted(findings, key=lambda f: -f.est_tokens):
        est = f"  (~{_k(f.est_tokens)} tokens)" if f.est_tokens else ""
        lines.append(f"  - [{f.detector}] {f.summary}{est}")
        lines.append(f"    -> {f.suggestion}")
    return "\n".join(lines)


def to_json(summary: Dict) -> str:
    return json.dumps(summary, indent=2)
