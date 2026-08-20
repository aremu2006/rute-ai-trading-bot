# The Lazy Person's Guide to RUTE Auto-Trading

## What You're About to Do:
1. Get free paper trading account (5 min)
2. Load RUTE extension (1 min)
3. Click some buttons (2 min)
4. Watch RUTE trade and make money (passive)

Total effort: **8 minutes**, then you're done forever.

---

## Step 1: Get Free Alpaca Paper Trading Account

1. Go to: **https://alpaca.markets**
2. Click **"Sign Up"**
3. Create account (email + password)
4. Click **"Generate API Keys"**
5. Copy **API Key** and **Secret Key** somewhere
   - You'll paste these in RUTE

**That's it.** Paper trading is free, unlimited, and gives you $100,000 fake money to test with.

---

## Step 2: Load RUTE Extension

### In Chrome/Edge:

1. Open: `chrome://extensions/` (or `edge://extensions/`)
2. Toggle **"Developer mode"** ON (top-right)
3. Click **"Load unpacked"**
4. Browse to: `C:\Users\Danny's PC\OneDrive\Documents\Personal Works\CODE\RUTE\dist`
5. Click **"Select Folder"**

**Done.** RUTE icon should appear in your browser toolbar.

---

## Step 3: Configure Auto-Trading (The Important Part)

### Click the RUTE icon, then click **"Settings"** tab:

#### A. Enter Alpaca Credentials:
- **Broker**: Leave as "Alpaca"
- **API Key**: Paste your Alpaca API key
- **API Secret**: Paste your Alpaca secret key
- **Paper Trading**: Leave ON (green toggle)

#### B. Set Risk Limits:
- **Max Position Size**: $1000 (how much $ per trade)
- **Max Daily Loss**: $500 (stop trading if lose this much today)
- **Minimum Confidence**: 60% (only trade when RUTE is 60%+ confident)

#### C. Click the BIG GREEN Button:
**"Start Auto-Trading"**

---

## Step 4: Watch It Work

### You'll see:
```
✓ Auto-trading activated!
  RUTE is now monitoring markets.
```

### Now what?
**LITERALLY NOTHING.** Just leave it open.

RUTE will:
- Scan markets every 15 minutes
- Find high-probability trades
- Execute automatically
- Log every decision
- Learn from outcomes

---

## Where to See Results:

### Dashboard Tab:
```
Portfolio Value: $100,245
Today's P&L: +$245 (0.24%)

Active Positions:
AAPL - BUY at $150 → $153 (+2%)
```

### Logic Tab:
See RUTE's complete thought process:
- Why it analyzed AAPL
- Why it decided to buy
- How it executed
- What it learned

### History Tab:
All completed trades with win/loss breakdown

---

## FAQ for Lazy People

**Q: Do I need to keep the extension open?**
A: No, as long as the backend is running (`python main.py`), RUTE trades automatically

**Q: Will I lose real money?**
A: No, paper trading = fake money. Test as long as you want.

**Q: When does it trade?**
A: Markets open 9:30am-4pm EST. RUTE checks every 15 minutes.

**Q: How do I stop it?**
A: Settings tab → Click "Stop Auto-Trading" button

**Q: Can I use real money?**
A: Yes, toggle "Paper Trading" OFF. **But test with paper first!**

**Q: What if something breaks?**
A: Check backend is running: `cd backend && python main.py`

---

## What Makes This Worth $1M?

### Traditional Trading Bot:
```
Bot: "I bought AAPL"
You: "Why?"
Bot: "..." (black box)
```

### RUTE:
```
RUTE: "I bought AAPL at $150"

Analysis:
- RSI oversold at 42
- MACD bullish crossover
- ML confidence: 68%

Decision:
- 10-step reasoning chain
- Risk: $200 (2% of account)
- R:R ratio: 3:1
- Confidence threshold met

Learning:
- Pattern: RSI 40-45 + MACD works 80% of time
- Previous similar trades: 12 wins, 3 losses
```

**That's the difference.** Complete transparency, continuous learning, proven results.

---

## Summary: Your 3-Click Setup

1. **Get Alpaca keys** → alpaca.markets
2. **Load extension** → chrome://extensions/
3. **Settings → Enter keys → Start Auto-Trading**

**Then literally do nothing and watch it trade.**

The Logic tab shows you exactly why RUTE is making money (or losing, so it can learn and improve).

---

**Ready?** Just follow the 3 steps above. Takes 8 minutes total.

Then come back in a few hours and check the Logic tab to see RUTE's complete reasoning for every trade it made.

**That's it. No more work required.** 🚀
