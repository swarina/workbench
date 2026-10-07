"""Idempotently register a command hook in a Claude Code settings file.

Used on throwaway cloud VMs, where nobody's settings are at risk. On your own machine,
wire hooks by hand (see README); `install.sh` never edits settings.
"""
import json
import os
from typing import Dict


def ensure_hook(settings_path: str, event: str, command: str) -> bool:
    """Add `command` under `event` unless already present. Returns True if the file changed.

    Existing settings and other hooks are preserved. A settings file that is not valid
    JSON is left alone and raises, rather than being overwritten.
    """
    settings: Dict = {}
    if os.path.exists(settings_path):
        with open(settings_path) as fh:
            text = fh.read()
        if text.strip():
            settings = json.loads(text)
    groups = settings.setdefault("hooks", {}).setdefault(event, [])
    for group in groups:
        if any(h.get("command") == command for h in group.get("hooks", [])):
            return False
    groups.append({"hooks": [{"type": "command", "command": command}]})
    os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
    with open(settings_path, "w") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    return True
