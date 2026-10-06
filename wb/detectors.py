"""Waste detectors. Each takes a Session and returns Findings.

To add one: write a function, decorate it with @detector, add a test. Keep every
threshold in THRESHOLDS so tuning never means reading detector code.
"""
import json
from collections import Counter, defaultdict
from typing import Callable, List

from .model import EDIT_TOOLS, READ_ONLY_TOOLS, Finding, Session

THRESHOLDS = {
    "context_baseline": 150_000,   # context a fresh session needs for real work
    "long_session_peak": 300_000,  # flag sessions whose context grows past this
    "repeat_reads": 3,             # reads of one unchanged file before flagging
    "large_output_tokens": 2_000,  # single tool result size worth flagging
    "duplicate_calls": 3,          # identical search/fetch calls before flagging
    "unbatched_run": 4,            # consecutive single read-only-call turns
}

DETECTORS: List[Callable[[Session], List[Finding]]] = []


def detector(fn):
    DETECTORS.append(fn)
    return fn


def run_all(session: Session) -> List[Finding]:
    found = []
    for fn in DETECTORS:
        for f in fn(session):
            f.session = session.id
            found.append(f)
    return found


@detector
def long_session(s: Session) -> List[Finding]:
    if s.peak_context < THRESHOLDS["long_session_peak"]:
        return []
    base = THRESHOLDS["context_baseline"]
    excess = sum(max(0, t.context - base) for t in s.turns)
    return [Finding(
        "long_session",
        f"{len(s.turns)} turns, context peaked at {round(s.peak_context / 1000)}k",
        "Hand off at task boundaries and continue in a fresh session (handoff skill).",
        excess,
    )]


@detector
def repeat_reads(s: Session) -> List[Finding]:
    since_edit = Counter()
    redundant = Counter()
    wasted = 0
    for c in s.calls:
        if not c.path:
            continue
        if c.name in EDIT_TOOLS:
            since_edit[c.path] = 0
        elif c.name == "Read":
            since_edit[c.path] += 1
            if since_edit[c.path] >= THRESHOLDS["repeat_reads"]:
                redundant[c.path] += 1
                wasted += c.output_tokens
    if not redundant:
        return []
    worst, n = redundant.most_common(1)[0]
    return [Finding(
        "repeat_reads",
        f"{sum(redundant.values())} re-reads of unchanged files "
        f"(worst: {worst.split('/')[-1]}, {n} extra)",
        "Usually a symptom of a long session: earlier reads were compacted away.",
        wasted,
    )]


@detector
def large_outputs(s: Session) -> List[Finding]:
    by_label = defaultdict(lambda: [0, 0])
    for c in s.calls:
        if c.output_tokens >= THRESHOLDS["large_output_tokens"]:
            by_label[c.label][0] += 1
            by_label[c.label][1] += c.output_tokens
    out = []
    for label, (n, tok) in sorted(by_label.items(), key=lambda kv: -kv[1][1])[:3]:
        out.append(Finding(
            "large_outputs",
            f"{label}: {n} results over {THRESHOLDS['large_output_tokens']} tokens, {tok // 1000}k total",
            "Bound the output: summary first, then only the part needed.",
            tok,
        ))
    return out


@detector
def duplicate_calls(s: Session) -> List[Finding]:
    seen = Counter()
    for c in s.calls:
        if c.name in ("Grep", "Glob", "WebFetch", "WebSearch"):
            seen[(c.name, json.dumps(c.input, sort_keys=True))] += 1
    dupes = sum(n - 1 for n in seen.values() if n >= THRESHOLDS["duplicate_calls"])
    if not dupes:
        return []
    return [Finding("duplicate_calls", f"{dupes} identical repeated searches or fetches",
                    "Note results in task state instead of searching again.")]


@detector
def unbatched_calls(s: Session) -> List[Finding]:
    per_turn = defaultdict(list)
    for c in s.calls:
        per_turn[c.turn].append(c.name)
    mergeable, wasted, run = 0, 0, 0
    for i, t in enumerate(s.turns):
        names = per_turn.get(i, [])
        if len(names) == 1 and names[0] in READ_ONLY_TOOLS:
            run += 1
            if run >= THRESHOLDS["unbatched_run"]:
                mergeable += 1
                wasted += t.context
        else:
            run = 0
    if not mergeable:
        return []
    return [Finding("unbatched_calls",
                    f"{mergeable} turns spent on one read-only call each, back to back",
                    "Issue independent reads and searches in one turn.", wasted)]
