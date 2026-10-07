"""Save report summaries as snapshots and compare two of them.

Snapshots live outside the repo (they describe private work): $WB_HOME/snapshots,
default ~/.workbench/snapshots. Comparisons are normalized per session and per 1000 turns
so periods with different amounts of work stay comparable.
"""
import datetime
import glob
import json
import os
from typing import Callable, Dict, List, Optional, Tuple

# (label, extractor, formatter, lower_is_better)
Metric = Tuple[str, Callable[[Dict], Optional[float]], Callable[[float], str], bool]


def snapshot_dir() -> str:
    home = os.environ.get("WB_HOME") or os.path.expanduser("~/.workbench")
    return os.path.join(home, "snapshots")


def save(summary: Dict, name: str = "") -> str:
    os.makedirs(snapshot_dir(), exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = os.path.join(snapshot_dir(), f"{stamp}-{name}.json" if name else f"{stamp}.json")
    with open(path, "w") as fh:
        json.dump(summary, fh, indent=2)
    return path


def resolve(ref: str) -> str:
    """A path, or the newest snapshot whose filename contains `ref`."""
    if os.path.isfile(ref):
        return ref
    matches = sorted(glob.glob(os.path.join(snapshot_dir(), f"*{ref}*.json")))
    if not matches:
        raise FileNotFoundError(f"no snapshot matching '{ref}' in {snapshot_dir()}")
    return matches[-1]


def load(ref: str) -> Dict:
    with open(resolve(ref)) as fh:
        return json.load(fh)


def _k(n: float) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else f"{n:.0f}"


def _ratio(num: Optional[float], den: Optional[float], scale: float = 1.0) -> Optional[float]:
    return num * scale / den if num is not None and den else None


def _waste(name: str) -> Callable[[Dict], Optional[float]]:
    # Avoidable tokens per 1000 turns; a detector that did not fire counts as zero.
    return lambda s: _ratio(s.get("waste", {}).get(name, {}).get("est_tokens", 0), s.get("turns"), 1000)


METRICS: List[Metric] = [
    ("main sessions", lambda s: s.get("sessions"), lambda v: f"{v:.0f}", False),
    ("turns per session p50", lambda s: s["turns_per_session"]["p50"], lambda v: f"{v:.0f}", True),
    ("turns per session p90", lambda s: s["turns_per_session"]["p90"], lambda v: f"{v:.0f}", True),
    ("peak context p50", lambda s: s["peak_context"]["p50"], _k, True),
    ("peak context p90", lambda s: s["peak_context"]["p90"], _k, True),
    ("cost units per turn", lambda s: _ratio(s.get("cost_units"), s.get("turns")), lambda v: f"{v:.0f}", True),
    ("cost units per session", lambda s: _ratio(s.get("cost_units"), s.get("sessions") + s.get("subagent_runs", 0)),
     _k, True),
    ("cache read share of cost", lambda s: s["cost_share"]["cache_read"], lambda v: f"{v:.0%}", True),
    ("cache write share of cost", lambda s: s["cost_share"]["cache_write"], lambda v: f"{v:.0%}", True),
]
# Waste rows per detector are added dynamically from the union of both snapshots.


def _delta(a: Optional[float], b: Optional[float], lower_better: bool) -> str:
    if a is None or b is None:
        return "n/a"
    if a == 0:
        return "n/a" if b == 0 else "new"
    pct = (b - a) / a
    if abs(pct) < 0.02:
        return "same"
    arrow = "better" if (pct < 0) == lower_better else "worse"
    return f"{pct:+.0%} {arrow}"


def compare(a: Dict, b: Dict, label_a: str = "before", label_b: str = "after") -> str:
    rows = [(label, ext, fmt, lower) for label, ext, fmt, lower in METRICS]
    for name in sorted(set(a.get("waste", {})) | set(b.get("waste", {}))):
        rows.append((f"waste/1k turns: {name}", _waste(name), lambda v: _k(v), True))

    width = max(len(r[0]) for r in rows)
    lines = [f"{'':{width}}  {label_a[:14]:>14}  {label_b[:14]:>14}  change"]
    for label, ext, fmt, lower in rows:
        va, vb = _safe(ext, a), _safe(ext, b)
        lines.append(f"{label:{width}}  {fmt(va) if va is not None else '-':>14}  "
                     f"{fmt(vb) if vb is not None else '-':>14}  {_delta(va, vb, lower)}")
    return "\n".join(lines)


def _safe(ext: Callable[[Dict], Optional[float]], summary: Dict) -> Optional[float]:
    try:
        return ext(summary)
    except (KeyError, TypeError):
        return None
