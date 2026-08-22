"""Drives `run_repl` against a stub `ChatPort`, so the REPL's input layer can
be exercised without an API key and without spending tokens on arrow keys.

Two modes:

    uv run python -m lib.repl.stubbed_chat_smoke_test
        An interactive echo REPL. Type, press up-arrow, move the cursor,
        delete a word - whatever the input layer is meant to do, do it by
        hand and watch.

    uv run python -m lib.repl.stubbed_chat_smoke_test --check
        Self-driving. Forks a pty, types a line, recalls it with the up
        arrow, and exits non-zero if the recall did not come back.

`--check` needs a pty because readline steps aside entirely when stdin is not
a terminal - piping lines into the REPL exercises none of this and would pass
whether or not `lib/repl/repl.py` still imports `readline`.
"""

import asyncio
import os
import pty
import sys
import time
from typing import Optional

from lib.ai_generation import MessageList

from .repl import run_repl

# Sent to the child: type a line, then recall it with the up arrow and submit
# it again without retyping. If readline is not driving input(), the escape
# sequence arrives as literal bytes and the second turn echoes "\x1b[A"
# instead of the recalled line.
LINE = "hola"
UP_ARROW = b"\x1b[A"
CTRL_D = b"\x04"


class EchoChat:
    """A `ChatPort` that answers from inside the process."""

    async def send(self, messages: MessageList) -> str:
        return f"echo: {messages[-1]['content']}"


def _read_until(fd: int, needle: bytes, timeout: float, seen: bytes = b"") -> bytes:
    """Accumulates pty output until `needle` shows up or `timeout` expires.
    Returns everything read so far either way - the caller decides whether a
    missing needle is a failure."""
    os.set_blocking(fd, False)
    deadline = time.monotonic() + timeout

    while needle not in seen and time.monotonic() < deadline:
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            time.sleep(0.02)
            continue
        except OSError:  # child closed its end
            break
        if not chunk:
            break
        seen += chunk

    return seen


def check() -> int:
    """Runs the REPL under a pty and reports whether history recall works."""
    pid, fd = pty.fork()

    if pid == 0:
        # The child is this same module, re-executed in interactive mode so
        # that input() binds to the pty rather than to whatever stdin the
        # parent was started with.
        os.execv(sys.executable, [sys.executable, "-m", __spec__.name])

    output = _read_until(fd, b"Ready", timeout=15)

    os.write(fd, f"{LINE}\n".encode())
    output = _read_until(fd, f"echo: {LINE}".encode(), timeout=5, seen=output)

    os.write(fd, UP_ARROW + b"\n")
    output = _read_until(fd, f"echo: {LINE}".encode() * 2, timeout=5, seen=output)

    os.write(fd, CTRL_D)
    output = _read_until(fd, b"Exciting", timeout=5, seen=output)

    # Reap the child before closing the master end: closing it first hangs up
    # the pty and the child dies of SIGHUP instead of exiting on its own.
    _, status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(status)
    os.close(fd)

    transcript = output.decode(errors="replace")
    recalls = transcript.count(f"echo: {LINE}")

    print(transcript, end="" if transcript.endswith("\n") else "\n")
    print("--- lib/repl/stubbed_chat_smoke_test --check")

    failures: list[str] = []
    if recalls < 2:
        failures.append(
            f"history recall: expected 2 '{LINE}' turns, got {recalls}. The up "
            "arrow did not bring the previous line back - has the readline "
            "import been dropped from lib/repl/repl.py?"
        )
    if exit_code != 0:
        failures.append(f"child exited with code {exit_code}, expected 0")

    for failure in failures:
        print(f"    FAIL  {failure}")
    if failures:
        return 1

    print("    PASS  history recall (readline is driving input())")
    return 0


def interactive() -> None:
    asyncio.run(run_repl(EchoChat()))


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--check" in argv:
        return check()

    interactive()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
