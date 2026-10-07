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

## 2026-10-07 Startup overhead is real but not the main cost
Evidence: `/context` in a quarry session (a cloud environment, not the local Mac) at 416k:
messages 354k (85%); fixed overhead about 62k (MCP tools 22k, system tools 21k, system
prompt 12k, skills 6k, MCP instructions 2k, memory files under 1k). Another 51k of MCP
tools are deferred and cost nothing until loaded. This matches the 62k to 64k first-turn
context `wb` measured for quarry and ravel. Workbench's own instructions are a rounding
error at this scale.
Fix: none for now. Trimming every unused connector would save at most about 22k tokens
per turn, roughly 5% of context at the median, against 85% for messages. Revisit only
if a project's startup context exceeds 100k.
Result: confirms that session length, not setup, is the lever. Handoff stays first.

## 2026-10-07 Diffs are the largest shell output
Evidence: `git diff`, `gh pr` and `git show` produced about 380k tokens of output.
Fix: script (`diff-summary`) plus an instruction line.
Result: pending.
