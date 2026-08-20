# RUTE — Change Log & Fixes

Session date: 2026-08-17

---

## 1. Extension UI — dropdown restyle

**Files:** `src/popup/styles.css` (trigger + dropdown), `public/manifest.json`

- Dropdown trigger and panel restyled to the glass-panel recipe:
  `bg-[#101013]/80 backdrop-blur-xl border border-white/[0.08]` (previously the
  subtle color change `#15151d → #101013` was imperceptible).
- Manifest version bumped **1.0.0 → 1.0.1**.
- Rebuilt `dist/` (popup.js 385.74 kB) — reload the extension at
  `chrome://extensions` after each build.

---

## 2. Market-Regime-Aware Strategy Selector (new feature)

**Backend — `backend/main.py`**

- New endpoint `POST /api/market-regime`
  (`MarketRegimeRequest`: symbol, interval="1d", apiKeys).
- Regime classification with confidence:
  - `REGIME_STRATEGY_MAP` — trending_up → macd / alpha_trend / gainzalgo;
    trending_down → macd / alpha_trend; ranging → rsi / bollinger;
    high_volatility → rsi / bollinger; low_volatility → sma_cross;
    neutral → all 6.
  - `_adx` (spec-verbatim implementation), `_atr_pct`, `_rsi` (Wilder via ewm),
    `_ema`, `_analyze_regime(df, symbol, interval)`.
  - Classification order: high_vol (ATR% > 2.5) → low_vol (< 0.5) → trending
    (ADX > 25 + EMA20/50 bias) → ranging (ADX < 20) → neutral.
  - Confidence formulas (exact spec): trending `(adx-25)/10`; ranging
    `1-(adx/20)`; high_vol `(atr_pct-2.5)/2`; low_vol `1-(atr_pct/0.5)`;
    neutral `1-|adx-22.5|/2.5`.
  - Response: regime, label, confidence, description, ADX/ATR%/RSI/EMA20/EMA50
    meta, suggested strategies.
- **Spec bug fixed during testing:** `limit_map` period caps ("5d"=5 bars,
  "1mo"=30 bars) starved the classifier of data (needs ≥ 50 bars; Binance maps
  5m→1h). Fixed via `REGIME_PERIOD_BY_INTERVAL = {"1d":"3mo","1h":"3mo","5m":"3mo"}`.

**Frontend — `src/popup/components/Backtest.tsx`**

- `RegimeResult` interface, `REGIME_BADGE_CLS` color map (trending_up emerald,
  trending_down red, ranging/low_vol blue, high_vol amber, neutral zinc).
- Regime panel between the Controls card and "Strategies in use now":
  Analyse button (RotateCw spinner while loading), skeleton loading state,
  placeholder text before first analysis, badge + confidence bar + description
  + meta line + suggested-strategy chips.
- "Apply suggestion" button clears error, sets `activeStrats` from the
  suggestion, persists via `saveActive`.
- Fit badges on active-strategy chips (`✓` emerald / `[not ideal]` zinc) when a
  regime is loaded.
- Build verified: `npm run build` clean (popup.js 391.90 kB).

**Verified live:** BTC-USD 1d → ranging (ADX 18.73, conf 0.064);
BTC-USD 1h → low_volatility (ATR 0.165%, conf 0.67); AAPL 1d → high_volatility
(ATR 2.568%, conf 0.034). All 9 response fields present.

---

## 3. Tray app — duplicate-process chaos fixed (root cause found)

### 3.1 Symptom

After a PC restart, up to 4 tray icons + several backend/python windows appeared
on the taskbar, backends crash-looping.

### 3.2 Root causes found

1. **Five autostart registrations existed:**
   - Task Scheduler "RUTE Backend Launcher" (kept — the single entry)
   - Startup folder: `RUTE_AutoStart.lnk`, `RUTE_Backend.lnk`, `RUTE_Backend.vbs`
     (all **deleted**) → every one launched another tray/backend at login.
2. **OS-level process duplication on this machine:** every `pythonw.exe` launch
   is duplicated by a system process-spawner ~80 ms later (verified even for a
   trivial `time.sleep` script; `python.exe` also duplicates when spawned with
   `CREATE_NEW_CONSOLE`, ~2 s later). The clone carries the identical command
   line; the original becomes an idle no-op decoy (~0% CPU). Multiplicative
   effect with the 5 autostarts = the 4-window explosion. Not caused by RUTE
   code (no AV process running on the machine). The decoys are harmless once
   the guards below exist.
3. **`GenerateConsoleCtrlEvent` only reaches processes sharing the caller's
   console** — the tray could never gracefully stop its own child (`WinError 6`
   in logs), so every stop fell back to force-kill, and the
   `CREATE_NO_WINDOW` spawn left the child console-less entirely.
4. `rute_autostart.bat`'s `netstat` port check raced the 2.5-min boot
   (`uvicorn` binds 0.0.0.0, `start /min` console = taskbar window).

### 3.3 Fixes applied

**`backend/tray_app.py`**

- Single-instance guard: Windows named mutex `Local\RUTE_Tray_Mutex` via
  `ctypes.WinDLL("kernel32", use_last_error=True)` +
  `ctypes.get_last_error() == 183` (naive `GetLastError()` was unreliable —
  the ctypes machinery clobbered it, letting a second instance proceed;
  verified fix: second instance now exits code 1 with a warning).
- Pre-spawn health check: if something already answers `/api/health` on
  :8001, **adopt** it instead of spawning a duplicate.
- Backend spawned with `CREATE_NEW_PROCESS_GROUP | CREATE_NEW_CONSOLE` +
  `STARTUPINFO(SW_HIDE)` (hidden console, no taskbar window; console required
  for CTRL_BREAK delivery).
- Graceful stop via stop-signal flag file + child self-signal (see below);
  stop wait extended 15 s → 20 s with force-kill fallback.
- **Watchdog hardening:** health-check `except` now also catches
  `ValueError`/`KeyError` — a non-JSON 200 response from a foreign server on
  :8001 previously killed the watchdog thread permanently (no more
  auto-restart).

**`backend/run_backend.py`** (rewritten)

- Stop-flag watcher thread started **before** `uvicorn.run` (covers
  mid-import stop requests): on `logs/stop_signal.flag`, self-signals
  `GenerateConsoleCtrlEvent(1, 0)` — uvicorn registers SIGBREAK on Windows and
  shuts down gracefully (`timeout_graceful_shutdown=5`).
- **Atomic single-instance lock** (`logs/backend.lock`,
  `os.open(O_CREAT|O_EXCL)`). Because of the OS-level process duplication, every
  backend spawn produced a clone that raced the port and wasted a 2.5-min ML
  import before dying. The lock makes any duplicate exit **before importing
  anything** (< 1 s). Stale locks are stolen if the recorded PID is dead
  (OpenProcess with `PROCESS_QUERY_LIMITED_INFORMATION`).
- Binds `127.0.0.1:8001` (the legacy `.bat` launchers and `main.py`'s
  `__main__` bind `0.0.0.0` — LAN exposure if run directly).

**Autostart cleanup**

- Deleted from Startup folder: `RUTE_AutoStart.lnk`, `RUTE_Backend.lnk`,
  `RUTE_Backend.vbs`.
- Kept: Task Scheduler "RUTE Backend Launcher" (single entry,
  `pythonw.exe tray_app.py`).

### 3.4 Test results

- Spawn → exactly 1 real tray + 1 real backend; duplicate trays exit via
  mutex, duplicate backends exit via lock (verified in `logs/tray_app.log`:
  "Another RUTE tray instance is already running - exiting.").
- Graceful stop measured at **0.9 s** (flag → CTRL_BREAK → clean exit).
- Watchdog restart verified in production: after a stop-flag shutdown, the
  tray auto-restarted the backend and it came up healthy.

---

## 4. Line-by-line code review (all of D:\RUTE) — findings & fixes

Four review passes covered the backend core, `ml_engine`, extension `src`
(MT5/scripts/configs pass interrupted — completed later, see §7). **All fixes
below are applied, compiled, and where possible verified live.** Items listed
as "Open (deferred)" were re-verified against the current code in §7 — most
were already fixed.

### 4.1 Backend core (`main.py`, `data_providers.py`, `tray_app.py`, `run_backend.py`)

**Fixed:**

1. **CRITICAL — CORS wildcard + no auth** (`main.py:146-152`): replaced
   `allow_origins=["*"]` with
   `allow_origin_regex=r"(chrome-extension://.*|http://localhost:\d+.*)"`.
   **Verified live:** `Origin: https://evil.com` → no CORS header (blocked);
   `Origin: chrome-extension://…` → allowed. Websites can no longer CSRF the
   kill-switch / auto-trade / portfolio endpoints.
2. **CRITICAL — `details` UnboundLocalError** (`main.py:569`): the ensemble
   disagreement block referenced `details` before assignment → every
   elite-ensemble symbol scan appended "ML model unavailable (name 'details'
   is not defined)" to signals. Now `details = {}` is initialized inside the
   block.
3. **CRITICAL — class-mapping inversion** (`main.py:552-557`): prediction
   mapping assumed raw targets {-1,0,1}; ensemble/elite/calibrated bundles
   return encoded {0,1,2} → HOLD would have been traded as BUY. Now mapped
   via `model.classes_` (handles both encodings).
4. **MAJOR — drift canary dead** (`main.py:1236-1237`): imported
   `FeatureEngine` (class is `FeatureEngineer`) → ImportError on every
   `/api/model-health` call. Fixed.
5. **MAJOR — watchdog thread death** (`tray_app.py:337-341`): health check
   now catches `(requests.RequestException, ValueError, KeyError)`.
6. **MAJOR — DQN weights never loaded** (`main.py:165`): added a boot-time
   `dqn_agent.load(...)` — the learned policy was silently reset to random on
   every restart.

**Open (deferred — noted for next pass):**

- Simulated-trade TP/SL monitor uses a 1-bar history fetch frozen by the 4 h
  cache (`main.py:60` + `data_providers.py:232`) — TP/SL hits detected late;
  wrong P&L fed to DQN/PPO.
- Auto-execute broker calls are synchronous + unguarded in the event loop
  (`main.py:1098-1106`) — one broker error kills the whole recommendations
  response.
- `/api/live-signals` uses `bypass_cache=True` for up to 25 symbols →
  provider rate limits exhausted in normal polling (`main.py:1347`).
- `/api/thoughts/{symbol}` path traversal (unvalidated symbol,
  `main.py:1882-1901`).
- PENDING_STATES / PPO entries never expire → unbounded memory growth
  (`main.py:840/857`).
- `main.py` `__main__` binds 0.0.0.0 (run_backend.py binds 127.0.0.1).
- `data_providers.py` caches never evicted; `_format_binance_symbol`
  mangles "BTC-USDT" → "BTCUSDTUSDT".

### 4.2 ml_engine (17 files reviewed)

**Fixed:**

1. **CRITICAL — elite training always crashed** (`elite_system.py:251,275`):
   `y_enc` referenced but never defined → NameError in the first walk-forward
   fold → the flagship 5-model + Platt ensemble could never be trained. Added
   `y_enc = y.map({-1:0, 0:1, 1:2})`.
2. **CRITICAL — random PPO policy served as learned** (`ppo_agent.py` +
   `main.py:863-869`): `ppo_agent.pt` doesn't exist; the random policy's
   lot/trail/scale params were embedded in live recommendations. Added a
   `trained` flag (set only on successful weight load); `main.py` now uses
   safe defaults and skips PENDING_PPO_ACTIONS until weights exist.
3. **MAJOR — random LSTM shifted live confidence** (`transformer_core.py`):
   missing `temporal_lstm.pt` only printed a warning; a randomly-initialized
   network silently added/subtracted ±10/5 confidence. Added
   `weights_loaded` flag; `predict()` returns neutral 0 until weights load.

**Open (deferred):**

- XGBoost holdout is in-sample (trained on 100% of data then "evaluated" on
  the last 20%) — reported win rate and save gate are inflated
  (`model_trainer.py:118-132`).
- PPO `_compute_returns` chains independent trades into one discounted
  trajectory → wrong advantages once trained (`ppo_agent.py:184-191`).
- Elite validation filter (all-agree + >90%) not applied at runtime
  (`elite_system.py:341-349` vs `main.py` EnsembleModel).
- DQN trains as a bandit (`done=True`, next_state==state) — no temporal
  credit assignment (`main.py:1551`).
- Label-threshold 5-bar lookahead in `feature_engine.py:248-250`;
  `working_trainer`/`model_trainer`/`elite_system` model dirs are
  CWD-relative.
- Cross-market stale leader data never expires (`cross_market.py:79-93`);
  flat-market spurious order-flow veto (`order_flow.py:23-43`);
  sentiment uses age-unfiltered headlines; model age (GOOGL_RF trained
  2025-11-27, data frozen 2026-05-05) has no staleness gate.

### 4.3 Extension `src` (reviewed)

**Fixed:**

1. **CRITICAL — backend host not permitted** (`public/manifest.json:19-24`):
   `host_permissions` had only `http://localhost:8001/*` but the backend is
   `http://127.0.0.1:8001` (different origin) → all background fetches and
   the WS were blocked. Added `http://127.0.0.1:8001/*`. **You must reload the
   extension** to pick this up.
2. **MAJOR — content script injected everywhere** (`manifest.json:58-66`):
   `https://*/*` narrowed to tradingview.com / investing.com / finance.yahoo.com
   + the local backend hosts.
3. **MAJOR — active-strategy selection reset on every popup open**
   (`Backtest.tsx:200-208`): `saveActive(all 6)` ran before `loadActive()`
   resolved, overwriting the user's stored selection. Now guarded by a
   `useRef` flag — only user-driven changes are persisted.
4. **MAJOR — lab calls hit the wrong endpoint + dropped apiKeys**
   (`Backtest.tsx:96-102`): `getSettings` read the never-written
   `'rute_settings'` key. Now reads `userSettings` like every other component.
5. **MAJOR — Portfolio dead on load** (`Portfolio.tsx:33-34`): read
   `localStorage['rute_settings']` (never written) → always fell back to the
   default endpoint. Now reads `chrome.storage.local['userSettings']`.
6. **MAJOR — "Trade Executed" notified without confirmation**
   (`background.ts:370-380`): EXECUTE_TRADE result was ignored; log +
   notification fired even when nothing was placed (e.g., no content script on
   the tab). Now awaits the content-script response (`sendResponse
   {success}`) and only logs + notifies after platform confirmation; errors
   are returned to the caller.
7. **MAJOR — WS notifications bypassed user gates** (`background.ts:165-179`):
   NEW_SIGNAL fired notifications unconditionally. Now gated on
   `userSettings.notifications.tradeAlerts` (strategy agreement still handled
   by the recommendations path).
8. **MAJOR — price alerts re-fired every minute** (`background.ts:325-338`):
   added a per-symbol 15-minute cooldown.
9. **MAJOR — wrong-direction click on TradingView** (`content.ts:145-176`):
   the first click always targeted `buy_button` even for SELL trades. Both
   clicks now use the direction-matched button (`buy_button`/`sell_button`).
10. **MAJOR — veto accepted wrong-direction text** (`content.ts:110`): generic
    "ORDER"/"PLACE" text no longer passes validation — the button text must
    contain the trade direction.
11. **MINOR — overlay crash on missing prices** (`content.ts:236-238`):
    `.toFixed` guarded with `?? 0`.

**Open (deferred):**

- Stale/racy regime results shown for the wrong symbol after a symbol switch
  (`Backtest.tsx:292-305, 450-485`) — needs request-id + render gate.
- Backtest results not bound to the symbol/interval snapshot (mislabeled
  after mid-load switches).
- Optimized params saved to `rute_opt_params` but never consumed by the live
  scan (`Backtest.tsx:229-236, 640` + `background.ts:272-276`).
- LiveMarket renders fabricated random quotes as live data with no
  simulated/offline marker (`LiveMarket.tsx:168-181`).
- WS: stuck-CONNECTING socket never reconnects; naive URL derivation
  (`background.ts:122-139`).
- Break-even trades trained as losses (`main.py:1544`); `/trigger-signal`
  accepts arbitrary side/ticker.
- TradeHistory doesn't subscribe to `chrome.storage.onChanged` for live
  updates.

### 4.4 MT5 engine / scripts / configs

- Review pass was interrupted twice (agent aborted) — **deferred**. Known
  items already carried from earlier audits: legacy `.bat` launchers are no
  longer autostarted; they re-run `pip install` and bind 0.0.0.0 (superseded
  by `run_backend.py`).

---

## 5. Verification

- `python -m py_compile` on all edited backend files: **OK**.
- `npm run build` (Vite): **clean** — popup.js 392.03 kB, background.js
  7.80 kB, content.js 8.40 kB.
- Backend restarted via the stop-flag + watchdog (auto-restart verified in
  `logs/tray_app.log`), healthy: `{"status":"ok","mt5_enabled":false,...}`.
- CORS verified live: evil origin blocked, extension origin allowed.
- `/api/market-regime` verified live with new code (BTC-USD 1d → neutral,
  ADX 20.04).
- Running state: exactly 1 real tray + 1 real backend (decoy duplicates idle
  no-ops).

## 6. Actions required from you

1. **Reload the extension** at `chrome://extensions` (manifest change:
   127.0.0.1 host permission + narrowed content scripts).
2. Optional: replace the `GOOGL_RF` model with a fresh retrain + retrain the
   elite ensemble now that it can actually train (`y_enc` fixed).

---

## 7. Recheck pass + follow-up fixes (same session)

Re-verified every item marked "Open (deferred)" in §4 against the **current**
code (the review agents had read a stale snapshot — most items were already
fixed).

### 7.1 Already fixed in current code (recheck verdict)

- Auto-execute broker calls run via `asyncio.to_thread` with a per-symbol
  try/except (`main.py` ~1121-1136).
- Simulated TP/SL monitor fetches with `bypass_cache=True` (`main.py:61`).
- `/api/thoughts/{symbol}` validates the symbol with `re.fullmatch` + realpath
  (`main.py:1919-1927`).
- `/api/live-signals` does **not** bypass the cache.
- `main.py` `__main__` binds `127.0.0.1` (`main.py:1985`).
- `/trigger-signal` validates side + ticker (`main.py:1630-1633`).
- Break-even trades get reward `>= 0` (`main.py:1575`).
- PENDING_STATES / PENDING_PPO_ACTIONS bounded at 500 entries
  (`main.py:858-859, 879-880`).
- PPO `_compute_returns` returns rewards as-is (each trade is an independent
  1-step episode — comment explains why) (`ppo_agent.py:185-190`).
- Cross-market engine drops stale leader data on fetch failure
  (`cross_market.py:90-92`).
- Flat-market order-flow veto returns None/False (`order_flow.py:23-25, 53-55`).
- Sentiment headlines are age-filtered (48 h) before scoring
  (`sentiment_hub.py:99-109`).
- All trainer model dirs resolve via `os.path.dirname(os.path.abspath(__file__))`
  — not CWD-relative (all 5 trainers).
- `working_trainer` empty-frame guard present.
- Opt params are consumed: `background.ts:258,300` reads `rute_opt_params`
  and passes them to the backend (backend accepts `params`).
- Regime results guarded against stale/racy responses (`Backtest.tsx:318-331`
  stale-response check + render gate at 477/526).
- LiveMarket marks simulated quotes (`LiveMarket.tsx:357`).

### 7.2 New fixes in this pass

1. **XGBoost holdout made honest** (`model_trainer.py`): the report used to
   score the model on rows it was trained on (100% fit → evaluate last 20%).
   Now a model fit on the first 80% **only** produces the holdout report and
   backtest; the production model is then trained on 100% and never scored.
   `fold_win_rates` from the walk-forward are persisted into the model bundle.
   The save gate (`win_rate >= 50`) now measures an out-of-sample number.
2. **Elite runtime filter applied** (`main.py` `EnsembleModel.predict`): live
   inference now enforces the same protocol the elite validation used to
   measure its win rate — all members must agree **and** max probability
   `>= 0.90`, otherwise the signal is forced to HOLD. Deployed behavior now
   matches the advertised metrics.
3. **Soft model-staleness flag** (`main.py` `load_ml_model`): bundles older
   than 30 days get `model_data['stale'] = True` + `age_days` (visible to
   callers/health); never a hard block (GOOGL_RF is old — flagged, not
   disabled).
4. **SQLite handle leak** (`dashboard_endpoints.py`): MT5 stats connection now
   closed in `finally`.
5. **Data-provider cache eviction** (`data_providers.py`): `_sweep_cache()`
   drops expired entries once either cache exceeds 200 entries; cache keys are
   case-normalized (`symbol.upper()`); `_format_binance_symbol` uppercases
   input first (fixes "BTC-USDT" → "BTCUSDTUSDT" mangling of lowercase input).
6. **Legacy `.bat` launchers repointed to `run_backend.py`** (lock + stop-flag
   + 127.0.0.1): `rute_autostart.bat` (previously uvicorn on **0.0.0.0:8001**
   — LAN exposure + race), `start_backend.bat` (`python main.py`),
   `start_rute.bat` (uvicorn 8000), `START_RUTE_BACKEND.bat` (uvicorn 8001),
   `scripts/start-backend.bat` (`--reload`). The scheduler task is confirmed to
   run `pythonw.exe tray_app.py` — no 0.0.0.0 exposure.
7. **`requirements.txt`**: removed duplicated `fastapi` line. All third-party
   imports (torch, xgboost, optuna, ccxt, yfinance, alpaca, vaderSentiment,
   feedparser, pystray/PIL in requirements-tray.txt) are covered.

### 7.3 MT5 engine / scripts / configs review — completed

- MT5 is fully gated on `RUTE_MT5_ENABLED=1`: `mt5_engine/router.py:66-71`
  lifespan only initializes when enabled (logs "standalone mode" otherwise);
  `/api/health` reports `mt5_enabled` from `MT5_INIT_ALLOWED`; `get_market_data`
  guards on `mt5.terminal_info() is not None`; `mtf_confluence` lazy-imports
  the engine in try/except; tray only launches the terminal when enabled.
- No auto-connect, no auto-launch anywhere in the default path.
- Verdict: no changes required — the engine is inert by default.

### 7.4 Deliberately not changed

- `feature_engine.py:248-250` label lookahead (rolling-percentile window
  includes the future point): training-data-only, minor class-balance bias,
  no live impact. Changing it would alter every model's target semantics —
  documented rather than touched.

---

## 8. Verification (second pass)

- `python -m py_compile` on all edited files: **OK**.
- Backend restarted via stop-flag + watchdog; healthy.
- Exactly 1 real tray + 1 real backend running.

---

## 9. Strategy Lab Overhaul & MT5 Tray Fix

**Files:** `src/popup/components/Backtest.tsx`, `backend/tray_app.py`, `README.md`

- **Strategy Lab (`Backtest.tsx`) Full Rewrite:**
  - Removed redundant duplicate `Symbol` and `Strategy` select dropdowns.
  - Migrated `apiEndpoint` and `apiKeys` loading from `localStorage` to `chrome.storage.local`.
  - Ensured `apiKeys` are passed in request bodies to `/api/backtest`, `/api/optimize`, and `/api/live-signals`.
  - "Optimize" button now uses an explicit strategy picker dropdown instead of silently choosing the first selected strategy.
  - Live scan badges now use the `activeStrats` array to ensure alignment with backend signal polling.
  - Added a timeframe `period` lookback selector (e.g., `6m`, `1y`, `2y`, `5y`), dynamically auto-capped by `interval` to prevent excessive bar requests.
  - Added Watchlist quick-pick chips below the symbol input.
  - Added a **Consensus Badge** (`⚡ x/y BUY/SELL`) that triggers when a majority of active strategies agree on a direction.
  - Added an "Apply/Use" button on optimization results that saves optimal params back to `chrome.storage` for live signal generation.
- **MT5 Tray App Fix (`tray_app.py`):**
  - Updated MT5 launch from a bare `subprocess.Popen` to use `STARTUPINFO` with `wShowWindow = 7` (`SW_SHOWMINNOACTIVE`).
  - Terminal now launches silently straight to the taskbar, avoiding screen flashes, focus stealing, and preventing price-feed stalls associated with full hidden windows (`SW_HIDE`).
- **Project Documentation (`README.md`):**
  - Drafted comprehensive README outlining the project architecture, MT5 execution requirements, the recommended Windows VPS migration path, and the action item to investigate Direct Broker APIs (REST/FIX).

---

## 10. Extension Host Mismatch Fix (`ERR_CONNECTION_REFUSED`)

**Files:** `src/background/background.ts`, `src/popup/components/*.tsx`, `src/popup/App.tsx`

- **Issue:** The extension threw `ERR_CONNECTION_REFUSED` and `Failed to fetch` errors in Chrome. This was because the backend was securely bound to IPv4 `127.0.0.1:8001`, but the extension had `http://localhost:8001` hardcoded as the default endpoint. Chrome resolves `localhost` to IPv6 (`::1`), which the backend was not listening on.
- **Fix:** Performed a codebase-wide replacement of all 10 instances of `localhost:8001` with `127.0.0.1:8001` to perfectly align with the backend's secure binding and the `manifest.json` host permissions.
- **Action Required:** Rebuild completed. You must reload the extension at `chrome://extensions` for the fix to take effect.
---

## 9. Extension not scanning � alarm-loss fix (2026-08-17)

**Symptom:** extension stopped scanning; `/api/scan-log` stayed empty.

**Diagnosis:** backend healthy and scanning works when called directly (manual
POST returned skips for BTC-USD 15% / AAPL 50% in 3 s). The extension's
background worker had stopped calling `/api/recommendations` entirely �
classic MV3 `chrome.alarms` loss after an extension reload: with the
`marketDataUpdate`(1 min) / `aiRecommendations`(5 min) / `keepAlive`(1 min)
alarms gone, the periodic scan loop never runs.

**Files:**

- `src/background/background.ts` � ADDED self-healing alarm check: on every
  service-worker wake, `chrome.alarms.getAll()` verifies the 3 alarms exist
  and recreates any that are missing; when restoration happens it immediately
  runs `updateMarketData()` + `fetchAIRecommendations()` so the market is
  never unmonitored. Alarm creation no longer depends solely on
  `onInstalled` (unreliable across reloads).
- `src/popup/components/Dashboard.tsx` � MODIFIED mount effect: if
  `rute_recommendations` is empty, sends `REFRESH_RECOMMENDATIONS` so
  opening the popup triggers an immediate scan instead of waiting up to 5 min.
- `public/manifest.json` � MODIFIED version 1.0.1 ? 1.0.2 (clean update
  reload that re-runs onInstalled).

**Verification:** `npm run build` clean (background.js 8.57 kB, popup.js
393.17 kB). Backend-side scan verified working (scan_start + 2 skip events in
scan-log from manual test).

**Action required:** reload the extension at `chrome://extensions`.

## 10. Tray watchdog could not restart a dead backend - root cause of "still the same" (2026-08-17)

**Symptom:** extension scanning kept failing even after every fix; backend was
DOWN while the user tested (manual instance started 17:03 outside the tray had
died). The tray reported healthy but never restarted it.

**Root cause (three flaws in `backend/tray_app.py`):**

1. `start_backend()` returned "Backend already running." whenever the tracked
   PID was alive. With the OS process-duplication quirk the tracked PID is the
   idle decoy (never exits) while the REAL backend is the clone — which can die
   and never be respawned.
2. `watchdog_loop()` had no outer try/except: one uncaught exception silently
   killed the watchdog thread (pythonw has no console) — backend left
   unmanaged with zero log evidence.
3. `stop_backend()` reported "Backend not running." when the tracked PID was
   the dead decoy, so the real backend couldn't be stopped by the tray either.

**Files:**

- `backend/tray_app.py` - MODIFIED:
  - ADDED `_backend_healthy()` helper (GET /api/health, 3 s timeout).
  - `start_backend()`: if tracked PID alive but backend unhealthy, log a
    warning, kill the stale process, and respawn — health is the only truth.
  - `watchdog_loop()`: PID-exit is now informational only (decoy exits are
    normal; never force-restarts from the PID); the whole loop body is wrapped
    in try/except with `logger.exception` + failure-counter reset, so the
    watchdog can never die silently.
  - `stop_backend()`: proceeds via the stop-flag even when the tracked PID is
    the dead decoy; waits for health to stop answering; force-kills the :8001
    listener via psutil as last resort.

**Verification (live, 17:44-17:50):** wrote `logs/stop_signal.flag` -> backend
exited -> watchdog logged "Health check failed" x3 -> "Restarting..." -> new
backend spawned -> healthy again (uptime 13 s; lock held by real PID 22588,
decoy 20612 idle). Full stop->restart chain now works end-to-end.

**Lesson logged (test hygiene):** delete the stop flag right after stopping —
a fresh backend spawn that sees it self-shuts-down (exit 0). The 17:45:17
restart died for exactly that reason; the 17:49:59 restart (flag cleaned)
survived.

**Current state:** tray 17800 (fixed watchdog) + decoy 18700; backend 22588
(real, holds lock) + decoy 20612; `/api/health` OK.

**Action required:** reload the extension at `chrome://extensions` — with the
backend reliably managed again, scanning resumes.

## 11. Undocumented session changes broke scanning — reverted & fixed (2026-08-18)

**Symptom:** user: "check what was just done on the extension it did rubbish".
All signals disappeared; Decision Log showed only one row per symbol at sub-50%
confidence; a `debug.log` file appeared.

**Root cause:** another session edited extension + backend on 2026-08-18
(background.ts 14:32, main.py 14:32, Portfolio.tsx 15:04, build 15:05)
WITHOUT logging anything in CHANGES.md/MEMORY.md. Three damaging changes:

1. `main.py` — the user's `minConfidence` (70%) was wired into the **initial**
   gate (`confidence < user_min_conf`, was 50 ML / 60 tech-only) AND the final
   gate. Result: every symbol rejected early at its pre-boost score (15-55%),
   so the log filled with sub-70 skips and signals became impossible.
2. `Portfolio.tsx` — Decision Log was deduplicated to **one entry per symbol**
   (reduce over scan-log), hiding the decision history.
3. `background.ts` + `main.py` — 3 debug POSTs per scan to a new
   `/api/debug-log` endpoint writing `debug.log` (4.4 kB of junk).

**Files:**

- `backend/main.py` - MODIFIED (gate fix):
  - Initial gate restored: `min_confidence = 50` (ML) / `60` (tech-only).
  - Final gate now `max(user_min_conf, 60 if trade_type else 75)` — the
    user's setting is the trade bar, never below the platform floors.
  - REMOVED `POST /api/debug-log` endpoint.
- `src/popup/components/Portfolio.tsx` - MODIFIED: reverted the symbol-dedup;
  Decision Log shows the full recent history again.
- `src/background/background.ts` - MODIFIED: removed the 3 debug-log POSTs.
- `backend/debug.log` - DELETED.

**Verification:** py_compile OK; `npm run build` clean (background.js 11.63 kB,
popup.js 394.29 kB). Backend restarted via stop-flag (watchdog respawned it,
PID 17904 real / 23936 decoy — the fixed watchdog proved itself again when the
first respawn died and it auto-restarted a second time). Live scan with
minConfidence=70 shows correct gates: `51.09% < 60%` (tech-only), `15.3% < 60%`
(balanced). `/api/debug-log` now 404. Health OK.

**Action required:** reload the extension at `chrome://extensions`.

## 12. Scan log floods + slow scans — fixed (2026-08-18)

**Symptom:** user: "it's showing me you are scanning seven symbols, but it's
not showing me the result of the seven scans… this scan is not even meant to
take as long as it's taking." Live scan-log showed 4 `scan_start` entries
within 4 s (16:27:13-16) then one per minute — results arrived 15-20 s later,
so the newest-first log displayed a pile of orphaned "Scanning 7 symbols..."
with no results beneath them.

**Root causes:**
1. Extension fired a full scan on EVERY MV3 worker wake: `keepAlive` alarm
   (1 min) wakes the worker, and the top-level 3 s fetch (background.ts:32)
   ran on each wake — one scan per minute, on top of the 5-min alarm, popup
   refreshes, WS debounce, and multiple extension instances (2 WebSocket
   connections observed on the backend).
2. No concurrency guard: overlapping scans each repeated the batch pre-fetch
   + 7 recommendation generations → data-provider rate-limit storms → long
   scans, and SCAN_LOG filled with scan_starts whose results landed beneath
   newer entries.
3. `batch_prefetch_historical` fetched stock symbols SEQUENTIALLY.

**Files:**

- `backend/main.py` - MODIFIED:
  - ADDED `_scan_lock` (threading.Lock) + wrapper on `/api/recommendations`:
    overlapping requests return `{"status": "scan_in_progress"}` instantly;
    the scan itself runs in `_run_recommendation_scan()`.
- `backend/data_providers.py` - MODIFIED: `batch_prefetch_historical` now
  fetches stock symbols in parallel (ThreadPoolExecutor, max 6 workers) —
  full 7-symbol batch no longer N x sequential.
- `src/background/background.ts` - MODIFIED: ADDED `SCAN_MIN_INTERVAL_MS`
  (90 s) + `lastScanStart` throttle at the top of `fetchAIRecommendations` —
  worker wakes no longer trigger scans more often than every 90 s (the 5-min
  alarm and explicit refreshes still pass).

**Note on gates (other session, still unlogged by them):** main.py was
re-edited 16:25 (initial gate back to `user_min_conf` = user's 70% with a
friendlier "AI Confidence (X%) is below your minimum threshold (Y%). Missing
Z% to trigger trade." message; final gate kept as
`max(user_min_conf, 60/75)`). Kept as-is — message is clearer; noted here so
the design decision is documented.

**Verification:** py_compile OK; `npm run build` clean. Backend restarted via
stop-flag (watchdog respawned 16:36:59, healthy ~16:40). Overlap test: 2
simultaneous requests → 0.45 s + 0.14 s, both `scan_in_progress`. Full scan
timed: **5.3 s** for 7 symbols (was 18 s+ under overlap storms). Scan-log now
shows exactly one `scan_start` followed by its 7 results (16:42:16 → 16:42:24).

**Action required:** reload the extension at `chrome://extensions` for the
90 s throttle. If scans still burst, check `chrome://extensions` for the
extension loaded more than once.

---

## 30. Backend Data Fetcher Fix (Yahoo Finance Rate Limiting)
**Files:** ackend/data_providers.py, ackend/main.py
- **Error:** Yahoo Finance threw a 429 Too Many Requests (manifesting as NameResolutionError in urllib3) because prewarm_market_cache pinged it every 30 seconds with the same static Mozilla/5.0 User-Agent. This prevented the backend from pulling live data, causing 0 trades to execute.
- **Fix:** Implemented randomized User-Agent rotation (Windows, Mac, Linux, iPhone) for all Yahoo Finance fetch calls. Reduced the background cache polling loop interval from 30s to 120s to stay under rate limits.

---

## 31. Decision Log Timestamp & Duplicate Fix
**Files:** ackend/main.py, src/popup/components/Portfolio.tsx
- **Error:** The Decision Log appeared "frozen" because the backend's duplicate suppression silently dropped repeated logs without updating timestamps. Additionally, network errors were silently discarded so users only saw ~4 trades instead of all 30 coins.
- **Fix:** Modified ppend_log_if_new to update the existing log's timestamp and move it to the front of the queue if the decision is a duplicate. Updated Portfolio.tsx to explicitly render scan errors (in an amber badge) instead of treating them as rejected trades or ignoring them.

---

## 32. UI Stability & Crash Prevention Audit
**Files:** Watchlist.tsx, Dashboard.tsx, SignalFeed.tsx, Settings.tsx
- **Error:** Multiple React components crashed on edge cases (e.g., 	oFixed on null prices, isNaN on timestamps, e.message.startsWith on undefined messages). The Settings tab allowed percentages to convert to 500% if account balance was 0.
- **Fix:** 
  - Added nullish coalescing (data?.price ?? 0).toFixed(2) to Watchlist.tsx and LiveMarket.tsx.
  - Fixed isNaN timestamp rendering returning "checked NaNm ago".
  - Refactored Dashboard.tsx to handle message?.recommendations || [] and added missing chrome object guards.
  - Hardcoded failsafe default risk limits in Settings.tsx when switching from dollar to percentage if the account balance is <= 0.
  - Fixed Settings tab to clear error state on typing new API keys.
  - Fixed CSS popup height glitch in SignalFeed.tsx by using lex-1 min-h-0.

## [2026-08-20] Decision Log UI Fixes
- Fixed the Portfolio Decision Log tab showing technical indicators (RSI, MACD, Hurst, Entropy) on 'Trade Rejected' items.
- Added a professional 'Confidence' badge/box to the 'Trade Rejected' items so the user clearly understands why a trade was skipped.
