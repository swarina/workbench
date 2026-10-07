# Lessons

Real failures and waste, and where the fix belongs. An entry needs evidence: a
`wb report` finding or a concrete incident. Prefer fixes in this order:
script or hook (deterministic) > skill > instruction line.

Format:

    ## YYYY-MM-DD short title
    Evidence: what happened, with numbers if available.
    Fix: script | hook | skill | agent | instruction | none yet. What changed.
    Result: filled in after the next measurement.

## 2026-10-07 Sessions run for weeks in one context
Evidence: baseline over 16 main sessions. Median 567 turns, p90 peak context 996k.
Cache reads are about 69% of estimated cost; all tool output is under 1% by volume.
Fix: skill (`handoff`) plus an instruction line (one task or PR per session).
Result: pending. Compare `wb report --since 7` after a week of use.

## 2026-10-07 Long-session cost was invisible while working
Evidence: no live signal of context size existed; sessions reached about 1M tokens.
Fix: script and hook (`wb statusline`, `hooks/context-nudge`), plus `wb compare` to
measure the effect. Neither is active until wired into settings.
Result: pending. Check peak context p50 and p90 with `wb compare baseline latest`.

## 2026-10-07 Diffs are the largest shell output
Evidence: `git diff`, `gh pr` and `git show` produced about 380k tokens of output.
Fix: script (`diff-summary`) plus an instruction line.
Result: pending.
