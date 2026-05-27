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

# Update the live token counter at most this often (seconds) to avoid
# flickering on fast local models.
_STREAM_REFRESH_INTERVAL = 0.1


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

        # Streaming token counter state
        self._stream_label = ""
        self._stream_chars = 0
        self._stream_started_at: Optional[float] = None
        self._stream_last_render = 0.0

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

    def note(self, message: str, indent: str = "    "):
        """Print an informational note aligned with the current phase/task output."""
        self.spinner_stop()
        print(f"{indent}{message}")

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

    def task_done(self, name: str, files: list[str] = None, usage: dict | None = None):
        """Stop the spinner and print a completed task line."""
        self.spinner_stop()
        elapsed = self._task_elapsed(name)
        print(f"    [+] {name}{elapsed}")
        if usage:
            print(f"        usage: {format_usage_summary(usage)}")
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
    # Streaming token counter
    # ------------------------------------------------------------------

    def stream_start(self, label: str):
        """Begin a live token counter under *label*.

        Replaces any active spinner. On non-TTY, prints the label once and
        suppresses per-chunk updates.
        """
        self.spinner_stop()
        self._stream_label = label
        self._stream_chars = 0
        self._stream_started_at = time.monotonic()
        self._stream_last_render = 0.0
        if not self._is_tty:
            print(label, flush=True)
            return
        self._render_stream_line()

    def stream_chunk(self, text: str):
        """Record a streamed chunk and re-render the counter (TTY only)."""
        if not text or self._stream_started_at is None:
            return
        self._stream_chars += len(text)
        if not self._is_tty:
            return
        now = time.monotonic()
        if now - self._stream_last_render < _STREAM_REFRESH_INTERVAL:
            return
        self._stream_last_render = now
        self._render_stream_line()

    def stream_stop(self):
        """Clear the streaming line and emit a final summary."""
        if self._stream_started_at is None:
            return
        elapsed = time.monotonic() - self._stream_started_at
        chars = self._stream_chars
        # Rough token estimate (4 chars/token) for a more familiar unit
        tokens = max(1, chars // 4) if chars else 0
        if self._is_tty:
            sys.stdout.write("\r" + " " * (len(self._stream_label) + 40) + "\r")
            sys.stdout.flush()
        if tokens:
            print(f"    {self._stream_label}: ~{tokens} tokens in {elapsed:.1f}s")
        self._stream_label = ""
        self._stream_chars = 0
        self._stream_started_at = None

    def _render_stream_line(self):
        if self._stream_started_at is None:
            return
        elapsed = time.monotonic() - self._stream_started_at
        tokens = max(1, self._stream_chars // 4) if self._stream_chars else 0
        with self._spinner_lock:
            sys.stdout.write(f"\r{self._stream_label}: ~{tokens} tok ({elapsed:.1f}s)   ")
            sys.stdout.flush()

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
    if "out of memory" in err_lower or "cannot allocate" in err_lower:
        return "Model ran out of memory — try a smaller model (e.g. qwen2.5:3b)"
    if "not installed" in err_lower or "model not found" in err_lower:
        return "Run `ollama pull <model>` or pick another with `forge doctor`"
    if "context length" in err_lower or "maximum context" in err_lower:
        return "Prompt too large — try `forge build --feature` or a larger-context model"
    if "model is loading" in err_lower or "loading model" in err_lower:
        return "Ollama is still loading the model — give it ~30s and retry"
    if "connection refused" in err_lower:
        return "Local server unreachable — is Ollama running? (`ollama serve`)"
    if "token" in err_lower and ("limit" in err_lower or "exceed" in err_lower):
        return "Try `forge build --feature` to build incrementally"
    if "rate limit" in err_lower or "429" in err_lower:
        return "Provider rate limit hit — wait a moment and retry"
    if "api key" in err_lower or "unauthorized" in err_lower or "401" in err_lower:
        return "Check your API key with `forge config show`"
    if "connection" in err_lower or "timeout" in err_lower:
        return "Network issue — check your connection and retry"
    return ""


def format_usage_summary(usage: dict) -> str:
    """Format provider usage into a compact human-readable line."""
    if not usage:
        return "no usage data"

    parts: list[str] = []
    prompt_tokens = usage.get("prompt_eval_count")
    completion_tokens = usage.get("eval_count")
    if prompt_tokens is not None or completion_tokens is not None:
        left = f"prompt {prompt_tokens}" if prompt_tokens is not None else None
        right = f"completion {completion_tokens}" if completion_tokens is not None else None
        token_bits = [item for item in (left, right) if item]
        if token_bits:
            parts.append(", ".join(token_bits) + " tok")

    total_duration = usage.get("total_duration")
    load_duration = usage.get("load_duration")
    eval_duration = usage.get("eval_duration")
    duration_bits: list[str] = []
    if total_duration is not None:
        duration_bits.append(f"total {_format_ns(total_duration)}")
    if load_duration is not None:
        duration_bits.append(f"load {_format_ns(load_duration)}")
    if eval_duration is not None:
        duration_bits.append(f"eval {_format_ns(eval_duration)}")
    if duration_bits:
        parts.append(", ".join(duration_bits))

    size_vram = usage.get("size_vram_bytes")
    size_total = usage.get("size_bytes")
    memory_bits: list[str] = []
    if size_vram is not None:
        memory_bits.append(f"vram {_format_bytes(size_vram)}")
    if size_total is not None:
        memory_bits.append(f"model {_format_bytes(size_total)}")
    processor = usage.get("processor")
    if processor:
        memory_bits.append(str(processor))
    if memory_bits:
        parts.append(", ".join(memory_bits))

    return " | ".join(parts) if parts else "no usage data"


def _format_ns(value: int | float) -> str:
    seconds = float(value) / 1_000_000_000
    if seconds >= 60:
        return f"{seconds / 60:.1f}m"
    if seconds >= 1:
        return f"{seconds:.1f}s"
    return f"{seconds * 1000:.0f}ms"


def _format_bytes(value: int | float) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"
