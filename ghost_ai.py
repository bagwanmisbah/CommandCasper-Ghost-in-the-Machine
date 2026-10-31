"""ghost_ai.py - optional AI explanation for Command Casper.

RULES decide the colour. The AI never does. It only rewords an explanation,
and it is told the verdict as a fixed fact.

Standard library only. Settings come from D:\\ghost\\.env (git-ignored):

  Google AI Studio (default, Gemma):
      GHOST_API_MODEL=gemma-4-26b-a4b-it
      GHOST_API_KEY=your-key

  Any OpenAI-style provider (Groq, OpenRouter, ...): ALSO set
      GHOST_API_URL=https://.../chat/completions
    and put that provider's model name in GHOST_API_MODEL.

If anything is missing or fails, ask_ai() returns None and the caller just
shows the template text. In the app this is silent.

Test from the terminal:
    python ghost_ai.py "Remove-Item .\\old -Recurse -Force"
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_SECONDS = 25
GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"

# Last error text, so the terminal test can show WHY it failed.
last_error = ""
last_raw = ""
ENV_PATH = None  # a script may point this at another env file (e.g. .env.groq)


def load_env(path=None):
    """Tiny .env reader: KEY=value lines, # comments, optional quotes."""
    path = path or os.path.join(HERE, ".env")
    values = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


def get_settings():
    """Return (model, key, openai_url_or_empty) or None if not configured."""
    env = load_env(ENV_PATH)
    model = env.get("GHOST_API_MODEL", "").strip()
    key = env.get("GHOST_API_KEY", "").strip()
    url = env.get("GHOST_API_URL", "").strip()
    if not model or not key:
        return None
    return model, key, url


def build_prompt(line, verdict, reasons, facts):
    """ONLY the command, verdict, reasons and counts/sizes. Never file contents."""
    if isinstance(reasons, (list, tuple)):
        reasons = "; ".join(str(r) for r in reasons)
    if isinstance(facts, (list, tuple)):
        facts = "\n".join("- " + str(f) for f in facts)
    v = str(verdict).upper()
    return (
        "You are Casper, a friendly little ghost who warns people about "
        "PowerShell commands before they press Enter.\n"
        f"The verdict is {v} and it is final. Never contradict it, never change it.\n"
        "Use ONLY the facts given below. Do not invent files or numbers.\n"
        "Explain in 2 or 3 short plain sentences for a beginner. "
        "No markdown, no lists, no greeting.\n\n"
        f"Command: {line}\n"
        f"Why the rules chose {v}: {reasons or 'n/a'}\n"
        + ("Facts about the files named in the command:\n" + facts + "\n" if facts else
           "No file facts were collected. Say NOTHING about what is or is not in the folder.\n")
    )


def _post(url, headers, payload):
    headers = dict(headers)
    headers["Content-Type"] = "application/json"
    # Some providers block Python's default User-Agent.
    headers["User-Agent"] = "command-casper/0.1"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _ask_google(model, key, prompt):
    global last_raw
    # Gemma 4 "thinks" before answering, which can use up every token.
    # Ask for minimal thinking; if Google rejects a level (HTTP 400), try the next.
    last_http = None
    for level in ("minimal", "low", None):
        cfg = {"maxOutputTokens": 2000, "temperature": 0.4}
        if level:
            cfg["thinkingConfig"] = {"thinkingLevel": level}
        try:
            data = _post(
                GOOGLE_BASE + model + ":generateContent",
                {"x-goog-api-key": key},
                {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                 "generationConfig": cfg},
            )
        except urllib.error.HTTPError as e:
            if e.code == 400 and level is not None:
                last_http = e
                continue
            raise
        cand = data["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
        last_raw = "finishReason=%s, thinkingLevel=%s, parts=%s" % (
            cand.get("finishReason"), level,
            json.dumps(parts)[-700:])
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if text.strip():
            return text
    if last_http is not None:
        raise last_http
    return ""


def _ask_openai_style(url, model, key, prompt):
    data = _post(
        url,
        {"Authorization": "Bearer " + key},
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400,
            "temperature": 0.4,
        },
    )
    return data["choices"][0]["message"]["content"]


def ask_ai(line, verdict, reasons="", facts="", model=None):
    """Return the AI's explanation text, or None on any problem."""
    global last_error
    last_error = ""
    settings = get_settings()
    if settings is None:
        last_error = "Not configured: set GHOST_API_MODEL and GHOST_API_KEY in .env (no # at the start of the line)"
        return None
    model_default, key, url = settings
    model = model or model_default
    prompt = build_prompt(line, verdict, reasons, facts)
    try:
        if url:
            text = _ask_openai_style(url, model, key, prompt)
        else:
            text = _ask_google(model, key, prompt)
        text = (text or "").strip()
        if not text:
            last_error = "The model answered with empty text. Raw reply: " + last_raw
            return None
        return text
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        last_error = "HTTP %s: %s" % (e.code, detail)
    except Exception as e:  # no internet, timeout, bad JSON, unexpected shape...
        last_error = "%s: %s" % (type(e).__name__, e)
    return None


def ask_ai_in_background(line, verdict, reasons, facts, out_queue):
    """Run ask_ai in a thread; put (line, text_or_None) on out_queue.

    The window polls the queue with root.after(...) so the UI never freezes.
    """
    def work():
        out_queue.put((line, ask_ai(line, verdict, reasons, facts)))
    threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    cmd = " ".join(sys.argv[1:]) or "Remove-Item .\\old -Recurse -Force"
    s = get_settings()
    print("Command:", cmd)
    print("Model:  ", s[0] if s else "(not set)")
    print("Asking the model (this can take a few seconds)...")
    answer = ask_ai(
        cmd,
        "red",
        "deletes files recursively and -Force skips safety prompts",
        ["Folder .\\old has 12 files (3.4 MB)"],
    )
    if answer:
        print("\nCasper says:\n" + answer)
    else:
        print("\nNo AI answer. Reason:", last_error)