---
name: handoff
description: Write durable task state to .workbench/task.md so work can continue in a fresh session with a small context. Use at a task or PR boundary, before switching phase (explore to implement, implement to review), when context is large, or when the user says "handoff", "checkpoint" or "wrap up".
status: experimental
---

# Handoff

Long sessions are the main cost driver: every turn re-reads the whole context. This
skill replaces a large conversation with a short state file a new session can start from.

## Steps

1. Get the mechanical facts from tools, not memory: `git status --short`,
   `git diff --stat`, current branch, and the last test or check command with its result.
2. Write `.workbench/task.md` in the project root using the template below. Overwrite
   the previous version; this file is current state, not a log.
3. If `.workbench/` is not ignored, add it to `.git/info/exclude`. Never commit it.
4. Tell the user in two or three lines what is done and what is next, and that a fresh
   session can resume from the file.

## Template

```markdown
# Task: <one line>
Updated: <date>  Branch: <branch>  Status: in progress | blocked | done

## Goal
What done looks like, including constraints the user stated.

## Relevant files
- path/to/file: why it matters (one line each, only files the next session needs)

## How it works
The few facts about existing behavior that were expensive to discover.

## Decisions
- Decision, and the reason. Include rejected alternatives worth not revisiting.

## Done
- Completed work, with commit or PR references where they exist.

## Verification
- Command run and result. State plainly what has not been verified.

## Next
1. Ordered remaining steps, concrete enough to start without re-exploring.

## Risks and open questions
- Anything unresolved, and who needs to decide.

## Outcome
Fill in when Status is done: done | partial | abandoned, plus rework needed (yes/no).
```

## Rules

- Target under 60 lines. If it is longer, it is a transcript, not state.
- Record conclusions, not the path taken to reach them.
- Do not paste code or diffs. Point to files and line ranges.
- Every "Next" step must be actionable by someone who has read only this file.
