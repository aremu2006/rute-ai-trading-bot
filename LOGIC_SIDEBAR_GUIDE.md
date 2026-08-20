# RUTE Logic Sidebar - User Guide

## What's New?

RUTE now has a **Logic** tab in the extension that shows you **exactly why RUTE makes every decision**!

## How to Use It

### 1. Open the RUTE Extension

Click the RUTE icon in your browser to open the extension popup.

### 2. Navigate to the Logic Tab

You'll see a new **"Logic"** tab with a brain icon (🧠) in the navigation bar at the bottom.

### 3. Select a Symbol

Use the symbol selector at the top to choose which stock you want to see thoughts for:
- AAPL
- TSLA
- GOOGL
- MSFT
- AMZN

### 4. View RUTE's Thoughts

The Logic tab displays **4 types of thoughts** for each symbol:

#### 📊 Analysis Thoughts
- What RUTE observed in the market
- Technical indicator analysis (RSI, MACD, SMA, etc.)
- ML model predictions and confidence levels
- Market sentiment

**Example:**
```
Observation: AAPL at $150.00
Technical Analysis:
  • RSI oversold at 42
  • MACD bullish crossover
  • Price at SMA50 support
ML Prediction: BUY
Confidence: 68%
```

#### 🧠 Decision Thoughts
- The complete reasoning chain (step-by-step)
- Why RUTE decided to execute or skip a trade
- Alternatives considered and why they were rejected
- Confidence breakdown

**Example:**
```
Decision: EXECUTE_BUY
Reasoning Chain:
  → Step 1: ML model predicts BUY with 68% confidence
  → Step 2: Technical indicators confirm signal
  → Step 3: Risk assessment: Account balance $10,000.00
  → Step 4: Position sizing: Risk 2% of account = $200.00
  → Step 5: Stop loss calculation: $150.00 - 2% = $147.00
  ... (5 more steps)
```

#### ⚡ Execution Thoughts
- How the trade was executed
- Entry price, stop loss, take profit
- Why market order vs limit order
- Position management strategy

**Example:**
```
Action: BUY
Quantity: 13 shares
Entry Price: $150.00
Stop Loss: $147.00
Take Profit: $159.00
• Strong signal, immediate execution preferred
```

#### 🎯 Outcome & Learning
- What happened (WIN or LOSS)
- What worked (for wins)
- What went wrong (for losses)
- Corrective actions taken
- Learning points for future trades

**Example (WIN):**
```
✓ What Worked:
  ✓ ML prediction was accurate - 68% confidence justified
  ✓ RSI oversold signal correctly identified reversal
  ✓ Entry timing was good - caught bounce off SMA 50 support

💡 Learning Points:
  • REINFORCEMENT: RSI 40-45 + SMA support = high probability setup
  • PATTERN IDENTIFIED: Bullish MACD crossover at support works well
```

**Example (LOSS):**
```
✗ What Went Wrong:
  ✗ Failed to account for broader market weakness
  ✗ Volume spike was SELLING volume, not buying
  ✗ Entry was too aggressive

→ Corrective Actions:
  → ADD FILTER: Check S&P 500 direction before trades
  → IMPROVE FEATURE: Add buy/sell volume ratio indicator
  → UPDATE RULE: Require 15-min price confirmation
```

### 5. View Overall Learning

Click on **"Overall Learning (Last 7 Days)"** to expand performance metrics:

- **Performance Metrics**
  - Total trades
  - Win rate
  - Wins vs Losses
  - Profit factor

- **Successful Patterns**
  - Patterns that consistently win
  - Win rate for each pattern
  - How many times it occurred

- **Mistakes to Avoid**
  - Common mistakes identified
  - Corrective actions implemented
  - How they improved performance

## Features

### ✅ Real-Time Updates
- Thoughts are logged as RUTE makes decisions
- Refresh to see latest thoughts

### ✅ Expandable Sections
- Click section headers to expand/collapse
- Only show what you want to see

### ✅ Color-Coded Outcomes
- 🟢 Green border = WIN
- 🔴 Red border = LOSS
- Easy to spot performance at a glance

### ✅ Symbol Switching
- Quick tabs to switch between symbols
- See thoughts for any tracked stock

## When Will You See Thoughts?

### Currently
The Logic tab is ready but will show "No thoughts logged yet" because:
- Auto-trading is not yet enabled
- No trades have been executed

### Once Auto-Trading is Enabled
1. Set up auto-trading in the Settings tab
2. Configure your broker credentials
3. Enable auto-trading
4. **RUTE will automatically log all thoughts as it trades**
5. View complete reasoning in the Logic tab

## Why This Is Valuable

### 🔍 Complete Transparency
- No "black box" - see every decision
- Understand RUTE's reasoning
- Build trust in the system

### 📚 Continuous Learning
- See what patterns work
- Learn from mistakes
- Watch RUTE improve over time

### 🎯 Better Decision Making
- Understand why trades succeed or fail
- Identify your own trading patterns
- Learn AI-powered trading strategies

### 🛡️ Risk Management
- Verify RUTE follows your rules
- Track decision quality
- Know when to intervene

## Example Workflow

1. **Morning**: Check Logic tab for yesterday's trades
2. **Review Outcomes**: See what worked and what didn't
3. **Learn**: Read RUTE's learning points
4. **Adjust**: Make strategy adjustments if needed
5. **Repeat**: Watch RUTE get better every day

## Technical Details

### API Endpoints Used
The Logic component connects to these backend endpoints:

- `GET /api/thoughts/{symbol}` - Fetch thoughts for a symbol
- `GET /api/learning/summary?days=7` - Fetch learning summary

### Data Refresh
- Thoughts are fetched when you:
  - Open the Logic tab
  - Switch symbols
  - Refresh the page

### Storage
- All thoughts are stored in `backend/reasoning_engine/thoughts/`
- Learning data in `backend/reasoning_engine/learning_db/`
- Organized by symbol and thought type

## Need Help?

- See [REASONING_ENGINE_GUIDE.md](REASONING_ENGINE_GUIDE.md) for complete technical documentation
- Run `python backend/test_rute_reasoning.py` to test the reasoning system
- Check backend logs if thoughts aren't appearing

---

**🧠 The Logic tab is the MILLION-DOLLAR FEATURE that makes RUTE truly valuable - complete transparency into every AI decision!**
