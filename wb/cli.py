"""wb: Workbench command line. Subcommands: report, compare, statusline, wire-hook, check."""
import argparse
import json
import os
import sys
import time

from . import check as check_mod
from . import compare as compare_mod
from . import hookconfig, report, statusline
from .detectors import run_all
from .sources import SOURCES

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_sessions(source: str, since_days: float, project: str, session: str):
    names = list(SOURCES) if source == "all" else [source]
    cutoff = time.time() - since_days * 86400 if since_days else 0
    sessions = []
    for name in names:
        mod = SOURCES[name]
        for path in mod.discover():
            if session and session not in path:
                continue
            if cutoff and os.path.getmtime(path) < cutoff:
                continue
            s = mod.parse(path)
            if s and (not project or project.lower() in s.project.lower()):
                sessions.append(s)
    return sessions


def cmd_report(args) -> int:
    sessions = load_sessions(args.source, args.since, args.project, args.session)
    if not sessions:
        print("No sessions matched.", file=sys.stderr)
        return 1
    per_session = {s.id: run_all(s) for s in sessions}
    findings = [f for fs in per_session.values() for f in fs]
    if args.session or args.worst:
        ranked = sorted((s for s in sessions if s.kind == "main" or args.session),
                        key=lambda s: -s.cost_units)
        for s in ranked[: args.worst or len(ranked)]:
            print(report.render_session(s, per_session[s.id]))
            print()
        return 0
    summary = report.summarize(sessions, findings)
    if args.save is not None:
        print("Saved " + compare_mod.save(summary, args.save), file=sys.stderr)
    if args.by == "branch":
        print(report.render_branches(summary, args.top))
    else:
        print(report.to_json(summary) if args.json else report.render_summary(summary, args.top))
    return 0


def cmd_compare(args) -> int:
    try:
        a, b = compare_mod.load(args.before), compare_mod.load(args.after)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(compare_mod.compare(a, b, args.before, args.after))
    return 0


def cmd_statusline(args) -> int:
    # Never fail: a broken status line is worse than an empty one.
    try:
        print(statusline.render(json.load(sys.stdin)))
    except Exception:
        print("")
    return 0


def cmd_wire_hook(args) -> int:
    command = os.path.join(REPO_ROOT, "hooks", "context-nudge")
    try:
        changed = hookconfig.ensure_hook(os.path.expanduser(args.settings), "UserPromptSubmit", command)
    except ValueError as exc:
        print(f"{args.settings} is not valid JSON, left unchanged: {exc}", file=sys.stderr)
        return 1
    print(("added nudge hook to " if changed else "nudge hook already in ") + args.settings)
    return 0


def cmd_check(args) -> int:
    problems = check_mod.check(REPO_ROOT)
    for p in problems:
        print("FAIL", p)
    print(f"{len(problems)} problem(s)" if problems else "ok")
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wb", description="Workbench tooling")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("report", help="where tokens went, and detected waste")
    r.add_argument("--source", choices=list(SOURCES) + ["all"], default="all")
    r.add_argument("--since", type=float, default=0, metavar="DAYS",
                   help="only sessions modified in the last DAYS")
    r.add_argument("--project", default="", help="substring of the project directory name")
    r.add_argument("--session", default="", help="session id (or part of it): per-session report")
    r.add_argument("--worst", type=int, default=0, metavar="N",
                   help="per-session reports for the N most expensive main sessions")
    r.add_argument("--top", type=int, default=10, help="rows per table")
    r.add_argument("--json", action="store_true", help="machine-readable summary")
    r.add_argument("--by", choices=["branch"], help="group cost by branch instead of the overview")
    r.add_argument("--save", nargs="?", const="", metavar="NAME",
                   help="also save a snapshot (see `wb compare`)")
    r.set_defaults(fn=cmd_report)

    cmp_ = sub.add_parser("compare", help="compare two saved snapshots")
    cmp_.add_argument("before", help="snapshot file, or a name fragment")
    cmp_.add_argument("after", help="snapshot file, or a name fragment")
    cmp_.set_defaults(fn=cmd_compare)

    sl = sub.add_parser("statusline", help="status line for Claude Code (reads JSON on stdin)")
    sl.set_defaults(fn=cmd_statusline)

    w = sub.add_parser("wire-hook", help="add the nudge hook to a settings file (for cloud VMs)")
    w.add_argument("--settings", required=True, help="settings.json to update, e.g. ~/.claude/settings.json")
    w.set_defaults(fn=cmd_wire_hook)

    c = sub.add_parser("check", help="lint this repo (budgets, skill frontmatter)")
    c.set_defaults(fn=cmd_check)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
