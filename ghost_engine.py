"""
ghost_engine.py - the rule engine ("the brain") of Ghost.

Give it a PowerShell command line (typed, NOT run) and it returns a colour:
    green  = only reads
    yellow = changes something, usually recoverable (also: unknown commands)
    red    = destructive / hard to undo
    idle   = nothing typed

Rules decide the colour from rules.json. No AI is used here, ever.
This file only READS text; it never runs the command and never touches files
(except reading rules.json, and - if you pass `exists` - asking whether a path
exists). Standard library only, works on Python 3.9.

Quick try (from the folder with these files):
    python ghost_engine.py "Remove-Item .\\old -Recurse"
Exit code: 0 = green/idle, 1 = yellow, 2 = red  (handy as a guard for scripts/agents).

For the real ghost, pass `exists` so the engine can tell "creates a new file"
from "overwrites an existing file". Remember the ghost runs in its own process,
so resolve relative paths against the terminal's folder:
    classify(line, exists=lambda p: os.path.exists(os.path.join(cwd, p)))
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

ORDER = {"idle": 0, "green": 1, "yellow": 2, "red": 3}
HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "rules.json")
_CACHE = {}

SEPARATORS = ";|{}()\n\r"
SCRIPT_EXTS = (".exe", ".com", ".cmd", ".bat", ".ps1")

ASSIGN_RE = re.compile(r"^\$[\w:.\[\]]+\s*[-+*/%]?=\s*(.*)$", re.S)
EXPR_RE = re.compile(
    r"^[\w.\[\]'\"]+\s*(=(?!=)|-(eq|ne|gt|lt|ge|le|like|notlike|match|notmatch|"
    r"contains|notcontains|in|notin|and|or|is|isnot|replace|split|join)\b)",
    re.I,
)
REDIRECT_RE = re.compile(r"(?<![\d&<>])(>>?)\s*([^\s;|&<>]+)")
INSTANCE_DANGER_RE = re.compile(r"\.\s*delete\s*\(", re.I)


@dataclass
class Verdict:
    colour: str
    reasons: List[str] = field(default_factory=list)
    segments: List[Dict[str, str]] = field(default_factory=list)


def load_rules(path: str = RULES_PATH) -> dict:
    if path not in _CACHE:
        with open(path, encoding="utf-8") as f:
            _CACHE[path] = json.load(f)
    return _CACHE[path]


# ---------------------------------------------------------------- text helpers
def _quote_mask(text: str) -> List[bool]:
    """True for every character that is inside quotes (or backtick-escaped)."""
    mask: List[bool] = []
    q = None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if q is None:
            if c == "`" and i + 1 < n:
                mask.extend([False, True])
                i += 2
                continue
            if c in "'\"":
                q = c
                mask.append(True)
            else:
                mask.append(False)
        else:
            if q == '"' and c == "`" and i + 1 < n:
                mask.extend([True, True])
                i += 2
                continue
            mask.append(True)
            if c == q:
                if i + 1 < n and text[i + 1] == q:  # doubled quote = literal quote
                    mask.append(True)
                    i += 2
                    continue
                q = None
        i += 1
    return mask


def _masked(text: str) -> str:
    return "".join("x" if m else c for c, m in zip(text, _quote_mask(text)))


def split_segments(line: str) -> List[str]:
    """Split a line into separate commands at ; | && || { } ( ) outside quotes."""
    mask = _quote_mask(line)
    segs: List[str] = []
    cur: List[str] = []
    i = 0
    while i < len(line):
        c = line[i]
        if not mask[i] and line.startswith("&&", i):
            segs.append("".join(cur))
            cur = []
            i += 2
            continue
        if not mask[i] and c in SEPARATORS:
            segs.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    segs.append("".join(cur))
    return [s.strip() for s in segs if s.strip()]


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "'\"":
        return tok[1:-1]
    return tok


def tokenize(seg: str) -> List[str]:
    mask = _quote_mask(seg)
    toks: List[str] = []
    cur: List[str] = []
    for c, m in zip(seg, mask):
        if c.isspace() and not m:
            if cur:
                toks.append("".join(cur))
                cur = []
        else:
            cur.append(c)
    if cur:
        toks.append("".join(cur))
    return [_unquote(t) for t in toks]


def flag_match(arg: str, flag: str, case_sensitive: bool = False) -> bool:
    """Does `arg` (as typed) mean `flag`? PowerShell allows shortened flags (-fo for -force)."""
    a = arg.split(":", 1)[0] if arg.startswith("-") else arg
    f = flag
    if not case_sensitive:
        a, f = a.lower(), f.lower()
    if a == f:
        return True
    if (f.startswith("-") and not f.startswith("--") and len(f) > 3
            and a.startswith("-") and not a.startswith("--") and len(a) >= 3
            and f.startswith(a)):
        return True
    return False


def _has_flag(args: List[str], flags: Optional[List[str]], cs: bool = False) -> Optional[str]:
    for f in flags or []:
        for a in args:
            if flag_match(a, f, cs):
                return f
    return None


def _first_positional(args: List[str], opts_with_value: List[str]) -> Optional[str]:
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in opts_with_value:
            skip = True
            continue
        if a.startswith("-"):
            continue
        return a
    return None


def _target_of(args: List[str]) -> Optional[str]:
    for i, a in enumerate(args):
        if any(flag_match(a, f) for f in ("-path", "-literalpath", "-filepath")):
            return args[i + 1] if i + 1 < len(args) else None
    for a in args:
        if not a.startswith("-"):
            return a
    return None


def _worse(a: str, b: str) -> str:
    return a if ORDER[a] >= ORDER[b] else b


def _norm(entry) -> dict:
    return {"colour": entry} if isinstance(entry, str) else dict(entry)


# ------------------------------------------------------------ classification
def _apply_entry(entry, args: List[str], rules: dict, exists: Optional[Callable]):
    e = _norm(entry)
    cs = bool(e.get("case_sensitive"))
    defaults = rules["default_reasons"]

    if _has_flag(args, e.get("green_flags"), cs):
        return "green", e.get("green_reason", "Preview / read-only option")

    subs = e.get("subcommands")
    if subs:
        sub = _first_positional(args, e.get("options_with_value", []))
        if sub is None:
            return e.get("default", "yellow"), e.get("reason", defaults["yellow"])
        se = subs.get(sub.lower())
        if se is None:
            return e.get("default", "yellow"), "Unrecognised subcommand '%s' - can't tell what it does" % sub
        merged = {k: v for k, v in e.items() if k not in ("subcommands", "green_flags", "green_reason", "reason", "colour")}
        merged.update(_norm(se))
        e = merged
        if _has_flag(args, e.get("green_flags"), cs):
            return "green", e.get("green_reason", "Preview / read-only option")

    colour = e.get("colour", "yellow")
    reason = e.get("reason") or defaults.get(colour, "")

    hit = _has_flag(args, e.get("red_flags"), cs)
    if hit:
        return "red", "With %s: %s" % (hit, e.get("red_reason", "this is more destructive"))
    hit = _has_flag(args, e.get("yellow_flags"), cs)
    if hit and ORDER[colour] < ORDER["yellow"]:
        colour, reason = "yellow", "With %s: %s" % (hit, e.get("yellow_reason", "this changes something"))

    if e.get("overwrites_target") and not _has_flag(args, e.get("safe_flags"), cs):
        target = _target_of(args)
        if exists is not None and target:
            try:
                there = bool(exists(target))
            except Exception:
                there = False
            if there:
                return "red", "Replaces the existing file '%s'" % target
            return "yellow", "Creates a new file '%s'" % target
        return "yellow", "May overwrite a file that already exists"

    return colour, reason


def _command_verdict(name: str, args: List[str], text: str, rules: dict, exists: Optional[Callable]):
    defaults = rules["default_reasons"]
    first = name[0]

    if first == "[":  # .NET static call such as [System.IO.File]::Delete(...)
        m = re.search(r"::\s*(\w+)", text)
        if m:
            if m.group(1).lower() in rules["dotnet_red_methods"]:
                return "red", "Calls .NET code that deletes or overwrites files (%s)" % m.group(1)
            return "yellow", "Calls .NET code directly - can't tell what it does"
        return "green", "Plain expression, no command"
    if first in "$\"'@0123456789-+!" or EXPR_RE.match(text):
        return "green", "Plain expression, no command"

    low = name.lower()
    if low in rules["keywords"]:
        return "green", "PowerShell control-flow keyword"

    if _has_flag(args, ["-whatif"], False):
        return "green", "-WhatIf: preview only, nothing will change"

    base = re.split(r"[\\/]", low)[-1]
    had_path = base != low
    stem, ext = base, ""
    for e in SCRIPT_EXTS:
        if base.endswith(e):
            stem, ext = base[: -len(e)], e
            break
    canon = stem if ext else rules["aliases"].get(stem, stem)

    entry = rules["commands"].get(canon)
    if entry is not None:
        return _apply_entry(entry, args, rules, exists)

    if "-" in canon:
        verb = canon.split("-", 1)[0]
        if verb in rules["verb_defaults"]:
            colour, reason = rules["verb_defaults"][verb]
            return colour, reason

    if had_path or ext in (".ps1", ".cmd", ".bat", ".exe", ".com"):
        return "yellow", "Runs a script or program - can't see inside"
    return "yellow", "Unknown command - can't tell what it does"


def _redirect_verdict(text: str, exists: Optional[Callable]):
    worst, why = None, ""
    masked = _masked(text)
    for m in REDIRECT_RE.finditer(masked):
        op = m.group(1)
        target = _unquote(text[m.start(2): m.end(2)])
        if target.lower() in ("$null", "nul") or target.startswith("&"):
            continue
        if op == ">>":
            colour, reason = "yellow", "Appends output to '%s'" % target
        elif exists is not None:
            try:
                there = bool(exists(target))
            except Exception:
                there = False
            colour, reason = ("red", "Redirect (>) replaces the existing file '%s'" % target) if there \
                else ("yellow", "Redirect (>) creates a new file '%s'" % target)
        else:
            colour, reason = "yellow", "Redirect (>) may overwrite a file"
        if worst is None or ORDER[colour] > ORDER[worst]:
            worst, why = colour, reason
    return worst, why


def classify_segment(seg: str, rules: dict, exists: Optional[Callable] = None) -> Optional[Dict[str, str]]:
    text = seg.strip()
    m = re.match(r"^[&.]\s+(.*)$", text, re.S)
    if m:
        text = m.group(1).strip()
    elif text.startswith("&"):
        text = text[1:].strip()
    if not text:
        return None

    m = ASSIGN_RE.match(text)
    if m:
        rhs = m.group(1).strip()
        inner = classify_segment(rhs, rules, exists) if rhs else None
        return inner or {"text": seg, "colour": "green", "reason": "Stores a value in a variable"}

    tokens = tokenize(text)
    if not tokens:
        return None
    colour, reason = _command_verdict(tokens[0], tokens[1:], text, rules, exists)

    rc, rr = _redirect_verdict(text, exists)
    if rc and ORDER[rc] > ORDER[colour]:
        colour, reason = rc, rr
    elif rc and ORDER[rc] == ORDER[colour] and colour != "green":
        reason = reason + "; " + rr
    return {"text": seg, "colour": colour, "reason": reason}


def classify(line: str, rules: Optional[dict] = None, exists: Optional[Callable] = None) -> Verdict:
    rules = rules or load_rules()
    line = (line or "").strip()
    if not line:
        return Verdict("idle", ["Nothing typed yet"], [])

    results = []
    for seg in split_segments(line):
        r = classify_segment(seg, rules, exists)
        if r:
            results.append(r)
    if INSTANCE_DANGER_RE.search(_masked(line)):
        results.append({"text": line, "colour": "red", "reason": "Calls .Delete() directly on an object"})
    if not results:
        return Verdict("green", ["Nothing here changes anything"], [])

    worst = "green"
    for r in results:
        worst = _worse(worst, r["colour"])
    reasons: List[str] = []
    for r in results:
        if r["colour"] == worst and r["reason"] and r["reason"] not in reasons:
            reasons.append(r["reason"])
    return Verdict(worst, reasons, results)


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print('Usage: python ghost_engine.py "<powershell command>"')
        return 3
    v = classify(" ".join(argv[1:]), exists=os.path.exists)
    print(v.colour.upper())
    for r in v.reasons:
        print(" -", r)
    return {"idle": 0, "green": 0, "yellow": 1, "red": 2}[v.colour]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
