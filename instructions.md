# Working defaults

These apply to every project. A project's own instructions win where they conflict.

## Scale effort to the task
- Trivial (typo, rename, one-line fix): just do it and verify.
- Normal: find the relevant code, state the plan in a few lines, implement, verify.
- Risky or cross-cutting (public APIs, data models, concurrency, migrations): plan first
  and wait for agreement. Name backward-compatibility and failure-mode concerns.

## Context
- Search before reading. Read the parts of a file you need, not whole files by habit.
- Send independent reads and searches together in one turn, not one per turn.
- Keep tool output bounded: counts, stats or summaries first, full output only for the
  part you need. For diffs use `diff-summary` or `git diff --stat` before a full diff.
- Use a subagent for broad exploration when only the conclusion matters. Ask it for
  relevant files, findings, recommendation and risks, not a narrative.
- Use tools for mechanics (git, formatter, type checker, test runner). Reason about
  design, tradeoffs and root causes.

## Changes
- Understand existing behavior before changing it. In mature code, match what is there.
- Make the smallest correct change. No unrelated refactoring, renames or reformatting.
- Verify with the narrowest relevant check first, then widen only if it is warranted.
- Before calling it done, read your own final diff against the request.

## Sessions
- One task or PR per session. At a task boundary, or when context is large, run the
  `handoff` skill and continue in a fresh session.
- If `.workbench/task.md` exists at session start, read it before anything else.

## Reporting
- Lead with the outcome. Say what was verified and how, what was not, and what risk remains.
- If the same mistake or waste shows up twice, propose an entry for Workbench `lessons.md`.
