"""
RUTE Backend Entry Point — spawned by tray_app.py

This is the lightweight wrapper that the tray app launches as a subprocess.
It mirrors what start_backend.bat does, minus the pip install step.

Key decisions:
  - Hardcodes port 8001 (matches main.py, START_RUTE_BACKEND.bat, and the extension)
  - Binds to 127.0.0.1 (localhost only — prevents LAN exposure)
  - Sets working directory to D:\\RUTE\\backend (required for relative imports)

Graceful shutdown: the tray cannot deliver console signals to this process —
GenerateConsoleCtrlEvent only reaches processes sharing the CALLER's console,
and the child has its own (hidden) console. So instead the tray drops a
stop-signal flag file, and a watcher thread here self-signals CTRL_BREAK to
its own console group. uvicorn registers SIGBREAK on Windows
(uvicorn.server.HANDLED_SIGNALS) and performs its normal graceful shutdown.
"""

import os
import sys
import time
import ctypes
import threading
from pathlib import Path

# Set working directory to backend root (mirrors start_backend.bat's "cd /d D:\\RUTE\\backend")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BACKEND_DIR)

# Ensure the backend directory is on the Python path
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

STOP_FLAG = Path(BACKEND_DIR) / "logs" / "stop_signal.flag"
LOCK_FILE = Path(BACKEND_DIR) / "logs" / "backend.lock"


def _acquire_backend_lock() -> bool:
    """
    Atomic single-instance guard for the backend role.

    On this machine every pythonw launch and every python.exe launch with a
    new console gets duplicated by a system-level process-spawner (observed
    for every script, ~80ms-2s after creation). The duplicate carries the
    same command line, so without a guard every backend spawn races the port
    and wastes a 2.5-minute ML import before dying. The lock lets the first
    arrival win and makes any duplicate exit before importing anything.
    """
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        # Stale lock? If the recorded PID is gone, steal the lock.
        try:
            stale_pid = int(LOCK_FILE.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            # Garbage/partial content (crash mid-write) — treat as stale and retry.
            try:
                LOCK_FILE.unlink()
            except OSError:
                pass
            return _acquire_backend_lock()
        try:
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(
                0x1000, False, stale_pid  # PROCESS_QUERY_LIMITED_INFORMATION
            )
            if not handle:
                err = ctypes.get_last_error()
                if err in (87, 161):  # ERROR_INVALID_PARAMETER / ERROR_BAD_EXE_FORMAT
                    LOCK_FILE.unlink(missing_ok=True)
                    return _acquire_backend_lock()
                return False
            kernel32.CloseHandle(handle)
            return False  # recorded PID is alive — a sibling owns the role
        except Exception:
            return False
    except OSError:
        return True  # filesystem trouble — proceed rather than hard-fail


def _release_backend_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except OSError:
        pass


def _watch_stop_flag() -> None:
    """Poll for the tray's stop flag; on sight, self-signal CTRL_BREAK."""
    while True:
        try:
            if STOP_FLAG.exists():
                try:
                    STOP_FLAG.unlink()
                except OSError:
                    pass
                # CTRL_BREAK_EVENT (1) to our own console group (0 = all in group).
                ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, 0)
                return
        except Exception:
            pass
        time.sleep(1)


if __name__ == "__main__":
    # Single-instance guard FIRST — a duplicate (see _acquire_backend_lock)
    # must exit before importing uvicorn/main, not after a 2.5-min ML import.
    if not _acquire_backend_lock():
        sys.exit(0)

    # Start the watcher BEFORE uvicorn.run so it is alive during the long
    # main.py import (torch/xgboost take ~2.5 min; stopping mid-import should
    # still terminate the process promptly).
    threading.Thread(target=_watch_stop_flag, daemon=True).start()

    import uvicorn

    try:
        uvicorn.run(
            "main:app",
            host="127.0.0.1",   # Localhost only — no LAN exposure
            port=8001,           # Matches hardcoded port across the entire stack
            log_level="info",
            timeout_graceful_shutdown=5,  # Bound the wait on open WS connections
        )
    finally:
        _release_backend_lock()