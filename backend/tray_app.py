r"""
RUTE Backend Launcher & Watchdog — System Tray Application

Spawns the backend as a subprocess, monitors health, and restarts on failure.
All files stay inside D:\RUTE\backend. No keyring, no /api/shutdown, no bundling.

Shutdown is graceful: the tray drops a stop-signal flag file and the backend
subprocess self-signals CTRL_BREAK (uvicorn treats it as a clean exit). An
HTTP shutdown endpoint would be reachable by any browser tab on localhost
(localhost CSRF), which is a real attack surface for a trading tool.
"""

import os
import sys
import time
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths — everything lives inside D:\RUTE\backend
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent  # D:\RUTE\backend
VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
RUN_BACKEND = BACKEND_DIR / "run_backend.py"
LOG_DIR = BACKEND_DIR / "logs"
ENV_FILE = BACKEND_DIR / ".env"

# Ensure log directory exists
LOG_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_handler = RotatingFileHandler(
    LOG_DIR / "tray_app.log", maxBytes=2 * 1024 * 1024, backupCount=3
)
log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
))
logger = logging.getLogger("rute_tray")
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(logging.StreamHandler())  # Also print to console

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv(ENV_FILE)

HEALTH_URL = "http://127.0.0.1:8001/api/health"
HEALTH_POLL_INTERVAL = 30       # seconds
BOOT_GRACE_PERIOD = 180         # 3 minutes for ML ensemble to load
FAILURE_THRESHOLD = 3           # consecutive health failures before restart
MAX_RESTARTS = 3                # per cooldown window
RESTART_COOLDOWN = 1800         # 30-minute window for restart cap

MT5_ENABLED = os.environ.get("RUTE_MT5_ENABLED", "0") == "1"
MT5_TERMINAL_PATH = os.environ.get(
    "MT5_TERMINAL_PATH",
    r"C:\Program Files\MetaTrader 5\terminal64.exe"
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
backend_process = None
backend_log_handle = None
is_running = False
lock = threading.Lock()  # Protects backend_process mutations

# Restart tracking
restart_timestamps: list[datetime] = []

# ---------------------------------------------------------------------------
# Icon generation (simple colored square — no external .ico dependency)
# ---------------------------------------------------------------------------
def _make_icon(color: str = "green"):
    """Generate a tiny tray icon in-memory. No file dependency."""
    from PIL import Image, ImageDraw
    colors = {"green": "#22c55e", "yellow": "#eab308", "red": "#ef4444", "grey": "#6b7280"}
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=colors.get(color, color))
    # R letter
    draw.text((20, 14), "R", fill="white")
    return img


# ---------------------------------------------------------------------------
# Single-instance guard — Windows named mutex
# ---------------------------------------------------------------------------
_mutex_handle = None


def _single_instance() -> bool:
    """
    Ensure only one tray instance runs. Returns True if this process acquired
    the mutex (i.e. it is the first instance). The handle is kept in a module
    global so it is not garbage-collected; the OS releases it on process exit.
    """
    global _mutex_handle
    try:
        import ctypes
        # use_last_error=True is REQUIRED here: without it, ctypes' call
        # machinery can clobber the thread's last-error value between
        # CreateMutexW and GetLastError, so a second instance would see 0
        # and wrongly proceed (observed in testing).
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, "Local\\RUTE_Tray_Mutex")
        if not handle:
            logger.error("Failed to create instance mutex.")
            return False
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            logger.warning("Another RUTE tray instance is already running — exiting.")
            return False
        _mutex_handle = handle
        return True
    except Exception as e:
        logger.error(f"Single-instance check failed ({e}) — continuing anyway.")
        return True


# ---------------------------------------------------------------------------
# MT5 Terminal Management
# ---------------------------------------------------------------------------
def _ensure_mt5_running():
    """Launch MT5 terminal if RUTE_MT5_ENABLED=1 and it's not already running.

    Uses SW_SHOWMINNOACTIVE (wShowWindow=7) so the terminal opens straight to
    the taskbar — it never flashes on top and never steals focus. SW_HIDE (0)
    is intentionally avoided: some Win32 builds of MT5 assume they always have
    a visible window surface and stall the price feed when fully hidden.
    """
    if not MT5_ENABLED:
        return

    import psutil
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"] and "terminal64" in proc.info["name"].lower():
            logger.info("MT5 terminal already running.")
            return

    if os.path.exists(MT5_TERMINAL_PATH):
        logger.info(f"Launching MT5 terminal minimized: {MT5_TERMINAL_PATH}")
        # SW_SHOWMINNOACTIVE = 7 — minimized to taskbar, no focus steal, no flash
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        subprocess.Popen(
            [MT5_TERMINAL_PATH],
            startupinfo=si,
            creationflags=subprocess.DETACHED_PROCESS,
        )
        time.sleep(5)  # Give MT5 a moment to initialize
    else:
        logger.warning(f"MT5 terminal not found at: {MT5_TERMINAL_PATH}")


# ---------------------------------------------------------------------------
# Backend Process Management
# ---------------------------------------------------------------------------
def _backend_healthy() -> bool:
    """True when something answers /api/health on :8001."""
    try:
        resp = requests.get(HEALTH_URL, timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def start_backend():
    """Spawn the backend as a subprocess."""
    global backend_process, backend_log_handle

    with lock:
        if backend_process and backend_process.poll() is None:
            # The tracked PID may be the OS-duplication DECOY (idle no-op that
            # never exits) while the real backend is dead — so "PID alive" is
            # NOT proof the backend runs. Health is the only truth.
            if _backend_healthy():
                logger.info("Backend already running.")
                return
            logger.warning(
                f"Tracked backend PID {backend_process.pid} is alive but the "
                "backend is unhealthy — killing the stale process and respawning."
            )
            try:
                backend_process.terminate()
            except OSError:
                pass
            backend_process = None

        # Pre-spawn check: if something already answers on :8001, adopt it
        # instead of spawning a duplicate (which would die with "address in
        # use" and trip the watchdog into a restart loop).
        try:
            resp = requests.get(HEALTH_URL, timeout=3)
            if resp.status_code == 200:
                logger.info("Backend already healthy at %s — adopting it (not spawning).", HEALTH_URL)
                return
        except requests.RequestException:
            pass

        # Ensure MT5 is up first (if enabled)
        _ensure_mt5_running()

        # Clear any stale stop flag from a previous run
        try:
            (LOG_DIR / "stop_signal.flag").unlink(missing_ok=True)
        except OSError:
            pass

        # Open log file for backend stdout/stderr
        backend_log_handle = open(LOG_DIR / "backend.log", "a", encoding="utf-8")

        cmd = [str(VENV_PYTHON), str(RUN_BACKEND)]
        logger.info(f"Starting backend: {' '.join(cmd)}")

        # Spawn with its OWN hidden console + new process group. The console is
        # required for CTRL_BREAK_EVENT to be deliverable (CREATE_NO_WINDOW
        # leaves the child console-less and os.kill(SIGBREAK) fails with
        # WinError 6, forcing every stop into the force-kill fallback).
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = subprocess.SW_HIDE
        backend_process = subprocess.Popen(
            cmd,
            cwd=str(BACKEND_DIR),
            stdout=backend_log_handle,
            stderr=subprocess.STDOUT,
            startupinfo=startup_info,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE,
        )
        logger.info(f"Backend started (PID: {backend_process.pid})")


def stop_backend(wait: bool = True):
    """
    Gracefully stop the backend.

    The backend subprocess has its OWN console, so the tray cannot deliver
    console signals to it directly (GenerateConsoleCtrlEvent only reaches
    processes sharing the caller's console — the earlier os.kill(SIGBREAK)
    attempt always failed with WinError 6 and every stop fell back to a
    force-kill). Instead we drop a stop-signal flag file that run_backend.py
    watches; the child self-signals CTRL_BREAK, which uvicorn handles as a
    graceful exit (SIGBREAK is in uvicorn's HANDLED_SIGNALS on Windows).
    Force-kill remains the fallback if it doesn't exit in time.
    """
    global backend_process, backend_log_handle

    with lock:
        if (not backend_process or backend_process.poll() is not None) and not _backend_healthy():
            logger.info("Backend not running.")
            _close_log_handle()
            return

        # The tracked PID may be the decoy (dead or idle) while the REAL
        # backend is the clone — the flag-based graceful stop works regardless
        # of which PID we hold, because the real backend watches the flag.
        tracked = backend_process
        logger.info(
            f"Stopping backend (PID: {tracked.pid if tracked else 'untracked'} "
            f"{'[decoy/clone]' if tracked and tracked.poll() is not None else ''})..."
        )

        stop_flag = LOG_DIR / "stop_signal.flag"
        try:
            stop_flag.write_text("stop", encoding="utf-8")
        except OSError as e:
            logger.warning(f"Could not write stop flag: {e}")

        if wait:
            deadline = time.time() + 20
            if tracked and tracked.poll() is None:
                try:
                    tracked.wait(timeout=20)
                    logger.info(f"Backend stopped (exit code {tracked.returncode}).")
                except subprocess.TimeoutExpired:
                    logger.warning("Backend did not stop in 20s — force killing.")
                    tracked.kill()
                    tracked.wait(timeout=5)
                    logger.info("Backend force-killed.")
            # The tracked process may be the decoy; the REAL backend needs the
            # flag watcher + a moment to exit. Give it until the deadline.
            while time.time() < deadline and _backend_healthy():
                time.sleep(2)
            if _backend_healthy():
                logger.warning("Backend still answering after stop request — force killing listener on :8001.")
                try:
                    import psutil
                    for conn in psutil.net_connections(kind="tcp"):
                        if conn.laddr and conn.laddr.port == 8001 and conn.status == "LISTEN":
                            proc = psutil.Process(conn.pid)
                            proc.kill()
                            logger.info(f"Force-killed backend listener PID {conn.pid}.")
                except Exception as e:
                    logger.error(f"Could not force-kill backend listener: {e}")
            else:
                logger.info("Backend stopped (health no longer answering).")
        try:
            stop_flag.unlink(missing_ok=True)
        except OSError:
            pass

        backend_process = None
        _close_log_handle()


def _close_log_handle():
    """Close the backend log file handle to prevent leaks."""
    global backend_log_handle
    if backend_log_handle:
        try:
            backend_log_handle.close()
        except Exception:
            pass
        backend_log_handle = None


def restart_backend():
    """Stop then start the backend."""
    logger.info("Restarting backend...")
    stop_backend(wait=True)
    time.sleep(2)
    start_backend()


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------
def _can_restart() -> bool:
    """Check if we're within the restart cap (3 per 30 minutes)."""
    global restart_timestamps
    now = datetime.now()
    cutoff = now - timedelta(seconds=RESTART_COOLDOWN)
    restart_timestamps = [ts for ts in restart_timestamps if ts > cutoff]
    return len(restart_timestamps) < MAX_RESTARTS


def watchdog_loop():
    """
    Background thread that monitors backend health.

    - Waits BOOT_GRACE_PERIOD before first check.
    - Polls /api/health every HEALTH_POLL_INTERVAL seconds.
    - After FAILURE_THRESHOLD consecutive failures, triggers restart.
    - Caps restarts at MAX_RESTARTS per RESTART_COOLDOWN.
    """
    global is_running

    logger.info(f"Watchdog: waiting {BOOT_GRACE_PERIOD}s boot grace period...")
    boot_deadline = time.time() + BOOT_GRACE_PERIOD

    # During grace period, just wait (but exit early if shutdown requested)
    while time.time() < boot_deadline and is_running:
        time.sleep(5)

    consecutive_failures = 0

    while is_running:
        try:
            time.sleep(HEALTH_POLL_INTERVAL)
            if not is_running:
                break

            # Check if the process is still alive at the OS level. This is
            # informational ONLY — on this machine the OS clones the spawned
            # process, and the tracked PID can be the idle decoy that exits
            # (or stays idle) while the REAL backend (the clone) is healthy.
            # Never force a restart from the PID alone; health decides.
            with lock:
                proc = backend_process
            if proc and proc.poll() is not None:
                logger.warning(
                    f"Spawned backend PID {proc.pid} exited (code {proc.returncode}) — "
                    "health check decides the next step."
                )

            # HTTP health check
            if consecutive_failures < FAILURE_THRESHOLD:
                try:
                    resp = requests.get(HEALTH_URL, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", "unknown")
                        uptime = data.get("uptime_seconds", "?")
                        mt5_info = ""
                        if data.get("mt5_enabled"):
                            mt5_conn = data.get("mt5_connected")
                            mt5_info = f" | MT5: {'Connected' if mt5_conn else 'Disconnected'}"
                        logger.debug(f"Health OK: {status}, uptime={uptime}s{mt5_info}")
                        consecutive_failures = 0
                        continue
                    else:
                        logger.warning(f"Health check returned HTTP {resp.status_code}")
                        consecutive_failures += 1
                except (requests.RequestException, ValueError, KeyError) as e:
                    logger.warning(f"Health check failed: {e}")
                    consecutive_failures += 1

            # Restart logic
            if consecutive_failures >= FAILURE_THRESHOLD:
                if _can_restart():
                    logger.error(
                        f"Backend unhealthy ({consecutive_failures} failures). Restarting..."
                    )
                    restart_timestamps.append(datetime.now())
                    restart_backend()
                    consecutive_failures = 0

                    # New grace period after restart
                    logger.info(f"Watchdog: post-restart grace period ({BOOT_GRACE_PERIOD}s)...")
                    grace_end = time.time() + BOOT_GRACE_PERIOD
                    while time.time() < grace_end and is_running:
                        time.sleep(5)
                else:
                    logger.critical(
                        f"Restart cap reached ({MAX_RESTARTS} in {RESTART_COOLDOWN}s). "
                        "Manual intervention required."
                    )
                    consecutive_failures = 0  # Reset to avoid log spam
                    time.sleep(60)  # Back off before checking again
        except Exception as e:
            # Never let the watchdog die silently — an unmanaged backend is
            # the worst failure mode (user found the backend dead with the
            # tray "healthy"). Log, reset the failure counter, keep going.
            logger.exception(f"Watchdog loop error (continuing): {e}")
            consecutive_failures = 0
            time.sleep(HEALTH_POLL_INTERVAL)


# ---------------------------------------------------------------------------
# System Tray
# ---------------------------------------------------------------------------
def create_tray():
    """Build and run the system tray icon with context menu."""
    import pystray

    global is_running
    is_running = True

    def on_start(icon, item):
        threading.Thread(target=start_backend, daemon=True).start()

    def on_stop(icon, item):
        threading.Thread(target=stop_backend, daemon=True).start()

    def on_restart(icon, item):
        threading.Thread(target=restart_backend, daemon=True).start()

    def on_open_logs(icon, item):
        os.startfile(str(LOG_DIR))

    def on_quit(icon, item):
        global is_running
        logger.info("Quit requested — shutting down...")
        is_running = False
        # Stop backend FIRST (while icon is still visible)
        stop_backend(wait=True)
        # Then stop the tray icon
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Start Backend", on_start),
        pystray.MenuItem("Stop Backend", on_stop),
        pystray.MenuItem("Restart Backend", on_restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Logs", on_open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit RUTE", on_quit),
    )

    icon = pystray.Icon("RUTE", _make_icon("green"), "RUTE Backend", menu)

    # Auto-start backend on launch
    start_backend()

    # Start watchdog in background thread
    watchdog_thread = threading.Thread(target=watchdog_loop, daemon=True)
    watchdog_thread.start()

    logger.info("RUTE tray app running. Right-click the tray icon for options.")
    icon.run()  # Blocks until icon.stop() is called

    # After icon.run() returns, cleanup
    logger.info("Tray app exited.")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Verify venv exists
    if not VENV_PYTHON.exists():
        logger.error(f"Python venv not found at: {VENV_PYTHON}")
        logger.error("Run: python -m venv venv && venv\\Scripts\\pip install -r requirements.txt")
        sys.exit(1)

    # Verify run_backend.py exists
    if not RUN_BACKEND.exists():
        logger.error(f"run_backend.py not found at: {RUN_BACKEND}")
        sys.exit(1)

    # Only one tray instance may run — prevents duplicate watchdogs/backends
    if not _single_instance():
        sys.exit(1)

    create_tray()
