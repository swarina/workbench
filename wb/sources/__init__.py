"""Transcript sources. To support another tool, add a module with NAME, discover() and
parse(), then list it in SOURCES."""
from . import claude, codex

SOURCES = {m.NAME: m for m in (claude, codex)}
