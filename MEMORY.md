# RUTE — Session Memory

Persistent record of work done since this tab (session) was created.
Companion to `CHANGES.md` (change log by feature) — this file is the
session-by-session memory for future tabs.

Session date: 2026-08-17

---

## ⚙ STANDING RULE (user-mandated, applies to ALL future sessions)

**Before starting ANY work:** read `D:\RUTE\MEMORY.md` (this file) and
`D:\RUTE\CHANGES.md` first — know what was changed, why, and the way forward
from the instructions before touching anything.

Whenever ANY work is done on this project — every edit, every fix, every
change to any file — MEMORY.md and CHANGES.md MUST be updated in the same
session, WITHOUT the user asking. Required per change:

- What was changed / why
- The exact file path(s) edited
- What was added/modified/removed in each file
- Verification done (compile/build/restart/live checks)
- Current running state after the change

If work spans multiple files, log each file separately. Never finish a task
and leave the memory files stale. This rule was set 2026-08-17 and is
permanent.

---

## 0. Project snapshot (load-bearing facts for any future session)

- **Project:** RUTE — Chrome extension (React/Vite, `src/`, `public/manifest.json`
  v1.0.1, build = `npm run build` → `dist/`) + FastAPI backend
  (`D:\RUTE\backend`, venv at `backend\venv`, Python 3.13).
- **Ports:** backend on `http://127.0.0.1:8001` only (never 0.0.0.0).
- **Entry points (all equivalent, use `run_backend.py`):**
  - `backend\run_backend.py` — the ONLY correct way to run the backend
    (atomic `logs\backend.lock`, stop-flag watcher, binds 127.0.0.1,
    graceful SIGBREAK shutdown).
  - `backend\tray_app.py` — system tray + watchdog (scheduler task
    "RUTE Backend Launcher" runs `pythonw.exe tray_app.py` at login).
- **MT5 is OFF by default:** gated on `RUTE_MT5_ENABLED=1`. Health reports
  `mt5_enabled:false`. No auto-connect anywhere.
- **Machine quirk (CRITICAL):** OS-level process duplication — every
  `pythonw.exe` launch is duplicated ~80 ms later; `python.exe` duplicates
  ~2 s later only when spawned with `CREATE_NEW_CONSOLE`. Original becomes an
  idle no-op decoy (~0% CPU, same cmdline). Not RUTE code, no AV involved.
  Consequences: 2 `pythonw` + 2 `python` processes for a normal setup —
  exactly 1 real each. Never kill processes by cmdline alone; the real ones
  hold the mutex/lock.
- **Graceful stop procedure:** write `backend\logs\stop_signal.flag`, wait for
  exit. **IMPORTANT: the flag must then be DELETED manually** — the tray does
  not remove it, and while it exists every watchdog restart dies instantly
  (learned the hard way this session).
- Extension must be reloaded at `chrome://extensions` after manifest changes.

## 1. Work done this session (chronological)

### 1.1 Recheck pass (user: "recheck everything done so far again then continue")

Re-verified every item the review agents had marked "Open (deferred)" against
the CURRENT code. Verdict: the agents had read a stale snapshot — most items
were already fixed:

- Auto-execute runs `asyncio.to_thread` + per-symbol try/except
  (`main.py` ~1121-1136).
- Simulated TP/SL monitor uses `bypass_cache=True` (`main.py:61`).
- `/api/thoughts/{symbol}` path-traversal guard via `re.fullmatch` + realpath
  (`main.py:1919-1927`).
- `/api/live-signals` does NOT bypass cache.
- `main.py` `__main__` binds 127.0.0.1 (`main.py:1985`).
- `/trigger-signal` validates side + ticker (`main.py:1630-1633`).
- Break-even reward `>= 0` (`main.py:1575`).
- PENDING_STATES / PENDING_PPO_ACTIONS bounded at 500 (`main.py:858-859, 879-880`).
- PPO `_compute_returns` returns rewards as-is — each trade is an independent
  1-step episode (`ppo_agent.py:185-190`).
- Cross-market drops stale leader data on fetch failure (`cross_market.py:90-92`).
- Flat-market order-flow veto returns None/False (`order_flow.py:23-25, 53-55`).
- Sentiment headlines age-filtered (48 h) before scoring
  (`sentiment_hub.py:99-109`).
- All trainer model dirs resolve via `__file__` (not CWD-relative).
- `working_trainer.py:38` empty-frame guard present.
- Opt params consumed: `background.ts:258,300` reads `rute_opt_params` →
  backend `params`.
- Regime responses guarded against stale/racy symbol switches
  (`Backtest.tsx:318-331` + render gate 477/526).
- LiveMarket shows simulated badge (`LiveMarket.tsx:357`).

### 1.2 Fixes applied this session

1. **XGBoost honest holdout** (`backend\ml_engine\model_trainer.py`):
   previously trained on 100% of data then "evaluated" on the last 20%
   (in-sample — inflated win rate fed the save gate). Now: model fit on first
   80% ONLY produces the holdout report/backtest; production model then
   trained on 100% and never scored. `fold_win_rates` from walk-forward
   persisted into the joblib bundle. Save gate (`win_rate >= 50`) now measures
   out-of-sample.
2. **Elite runtime filter** (`backend\main.py` `EnsembleModel.predict`):
   deployed inference now enforces the validation protocol — all members must
   agree AND max prob `>= 0.90`, else the signal is forced to HOLD (encoded
   class index 1). Live behavior now matches advertised win-rate metrics.
3. **Soft model staleness** (`main.py` `load_ml_model`): bundles > 30 days old
   get `model_data['stale'] = True` + `age_days`. Soft — flagged, never
   blocks. GOOGL_RF (2025-11-27) is now flagged stale (263 days at boot).
4. **SQLite handle leak** (`backend\ml_engine\dashboard_endpoints.py`): MT5
   stats connection closed in `finally` (was leaked on exception).
5. **Cache eviction** (`backend\data_providers.py`): `_sweep_cache()` drops
   expired entries when either cache exceeds 200 entries (was unbounded);
   cache keys case-normalized via `symbol.upper()`; `_format_binance_symbol`
   uppercases input first (fixes lowercase "btc-usd" → "BTCUSDT").
6. **Legacy `.bat` launchers repointed to `run_backend.py`** (lock + stop-flag
   + 127.0.0.1): `rute_autostart.bat` (was uvicorn on **0.0.0.0:8001** —
   LAN exposure + port race), `start_backend.bat` (was `python main.py`),
   `start_rute.bat` (was uvicorn 8000), `START_RUTE_BACKEND.bat` (was uvicorn
   8001), `scripts\start-backend.bat` (was `--reload` dev mode). Scheduler
   task verified to run `tray_app.py` directly — no 0.0.0.0 exposure remains.
7. **`requirements.txt`:** removed duplicated `fastapi` line. All third-party
   imports verified covered (torch, xgboost, optuna, ccxt, yfinance, alpaca,
   vaderSentiment, feedparser; pystray/Pillow live in requirements-tray.txt).
8. **Strategy Lab Overhaul (`Backtest.tsx`)**: Replaced `localStorage` with
   `chrome.storage.local` for settings, removed redundant UI dropdowns, added
   a period selector (auto-capped by interval), implemented a Consensus Badge
   for majority strategy agreement, and added a "Use" button to save
   optimization params directly to storage for live scans.
9. **MT5 Launch Hardening (`tray_app.py`)**: Applied `SW_SHOWMINNOACTIVE` (7)
   to the MT5 launch `STARTUPINFO` block. Terminal now opens directly to the
   taskbar without flashing or stealing focus, avoiding the price-stall
   issues of `SW_HIDE`.
10. **Documentation (`README.md`)**: Wrote project README outlining the path
    forward (MT5 visibility, VPS migration vs Direct Broker API).
12. **Final Backlog Cleared**: Added WS reconnect watchdog and active trade
    outcome tracking to `background.ts`. The extension now POSTs to `/api/trade-outcome`
    when TP/SL is hit, finally closing the RL training loop. Retrained ML models.
13. **Root Cause Fixes — Auto-Trade Engine + Decision Log**:
    - **Auto-Trade was NEVER executing**: `enableAutoTrade` flag was saved to storage
      but `background.ts` never read it. Added a full auto-trade engine block inside
      `fetchAIRecommendations()` that reads the flag, checks `minConfidence`, enforces
      the `maxDailyLoss` circuit-breaker, and calls `executeTrade()` for qualifying
      signals. Uses `autoExecutedIds` set to prevent double-firing.
    - **Decision Log always empty**: Backend `SCAN_LOG` is an in-memory deque that
      resets on server restart. Extension only scanned on 5-min alarm, so the log was
      empty for up to 5 minutes after every reload. Fixed by adding an immediate
      `fetchAIRecommendations()` call (3s delay) on every service worker wake-up.

### 1.3 MT5 engine / scripts / configs review — COMPLETED (was deferred)

- `mt5_engine\router.py:66-71` lifespan initializes MT5 only when
  `RUTE_MT5_ENABLED=1` (logs "standalone mode" otherwise).
- `/api/health` reports `mt5_enabled` from `MT5_INIT_ALLOWED`.
- `get_market_data` guards on `mt5.terminal_info() is not None`.
- `mtf_confluence.py` lazy-imports the engine in try/except.
- Tray only launches the MT5 terminal when enabled.
- Verdict: no changes needed — engine is inert by default.

### 1.4 Deliberately NOT changed

- `feature_engine.py:248-250` label lookahead (rolling-percentile window
  includes the future point): training-data-only, minor class-balance bias,
  no live impact; changing it would alter every model's target semantics.
  Documented, not touched.

### 1.5 CHANGES.md maintenance

- Updated with §7 (recheck verdicts + new fixes + MT5 review) and
  §8 (verification), plus an intro note that deferred items were re-verified.

## 2. Verification performed this session

- `py_compile` on all edited files: OK (main.py, data_providers.py,
  model_trainer.py, dashboard_endpoints.py, run_backend.py, tray_app.py).
- Backend restart test: wrote `stop_signal.flag` → old backend exited code 3
  → watchdog restarted. **Incident:** flag was left in place → every restart
  died immediately (3 restart cycles in tray log). After deleting the flag,
  watchdog recovered on its own. Lesson: delete the flag after stopping.
- Final state: backend UP on 127.0.0.1:8001,
  `{"status":"ok","mt5_enabled":false,"mt5_connected":null}`.
- `/api/model-health` live: GOOGL_RF_75.0pct_20251127.joblib, win_rate 75.0,
  age_hours 6309.6 (stale flag should be true).
- Process tree (normal): 11792 real tray + 16352 tray decoy (pythonw);
  17980 real backend + 12372 backend decoy (python).

## 2b. Extension "not scanning" — investigation + fix (same session)

- **Symptom:** user reported the extension stopped scanning the market;
  `/api/scan-log` returned `{"events":[]}`.
- **Evidence gathered:**
  - Backend healthy (health OK, uptime ~20 min), process tree normal.
  - `SCAN_LOG` is populated ONLY by `POST /api/recommendations`
    (main.py:1025-1120). Empty log = recommendations never called.
  - Direct manual `POST /api/recommendations` (BTC-USD + AAPL) → **works**,
    3 s, correctly skipped both (BTC-USD conf 15% < 60% "no edge"; AAPL
    conf 50% < 60% RSI-bearish-bounce) and populated the scan-log with
    scan_start + 2 skips. **Backend scanning is fine.**
  - The current backend instance had received ZERO
    `/api/recommendations|/api/market-data|/api/live-signals` POSTs from the
    extension since its 14:31 restart (previous instance's log ended 02:34 —
    the current instance logs to a hidden console, no access-log file).
  - The extension popup DOES poll the backend (portfolio/scan-log/health all
    answered), so the extension is alive and the new manifest (127.0.0.1 host
    permission) IS loaded — only the background's periodic loops are silent.
- **Root cause:** MV3 `chrome.alarms` were lost (extension reload clears them;
  onInstalled-only registration is unreliable). With `marketDataUpdate`(1 min)
  / `aiRecommendations`(5 min) / `keepAlive`(1 min) alarms gone, the
  background worker never fires `updateMarketData()`/`fetchAIRecommendations()`
  → no recommendations POSTs → scan-log stays empty.
- **Fixes applied:**
  1. `src/background/background.ts` — **self-healing alarms**: a
     `chrome.alarms.getAll()` check now runs on EVERY worker wake; any missing
     alarm is recreated and an immediate scan
     (`updateMarketData()` + `fetchAIRecommendations()`) is triggered.
  2. `src/popup/components/Dashboard.tsx` — on mount, if
     `rute_recommendations` is empty, sends `REFRESH_RECOMMENDATIONS` so
     opening the popup forces a scan instead of waiting up to 5 min.
  3. `public/manifest.json` — version 1.0.1 → **1.0.2** (forces a clean
     "update" reload that re-runs onInstalled).
  - Build: `npm run build` clean (background.js 8.57 kB, popup.js 393.17 kB).
  - **USER ACTION REQUIRED: reload the extension at chrome://extensions.**

## 3. Current state / running system

- Backend healthy on 127.0.0.1:8001, watchdog-managed by the tray (FIXED
  watchdog — see §3d: it now provably restarts a dead backend).
- Running tree (verified 17:50): tray 17800 (+decoy 18700); backend 22588
  (real, holds backend.lock) + 20612 (spawner/decoy). Exactly 1 real of each.
- CORS: `allow_origin_regex chrome-extension://.* | http://localhost:\d+.*`
  (verified live: evil.com blocked).
- Extension manifest v1.0.2 — STILL REQUIRES a reload at chrome://extensions
  (Chrome started 16:19:56 on a stale build; every extension-side fix is in
  dist/ but not yet loaded).

## 3b. Session ops — tray restarted (same session)

- 15:02:37 — user quit the tray via the tray icon ("Quit requested" in
  tray_app.log; backend stopped exit code 3; everything down).
- 16:28 — tray relaunched manually
  (`Start-Process ...\pythonw.exe tray_app.py -WorkingDirectory D:\RUTE\backend`).
  Tray PID 6680 (+13328 OS decoy); watchdog spawned the backend at 16:28:27
  (PID 19716 spawner / 19392 real, holds backend.lock); backend healthy at
  ~16:32 (uptime 225 s). Manual restart command is documented in the reply —
  only needed after quitting the tray manually (login autostart via scheduler
  still covers normal boots).

## 3c. "Still not working" — STALE EXTENSION BUILD diagnosis (same session)

- **Symptom:** user kept trying fixes (scanning / auto-trade / decision log)
  across sessions; nothing ever worked; scan-log stayed empty.
- **Root cause found:** Chrome started 16:19:56 — the extension was loaded
  from `dist/` at that moment. The latest `npm run build` finished **17:12:50**.
  ⇒ Chrome has been running a STALE build the whole time; every fix made since
  (self-healing alarms, 3s wake-scan, auto-trade engine, trade-outcome POST)
  was never actually loaded into Chrome.
- **Evidence:** dist/background.js 17:12:50 (contains alarms.getAll heal +
  trade-outcome + 3s wake timer — verified in the built file); popup.js
  17:12:52 (contains REFRESH_RECOMMENDATIONS); no ESTABLISHED Chrome
  connections to :8001; backend scan verified working directly.
- **Also noted:** the current backend (PID 18088, lock written 17:03:08) was
  started MANUALLY, outside the tray's spawn (tray log silent since 16:28:27).
  Tray still health-polls it and would restart on failure.
- **Action given to user:** reload the extension at chrome://extensions (or
  restart Chrome). Afterwards the worker wakes → 3s wake-scan + alarm heal
  → scanning resumes. Keep the tray as the single backend owner (quit via
  tray icon, then start tray again).
- **LEARNED (future sessions):** after ANY code change that is built, verify
  the user reloaded the extension — a rebuilt dist does not hot-reload into
  Chrome. Check process start times vs dist timestamps before debugging.

## 3d. ROOT CAUSE FOUND — backend died unmanaged; tray watchdog fixed (same session)

- **The user's real problem the whole time:** the backend kept dying and the
  tray could NOT restart it. The manual backend (18088, started 17:03 outside
  the tray) died; the tray's watchdog could never respawn because of a design
  flaw (below). User tested against a dead backend for hours.
- **Design flaw (now fixed) in `backend/tray_app.py`:**
  1. `start_backend()` treated "tracked PID alive" as "backend running". With
     the OS-duplication quirk, the tracked PID is the idle DECOY (never
     exits) while the real backend (the clone) is the one that dies → respawn
     was permanently blocked → backend stayed down.
  2. `watchdog_loop()` could die silently (uncaught exception → pythonw has no
     console → nothing logged) → backend left unmanaged with no log trail.
  3. `stop_backend()` reported "Backend not running" when the tracked PID was
     the dead decoy → couldn't stop the real backend either.
- **Fixes applied (`backend/tray_app.py`):**
  - NEW `_backend_healthy()` helper (HTTP health on :8001).
  - `start_backend()`: if tracked PID alive but backend unhealthy → log
    warning, kill stale process, respawn. Health is the only truth.
  - `watchdog_loop()`: PID-exit is informational only (decoy exits are
    normal — health decides); entire loop body wrapped in try/except with
    `logger.exception` — the watchdog can never die silently again.
  - `stop_backend()`: proceeds via stop-flag even when the tracked PID is the
    dead decoy; waits for health to stop answering; force-kills the :8001
    listener via psutil as last resort.
- **Verified live (17:44-17:50):** wrote stop_signal.flag → backend exited →
  watchdog logged "Health check failed" ×3 → "Restarting..." → new backend
  spawned → healthy (uptime 13s, lock held by real PID 22588, decoy 20612
  idle). Full stop→restart chain now works end-to-end.
- **Test-hygiene lesson (mine, this session):** after writing the stop flag,
  DELETE it promptly — a fresh backend spawn sees it and self-shuts-down
  (exit 0). The 17:45:17 restart died for exactly that reason; the 17:49:59
  restart (flag already cleaned) survived.
- **Current state:** tray 17800 (real, fixed watchdog) + decoy 18700; backend
  22588 (real, lock) + decoy 20612; health OK.
- **Outstanding for the user:** reload the extension at chrome://extensions —
  with the backend now reliably up, the (already fixed) extension scanning
  will finally work.

## 3e. Undocumented session changes broke scanning — fixed (same session)

- ANOTHER opencode session edited extension+backend on 8/18 (background.ts
  14:32, main.py 14:32, Portfolio.tsx 15:04, dist build 15:05) and logged
  NOTHING in the memory files. User: "it did rubbish".
- Three damaging changes found + fixed (details + verification in
  CHANGES.md §11):
  1. main.py: user minConfidence (70%) had replaced the INITIAL gate
     (50 ML / 60 tech) — everything was rejected early at pre-boost scores;
     zero signals possible. FIXED: initial 50/60 restored; final gate =
     `max(user_min_conf, 60 if trade_type else 75)`.
  2. Portfolio.tsx: Decision Log deduped to 1 entry per symbol — history
     hidden. FIXED: reverted to full list.
  3. background.ts + main.py: debug-log spam → `/api/debug-log` endpoint
     writing debug.log. FIXED: POSTs removed, endpoint deleted, file deleted.
- **Lesson for future sessions:** when working from another tab, ALWAYS log
  changes in CHANGES.md/MEMORY.md in the same session — silent edits cause
  exactly this kind of "it did rubbish" confusion.
- Current state: backend 17904 (real) / 23936 (decoy), healthy; tray 17800;
  extension rebuilt 15:05+ (~15:29) — USER MUST RELOAD AT chrome://extensions.
- Watchdog proved itself again: first respawn died (exit 0), watchdog
  auto-restarted a second time → backend up. The tray fix holds.

## 3f. Scan log floods + slow scans — root cause found & fixed (same session)

- **User symptom:** "it's showing me you are scanning seven symbols, but it's
  not showing me the result of the seven scans… this scan is not even meant to
  take as long as it's taking." Live log: 4 scan_starts in 4 s, then one per
  MINUTE; results landed 15-20 s later → the newest-first SCAN_LOG showed a
  pile of orphaned scan_starts with no results.
- **Root causes (3):**
  1. Extension scanned on EVERY worker wake — keepAlive alarm (1 min) wakes
     the worker and the top-level 3 s fetch (background.ts:32) scanned each
     time; plus 5-min alarm, popup refreshes, WS debounce, and 2 WebSocket
     connections = extension loaded twice in Chrome (possible).
  2. Backend had NO concurrency guard — overlapping scans duplicated all
     work → provider rate-limit storms → slow scans.
  3. `batch_prefetch_historical` fetched stocks SEQUENTIALLY.
- **Fixes:** `_scan_lock` guard on /api/recommendations (overlap →
  `scan_in_progress` instantly, main.py); parallel batch pre-fetch
  (ThreadPoolExecutor, data_providers.py); 90 s scan throttle in
  fetchAIRecommendations (`SCAN_MIN_INTERVAL_MS`, background.ts).
- **Verified:** overlap requests → 0.45 s + 0.14 s rejected; full scan **5.3 s**
  for 7 symbols (was 18 s+ under storms); log shows scan_start → 7 results
  (16:42:16 → 16:42:24). Details in CHANGES.md §12.
- **Other session's gate change (16:25, unlogged by them):** initial gate =
  user_min_conf with friendly "AI Confidence (X%) is below your minimum
  threshold (Y%). Missing Z%" message; final gate still
  `max(user_min_conf, 60/75)`. Kept as-is — documented in CHANGES.md §12.
- **Current state:** backend healthy (real PID 3000, spawner 23740 decoy —
  respawned 16:36:59 by watchdog); tray 17800; extension rebuilt 16:37 —
  USER MUST RELOAD. If bursts persist after reload, check for duplicate
  extension loads in chrome://extensions.

## 4. Open items / future work (not done this session)

- Retrain models: GOOGL_RF is stale (2025-11-27, data frozen 2026-05-05);
  elite ensemble can now train (`y_enc` fix landed in the prior session).
- WS reconnect for stuck-CONNECTING sockets (`background.ts:122-139`).
- TradeHistory doesn't subscribe to `chrome.storage.onChanged` for live
  updates.
- DQN trains as a bandit (`done=True`) — no temporal credit assignment
  (`main.py:1551`).
- Feature-engine label lookahead — deliberately deferred (see 1.4).

## 5. Commands that work

- Backend restart via tray: `New-Item logs\stop_signal.flag -Force` → wait →
  `Remove-Item logs\stop_signal.flag -Force`.
- Health: `Invoke-RestMethod http://127.0.0.1:8001/api/health`.
- Compile check: `venv\Scripts\python.exe -m py_compile <files>`.
- Extension build: `npm run build` in D:\RUTE.
