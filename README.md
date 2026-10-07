# Workbench

A personal productivity layer for Claude Code and Codex: shared working defaults, a few
skills and scripts, and a measurement loop. It configures the tools; it does not wrap or
replace them.

## Why

Agent sessions get expensive and sloppy in predictable ways: contexts that grow for
weeks, unbounded tool output, one small call per turn, repeated exploration. Workbench
makes the efficient behavior the default and measures whether it worked.

Principles:

- Model for judgment, tools for mechanics.
- Never consume context without a reason. Always-loaded instructions stay tiny.
- Use native Claude Code and Codex features before building anything.
- Optimize engineering value per token, never raw token count.
- Add nothing without evidence, and delete what does not earn its keep.

## Quick start

Requires Python 3.9+, git and bash. No third-party packages.

    git clone https://github.com/swarina/workbench.git && cd workbench
    ./install.sh link --dry-run    # preview
    ./install.sh link              # symlink into ~/.claude, ~/.codex and ~/.local/bin
    wb report                      # baseline before changing anything

Then work as usual. At a task or PR boundary run the `handoff` skill and start a fresh
session; after a week compare `wb report --since 7` against the baseline.

## Layout

| Path | What it is | Loaded when |
|---|---|---|
| `instructions.md` | Working defaults for every project. Linked as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. | Always, so it has a 60-line budget |
| `skills/<name>/SKILL.md` | Focused procedures, shared by both tools. | On use |
| `agents/<name>.md` | Claude Code subagents (none yet). | On delegation |
| `bin/` | Deterministic helpers on PATH: `wb`, `diff-summary`. | When called |
| `hooks/` | Hook scripts, wired into settings by hand: `context-nudge`. | On the hook event |
| `wb/` | Python package behind `wb` (standard library only). | n/a |
| `lessons.md` | Evidence-backed failures and where each fix belongs. | Never loaded automatically |
| `tests/` | Unit tests, including a lint of this repo. | n/a |

## Install details

    ./install.sh status            # what is linked, missing or in conflict
    ./install.sh link [--dry-run]
    ./install.sh unlink

Symlinks only, so edits in this repo take effect immediately. Existing files are never
overwritten; they are reported as conflicts. Override targets with `CLAUDE_HOME`,
`CODEX_HOME` and `WB_BIN_DIR`.

## Measure

    wb report                      # all sessions: cost split, tool output, detected waste
    wb report --since 7            # last week
    wb report --project <name>
    wb report --worst 3            # per-session reports for the most expensive sessions
    wb report --session <id>       # one session
    wb report --json               # machine-readable summary
    wb report --by branch          # cost per branch, a proxy for cost per task or PR
    wb report --save baseline      # also save a snapshot to ~/.workbench/snapshots
    wb compare baseline latest     # before and after, normalized per turn and session

Token classes are weighted by approximate relative price to rank waste. The estimates
are for comparison, not accounting.

Detectors: `long_session`, `cache_rewrite` (large context re-cached after an idle gap),
`cache_invalidation` (re-cached with no gap, so the prefix changed), `startup_overhead`,
`large_outputs`, `repeat_reads`, `duplicate_calls`, `unbatched_calls`.

## Live visibility and enforcement

Two small pieces act during a session. Neither is installed automatically, because both
need an entry in your Claude Code settings.

Status line, showing context size, session cost and a handoff hint:

    "statusLine": { "type": "command", "command": "wb statusline" }

Handoff nudge: on each prompt, if context is above 200k tokens, one line asks the agent
to run `handoff` at the next boundary (above 400k: now). It repeats at most every 10
prompts, and always exits 0:

    "hooks": { "UserPromptSubmit": [ { "hooks": [
      { "type": "command", "command": "/path/to/workbench/hooks/context-nudge" } ] } ] }

The status line reads `transcript_path` and, when present, `cost.total_cost_usd` and
`context_window.context_window_size` from the JSON Claude Code sends. Missing fields
shorten the line rather than break it. Thresholds live in `wb/live.py`.

## The loop

1. `wb report` or a real incident shows waste or a failure.
2. Record it in `lessons.md` with the evidence.
3. Fix it in the cheapest durable place: script or hook, then skill, then an instruction line.
4. Measure again and fill in the result. Remove what did not help.

## Extending

Everything is discovered by convention. Adding an artifact means adding a file; nothing
is registered anywhere.

| To add | Do this | Guardrail |
|---|---|---|
| A skill | `skills/<name>/SKILL.md` with `name`, `description`, `status` frontmatter | `wb check` enforces frontmatter and a 150-line limit; put long reference material in sibling files |
| Stack knowledge (Java, AWS, a service) | A skill, or path-scoped rules in that project. Never `instructions.md`. | Keeps always-loaded context flat as coverage grows |
| A subagent | `agents/<name>.md` | Only when it compresses context, runs in parallel, or needs a different model |
| A script | Executable in `bin/` | Only when it replaces repeated model work or bounds noisy output |
| A hook | Executable in `hooks/`, then wire it in the tool's settings by hand | Must be fast and deterministic; settings are not auto-edited |
| A waste pattern | A function with `@detector` in `wb/detectors.py`, plus a test | Thresholds live in `THRESHOLDS` |
| Another agent tool | A module in `wb/sources/` with `NAME`, `discover()`, `parse()`, listed in `SOURCES` | Parse into `wb/model.py`; detectors and reports need no change |
| A `wb` subcommand | A `cmd_*` function and parser entry in `wb/cli.py` | |

Skill `status` moves through `experimental`, `validated`, `stable`, `deprecated`. Git
history is the changelog.

## Admission rule

Nothing is added on intuition. A new artifact needs a `lessons.md` entry or a `wb report`
finding behind it, and something that stops earning its keep gets deleted.

## Checks

    python3 -m unittest discover -s tests
    wb check

## Status

Early. The Claude Code transcript source is exercised on real sessions; the Codex source
is experimental. The `handoff` skill is `experimental` until a before and after
measurement supports it.
