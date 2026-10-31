"""
Ghost art test - read-only, installs nothing, creates no files.

Uses only tkinter, which already ships with your Python (it reads PNG and GIF).

Put this script in the SAME folder as your ghost images, for example
D:\\ghost\\art  (copy the images there, keep your originals untouched).

Usage (PowerShell):
    cd D:\\ghost\\art
    python test_ghost_window.py                      <- lists the images it finds
    python test_ghost_window.py "my_ghost_file.png"  <- opens that image
    python test_ghost_window.py "my_ghost_file.png" fix

What you should see: ONLY the ghost floating on your screen (bobbing up and
down), with your desktop visible around it. Click it or press Esc to close.
It also closes by itself after 20 seconds, so it can never get stuck.

If you see a coloured/grey box around the ghost, the background is baked into
the file. Run again with the word "fix" at the end: it then treats the colour
of the top-left pixel as see-through (no extra install needed).
"""
import math
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
EXTS = (".png", ".gif")

# --- no file given: just list the images sitting next to this script ---------
if len(sys.argv) < 2:
    found = sorted(f for f in os.listdir(HERE) if f.lower().endswith(EXTS))
    print(f"Looking in: {HERE}")
    if not found:
        print("No .png or .gif files here. Copy your ghost images into this folder.")
    else:
        print("Images found:")
        for f in found:
            print(f'  python test_ghost_window.py "{f}"')
    sys.exit(0)

name = sys.argv[1]
path = name if os.path.isabs(name) else os.path.join(HERE, name)
use_fix = len(sys.argv) > 2 and sys.argv[2].lower() == "fix"

if not os.path.isfile(path):
    print(f"Can't find: {path}")
    print("Run the script with no file name to see what is in this folder.")
    sys.exit(1)
if not path.lower().endswith(EXTS):
    print("Please give a .png or .gif file.")
    sys.exit(1)

root = tk.Tk()
img = tk.PhotoImage(file=path)  # read only; tkinter handles PNG and GIF itself
w, h = img.width(), img.height()
corner_is_transparent = img.transparency_get(0, 0)
r, g, b = img.get(0, 0)

print(f"File: {path}")
print(f"Size: {w} x {h}  (should be 95 x 95)")
print(f"Top-left pixel transparent? {corner_is_transparent}")
if not corner_is_transparent:
    print(f"Top-left pixel colour is rgb({r},{g},{b}) -> the background is baked in.")
    print(f'Try again with:  python test_ghost_window.py "{name}" fix')

# A colour that is not used in the ghost; Windows treats it as see-through.
KEY = "#ff00ff"
if use_fix and not corner_is_transparent:
    KEY = "#%02x%02x%02x" % (r, g, b)
    print(f"Using the corner colour {KEY} as the see-through colour.")

big = img.zoom(2)  # 2x bigger, no blur (pixel art stays crisp)

root.overrideredirect(True)           # no title bar or border
root.attributes("-topmost", True)     # stay above other windows
root.attributes("-transparentcolor", KEY)
root.configure(bg=KEY)

label = tk.Label(root, image=big, bg=KEY, bd=0, highlightthickness=0)
label.image = big  # keep a reference so it is not garbage-collected
label.pack()

x = root.winfo_screenwidth() - big.width() - 60
y_base = root.winfo_screenheight() - big.height() - 140


def bob(t=0.0):
    y = int(y_base + 8 * math.sin(t))
    root.geometry(f"+{x}+{y}")
    root.after(40, bob, t + 0.15)


root.bind("<Button-1>", lambda e: root.destroy())
root.bind("<Escape>", lambda e: root.destroy())
root.after(20000, root.destroy)  # safety: closes itself after 20 seconds
bob()
root.mainloop()
print("Closed.")