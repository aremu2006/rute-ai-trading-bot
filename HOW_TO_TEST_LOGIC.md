# How to Test the Logic Sidebar

## Step 1: Load RUTE Extension

1. Open **Chrome** or **Edge**
2. Go to **Extensions** page:
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
3. Enable **"Developer mode"** (toggle in top-right corner)
4. Click **"Load unpacked"**
5. Navigate to: `C:\Users\Danny's PC\OneDrive\Documents\Personal Works\CODE\RUTE\dist`
6. Click **"Select Folder"**

## Step 2: Open RUTE

1. Click the **RUTE extension icon** in your browser toolbar
   - Look for the icon in the top-right of your browser
   - If you don't see it, click the puzzle piece icon to find it

2. You should see the RUTE popup with tabs at the bottom:
   - Dashboard
   - Live Market
   - **Logic** ← (NEW!)
   - History
   - Settings

## Step 3: Test the Logic Tab

1. Click the **"Logic"** tab (has a brain icon)

2. You should see:
   - Header: "RUTE's Logic & Learning"
   - Symbol selector with buttons: AAPL, TSLA, GOOGL, MSFT, AMZN
   - Four expandable sections:
     - 📊 Analysis Thoughts
     - 🧠 Decision Thoughts
     - ⚡ Execution Thoughts
     - 💡 Outcome & Learning
   - Overall Learning section

3. Click on different symbols to switch

4. Click on section headers to expand/collapse them

## What You'll See Right Now

Since auto-trading isn't enabled yet, you'll see:
```
ℹ️ No Thoughts Logged Yet

RUTE's complete thought process will appear here when
auto-trading is enabled. You'll see every decision, the
reasoning behind it, and what RUTE learns from each trade.

Enable auto-trading in Settings to see RUTE's logic in action!
```

This is **CORRECT** - it means the Logic tab is working!

## Step 4: Verify Backend Connection

The Logic tab tries to connect to `http://localhost:8000`. Let's verify:

1. Make sure the backend is running:
   ```bash
   cd backend
   python main.py
   ```

2. Open browser console (F12) while viewing the Logic tab

3. You should see API requests to:
   - `http://localhost:8000/api/thoughts/AAPL`
   - `http://localhost:8000/api/learning/summary`

4. These will return `{"error": "Auto-trader not configured"}` - that's expected!

## Step 5: See It With Real Data (Optional)

To see the Logic tab with actual thoughts, you need to:

### A. Quick Test with Mock Data

I can create a script that adds fake thoughts to test the UI.

### B. Enable Auto-Trading (Real Data)

1. Go to **Settings** tab in RUTE
2. Configure broker credentials (Alpaca recommended)
3. Enable auto-trading
4. Wait for RUTE to make a trade
5. Go to **Logic** tab and select that symbol
6. See RUTE's complete thought process!

## Troubleshooting

### Extension doesn't load
- Make sure you selected the `dist` folder, not the root folder
- Check for build errors: `npm run build`
- Reload the extension after changes

### Logic tab is blank
- Open browser console (F12) and check for errors
- Make sure backend is running on port 8000
- Try clicking a different symbol

### API errors in console
- This is normal if auto-trading isn't enabled
- The errors should say "Auto-trader not configured"

## Visual Confirmation

When working correctly, the Logic tab should show:

```
╔════════════════════════════════════════╗
║  🧠 RUTE's Logic & Learning           ║
║  Complete transparency - see exactly   ║
║  why RUTE makes every decision        ║
╚════════════════════════════════════════╝

Select Symbol
[AAPL] [TSLA] [GOOGL] [MSFT] [AMZN]
  ↑ These should be clickable buttons

📊 Analysis Thoughts (0)        [v]
🧠 Decision Thoughts (0)        [v]
⚡ Execution Thoughts (0)       [v]
💡 Outcome & Learning (0)       [v]
💡 Overall Learning (Last 7 Days) [v]

ℹ️ No Thoughts Logged Yet
(message about enabling auto-trading)
```

If you see this structure, **IT WORKS!** ✅

## Next Steps

Once you verify the UI is working:

1. Configure auto-trading in Settings
2. Let RUTE make some trades
3. Come back to Logic tab
4. See complete reasoning for every decision!

---

**Need help?** Check the browser console for specific errors.
