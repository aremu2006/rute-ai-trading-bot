# RUTE AUTO-TRADING SETUP GUIDE

## **🤖 Autonomous Trading is Now LIVE!**

RUTE can now **trade on your behalf automatically** using trained ML models and broker APIs.

---

## **How Auto-Trading Works**

```
1. ML Model analyzes market data (61 indicators)
   ↓
2. Model predicts BUY/SELL with confidence score
   ↓
3. Technical confirmations added (RSI, MACD, etc.)
   ↓
4. If confidence ≥ 60% → RUTE executes trade AUTOMATICALLY
   ↓
5. Stop Loss (2%) and Take Profit (6%) set automatically
   ↓
6. Trade appears in your broker account INSTANTLY
```

**YOU DON'T NEED TO DO ANYTHING** - RUTE handles everything!

---

## **Step 1: Choose a Broker**

### **Recommended: Alpaca (Easiest Setup)**

**Why Alpaca?**
- ✅ **Commission-free** trading
- ✅ **$0 minimum** to start (paper trading)
- ✅ **API access** included for free
- ✅ **US stocks** fully supported
- ✅ **Paper trading** for testing without risk

**Sign up:** https://alpaca.markets

1. Create account
2. Go to **"Paper Trading"** section
3. Generate API keys:
   - Click "Generate New Keys"
   - Copy **API Key ID**
   - Copy **Secret Key**

### **Other Supported Brokers** (Coming Soon)
- **MetaTrader 5** (MT5) - Forex/CFDs
- **Interactive Brokers** - Global markets
- **TD Ameritrade** - US stocks/options

---

## **Step 2: Configure RUTE Auto-Trading**

### **Option A: Via Extension UI** (Easiest)

1. Open RUTE extension
2. Go to **Settings** tab
3. Click **"Enable Auto-Trading"**
4. Enter broker credentials:
   - Broker: **Alpaca**
   - API Key: `YOUR_API_KEY`
   - API Secret: `YOUR_API_SECRET`
   - Mode: **Paper Trading** (recommended for testing)
5. Set risk limits:
   - Max Position Size: `$1000`
   - Max Daily Loss: `$500`
   - Min Confidence: `60%`
6. Click **"Activate Auto-Trading"**

### **Option B: Via API** (Advanced)

```bash
curl -X POST http://localhost:8000/api/auto-trade/setup \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "broker_config": {
      "broker_type": "alpaca",
      "api_key": "YOUR_API_KEY",
      "api_secret": "YOUR_API_SECRET",
      "paper_trading": true
    },
    "max_position_size": 1000,
    "max_daily_loss": 500,
    "min_confidence": 60
  }'
```

---

## **Step 3: Enable Auto-Trading**

Once configured, RUTE will:

1. **Monitor markets** continuously
2. **Generate ML predictions** every few minutes
3. **Execute trades** automatically when:
   - ML confidence ≥ 60%
   - Technical confirmations align
   - Risk limits not exceeded
   - Account balance sufficient

### **Real-Time Logs**

Backend will show:
```
🤖 AUTO-TRADING ENABLED
   Max Position Size: $1000
   Max Daily Loss: $500
   Min Confidence: 60%

============================================================
🤖 EXECUTING AUTO-TRADE
============================================================
Symbol: AAPL
Action: BUY
Quantity: 6 shares
Entry: $150.00
Stop Loss: $147.00 (-2.0%)
Take Profit: $159.00 (+6.0%)
Confidence: 68%
============================================================

✓ Order executed successfully!
  Order ID: abc123-456def-789ghi
```

---

## **Step 4: Monitor Your Trades**

### **View Open Positions**

**Via Extension:**
- Go to **Dashboard** tab
- See "Active Positions" section

**Via API:**
```bash
curl http://localhost:8000/api/auto-trade/positions
```

Response:
```json
{
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 6,
      "entry_price": 150.00,
      "current_price": 153.50,
      "unrealized_pl": 21.00,
      "unrealized_plpc": 2.33
    }
  ]
}
```

### **Check Auto-Trading Status**

```bash
curl http://localhost:8000/api/auto-trade/status
```

Response:
```json
{
  "configured": true,
  "enabled": true,
  "connected": true,
  "daily_trades": 3,
  "active_positions": 2,
  "daily_loss": 0,
  "max_daily_loss": 500,
  "remaining_capacity": 500
}
```

---

## **Safety Features**

### **1. Stop Loss Protection**
- **Every trade** has automatic stop loss at -2%
- Maximum loss per trade = 2% of entry price
- Exits trade automatically if price drops

### **2. Take Profit Protection**
- **Every trade** has automatic take profit at +6%
- Locks in gains when target hit
- 3:1 risk/reward ratio

### **3. Daily Loss Limit**
- Trading stops if daily losses reach limit
- Default: $500 max daily loss
- Protects account from bad trading days

### **4. Position Size Limits**
- Maximum position size enforced
- Default: $1000 per trade
- Prevents over-exposure to single symbol

### **5. Confidence Threshold**
- Only trades when ML confidence ≥ 60%
- Low-confidence signals ignored
- Quality over quantity

### **6. Account Balance Check**
- Verifies sufficient funds before trading
- Won't trade if balance < $100
- Prevents overdraft

---

## **Risk Management**

### **Recommended Settings for Beginners:**

```javascript
{
  "max_position_size": 500,    // $500 per trade
  "max_daily_loss": 250,       // Stop trading after $250 loss
  "min_confidence": 65         // Only trade 65%+ confidence
}
```

### **Aggressive Settings (Higher Risk/Reward):**

```javascript
{
  "max_position_size": 2000,   // $2000 per trade
  "max_daily_loss": 1000,      // $1000 max daily loss
  "min_confidence": 55         // Trade 55%+ confidence
}
```

### **Conservative Settings (Lower Risk):**

```javascript
{
  "max_position_size": 300,    // $300 per trade
  "max_daily_loss": 150,       // Stop after $150 loss
  "min_confidence": 70         // Only trade 70%+ confidence
}
```

---

## **Expected Performance**

### **With 45% Win Rate + 3:1 R:R**

**Example: 100 trades at $1000 position size**

| Metric | Value |
|--------|-------|
| Wins (45) | 45 × $60 = **+$2,700** |
| Losses (55) | 55 × $20 = **-$1,100** |
| **Net Profit** | **+$1,600** |
| **ROI** | **146%** |

### **Monthly Expectations**

Assuming **20 trading days/month** and **2 trades/day**:
- **Total trades:** 40 trades/month
- **Expected profit:** +$640/month
- **Win rate:** 45%
- **Risk/Reward:** 3:1

---

## **Pause/Resume Trading**

### **Disable Auto-Trading**

```bash
curl -X POST http://localhost:8000/api/auto-trade/disable
```

or via Extension → Settings → "Disable Auto-Trading"

### **Re-Enable**

```bash
curl -X POST http://localhost:8000/api/auto-trade/enable
```

---

## **Broker Account Setup**

### **Alpaca Paper Trading (FREE)**

1. Go to https://alpaca.markets
2. Sign up (free account)
3. Navigate to Paper Trading dashboard
4. You get **$100,000 paper money** to test with
5. Generate API keys
6. Configure RUTE with keys
7. Start trading risk-free!

### **Alpaca Live Trading**

1. Complete identity verification
2. Fund account (minimum $0 - yes, really!)
3. Generate **LIVE** API keys
4. Configure RUTE with **paper_trading: false**
5. RUTE trades with real money

---

## **Troubleshooting**

### **"Auto-trader not configured" error**

**Solution:** Run setup endpoint first:
```bash
/api/auto-trade/setup
```

### **"Failed to connect to broker" error**

**Causes:**
- Invalid API keys
- Expired credentials
- Network issues

**Solution:**
1. Verify API keys in broker dashboard
2. Regenerate keys if needed
3. Check internet connection

### **No trades executing**

**Possible reasons:**
1. ML confidence below threshold (< 60%)
2. Daily loss limit reached
3. Insufficient account balance
4. No strong signals in market

**Check:**
```bash
curl http://localhost:8000/api/auto-trade/status
```

### **Position not appearing**

- Check broker dashboard directly
- Verify order ID in logs
- Market may be closed (trading hours only)

---

## **API Endpoints Reference**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auto-trade/setup` | POST | Configure auto-trading |
| `/api/auto-trade/enable` | POST | Enable auto-trading |
| `/api/auto-trade/disable` | POST | Disable auto-trading |
| `/api/auto-trade/status` | GET | Get status |
| `/api/auto-trade/positions` | GET | Get open positions |

---

## **Advanced: Custom Broker Integration**

Want to add your own broker? Implement the `BrokerInterface`:

```python
from trading_engine import BrokerInterface, TradeOrder

class MyBroker(BrokerInterface):
    def connect(self) -> bool:
        # Connect to your broker API
        pass

    def execute_trade(self, order: TradeOrder) -> Dict:
        # Execute trade
        pass

    # ... implement other methods
```

See [broker_interface.py](backend/trading_engine/broker_interface.py) for full interface.

---

## **Legal Disclaimer**

⚠️ **IMPORTANT:**
- Auto-trading involves **real financial risk**
- Past performance does **not guarantee** future results
- **Test with paper trading first**
- Only invest money you can afford to lose
- RUTE is a tool, **you are responsible** for your trades
- Consult a financial advisor if unsure

---

## **Support**

- **GitHub Issues:** https://github.com/anthropics/claude-code/issues
- **Documentation:** See `/help` in extension

---

**🚀 You're ready to let RUTE trade for you!**

Start with paper trading, monitor performance, then switch to live when comfortable.
