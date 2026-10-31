"""
ghost_window.py - the floating ghost.

What it does
  * Shows your pixel ghost in the bottom-right corner, bobbing up and down,
    with a transparent background.
  * Listens on 127.0.0.1 (this computer only) for a short message containing
    the command you typed and the folder you are in.
  * Changes the ghost to green / yellow / red using the rule engine.
  * Click the ghost: a bubble opens above it with the explanation. Click the
    bubble (or the ghost again) to close it.
  * Right-click the ghost: menu with "Quit Ghost".

What it never does: run your command, change any file, or touch PowerShell.
It only reads the message text and (read-only) looks at the paths in it.

Run from D:\\ghost (the art images live in D:\\ghost\\art):
    python ghost_window.py
Try it without PowerShell, from a second terminal:
    python ghost_send.py "Remove-Item .\\old -Recurse"
    python ghost_send.py --quit

Settings (optional, per terminal session):
    GHOST_PORT  (default 47321)     GHOST_ZOOM (default 2 = 190 px ghost)
"""
import glob
import json
import math
import os
import queue
import random
import socket
import sys
import tkinter as tk
import traceback

try:  # sharper text/sprite on scaled Windows screens; harmless if unavailable
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from ghost_context import IDLE_BODY, TITLES, analyse
import ghost_ai

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "art")
PORT = int(os.environ.get("GHOST_PORT", "47321"))
ZOOM = max(1, int(os.environ.get("GHOST_ZOOM", "2")))
KEY = "#ff00ff"  # this exact colour becomes see-through on Windows

COLOURS = {"green": "#1fa84a", "yellow": "#e89a00", "red": "#d62a2a", "idle": "#2f6fd6"}
# Which art file each state uses (the file name starts with this text; _ or - both work).
SPRITES = {"green": "ghost_green", "yellow": "ghost_yellow", "red": "ghost_red", "idle": "ghost_idle",
           "hi": "ghost_hi", "bye": "ghost_bye"}

# Motion per state: (bob speed, bob height in px, sideways wobble in px).
# Green is calm, yellow is quicker, red is frantic (fastest, but not absurd).
MOTION = {"idle": (0.10, 8, 0), "green": (0.10, 8, 0), "yellow": (0.17, 8, 0), "red": (0.30, 6, 3)}
DROP = 260        # how far above its spot the ghost starts / ends (pixels)
IN_FRAMES = 28    # drop-in length  (28 x 40 ms = about 1.1 s)
OUT_FRAMES = 24   # bye length


def ease_out_back(p):
    """0 -> 1 with a tiny overshoot, so the ghost 'settles' into place."""
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (p - 1.0) ** 3 + c1 * (p - 1.0) ** 2


def _log(text):
    """Write problems to ghost_error.log next to this file (the ghost may run with no console)."""
    try:
        with open(os.path.join(HERE, "ghost_error.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass


def find_sprite(prefix, required=True):
    # Accept both ghost_idle.png and ghost-idle.png style names.
    for name in (prefix, prefix.replace("_", "-")):
        for ext in ("png", "gif"):
            found = sorted(glob.glob(os.path.join(ART, name + "*." + ext)))
            if found:
                return found[0]
    if not required:
        return None
    sys.exit("Can't find %s*.png in %s" % (prefix, ART))


def load_personality():
    """Titles per colour from personality.json (edit it freely). Falls back to built-ins."""
    try:
        with open(os.path.join(HERE, "personality.json"), "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return {k: [str(t) for t in v] for k, v in data.items() if isinstance(v, list) and v}
    except (OSError, ValueError):
        return {}


PERSONALITY = load_personality()


def pick_title(state):
    options = PERSONALITY.get(state)
    return random.choice(options) if options else TITLES[state]


class Ghost:
    def __init__(self):
        # Take the port FIRST so a second copy exits instead of fighting.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("127.0.0.1", PORT))
        except OSError:
            sys.exit("Ghost already seems to be running (port %d is in use)." % PORT)
        self.sock.setblocking(False)

        self.root = tk.Tk()
        self.root.title("Ghost")
        self.root.report_callback_exception = lambda *a: _log("".join(traceback.format_exception(*a)))
        self.images = {}
        for state in ("green", "yellow", "red", "idle"):
            self.images[state] = tk.PhotoImage(file=find_sprite(SPRITES[state])).zoom(ZOOM)
        for extra in ("hi", "bye"):  # optional: fall back to the idle sprite if missing
            path = find_sprite(SPRITES[extra], required=False)
            self.images[extra] = tk.PhotoImage(file=path).zoom(ZOOM) if path else self.images["idle"]
        self.gw = self.images["green"].width()
        self.gh = self.images["green"].height()

        self.state = "idle"
        self.title = pick_title("idle")
        self.body = IDLE_BODY
        self.base_body = IDLE_BODY
        self.ai_queue = queue.Queue()
        self.ai_cache = {}
        self.ai_text = ""
        self.ai_pending = False
        self.cur_line = ""
        self.bubble = None
        self.t = 0.0
        self.hop = 0
        self.mode = "in"   # "in" = dropping in, "normal", "out" = saying bye
        self.anim = 0

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-transparentcolor", KEY)  # Windows only
        except tk.TclError:
            pass
        self.root.configure(bg=KEY)
        self.label = tk.Label(self.root, image=self.images["hi"], bg=KEY, bd=0, highlightthickness=0)
        self.label.pack()

        self.x = self.root.winfo_screenwidth() - self.gw - 60
        self.y_base = self.root.winfo_screenheight() - self.gh - 140
        self.root.geometry("+%d+%d" % (self.x, self.y_base))

        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="Send Casperr home", command=self.quit)
        self.label.bind("<Button-1>", lambda e: self.toggle_bubble())
        self.label.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.set_alpha(0.0)  # start invisible, then drop in
        self.tick()
        self.poll()

    # ------------------------------------------------------------ messages
    def set_alpha(self, a):
        if os.environ.get("GHOST_NOFADE"):  # escape hatch if fading ever misbehaves on your PC
            return
        try:
            self.root.attributes("-alpha", max(0.0, min(1.0, a)))
        except tk.TclError:
            pass

    def poll(self):
        while True:
            try:
                data, _addr = self.sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            self.handle(data)
        self.drain_ai()
        self.root.after(100, self.poll)

    def drain_ai(self):
        """Pick up finished AI answers from background threads."""
        while True:
            try:
                line, text = self.ai_queue.get_nowait()
            except queue.Empty:
                break
            if text:
                self.ai_cache[line] = text
            else:
                _log("AI gave no answer: " + ghost_ai.last_error)
            if line == self.cur_line:  # ignore answers for an older command
                self.ai_pending = False
                self.ai_text = text or ""
                self.update_body()
                if self.bubble is not None:
                    self.refresh_bubble()

    def update_body(self):
        body = self.base_body
        if self.ai_text:
            body += "\n\nCasper says:\n" + self.ai_text
        elif self.ai_pending:
            body += "\n\nCasper is thinking..."
        self.body = body

    def handle(self, data):
        if self.mode == "out":
            return
        text = data.decode("utf-8", "replace")
        msg = {"line": text}
        if text.lstrip().startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    msg = parsed
            except ValueError:
                pass
        if msg.get("cmd") == "quit":
            self.quit()
            return
        line = str(msg.get("line", ""))[:2000]
        cwd = str(msg.get("cwd") or os.getcwd())
        verdict, facts, body = analyse(line, cwd)
        self.state = verdict.colour
        self.title = pick_title(self.state)  # one random line per verdict
        self.base_body = body
        self.cur_line = line
        self.ai_text = ""
        self.ai_pending = False
        # The rules already chose the colour. The AI only adds a friendly explanation.
        if verdict.colour != "idle" and ghost_ai.get_settings() is not None:
            if line in self.ai_cache:
                self.ai_text = self.ai_cache[line]
            else:
                self.ai_pending = True
                ghost_ai.ask_ai_in_background(
                    line, verdict.colour, verdict.reasons, facts, self.ai_queue)
        self.update_body()
        self.label.configure(image=self.images[self.state])
        self.hop = 15  # a little hop so you notice the new verdict
        if self.bubble is not None:
            self.refresh_bubble()

    # ------------------------------------------------------------- bubble
    def toggle_bubble(self):
        if self.bubble is None:
            self.open_bubble()
        else:
            self.close_bubble()

    def open_bubble(self):
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        self.bubble = b
        self.frame = tk.Frame(b, padx=3, pady=3)
        self.frame.pack()
        self.title_lbl = tk.Label(self.frame, fg="white", font=("Segoe UI", 11, "bold"),
                                  anchor="w", justify="left", padx=10, pady=5, wraplength=340)
        self.title_lbl.pack(fill="x")
        self.body_lbl = tk.Label(self.frame, bg="#fffdf5", fg="#222222", font=("Segoe UI", 10),
                                 anchor="w", justify="left", padx=10, pady=8, wraplength=340)
        self.body_lbl.pack(fill="x")
        for w in (b, self.frame, self.title_lbl, self.body_lbl):
            w.bind("<Button-1>", lambda e: self.close_bubble())
        self.refresh_bubble()

    def refresh_bubble(self):
        colour = COLOURS[self.state]
        self.frame.configure(bg=colour)
        self.title_lbl.configure(bg=colour, text=self.title)
        self.body_lbl.configure(text=self.body)
        self.place_bubble()

    def place_bubble(self):
        b = self.bubble
        if b is None:
            return
        b.update_idletasks()
        bw, bh = b.winfo_reqwidth(), b.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        x = min(max(0, self.x + self.gw // 2 - bw // 2), max(0, sw - bw))
        y = self.y_base - bh - 6
        if y < 0:
            y = self.y_base + self.gh + 6
        b.geometry("+%d+%d" % (x, y))

    def close_bubble(self):
        if self.bubble is not None:
            self.bubble.destroy()
            self.bubble = None

    # ---------------------------------------------------------- animation
    def tick(self):
        speed, amp, wobble = MOTION.get(self.state, MOTION["idle"])
        self.t += speed
        lift = 0
        if self.hop > 0:
            lift = int(18 * math.sin(self.hop / 15.0 * math.pi))
            self.hop -= 1
        y = self.y_base + amp * math.sin(self.t) - lift
        x = self.x + wobble * math.sin(self.t * 2.7)
        alpha = None
        if self.mode == "in":  # drops in from above, fading in, and settles
            self.anim += 1
            p = min(1.0, self.anim / float(IN_FRAMES))
            y -= (1.0 - ease_out_back(p)) * DROP
            alpha = min(1.0, p * 2.0)
            if p >= 1.0:
                self.mode = "normal"
                alpha = 1.0
        elif self.mode == "out":  # exactly the reverse: dips, then rises away, fading out
            self.anim += 1
            p = min(1.0, self.anim / float(OUT_FRAMES))
            y -= (1.0 - ease_out_back(1.0 - p)) * DROP
            alpha = 1.0 - p
            if p >= 1.0:
                self.root.destroy()
                return
        if alpha is not None:
            self.set_alpha(alpha)
        self.root.geometry("+%d+%d" % (int(x), int(y)))
        self.root.after(40, self.tick)

    # --------------------------------------------------------------- exit
    def quit(self):
        """Say bye (animation), then the window closes itself at the end of tick()."""
        if self.mode == "out":
            return
        self.mode = "out"
        self.anim = 0
        self.close_bubble()
        self.label.configure(image=self.images["bye"])
        try:
            self.sock.close()  # free the port right away
        except OSError:
            pass

    def run(self):
        print("Ghost is awake. Click it for the bubble, right-click it to quit.")
        print("Test from another terminal:  python ghost_send.py \"Remove-Item .\\old -Recurse\"")
        self.root.mainloop()
        print("Ghost closed.")


if __name__ == "__main__":
    try:
        Ghost().run()
    except SystemExit:
        raise
    except Exception:
        _log(traceback.format_exc())
        raise