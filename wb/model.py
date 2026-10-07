"""Tool-neutral session model. Sources parse into this; detectors and reports read it."""
import calendar
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def parse_timestamp(value: str) -> Optional[float]:
    """Epoch seconds from an ISO-8601 timestamp such as 2026-01-01T00:00:00.123Z, or None."""
    try:
        return calendar.timegm(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")) if value else None
    except ValueError:
        return None

# Relative price of each token class, in units of one fresh input token.
# Approximate, and only used to rank waste, never to report money.
COST_WEIGHTS = {"fresh_in": 1.0, "cache_write": 1.5, "cache_read": 0.1, "out": 5.0}

# Cache-write price depends on how long the entry is kept alive.
CACHE_WRITE_WEIGHT_5M = 1.25
CACHE_WRITE_WEIGHT_1H = 2.0

READ_ONLY_TOOLS = {"Read", "Grep", "Glob"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}


@dataclass
class Turn:
    fresh_in: int = 0
    cache_write: int = 0
    cache_read: int = 0
    out: int = 0
    model: str = ""
    timestamp: str = ""
    cache_write_5m: int = 0  # portion of cache_write kept alive 5 minutes (0 if unknown)
    cache_write_1h: int = 0  # portion kept alive 1 hour (0 if unknown)
    branch: str = ""

    @property
    def context(self) -> int:
        return self.fresh_in + self.cache_write + self.cache_read

    @property
    def cost_units(self) -> float:
        total = sum(getattr(self, k) * w for k, w in COST_WEIGHTS.items() if k != "cache_write")
        split = self.cache_write_5m + self.cache_write_1h
        if split:
            unsplit = max(0, self.cache_write - split)
            total += (self.cache_write_5m * CACHE_WRITE_WEIGHT_5M
                      + self.cache_write_1h * CACHE_WRITE_WEIGHT_1H
                      + unsplit * COST_WEIGHTS["cache_write"])
        else:
            total += self.cache_write * COST_WEIGHTS["cache_write"]
        return total


@dataclass
class ToolCall:
    name: str
    turn: int
    input: Dict = field(default_factory=dict)
    output_chars: int = 0

    @property
    def output_tokens(self) -> int:
        return self.output_chars // 4

    @property
    def path(self) -> str:
        return self.input.get("file_path") or self.input.get("notebook_path") or ""

    @property
    def label(self) -> str:
        """Short grouping key: the tool name, or the leading command for shell calls."""
        cmd = self.input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return self.name
        # Skip leading `cd dir` and VAR=value segments so the label names the real command.
        for segment in re.split(r"&&|;|\n", cmd):
            words = segment.split("|")[0].split()
            if words and words[0] != "cd" and "=" not in words[0]:
                return "$ " + " ".join(words[:2])
        return "$ " + cmd.split()[0]


@dataclass
class Session:
    source: str
    id: str
    path: str
    project: str = ""
    kind: str = "main"  # "main" or "subagent"
    turns: List[Turn] = field(default_factory=list)
    calls: List[ToolCall] = field(default_factory=list)

    @property
    def peak_context(self) -> int:
        return max((t.context for t in self.turns), default=0)

    @property
    def startup_context(self) -> int:
        """Context on the first turn: the fixed overhead paid before any work happens."""
        return self.turns[0].context if self.turns else 0

    @property
    def cost_units(self) -> float:
        return sum(t.cost_units for t in self.turns)

    def total(self, key: str) -> int:
        return sum(getattr(t, key) for t in self.turns)


@dataclass
class Finding:
    detector: str
    summary: str
    suggestion: str
    est_tokens: int = 0  # rough count of context tokens that were avoidable
    session: Optional[str] = None
