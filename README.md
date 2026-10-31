# 👻 Command Casperr

**A tiny hand-drawn ghost that haunts your PowerShell and warns you before you press Enter.**

Type a command (don't press Enter), press **Alt+G**, and Casperr turns **green**, **yellow** or **red**. Click him for a plain-English explanation plus real facts about your folder.

*Built for the [Hacktoberfest Open-Source AI Challenge, Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26).*



| 🟢 Green | 🟡 Yellow | 🔴 Red |
|---|---|---|
| Only reads things | Changes something, usually recoverable (installs, copies, `git commit`) | Destroys or is hard to undo (deletes, overwrites, `--force`, download-and-run) |





## The one rule that matters

**The rules decide the colour. The AI never does.**

The colour comes from a plain, editable [`rules.json`](rules.json) and a small deterministic engine (aliases, `&&` chains where the worst command wins, quotes, `>` vs `>>`, `-WhatIf` making a command green, unknown commands default to yellow). The AI (Gemma 4, an open-weight model) is told the verdict is final and only writes the friendly explanation. If there is no key, no internet, or an error, you simply get the built-in template text. Nothing breaks.

## What it never does

- It **never runs** your command and **never blocks Enter**.
- It only **reads** the text you typed and (read-only) looks at the paths in it: size, age, file counts.
- It adds **one key binding to the current terminal session only**. No `$PROFILE` edits, no registry, no PATH, no system-wide installs. Closing the terminal removes everything.
- Everything lives in one folder. Delete it and it's gone.

## Requirements

- Windows 10 or 11 with **Windows PowerShell 5.1** (PSReadLine 2.0)
- **Python 3.9 or newer** (tested on 3.9). It includes tkinter on Windows.
- **No packages to install.** Standard library only.
- Optional: a free [Google AI Studio](https://aistudio.google.com) API key, for the AI explanations. No card needed.

## Setup

```powershell
git clone https://github.com/[YOUR-NAME]/[YOUR-REPO].git
cd [YOUR-REPO]
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks scripts, allow them **for this session only**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
Unblock-File -Path .\ghost.ps1
```

### Optional: turn on the AI explanations

Create a file named `.env` in the project folder (it is git-ignored, never commit it):

```
GHOST_API_MODEL=gemma-4-26b-a4b-it
GHOST_API_KEY=your-key-here
```

Get the key from Google AI Studio. Without these two lines, Casperr still works with template explanations.

## Use it

```powershell
. .\ghost.ps1          # note the dot and the space
casperr summon         # Casperr drops in and Alt+G is switched on
```

Now type any command, **don't press Enter**, and press **Alt+G**. Click the ghost to open or close the bubble. Right-click him to send him home.

```powershell
casperr status         # is the ghost running? is the key bound?
casperr release        # Alt+G off, Casperr returns to the ghost realm
casperr summon -Key 'Alt+Shift+G'    # use another key if Alt+G is taken
```

You can also test without PowerShell's key binding:

```powershell
python ghost_send.py "Remove-Item .\old -Recurse -Force"
python ghost_send.py --quit
```

## Make it yours

- **Rules:** edit `rules.json` to change what is green, yellow or red.
- **Personality:** edit `personality.json`. Each colour has lines and one is picked at random. Swap "mortal" for anything.
- **Model:** change `GHOST_API_MODEL` in `.env`. For another OpenAI-style provider, also set `GHOST_API_URL` to its chat-completions URL (the code supports this, but only Google AI Studio has been tested).
- **Art:** sprites live in `art/` (95 x 95 transparent PNGs: green, yellow, red, idle, hi, bye).
- **If the fade effect misbehaves:** `$env:GHOST_NOFADE=1` before `casperr summon`.

## How it fits together

| File | Job |
|---|---|
| `ghost.ps1` | The PowerShell hook: `casperr summon / release / status`, binds Alt+G, sends your typed line to the ghost |
| `ghost_window.py` | The floating ghost: animation, bubble, listens on `127.0.0.1:47321` |
| `ghost_engine.py` + `rules.json` | The deterministic rule engine that picks the colour |
| `ghost_context.py` | Read-only folder facts plus the template explanation |
| `ghost_ai.py` | Optional AI explanation (standard library only, runs in a background thread) |
| `personality.json` | The ghost's lines |
| `compare_models.py` | Runs the same commands through different models (analyses only, never runs them) |
| `test_engine.py`, `test_context.py` | Tests |

The terminal and the ghost talk over a plain UDP message on your own machine (`127.0.0.1`).

## Tests

```powershell
python test_engine.py     # 114 commands: 37 green, 33 yellow, 44 red
python test_context.py
```

They also run automatically on every push through GitHub Actions (see the badge or the Actions tab).

## Privacy, honestly

With the AI switched on, the model is **hosted**, so the **text of the command you check** leaves your computer. Only that text, the verdict with its reasons, and counts or sizes (like "7 files, 18.6 KB") are sent. **Never file contents.** Still, a command can contain a secret, and Google says free-tier prompts may be used to improve its products. **Don't check commands that contain passwords or keys while the AI is on.** Leave out the `.env` lines and Casperr works fully offline with templates. Because it uses an open-weight model, running one yourself on a bigger machine is possible, but I haven't done that.

## Limits

- Windows PowerShell 5.1 only. `cmd.exe` is out of scope.
- A rules-based checker can be wrong or incomplete. Unknown commands default to yellow. Treat Casperr as a friendly second pair of eyes, not a security tool.
- Alt+G may clash with another app (for example VS Code). Use `-Key 'Alt+Shift+G'`.
- Only one ghost can run at a time (port 47321).
- The ghost hides errors when run without a console. Check `ghost_error.log` if something looks off.

## Challenge notes

- Built solo, as a new project, during the challenge window (Oct 26 to Oct 31, 2026).
- Commits after the Oct 31 deadline: [NONE, or list them here].
- Built with help from AI assistants (Claude and GitHub Copilot). The design, art, rules and testing are mine.

## Credits

- Ghost artwork: original pixel art by Misbah Bagwan
- Model: [Gemma 4](https://ai.google.dev/gemma) by Google, used through Google AI Studio under its terms.
- Video music: [TRACK NAME] by [ARTIST] from Pixabay.
- "Casper" is also the name of a famous cartoon ghost. This project is not affiliated with that character.

## License

