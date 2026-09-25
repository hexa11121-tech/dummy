"""Background job runner: keeps the Tk UI responsive during decompiles/parses."""
from __future__ import annotations

import queue
import threading
import traceback
from typing import Any, Callable, Optional


class JobRunner:
    """Single-worker job queue with line-level progress callbacks.

    The GUI polls :meth:`poll` from ``root.after``; everything else happens on
    the worker thread. Messages are tuples:

    ``("log", text)``          - a log line
    ``("done", result)``       - job finished OK (result is job's return value)
    ``("error", text)``        - job raised
    ``("cancelled", None)``    - job was cancelled
    """

    def __init__(self) -> None:
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False
        self._cancel: Optional[Callable[[], None]] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def busy(self) -> bool:
        return self._busy

    def submit(self, fn: Callable[[Callable[[str], None]], Any],
               on_cancel: Optional[Callable[[], None]] = None) -> bool:
        """``fn(sink)`` runs on the worker; ``sink(str)`` emits log lines."""
        if self._busy:
            return False
        self._busy = True
        self._cancel = on_cancel

        def work() -> None:
            try:
                result = fn(self._log)
                self._q.put(("done", result))
            except Exception as e:  # noqa: BLE001 - surface any error to UI
                self._log(traceback.format_exc())
                self._q.put(("error", str(e)))
            finally:
                self._busy = False

        self._thread = threading.Thread(target=work, name="apkdeco-job", daemon=True)
        self._thread.start()
        return True

    def cancel(self) -> None:
        if self._cancel is not None:
            try:
                self._cancel()
                self._q.put(("cancelled", None))
            except Exception:
                pass

    def _log(self, text: str) -> None:
        self._q.put(("log", text))

    def poll(self) -> list:
        """Drain pending messages (call from a Tk ``after`` loop)."""
        out = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                return out
