"""
ghost_send.py - send one line to the running ghost (for testing, and later the
PowerShell Alt+G hook will do the same thing).

It only sends a short text message to 127.0.0.1 (your own computer). It does
not run the command, and if no ghost is running it silently does nothing.

    python ghost_send.py "Remove-Item .\\old -Recurse"
    python ghost_send.py --quit        <- asks the ghost to close
"""
import json
import os
import socket
import sys

PORT = int(os.environ.get("GHOST_PORT", "47321"))


def send(payload: dict) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(json.dumps(payload).encode("utf-8"), ("127.0.0.1", PORT))
    finally:
        s.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--quit"]:
        send({"cmd": "quit"})
    else:
        send({"line": " ".join(args), "cwd": os.getcwd()})
