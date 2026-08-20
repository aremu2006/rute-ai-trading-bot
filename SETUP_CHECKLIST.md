# RUTE Setup Checklist

Follow this checklist to get RUTE running successfully.

## Pre-Setup Requirements

- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.9+ installed (`python --version`)
- [ ] npm installed (`npm --version`)
- [ ] Chrome browser installed
- [ ] Terminal/command prompt ready

## Initial Setup

### 1. Frontend Setup
- [ ] Navigate to RUTE directory
- [ ] Run `npm install`
- [ ] Wait for dependencies to install (may take 2-3 minutes)
- [ ] Verify no errors in output

### 2. Backend Setup
- [ ] Navigate to `backend/` directory
- [ ] Create virtual environment: `python -m venv venv`
- [ ] Activate virtual environment:
  - Windows: `venv\Scripts\activate`
  - macOS/Linux: `source venv/bin/activate`
- [ ] Install requirements: `pip install -r requirements.txt`
- [ ] Wait for packages to install (may take 3-5 minutes)
- [ ] Verify no errors

### 3. Build Extension
- [ ] Return to root RUTE directory
- [ ] Run `npm run build`
- [ ] Verify `dist/` folder is created
- [ ] Check for `dist/popup/`, `dist/background.js`, `dist/content.js`
- [ ] Verify `dist/manifest.json` exists

### 4. Chrome Extension Installation
- [ ] Open Chrome browser
- [ ] Navigate to `chrome://extensions/`
- [ ] Enable "Developer mode" toggle (top-right)
- [ ] Click "Load unpacked" button
- [ ] Select the `dist/` folder from RUTE directory
- [ ] Verify RUTE appears in extension list
- [ ] Verify RUTE icon appears in Chrome toolbar
- [ ] Check for any error messages

### 5. Start Backend Server
- [ ] Open new terminal
- [ ] Navigate to `backend/` directory
- [ ] Activate virtual environment (if not already)
- [ ] Run: `python -m uvicorn main:app --reload`
- [ ] Verify server starts on port 8000
- [ ] Check for "Uvicorn running on http://127.0.0.1:8000"
- [ ] Open browser to `http://localhost:8000/docs`
- [ ] Verify FastAPI documentation page loads

## First Run Test

### 6. Extension Popup Test
- [ ] Click RUTE icon in Chrome toolbar
- [ ] Popup window appears (420px width)
- [ ] See "RUTE AI Trading Assistant" header
- [ ] See "Live" indicator with green dot
- [ ] See navigation tabs at bottom
- [ ] No console errors (press F12 to check)

### 7. Add Watchlist Symbol
- [ ] Click "Watchlist" tab
- [ ] Type "AAPL" in input field
- [ ] Select "Stock" option
- [ ] Click "Add" button
- [ ] Verify AAPL appears in list
- [ ] Wait 30 seconds
- [ ] Check if price data loads
- [ ] Verify price and percentage change appear

### 8. Get AI Recommendation
- [ ] Add more symbols (TSLA, MSFT, GOOGL)
- [ ] Wait for market data to load
- [ ] Click "Dashboard" tab
- [ ] Click "Refresh" button
- [ ] Wait 10-15 seconds
- [ ] Verify recommendations appear
- [ ] Check recommendation has:
  - [ ] Symbol name
  - [ ] BUY or SELL badge
  - [ ] Entry price, stop-loss, take-profit
  - [ ] Confidence percentage
  - [ ] Technical indicators list
  - [ ] Market trend
  - [ ] AI reasoning summary

### 9. Execute Test Trade
- [ ] Select a recommendation
- [ ] Click "Execute Trade" button
- [ ] Confirmation modal appears
- [ ] Review trade details
- [ ] Click "Confirm & Execute"
- [ ] Verify execution overlay appears
- [ ] Click "History" tab
- [ ] Verify trade appears in history
- [ ] Check statistics updated

### 10. Settings Configuration
- [ ] Click "Settings" tab
- [ ] Modify "Max Position Size" to 2000
- [ ] Modify "Stop Loss %" to 3
- [ ] Modify "Take Profit %" to 6
- [ ] Toggle a notification setting
- [ ] Click "Save Settings"
- [ ] Verify "Settings Saved!" message
- [ ] Close and reopen popup
- [ ] Verify settings persisted

## Verification Tests

### Backend API Tests
- [ ] Test health endpoint:
  ```bash
  curl http://localhost:8000/api/health
  ```
  Should return: `{"status":"healthy",...}`

- [ ] Test market data endpoint:
  ```bash
  curl -X POST http://localhost:8000/api/market-data \
    -H "Content-Type: application/json" \
    -d '{"symbols": ["AAPL"]}'
  ```
  Should return market data JSON

### Extension Functionality
- [ ] Notifications work (if enabled)
- [ ] Market data updates automatically
- [ ] Trade history persists after closing popup
- [ ] Watchlist persists after closing popup
- [ ] Settings persist after closing popup
- [ ] No console errors
- [ ] No memory leaks (check Task Manager)

## Trading Platform Integration Test

### TradingView Test (Optional)
- [ ] Open https://www.tradingview.com/chart/
- [ ] Open any stock chart (e.g., AAPL)
- [ ] Execute trade from RUTE
- [ ] Verify trade overlay appears on TradingView page
- [ ] Check browser console for content script logs

### Investing.com Test (Optional)
- [ ] Open https://www.investing.com/
- [ ] Navigate to any stock
- [ ] Execute trade from RUTE
- [ ] Verify overlay appears

## Troubleshooting

If any step fails:

### Extension won't load:
- [ ] Check `dist/` folder exists
- [ ] Verify manifest.json in dist/
- [ ] Run `npm run build` again
- [ ] Check Chrome console for errors

### Backend won't start:
- [ ] Verify Python version 3.9+
- [ ] Check virtual environment is activated
- [ ] Reinstall requirements
- [ ] Check port 8000 is not in use

### No recommendations:
- [ ] Backend server running?
- [ ] Symbols added to watchlist?
- [ ] Valid stock symbols?
- [ ] Check browser console
- [ ] Check backend terminal logs
- [ ] Try refreshing manually

### Market data not loading:
- [ ] Check internet connection
- [ ] yfinance may be rate limited (wait 2 min)
- [ ] Try different symbols
- [ ] Check backend logs

## Post-Setup

After everything works:

- [ ] Bookmark `http://localhost:8000/docs` for API reference
- [ ] Read TESTING.md for comprehensive testing
- [ ] Read README.md for full documentation
- [ ] Consider creating extension icons (see CREATE_ICONS.md)
- [ ] Set up git repository (optional)
- [ ] Create .env file for API keys (optional)

## Daily Usage

When using RUTE regularly:

1. [ ] Start backend server first
2. [ ] Open Chrome and click RUTE icon
3. [ ] Verify "Live" status indicator
4. [ ] Monitor recommendations on Dashboard
5. [ ] Review and confirm trades carefully
6. [ ] Check history periodically
7. [ ] Adjust risk settings as needed

## Shutdown

When done:

- [ ] Close RUTE popup
- [ ] Stop backend server (Ctrl+C in terminal)
- [ ] Deactivate virtual environment: `deactivate`
- [ ] (Optional) Close Chrome

## Final Checks

- [ ] Extension icon visible in Chrome
- [ ] Backend accessible at http://localhost:8000
- [ ] Can add/remove watchlist items
- [ ] AI recommendations generate
- [ ] Trade execution workflow works
- [ ] Trade history records correctly
- [ ] Settings save and load
- [ ] No critical errors in consoles

## Status

Mark your overall setup status:

- [ ] ✅ COMPLETE - Everything working perfectly
- [ ] ⚠️ PARTIAL - Some features working, some issues
- [ ] ❌ FAILED - Major issues preventing use

---

**Congratulations!** If all items are checked, RUTE is fully operational! 🎉

Start trading with AI-powered recommendations! (But remember: start with small amounts and use risk management!)

For help: Review README.md, TESTING.md, or check console logs.
