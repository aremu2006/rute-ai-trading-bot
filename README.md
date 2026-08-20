# RUTE -- Project README and Way Forward

## What RUTE Is

A Chrome Extension + Python backend trading assistant.

---

## Current Status (Aug 2026)

- Tray app (autostart, watchdog, icon): DONE
- MT5 launch SW_SHOWMINNOACTIVE (no flash, no focus steal): DONE
- Strategy Lab Backtest.tsx audit + 8 bug fixes: DONE
- Backend data providers (yfinance removed): DONE
- Extension WebSocket backoff + chrome.storage fixes: DONE
- Auto-trader fractional sizing + breakeven stops: DONE
- VPS migration: PLANNED
- Broker direct API bypass investigation: PLANNED

---

## MT5 Visibility -- Options

### The key distinction

MT5 must run *somewhere* with an active Windows session.
It does NOT have to run on your laptop or be visible to you.

### Option 1 -- Minimized on your machine (DONE)

tray_app.py now launches MT5 with SW_SHOWMINNOACTIVE (wShowWindow=7).
The terminal goes straight to the taskbar -- no flash, no focus steal.
SW_HIDE (0) is intentionally avoided as some broker builds stall the price feed when the window is fully hidden.

Solves: visibility annoyance.
Does NOT solve: your laptop must stay on for the bot to trade.

### Option 2 -- Windows VPS (RECOMMENDED LONG TERM)

Move the entire backend + MT5 to a Windows VPS.
Your extension apiEndpoint changes from http://localhost:8001 to http://<vps-ip>:8001.

Codebase changes needed:
  1. main.py: add CORS allowed origins for your home IP
  2. .env: RUTE_MT5_ENABLED=1, MT5_TERMINAL_PATH=...
  3. Extension Settings: update apiEndpoint
  4. Optional: Nginx + TLS in front of Uvicorn

Solves: laptop dependency, visibility, 24/7 uptime.
Cost: ~-25/month (Vultr Windows Server 2022, Contabo, etc.)

### Option 3 -- Broker direct API (INVESTIGATE THIS FIRST)

Some brokers that offer MT5 also expose a REST or FIX API on the same account.
If your broker does this, mt5_engine/ can be replaced entirely -- no terminal at all.

How to check:
  1. Log in to your broker client portal
  2. Look for: API Access, FIX Protocol, cTrader Open API, REST API
  3. Brokers with direct APIs: IC Markets (cTrader), Pepperstone (cTrader),
     OANDA (v20 REST), Interactive Brokers (TWS / IBKR REST)

ACTION ITEM: Check your broker BEFORE planning the VPS move.
This is the most impactful single decision in the roadmap.

### Option 4 -- Wine + Xvfb on Linux (NOT RECOMMENDED)

Technically possible. Unsupported by MetaQuotes. Breaks on terminal updates.
Not appropriate for live capital.

---

## Next Steps (Priority Order)

1. CHECK BROKER API -- most impactful, changes the whole architecture
2. VPS MIGRATION -- if broker check is negative (MT5 only)
3. EXTENSION POLISH:
   - App.tsx: reads localStorage instead of chrome.storage (header balance bug)
   - Settings.tsx: native select for broker dropdown (styling mismatch)
   - ConfirmationModal.tsx: unguarded .toFixed() calls (crash risk)

---

## Running Locally

    # Backend + tray
    cd D:\RUTE\backend
    venv\Scripts\python tray_app.py

    # Extension dev watch
    cd D:\RUTE
    npm run dev

    # Load in Chrome: chrome://extensions -> Load unpacked -> D:\RUTE\dist

---

## Environment Variables (.env)

    RUTE_MT5_ENABLED=0
    MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
    FINNHUB_API_KEY=
    TWELVE_DATA_API_KEY=
    ALPHA_VANTAGE_API_KEY=

API keys can also be set in the extension Settings tab.
They are saved to chrome.storage.local and sent with every backend request.