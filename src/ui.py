"""Terminal progress UI for Forge builds.

Provides phase headers, animated spinner, per-task todo list,
and a build summary — with graceful fallback for non-TTY output.
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional


_DIVIDER = "─" * 51


class BuildUI:
    """Terminal feedback for the build pipeline.

    Non-TTY safe: spinner animation is disabled when stdout is not a terminal.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._is_tty = sys.stdout.isatty()
        self._phase_start_time: Optional[float] = None
        self._task_start_times: dict[str, float] = {}

        # Spinner state
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_stop_event = threading.Event()
        self._spinner_label = ""
        self._spinner_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Phase helpers
    # ------------------------------------------------------------------

    def phase_start(self, label: str):
        """Print a phase divider + header."""
        self._phase_start_time = time.monotonic()
        print(_DIVIDER)
        print(f"  {label}")

    def phase_end(self, label: str):
        """Print the phase completion line with elapsed time."""
        elapsed = ""
        if self._phase_start_time is not None:
            secs = time.monotonic() - self._phase_start_time
            elapsed = f"  ({secs:.1f}s)"
            self._phase_start_time = None
        print(f"  {label}{elapsed}")
        print("")

    # ------------------------------------------------------------------
    # Task list
    # ------------------------------------------------------------------

    def set_tasks(self, names: list[str]):
        """Print an initial todo list for all tasks."""
        print("  Tasks:")
        for name in names:
            print(f"    [ ] {name}")
        print("")

    def task_start(self, name: str):
        """Mark a task as in-progress and start the spinner."""
        self._task_start_times[name] = time.monotonic()
        self.spinner_start(f"    [>] {name}")

    def task_done(self, name: str, files: list[str] = None):
        """Stop the spinner and print a completed task line."""
        self.spinner_stop()
        elapsed = self._task_elapsed(name)
        print(f"    [+] {name}{elapsed}")
        for f in (files or []):
            print(f"        + {f}")

    def task_error(self, name: str, error: str):
        """Stop the spinner and print a failed task line with an actionable hint."""
        self.spinner_stop()
        elapsed = self._task_elapsed(name)
        print(f"    [X] {name}{elapsed}")
        hint = _error_hint(error)
        print(f"        Error: {error}")
        if hint:
            print(f"        Hint:  {hint}")

    def _task_elapsed(self, name: str) -> str:
        start = self._task_start_times.pop(name, None)
        if start is None:
            return ""
        secs = time.monotonic() - start
        return f"  ({secs:.1f}s)"

    # ------------------------------------------------------------------
    # Generic spinner
    # ------------------------------------------------------------------

    def spinner_start(self, label: str):
        """Start an animated spinner with *label* (no-op on non-TTY)."""
        self.spinner_stop()  # stop any previous spinner
        self._spinner_label = label
        self._spinner_stop_event.clear()

        if self._is_tty:
            self._spinner_thread = threading.Thread(
                target=self._spin_loop, daemon=True
            )
            self._spinner_thread.start()
        else:
            # Non-TTY: just print the label once
            print(label, flush=True)

    def spinner_stop(self):
        """Stop the spinner and clear its line (no-op if not running)."""
        if self._spinner_thread is not None:
            self._spinner_stop_event.set()
            self._spinner_thread.join(timeout=1.0)
            self._spinner_thread = None
            if self._is_tty:
                # Clear the spinner line
                with self._spinner_lock:
                    sys.stdout.write("\r" + " " * (len(self._spinner_label) + 8) + "\r")
                    sys.stdout.flush()

    def _spin_loop(self):
        frames = [".", "..", "..."]
        i = 0
        while not self._spinner_stop_event.is_set():
            with self._spinner_lock:
                frame = frames[i % len(frames)]
                sys.stdout.write(f"\r{self._spinner_label} {frame}   ")
                sys.stdout.flush()
            i += 1
            self._spinner_stop_event.wait(timeout=0.4)

    # ------------------------------------------------------------------
    # Build summary
    # ------------------------------------------------------------------

    def build_summary(self, files: list[str], errors: list[str], start_time: float):
        """Print the final build summary with file counts and next steps."""
        elapsed = time.monotonic() - start_time
        print(_DIVIDER)
        print(f"  Build complete  ({elapsed:.1f}s)")
        print("")

        if files:
            # Count by extension
            counts: dict[str, int] = {}
            for f in files:
                ext = Path(f).suffix.lower()
                label = _ext_label(ext)
                counts[label] = counts.get(label, 0) + 1

            print(f"  Files created: {len(files)}")
            for label, n in sorted(counts.items(), key=lambda x: -x[1]):
                print(f"    {label:<10} {n}")
            print("")

        if errors:
            print(f"  Errors: {len(errors)}")
            for e in errors[:3]:
                print(f"    - {e}")
            if len(errors) > 3:
                print(f"    ... and {len(errors) - 3} more")
            print("")

        print("  Next steps:")
        print("    forge dev                         # run locally")
        print('    forge build --feature "add auth"  # add a feature')
        print(_DIVIDER)
        print("")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _ext_label(ext: str) -> str:
    mapping = {
        ".py": "Python",
        ".js": "JS/JSX",
        ".jsx": "JS/JSX",
        ".ts": "TS/TSX",
        ".tsx": "TS/TSX",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "Config",
        ".yaml": "Config",
        ".yml": "Config",
        ".toml": "Config",
        ".env": "Config",
        ".md": "Docs",
        ".sh": "Shell",
        ".dockerfile": "Docker",
    }
    if ext == "" or ext not in mapping:
        # Check for files like Dockerfile (no extension)
        return "Other"
    return mapping[ext]


def _error_hint(error: str) -> str:
    """Return a short actionable hint based on common error patterns."""
    err_lower = error.lower()
    if "token" in err_lower and ("limit" in err_lower or "exceed" in err_lower):
        return "Try `forge build --feature` to build incrementally"
    if "rate limit" in err_lower or "429" in err_lower:
        return "Provider rate limit hit — wait a moment and retry"
    if "api key" in err_lower or "unauthorized" in err_lower or "401" in err_lower:
        return "Check your API key with `forge config show`"
    if "connection" in err_lower or "timeout" in err_lower:
        return "Network issue — check your connection and retry"
    return ""
