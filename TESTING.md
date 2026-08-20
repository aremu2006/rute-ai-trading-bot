# RUTE Testing Guide

This guide walks through testing the RUTE extension locally.

## Quick Start Testing

### 1. Start the Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Verify at: http://localhost:8000

### 2. Build and Load Extension
```bash
npm install
npm run build
```

Load in Chrome:
1. Go to `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `dist/` folder

### 3. Test Workflow

#### Test 1: Add Symbols to Watchlist
1. Click the RUTE extension icon
2. Go to "Watchlist" tab
3. Add symbols: AAPL, TSLA, MSFT
4. Verify they appear in the list

#### Test 2: Fetch Market Data
1. After adding symbols, wait 30 seconds
2. Market data should appear next to each symbol
3. Check for price and percentage change
4. Verify green (up) or red (down) indicators

#### Test 3: Get AI Recommendations
1. Go to "Dashboard" tab
2. Click "Refresh" button
3. Wait for AI to analyze symbols (may take 10-15 seconds)
4. Recommendations should appear with:
   - Symbol name and type
   - BUY or SELL signal
   - Entry price, stop-loss, take-profit
   - Confidence score
   - AI reasoning with technical indicators

#### Test 4: Execute Trade (Simulated)
1. Select a recommendation
2. Click "Execute Trade"
3. Review the confirmation modal
4. Click "Confirm & Execute"
5. Verify:
   - Trade execution overlay appears on screen
   - Trade appears in "History" tab
   - Recommendation disappears from dashboard

#### Test 5: View Trade History
1. Go to "History" tab
2. Verify executed trades are listed
3. Check statistics: Total Trades, Win Rate, Total P&L
4. Verify trade details are correct

#### Test 6: Configure Settings
1. Go to "Settings" tab
2. Modify risk settings:
   - Max Position Size: 2000
   - Stop Loss %: 3
   - Take Profit %: 6
3. Toggle notifications on/off
4. Click "Save Settings"
5. Verify "Settings Saved!" message appears

#### Test 7: Notifications
1. In Settings, enable "Trade Alerts"
2. Wait for new recommendations (or refresh manually)
3. Chrome notification should appear
4. Click notification to open extension

## Testing on Trading Platforms

### TradingView Test
1. Open https://www.tradingview.com/chart/
2. Open any chart (e.g., AAPL)
3. Execute a trade from RUTE
4. Verify trade execution overlay appears
5. Check console (F12) for interaction logs

### Investing.com Test
1. Open https://www.investing.com/
2. Navigate to a stock page
3. Execute trade from RUTE
4. Verify overlay appears

### Yahoo Finance Test
1. Open https://finance.yahoo.com/
2. View a stock quote
3. Execute trade from RUTE
4. Trade will be simulated

## Backend API Testing

### Test Health Endpoint
```bash
curl http://localhost:8000/api/health
```

Expected:
```json
{"status": "healthy", "timestamp": "2024-01-01T12:00:00"}
```

### Test Market Data Endpoint
```bash
curl -X POST http://localhost:8000/api/market-data \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "TSLA", "MSFT"]}'
```

Expected:
```json
{
  "marketData": {
    "AAPL": {
      "symbol": "AAPL",
      "price": 185.50,
      "change": 2.30,
      "changePercent": 1.25,
      "volume": 50000000,
      "timestamp": 1704124800000
    },
    ...
  }
}
```

### Test Recommendations Endpoint
```bash
curl -X POST http://localhost:8000/api/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": [
      {"symbol": "AAPL", "assetType": "STOCK"},
      {"symbol": "TSLA", "assetType": "STOCK"}
    ],
    "riskSettings": {
      "maxPositionSize": 1000,
      "maxDailyLoss": 500,
      "stopLossPercentage": 2,
      "takeProfitPercentage": 5,
      "enableAutoTrade": false
    }
  }'
```

Expected:
```json
{
  "recommendations": [
    {
      "id": "uuid-here",
      "symbol": "AAPL",
      "type": "BUY",
      "assetType": "STOCK",
      "entryPrice": 185.50,
      "stopLoss": 181.79,
      "takeProfit": 194.78,
      "confidence": 75,
      "reasoning": {
        "technicalIndicators": ["RSI oversold", "MACD bullish crossover"],
        "marketTrend": "Bullish uptrend with strong momentum",
        "sentiment": "Oversold - potential reversal",
        "summary": "AI recommends BUY for AAPL..."
      },
      "timestamp": 1704124800000,
      "status": "pending"
    }
  ],
  "marketAnalysis": {
    "overall": "AI analyzed 2 symbols and found 1 opportunities",
    "sentiment": "neutral",
    "volatility": "medium"
  }
}
```

## Debugging Tips

### Extension Console
1. Right-click extension icon → "Inspect popup"
2. Or open popup and press F12
3. Check Console tab for errors
4. Check Network tab for API calls

### Background Script Console
1. Go to `chrome://extensions/`
2. Click "service worker" link under RUTE
3. View background script logs

### Content Script Console
1. Open trading platform page
2. Press F12
3. Look for RUTE-related console messages

### Common Issues

**No recommendations appearing:**
- Check backend is running on port 8000
- Verify CORS is enabled
- Check browser console for errors
- Ensure symbols are valid Yahoo Finance tickers

**Market data not loading:**
- yfinance may rate limit - wait 1-2 minutes
- Check internet connection
- Verify symbol format (use Yahoo Finance format)

**Trade execution not working:**
- Trades are simulated by default (safe mode)
- Check content script loaded (console message)
- Verify trading platform URL matches manifest

**Extension not loading:**
- Run `npm run build` again
- Reload extension in chrome://extensions/
- Check for build errors in terminal

## Performance Testing

### Load Test Watchlist
1. Add 20+ symbols to watchlist
2. Verify all load within reasonable time
3. Check memory usage in Task Manager

### Rapid Fire Testing
1. Execute multiple trades quickly
2. Verify all are logged correctly
3. Check for memory leaks

### Notification Stress Test
1. Enable all notifications
2. Add many volatile stocks
3. Verify notifications don't spam

## Expected Behavior

### Update Intervals
- Market data: Every 30 seconds
- AI recommendations: Every 5 minutes
- UI refresh: Real-time on user action

### Data Persistence
- Watchlist: Persists across sessions
- Trade logs: Persists across sessions
- Settings: Persists across sessions
- Recommendations: Cleared on browser restart

### Confidence Scores
- 60-70%: Low confidence, proceed with caution
- 70-85%: Moderate confidence, reasonable signal
- 85-95%: High confidence, strong signal

Note: Confidence is calculated from technical indicator alignment. Higher confidence doesn't guarantee success.

## Test Checklist

- [ ] Backend starts without errors
- [ ] Extension loads in Chrome
- [ ] Can add symbols to watchlist
- [ ] Market data updates correctly
- [ ] AI recommendations generate
- [ ] Trade confirmation modal works
- [ ] Trade execution creates overlay
- [ ] Trades logged in history
- [ ] Statistics calculate correctly
- [ ] Settings save and persist
- [ ] Notifications appear
- [ ] Content script loads on platforms
- [ ] No console errors
- [ ] Extension icon shows "Live" status

## Next Steps

After testing locally:
1. Test with real market data during trading hours
2. Verify indicator calculations match expectations
3. Paper trade recommendations to validate AI logic
4. Optimize performance for large watchlists
5. Add error handling for edge cases

---

**Remember:** This is a testing/demo environment. Never use real money without thorough validation and risk management.
