# Ghost - handoff for GitHub Copilot

You are helping ONE person (solo, not a team) build a small project, and you also guide them
through any remaining SETUP. Go slowly, one step at a time, and wait for the user to confirm
each step. Never hand over a big block of commands.

## RULES FOR HOW YOU HELP (read first)

1. **Explain every step before it happens:** WHAT it does, WHERE files go, HOW MUCH disk space
   and RAM it uses, and HOW TO UNDO it. Wait for "done" before the next step.
2. **Do not break anything that already exists on this PC.** No system-wide installs, no
   changes to PATH, registry, existing Python packages, existing apps, PowerShell profile
   ($PROFILE), execution policy (machine/user scope), or Windows Terminal settings.
   Only session-scoped changes (e.g. `Set-ExecutionPolicy -Scope Process`) and things inside
   D:\ghost. Ask before any command that changes something. Prefer read-only checks first.
3. **Disk and RAM are the main constraints** (see below). Before each download or install,
   state the size and confirm it lands on D:, never C:. Tell the user how to watch RAM
   (Task Manager > Details tab, or the printed output of test_llm.py) and when to stop.
4. **Everything must be removable by deleting one folder** (D:\ghost). Redirect pip cache,
   Hugging Face cache and temp files into it, or say exactly where they go.
5. **Budget is zero.** Free tools only.
6. If anything fails: stop, explain the error in plain words, propose the safest fix. Never
   escalate to admin rights or "force" flags.
7. The user is new to GGUF / llama.cpp / virtual environments. Explain jargon in one plain
   sentence the first time you use it.

## Machine constraints (the big ones)

- Windows 10, **8 GB RAM total**, only **~4 GB free on C:**, 20+ GB free on **D:**.
- Python 3.9.10 (C:\Users\LDIN\AppData\Local\Programs\Python\Python39), Windows PowerShell
  5.1.19041, PSReadLine 2.0.0. Editor: VS Code with its integrated PowerShell terminal.
- RAM budget: the whole project idles at a few tens of MB. The language model is loaded ONLY
  while the user clicks the ghost for an explanation and is released afterwards. Target peak
  while answering: well under ~2 GB; the user must be able to keep normal apps open.
- Disk: nothing new on C:. Venv and models live on D:\ghost.

## Context

Hacktoberfest 2026 "Open-Source AI Challenge: Week 4 - Ghost in the Machine" on DEV.
Deadline: Oct 31 2026 11:59 PM PDT (= Nov 1 about 12:29 PM IST). Must be a NEW project built in
the window, with open-source / open-weight AI at its core, plus a DEV post (writing quality is
weighted most). Tags: devchallenge, hf26challenge. If the model is too heavy for this PC, the
project still works with plain template text (no model) - say so honestly in the post.

## The project

"Ghost" - a small floating pixel-art ghost for PowerShell. The user types a command, does NOT
press Enter, presses Alt+G. The ghost changes to one of three states:

- GREEN (ghost_green_framegif.png, tick) = read-only. Safe.
- YELLOW (ghost_yellow_framegif.png, "?") = may modify local state but usually recoverable
  (installs, copies, moves, creating files, git commit). "Proceed at your own risk".
- RED (ghost_red_framegif.png, "!") = destructive or hard to undo (deletes, overwrites,
  format, force flags, downloads-and-runs code). "Think this through".
  **Clicking the ghost (or its pumpkin)** opens a small speech-bubble rectangle ABOVE the ghost
  with the explanation: what the command does + real facts about the current folder (e.g.
  "deletes 47 files, 3 edited today"). The user can always just press Enter. Ghost never blocks
  or changes how any command runs.

## Art - DONE and verified

- Files: D:\ghost\art\ghost_green_framegif.png, ghost_yellow_framegif.png,
  ghost_red_framegif.png. Each is 95 x 95, transparent background, hard-edged pixel art.
- Verified with test_ghost_window.py (tkinter only, no extra install): size 95x95, top-left
  pixel transparent = True, and the ghost floats on screen with no box around it.
- Technique that works: tk.PhotoImage(file=png) (tkinter reads PNG natively), `.zoom(2)` for
  crisp 2x scaling, borderless window via overrideredirect(True), always on top, and
  `-transparentcolor` set to a key colour (#ff00ff) that is also the window and label bg.
  The floating motion is code (move the window up/down a few pixels on a timer with
  root.after), not animation frames.

## Hard design rules

1. RULES decide the colour (deterministic, editable JSON rules file). The AI NEVER picks the
   colour. Chains (a; b | c) take the worst verdict. Unknown = yellow.
2. A read-only "context check" gathers facts (file counts, sizes, dates). It never writes,
   deletes or runs the user's command.
3. A small local open-weight model (GGUF via llama-cpp-python, e.g. Qwen2.5 1.5B or 0.5B
   Instruct Q4_K_M from the official Qwen repo on Hugging Face) only rewords those facts into
   2-3 sentences, plus the cmdlet's own Get-Help text. Loaded lazily on click, then freed.
   Backend is swappable behind one function `explain(command, facts)`:
   local GGUF -> hosted open-weight API -> plain templates (no model).
4. Non-invasive: a session-only PowerShell function (`ghost watch`) binds Alt+G with
   Set-PSReadLineKeyHandler and reads the current line with
   [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState. Never rebind Enter. Never edit
   $PROFILE unless the user explicitly opts in later. Wrap everything in try/catch. Send the
   line to the ghost window with a fire-and-forget localhost UDP message. If the ghost is
   closed, Alt+G does nothing. Closing the terminal removes everything. (Keep in mind the
   user works inside the VS Code integrated terminal; test Alt+G does not collide with a
   VS Code or Windows Terminal shortcut, and change the key if it does.)
5. Ghost window: Python 3.9 + tkinter as described in "Art" above, bottom-right of the screen.
   The explanation bubble is a second small borderless window above the ghost.
6. cmd.exe is out of scope (no line-editor hook). Guard mode (blocking Enter) is out of scope.
   Clipboard watcher is dropped. VS Code extension is dropped.

## Build order (simplest case first; do not skip ahead)

0. DONE: art + transparency test. Remaining setup is guided, one confirmed step at a time:
   create the venv inside D:\ghost, redirect pip cache into D:\ghost, install only what is
   needed (psutil, then the llama-cpp-python CPU wheel). Explain and confirm each step.
1. Model feasibility test: the user downloads one GGUF file in a browser into
   D:\ghost\models; run test_llm.py (already written) to measure peak RAM + seconds and read
   the answers. If too heavy, try the smaller model; if still too heavy, drop local models and
   use templates or a hosted open-weight API (say plainly that file names would leave the PC).
2. Rule engine: classify(command) -> (colour, reasons) with the green/yellow/red definitions
   above. Tests for single commands, then chains, aliases (rm/del/ri), -Recurse/-Force,
   wildcards, quoting, iex/iwr, -EncodedCommand.
3. Read-only context check.
4. Real ghost window: swap between the 3 PNGs, bob animation, click-to-open bubble with
   template text first.
5. PowerShell Alt+G hook (session-only).
6. Plug the model into the bubble.
7. Later: git rules, session memory, `ghost check "cmd"` CLI (agent guard), personality lines,
   `-WhatIf` suggestion for red commands, README, benchmark table.

## For the DEV post

Explain why open matters: works offline, file names never leave the PC, free, models are
swappable. Be honest that similar checks exist (-WhatIf, AI agents asking permission) and say
what's different: deterministic rules, real folder facts, covers commands the human types or
copies, fully local. Include a rule-test accuracy table and a model RAM/speed benchmark.
Tell the story of the hand-drawn pixel ghost.
