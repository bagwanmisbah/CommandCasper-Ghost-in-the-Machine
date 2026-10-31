"""
ghost_context.py - READ-ONLY facts + the template explanation for Ghost.

Nothing in here writes, deletes, moves or runs anything. It only looks at
paths named in the command you typed (is it there? how big? how many files?)
and turns that into short plain-English lines.

    analyse(line, cwd)  ->  (verdict, facts, body_text)

`explain()` is the ONE place where a language model can be plugged in later:
it receives the verdict + facts and returns text. Today it is plain templates,
so Ghost works with no model, no internet and almost no memory.

Standard library only, Python 3.9.
"""
import glob
import os
import time

from ghost_engine import classify, split_segments, tokenize

MAX_FACTS = 5          # never show more than this many fact lines
SCAN_LIMIT = 5000      # never count more than this many items inside a folder

TITLES = {
    "green": "All clear - this only reads.",
    "yellow": "Proceed at your own risk.",
    "red": "Think this through!",
    "idle": "Ghost is awake.",
}

IDLE_BODY = (
    "Type a command, then press Alt+G (don't press Enter yet).\n"
    "I'll tell you whether it only reads, changes something, or destroys something.\n"
    "Click me to open or close this bubble."
)


def _ago(ts: float) -> str:
    days = (time.time() - ts) / 86400.0
    if days < 1:
        return "edited today"
    if days < 2:
        return "edited yesterday"
    return "edited %d days ago" % int(days)


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%d B" % n


def _describe(path: str, shown: str) -> str:
    if os.path.isdir(path):
        files = dirs = recent = seen = 0
        capped = False
        now = time.time()
        for _root, dnames, fnames in os.walk(path, onerror=lambda e: None):
            dirs += len(dnames)
            for f in fnames:
                files += 1
                try:
                    if now - os.path.getmtime(os.path.join(_root, f)) < 86400:
                        recent += 1
                except OSError:
                    pass
            seen = files + dirs
            if seen >= SCAN_LIMIT:
                capped = True
                break
        text = "folder '%s': %d file%s, %d subfolder%s" % (
            shown, files, "" if files == 1 else "s", dirs, "" if dirs == 1 else "s")
        if recent:
            text += ", %d edited today" % recent
        if capped:
            text += " (counted the first %d items only)" % SCAN_LIMIT
        return text
    st = os.stat(path)
    return "'%s': %s, %s" % (shown, _size(st.st_size), _ago(st.st_mtime))


def _looks_like_path(tok: str) -> bool:
    if not tok or tok.startswith("-") or tok.startswith("$") or "://" in tok:
        return False
    if tok.startswith("/") and len(tok) <= 3:  # cmd-style switch such as /s /q
        return False
    return True


def gather_facts(line: str, cwd: str) -> list:
    """Read-only facts about the files/folders named in the command."""
    facts, seen = [], set()
    for seg in split_segments(line):
        for tok in tokenize(seg)[1:]:
            if len(facts) >= MAX_FACTS:
                return facts
            if not _looks_like_path(tok):
                continue
            full = tok if os.path.isabs(tok) else os.path.join(cwd, tok)
            try:
                if any(c in tok for c in "*?["):
                    n = len(glob.glob(full))
                    key = ("glob", os.path.normcase(full))
                    if key not in seen:
                        seen.add(key)
                        facts.append("'%s' matches %d item%s here" % (tok, n, "" if n == 1 else "s"))
                elif os.path.exists(full):
                    key = os.path.normcase(os.path.abspath(full))
                    if key not in seen:
                        seen.add(key)
                        facts.append(_describe(full, tok))
            except (OSError, ValueError):
                continue
    return facts


def explain(verdict, facts, line: str) -> str:
    """TEMPLATE explanation (no model). The single swap point for AI later."""
    shown = line if len(line) <= 120 else line[:117] + "..."
    parts = ["Command: " + shown, ""]
    for r in verdict.reasons:
        parts.append("- " + r)
    if facts:
        parts += ["", "In this folder:"] + ["- " + f for f in facts]
    if verdict.colour == "red":
        parts += ["", "Tip: many PowerShell commands accept -WhatIf to preview without changing anything."]
    return "\n".join(parts)


def analyse(line: str, cwd: str):
    """Everything the window needs. Never raises: on any problem it says so."""
    try:
        line = (line or "").strip()
        verdict = classify(line, exists=lambda p: os.path.exists(os.path.join(cwd, p)))
        if verdict.colour == "idle":
            return verdict, [], IDLE_BODY
        facts = gather_facts(line, cwd) if verdict.colour in ("yellow", "red") else []
        return verdict, facts, explain(verdict, facts, line)
    except Exception as exc:  # never let the ghost crash the window
        from ghost_engine import Verdict
        v = Verdict("yellow", ["Ghost could not analyse this line (%s)" % type(exc).__name__])
        return v, [], "Ghost could not analyse this line, so treat it with care."
