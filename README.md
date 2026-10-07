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
session. Save the baseline first (`wb report --save baseline`); after a week of use,
`wb report --since 7 --save after` and `wb compare baseline after` show what changed.

## Layout

| Path | What it is | Loaded when |
|---|---|---|
| `instructions.md` | Working defaults for every project. Linked as `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md`. | Always, so it has a 60-line budget |
| `skills/<name>/SKILL.md` | Focused procedures, shared by both tools. | On use |
| `agents/<name>.md` | Claude Code subagents (none yet). | On delegation |
| `bin/` | Deterministic helpers on PATH: `wb`, `diff-summary`. | When called |
| `hooks/` | Hook scripts: `context-nudge`. Wired into settings by hand locally, by `cloud/setup.sh` on cloud VMs. | On the hook event |
| `cloud/` | Bootstrap for cloud session VMs: `setup.sh`. | At cloud environment setup |
| `wb/` | Python package behind `wb` (standard library only). | n/a |
| `lessons.md` | Evidence-backed failures and where each fix belongs. | Never loaded automatically |
| `tests/` | Unit tests, including a lint of this repo. | n/a |

## Install details

    ./install.sh status            # what is linked, missing or in conflict
    ./install.sh link [--dry-run]
    ./install.sh unlink
    ./install.sh link --import-instructions

Symlinks only, so edits in this repo take effect immediately. Existing files are never
overwritten; they are reported as conflicts. With `--import-instructions`, an existing
instructions file gets an `@<repo>/instructions.md` import line appended instead of being
skipped (used on cloud VMs, which ship their own `CLAUDE.md`). Codex is skipped when
`~/.codex` does not exist. Override targets with `CLAUDE_HOME`, `CODEX_HOME` and
`WB_BIN_DIR`.

## Measure

    wb report                      # all sessions: cost split, tool output, detected waste
    wb report --since 7            # only usage from the last 7 days, even inside older sessions
    wb report --project <name>
    wb report --source claude      # claude, codex or all (default)
    wb report --worst 3            # per-session reports for the most expensive sessions
    wb report --session <id>       # one session
    wb report --json               # machine-readable summary
    wb report --by branch          # cost per branch, a proxy for cost per task or PR
    wb report --save baseline      # also save a snapshot to ~/.workbench/snapshots
    wb compare baseline after      # two snapshots (name fragment or path), per turn and session

Token classes are weighted by approximate relative price to rank waste. The estimates
are for comparison, not accounting.

Detectors: `long_session`, `cache_rewrite` (large context re-cached after an idle gap),
`cache_model_switch` (re-cached because the model changed mid-session),
`cache_invalidation` (re-cached with no gap or model switch; mostly unexplained, likely
API errors or server-side misses), `startup_overhead`, `large_outputs`, `repeat_reads`,
`duplicate_calls`, `unbatched_calls`.

## Live visibility and enforcement

Two small pieces act during a session. Neither is installed automatically, because both
need an entry in your Claude Code settings.

Status line, showing context size, session cost and a handoff hint:

    "statusLine": { "type": "command", "command": "/path/to/workbench/bin/wb statusline" }

Handoff nudge: on each prompt, if context is above 200k tokens, one line asks the agent
to run `handoff` at the next boundary (above 400k: now). It repeats at most every 10
prompts, and always exits 0:

    "hooks": { "UserPromptSubmit": [ { "hooks": [
      { "type": "command", "command": "/path/to/workbench/hooks/context-nudge" } ] } ] }

Use absolute paths so neither depends on `~/.local/bin` being on PATH. The status line
reads `transcript_path`, `cost.total_cost_usd` and `context_window.context_window_size`
from the JSON Claude Code sends; the nudge hook reads `session_id` and `transcript_path`.
Field names were checked against the Claude Code docs on 2026-10-07. Missing fields
shorten the line rather than break it. Thresholds live in `wb/live.py`. On a throwaway
VM, `wb wire-hook --settings <file>` registers the hook idempotently; it refuses to
touch a file that is not valid JSON.

## Cloud sessions

Cloud sessions run on a fresh VM with only your repo, so nothing in `~/.claude` reaches
them. Instead of committing config into every repo, install Workbench from the
environment's setup script. In claude.ai/code, open the environment settings and paste
this into **Setup script**:

    #!/bin/bash
    git clone -q --depth 1 https://github.com/swarina/workbench.git /opt/workbench 2>/dev/null \
      || git -C /opt/workbench pull -q --ff-only
    bash /opt/workbench/cloud/setup.sh || true

`cloud/setup.sh` imports `instructions.md` into the VM's own `CLAUDE.md` (it does not
replace it), links the `handoff` skill and helpers, registers the nudge hook, and exits
0 whatever happens. Verify in a new cloud session with `/context`: the memory files
should include `instructions.md`.

- **Private repo:** the clone must succeed from the VM. If it fails, the session still
  starts, without Workbench. Check the setup log, and if needed make the repo public or
  provide read access.
- **Updates:** the setup result is cached for about a week and rebuilt when the script
  changes. Edit the script (a comment is enough) to pick up Workbench changes sooner.
- **Handoff:** the VM is discarded and the next session starts from a fresh clone, so in
  cloud sessions `handoff` saves state in the PR description (the `workbench:task`
  block) instead of `.workbench/task.md`.
- **Measurement:** cloud transcripts stay on the VM, so `wb report` on your Mac cannot
  see them. In a cloud session, ask for `wb report --session <id>` to inspect that
  session, or use `/context`.

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
measurement supports it. The cloud bootstrap is tested locally only, not yet in a real
cloud VM. Thresholds are tuned on TypeScript, Swift and Python projects, not on Java or
AWS work.
