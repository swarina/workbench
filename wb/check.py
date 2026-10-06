"""Repo lint: keeps Workbench itself small and well-formed. Run by `wb check` and the tests."""
import os
import re
from typing import Dict, List

INSTRUCTIONS_MAX_LINES = 60   # always-loaded context, so it has a hard budget
SKILL_MAX_LINES = 150         # loaded on use; longer material belongs in sibling files
SKILL_STATUSES = {"experimental", "validated", "stable", "deprecated"}
REQUIRED_SKILL_FIELDS = ("name", "description", "status")


def frontmatter(text: str) -> Dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    # nested metadata.status is allowed too
    nested = re.search(r"^\s+status:\s*(\S+)", m.group(1), re.M)
    if nested and "status" not in fields:
        fields["status"] = nested.group(1)
    return fields


def _read(path: str) -> str:
    with open(path) as fh:
        return fh.read()


def check(root: str) -> List[str]:
    problems = []
    instructions = os.path.join(root, "instructions.md")
    if os.path.exists(instructions):
        n = len(_read(instructions).splitlines())
        if n > INSTRUCTIONS_MAX_LINES:
            problems.append(f"instructions.md is {n} lines (budget {INSTRUCTIONS_MAX_LINES}); "
                            "move detail into a skill")
    else:
        problems.append("instructions.md is missing")

    skills = os.path.join(root, "skills")
    for name in sorted(os.listdir(skills)) if os.path.isdir(skills) else []:
        path = os.path.join(skills, name, "SKILL.md")
        if not os.path.isdir(os.path.join(skills, name)):
            continue
        if not os.path.exists(path):
            problems.append(f"skills/{name}: no SKILL.md")
            continue
        text = _read(path)
        fm = frontmatter(text)
        for key in REQUIRED_SKILL_FIELDS:
            if not fm.get(key):
                problems.append(f"skills/{name}: frontmatter missing '{key}'")
        if fm.get("name") and fm["name"] != name:
            problems.append(f"skills/{name}: name '{fm['name']}' does not match directory")
        if fm.get("status") and fm["status"] not in SKILL_STATUSES:
            problems.append(f"skills/{name}: status must be one of {sorted(SKILL_STATUSES)}")
        if len(text.splitlines()) > SKILL_MAX_LINES:
            problems.append(f"skills/{name}: over {SKILL_MAX_LINES} lines; split into reference files")

    for folder in ("bin", "hooks"):
        d = os.path.join(root, folder)
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            p = os.path.join(d, name)
            if os.path.isfile(p) and not os.access(p, os.X_OK):
                problems.append(f"{folder}/{name} is not executable")
    return problems
