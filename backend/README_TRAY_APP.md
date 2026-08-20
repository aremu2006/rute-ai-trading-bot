# RUTE Tray App — Quick Reference

## What it does

A Windows system tray application that:
- **Launches** the RUTE AI backend as a managed subprocess
- **Monitors** health via `/api/health` every 30 seconds
- **Restarts** automatically after 3 consecutive health failures
- **Caps** restarts at 3 per 30 minutes to prevent crash loops
- **Optionally** launches MetaTrader 5 before booting the backend

## Quick Start (Development)

```bash
cd D:\RUTE\backend

# Install tray app dependencies into your existing venv
venv\Scripts\pip install -r requirements-tray.txt

# Run the tray app
venv\Scripts\python tray_app.py
```

A green "R" icon will appear in your system tray. Right-click it for:
- **Start Backend** — manually start the backend
- **Stop Backend** — gracefully stop (CTRL_BREAK_EVENT → 15s timeout → force kill)
- **Restart Backend** — stop + start
- **Open Logs** — opens the `logs/` folder
- **Quit RUTE** — stops backend, then exits the tray app

## Configuration

All settings are read from `D:\RUTE\backend\.env`:

| Variable | Default | Description |
|---|---|---|
| `RUTE_MT5_ENABLED` | `0` | Set to `1` to auto-launch MT5 terminal |
| `MT5_TERMINAL_PATH` | `C:\Program Files\MetaTrader 5\terminal64.exe` | Path to `terminal64.exe` |

## Log Files

All logs are in `D:\RUTE\backend\logs\`:

| File | Contents |
|---|---|
| `tray_app.log` | Tray app lifecycle, watchdog events, restart decisions |
| `backend.log` | Backend stdout/stderr (uvicorn output, model loading, etc.) |

## Auto-Start on Login

Run the registration script once:

```powershell
powershell -ExecutionPolicy Bypass -File D:\RUTE\register_autostart.ps1
```

To remove:
```powershell
Unregister-ScheduledTask -TaskName "RUTE Backend Launcher" -Confirm:$false
```

## Packaging with PyInstaller (Optional)

Only package the **tray app**, not the backend:

```bash
cd D:\RUTE\backend
venv\Scripts\pip install pyinstaller

venv\Scripts\pyinstaller --onedir --windowed --name tray_app ^
  --add-data ".env;." ^
  tray_app.py
```

The output goes to `dist\tray_app\`. Update `register_autostart.ps1` to point at `dist\tray_app\tray_app.exe` instead of `pythonw.exe`.

## Architecture

```
tray_app.py (system tray + watchdog)
    │
    ├── spawns: venv\Scripts\python.exe run_backend.py
    │               │
    │               └── runs: uvicorn main:app --host 127.0.0.1 --port 8001
    │
    ├── polls: GET http://127.0.0.1:8001/api/health
    │
    └── shutdown: sends CTRL_BREAK_EVENT (OS signal, not HTTP)
```

**Why CTRL_BREAK_EVENT instead of an HTTP shutdown endpoint:**
Any browser tab can `fetch('http://127.0.0.1:8001/...')` — browsers don't block
requests to localhost. An unauthenticated shutdown endpoint would be trivially
exploitable by any malicious JS running in any open tab (localhost CSRF).
CTRL_BREAK_EVENT requires OS-level process-signal permission, which a browser
tab structurally cannot have.
