# Full System Audit & Upgrade Roadmap

Complete deep-dive analysis of every file across both `D:\RUTE` and `C:\Users\User\.gemini\antigravity\scratch`.

---

## 🔴 CRITICAL BUGS (Must Fix Before Merge)

These are bugs that are actively breaking functionality or causing silent failures right now.

### 1. DQN Reinforcement Learning is Completely Dead
**File:** [main.py](file:///D:/RUTE/backend/main.py) (Line 673)
- The `/api/trade-outcome` endpoint calls `dqn_agent.replay()`, but `dqn_agent.remember()` is **never called anywhere**. The DQN's memory buffer is permanently empty — it has never learned a single thing.
- **Fix:** Wire up `remember(state, action, reward, next_state)` during trade execution flow.

### 2. LSTM Temporal Engine Runs on Random Weights
**File:** [transformer_core.py](file:///D:/RUTE/backend/ml_engine/transformer_core.py)
- The `TemporalEngine` creates a fresh LSTM with **random weights** every time the feature dimensions change. There is no `train()` function and no saved weights file. Every "prediction" is pure noise.
- **Fix:** Add a training pipeline and `torch.save`/`torch.load` persistence.

### 3. Sentiment Hub is a Stub (Always Returns 0.0)
**File:** [sentiment_hub.py](file:///D:/RUTE/backend/ml_engine/sentiment_hub.py)
- `get_ticker_sentiment()` is hardcoded to return `0.0` (Neutral). Zero news analysis is actually happening.
- **Fix:** Integrate HuggingFace `ProsusAI/finbert` or a news API.

### 4. Correlation Data Tuple Bug
**File:** [main.py](file:///D:/RUTE/backend/main.py) (Line 421)
- Trailing comma creates a 1-tuple instead of a list: `correlations = [...],` — this silently breaks the Temporal Engine's cross-market feature stacking.
- **Fix:** Remove the trailing comma.

### 5. Optuna Tunes Against Synthetic Noise, Not Real Model Output
**File:** [ultimate_server.py](file:///C:/Users/User/.gemini/antigravity/scratch/ultimate_server.py) (Lines 758–767)
- The Optuna objective function uses `np.abs(features).mean() / 100` as a fake "confidence score" instead of actually running the XGBoost/LSTM ensemble. It's optimizing against random noise.
- **Fix:** Run genuine ensemble inference during historical trade replay.

### 6. No Feature Scaling Before LSTM Inference
**File:** [ultimate_server.py](file:///C:/Users/User/.gemini/antigravity/scratch/ultimate_server.py)
- Raw features (RSI 0–100, ATR varying wildly, volume in millions) are fed directly into the LSTM without any `StandardScaler` or `MinMaxScaler`. Neural networks perform terribly with unscaled inputs.
- **Fix:** Fit and save a scaler during training; apply it before every inference.

### 7. Daily Loss Tracking Only Counts Unrealized P&L
**File:** [auto_trader.py](file:///D:/RUTE/backend/trading_engine/auto_trader.py) (Line 318)
- `self.daily_loss = min(0, total_pl)` only measures open position P&L. If you close 5 losing trades and then open a new one that's green, the daily loss resets to zero. The circuit breaker is effectively broken.
- **Fix:** Accumulate realized closed-trade losses into the daily counter.

---

## 🟡 HIGH PRIORITY UPGRADES

### 8. MT5 WebRequest Freezes the Entire EA
**File:** [ML_Pure_Core_V15_Ultimate.mq5](file:///C:/Users/User/.gemini/antigravity/scratch/ML_Pure_Core_V15_Ultimate.mq5) (Lines 423–428)
- `WebRequest` runs on the main tick thread with a 5-second timeout × 3 retries = up to **15 seconds** of total freeze per tick. During this time, no trailing stops, no scale-outs, no risk management runs.
- **Upgrade:** Replace with async WebSocket/ZeroMQ communication or use a DLL-free async socket approach.

### 9. SuperTrend Fetches 900 Bars on Every Single Prediction
**File:** [ultimate_server.py](file:///C:/Users/User/.gemini/antigravity/scratch/ultimate_server.py) (Lines 486–525)
- `compute_mtf_supertrend()` fetches 300 candles for H1, H4, and D1 from MT5 on every `/predict` call. This adds ~500ms+ of IPC latency to every tick.
- **Upgrade:** Implement an in-memory TTL cache (e.g., cache H4/D1 data for 5 minutes since it barely changes).

### 10. DQN Architecture is Outdated
**File:** [dqn_agent.py](file:///D:/RUTE/backend/ml_engine/dqn_agent.py)
- Missing Target Network (standard in DQN since 2015).
- Replay loop backpropagates sample-by-sample instead of vectorized batch tensors.
- No model save/load.
- **Upgrade:** Add Target Network, vectorize batch ops, implement Double DQN (DDQN), or upgrade to PPO/SAC.

### 11. MQL5 JSON Parsing is Fragile
**File:** [ML_Pure_Core_V15_Ultimate.mq5](file:///C:/Users/User/.gemini/antigravity/scratch/ML_Pure_Core_V15_Ultimate.mq5) (Lines 434–453)
- Hand-rolled `StringFind` + `StringSubstr` JSON parsing. If the server ever changes the JSON field order or adds a nested object, parsing silently breaks.
- **Upgrade:** Replace with MQL5's `JAson.mqh` library.

### 12. News Distance is Always Hardcoded to 1440 Minutes
**Files:** Both [ultimate_server.py](file:///C:/Users/User/.gemini/antigravity/scratch/ultimate_server.py) and [ML_Pure_Core_V15_Ultimate.mq5](file:///C:/Users/User/.gemini/antigravity/scratch/ML_Pure_Core_V15_Ultimate.mq5) (Line 414)
- The EA sends `newsDistMins = 1440.0` (24 hours) as a constant, even though it already has access to `MqlCalendarValue` events. The ML model's "news awareness" feature is wasted.
- **Upgrade:** Compute actual minutes to the nearest high-impact event from the MQL5 calendar.

### 13. Elite Ensemble Has Severe Class Imbalance
**File:** [elite_system.py](file:///D:/RUTE/backend/ml_engine/elite_system.py)
- After filtering, `target == 0` (HOLD) is ~99% of all samples. Models learn to predict HOLD almost exclusively.
- **Upgrade:** Apply SMOTE oversampling or class weighting.

### 14. Data Miner Labels Are Unrealistic
**File:** [data_miner.py](file:///C:/Users/User/.gemini/antigravity/scratch/data_miner.py)
- Labels trades by checking price 10 bars ahead, ignoring whether SL/TP would have been hit in between. Also injects constant context features `[0.05, 50.0, 1440.0]`, teaching the model zero variance.
- **Upgrade:** Simulate bar-by-bar SL/TP execution; randomize context features.

---

## 🟢 MEDIUM PRIORITY UPGRADES

### 15. Hurst Exponent Can Crash on Flat Bars
**File:** [adaptive_system.py](file:///D:/RUTE/backend/ml_engine/adaptive_system.py)
- `np.polyfit(np.log(lags), np.log(tau), 1)` crashes if `tau` contains zero (flat-price bars).
- **Fix:** Add `tau = np.maximum(tau, 1e-10)` guard.

### 16. Order Flow Uses Simulated Volume Profile
**File:** [order_flow.py](file:///D:/RUTE/backend/ml_engine/order_flow.py)
- Splits daily bar volume uniformly across the high-low range instead of using real Level-2 order book data.
- **Upgrade:** Connect to Alpaca L2 WebSocket for real order book depth.

### 17. Alpaca Broker Truncates Fractional Shares
**File:** [alpaca_broker.py](file:///D:/RUTE/backend/trading_engine/alpaca_broker.py) (Line 97)
- `qty = int(order.quantity)` drops fractional shares. A $50 account trying to buy AAPL at $200 gets `qty=0`.
- **Fix:** Use Alpaca's fractional share API (`qty=0.25`).

### 18. Blocking yfinance Calls in Async FastAPI
**File:** [main.py](file:///D:/RUTE/backend/main.py)
- All `yf.Ticker().history()` calls are synchronous and block the async event loop, stalling all other concurrent requests.
- **Upgrade:** Wrap in `asyncio.to_thread()` or use `httpx` async client.

### 19. MQL5 News Filter Fails on Non-Forex Symbols
**File:** [ML_Pure_Core_V15_Ultimate.mq5](file:///C:/Users/User/.gemini/antigravity/scratch/ML_Pure_Core_V15_Ultimate.mq5) (Lines 299–307)
- `StringSubstr(chart_symbol, 0, 3)` assumes 6-char currency pair format. Fails on `US30`, `GER40`, `XAUUSD`, `SILVER`, etc.
- **Fix:** Add symbol-type detection and currency mapping table.

### 20. Reasoning Engine Uses Thousands of Tiny JSON Files
**File:** [thought_logger.py](file:///D:/RUTE/backend/reasoning_engine/thought_logger.py)
- Creates individual JSON files for every thought step. After months of trading, this becomes tens of thousands of files.
- **Upgrade:** Migrate to SQLite or append-mode JSONL.

### 21. Chrome Extension Background Worker State Resets
**File:** [background.ts](file:///D:/RUTE/src/background/background.ts)
- MV3 service workers get killed by Chrome when idle. In-memory `activeRecommendations` and `marketDataCache` are lost.
- **Fix:** Persist to `chrome.storage.local` on every update.

---

## 🔵 NEW FEATURE OPPORTUNITIES (Post-Merge)

| # | Feature | Description | Difficulty |
|---|---------|-------------|------------|
| 1 | **Cross-Market Leading Indicators** | Train AI to detect when US equity sell-offs predict crypto drops (and vice versa) using both data feeds | Hard |
| 2 | **LLM News Analyst** | Integrate Gemini/Claude API to read financial news and veto trades before high-impact events | Medium |
| 3 | **Unified React Dashboard** | Show MT5 Forex/Crypto trades AND Alpaca stock trades on one screen with a master kill switch | Medium |
| 4 | **Kelly Criterion Capital Allocator** | Dynamically shift capital between MT5 and Alpaca based on which market currently has the highest edge | Medium |
| 5 | **PPO/SAC Reinforcement Learning** | Replace the broken DQN with a modern RL algorithm that learns continuous actions (lot size, trailing distance) | Hard |
| 6 | **Live FinBERT Sentiment** | Replace the stub `SentimentHub` with real-time NLP on financial headlines | Medium |
| 7 | **Sparkline Charts in Extension** | Replace "Chart coming soon" placeholder in LiveMarket with inline SVG sparklines | Easy |
| 8 | **Draggable Trade Overlay** | Make the content script overlay draggable and minimizable so it doesn't block trading charts | Easy |
| 9 | **Trade History CSV Export** | Add "Export to CSV" button in the History tab for trade journaling | Easy |
| 10 | **Walk-Forward Validation** | Replace static 80/20 train/test splits with purged walk-forward cross-validation to prevent data leakage | Medium |

---

## Summary

| Category | Count |
|----------|-------|
| 🔴 Critical Bugs | 7 |
| 🟡 High Priority Upgrades | 7 |
| 🟢 Medium Priority Fixes | 7 |
| 🔵 New Feature Opportunities | 10 |
| **Total Items** | **31** |

> [!IMPORTANT]
> The 7 critical bugs mean that several "AI" components (DQN, Temporal LSTM, Sentiment Hub, Optuna tuner) are currently **not actually doing anything useful**. Fixing these alone would massively improve the system's real-world trading performance.
>
> **Do you want me to proceed with the merge + fix all critical bugs + implement selected upgrades?** If so, let me know which of the 🔵 New Features you'd also like included.
