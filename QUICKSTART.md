# RUTE Quick Start Guide

Get RUTE up and running in 5 minutes!

## Prerequisites Check

```bash
# Check Node.js (need 18+)
node --version

# Check Python (need 3.9+)
python --version

# Check npm
npm --version
```

If any are missing, install them first.

## 1. Install Frontend (30 seconds)

```bash
cd RUTE
npm install
```

## 2. Install Backend (1 minute)

**Windows:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS/Linux:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Build Extension (30 seconds)

```bash
# From root directory
npm run build
```

## 4. Load in Chrome (1 minute)

1. Open Chrome
2. Go to: `chrome://extensions/`
3. Toggle on: **Developer mode** (top-right)
4. Click: **Load unpacked**
5. Select: `RUTE/dist` folder
6. Done! Icon appears in toolbar

## 5. Start Backend (10 seconds)

**Windows:**
```bash
cd backend
venv\Scripts\activate
python -m uvicorn main:app --reload
```

**macOS/Linux:**
```bash
cd backend
source venv/bin/activate
python -m uvicorn main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

## 6. Test It! (2 minutes)

1. **Click RUTE icon** in Chrome toolbar
2. **Go to Watchlist tab**
3. **Add a symbol**: Type "AAPL", select "Stock", click "Add"
4. **Add more**: Try "TSLA", "MSFT", "GOOGL"
5. **Wait 30 seconds** for market data to appear
6. **Go to Dashboard tab**
7. **Click "Refresh"** to get AI recommendations
8. **Review a trade** and click "Execute Trade"
9. **Confirm** to see it in action!

## Verify Backend

Open in browser: http://localhost:8000/docs

You should see the FastAPI documentation page.

## Quick Test Commands

Test market data:
```bash
curl -X POST http://localhost:8000/api/market-data \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL"]}'
```

## Common First-Time Issues

**Extension not loading:**
- Make sure you selected the `dist` folder, not the root `RUTE` folder
- Run `npm run build` first
- Refresh the extension in chrome://extensions/

**No recommendations appearing:**
- Make sure backend is running on port 8000
- Check browser console (F12) for errors
- Add valid stock symbols (use Yahoo Finance format)

**Backend won't start:**
- Make sure virtual environment is activated
- Try: `pip install --upgrade pip` then reinstall requirements
- Check Python version is 3.9+

**"Module not found" errors:**
- Run: `npm install` again
- Delete `node_modules` and `package-lock.json`, then `npm install`
- Make sure you're in the correct directory

## Next Steps

- Read [README.md](README.md) for full documentation
- Read [TESTING.md](TESTING.md) for comprehensive testing guide
- Configure settings in the extension
- Add more symbols to your watchlist
- Explore the trade history and statistics

## Helpful Commands

**Rebuild extension:**
```bash
npm run build
```

**Restart backend:**
```bash
# Stop with Ctrl+C, then:
python -m uvicorn main:app --reload
```

**View backend logs:**
Just watch the terminal where backend is running

**Clear extension data:**
1. Go to chrome://extensions/
2. Click "Remove" on RUTE
3. Reinstall from dist folder

## Development Mode

If you want to develop and see changes live:

**Terminal 1 (Frontend):**
```bash
npm run dev
```

**Terminal 2 (Backend):**
```bash
cd backend
python -m uvicorn main:app --reload
```

Then load the extension from `dist/` after each build.

## Support

- Check browser console (F12 → Console)
- Check backend terminal for API errors
- Read TESTING.md for troubleshooting
- Review API docs at http://localhost:8000/docs

---

**You're ready to go!** Start adding symbols and exploring AI-powered trading recommendations! 🚀📈
