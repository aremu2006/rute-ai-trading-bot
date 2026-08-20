import yfinance as yf
from datetime import datetime

print("=" * 60)
print("TESTING REAL STOCK DATA FROM YAHOO FINANCE")
print("=" * 60)

# Test Apple stock
ticker = yf.Ticker('AAPL')
data = ticker.history(period='1d')

if not data.empty:
    current_price = data['Close'].iloc[-1]
    open_price = data['Open'].iloc[0]
    high_price = data['High'].max()
    low_price = data['Low'].min()
    volume = data['Volume'].iloc[-1]

    print(f"\n[REAL] APPLE (AAPL) - LIVE DATA:")
    print(f"   Current Price: ${current_price:.2f}")
    print(f"   Open: ${open_price:.2f}")
    print(f"   High: ${high_price:.2f}")
    print(f"   Low: ${low_price:.2f}")
    print(f"   Volume: {int(volume):,}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Test Tesla
ticker2 = yf.Ticker('TSLA')
data2 = ticker2.history(period='1d')

if not data2.empty:
    current_price2 = data2['Close'].iloc[-1]
    open_price2 = data2['Open'].iloc[0]

    print(f"\n[REAL] TESLA (TSLA) - LIVE DATA:")
    print(f"   Current Price: ${current_price2:.2f}")
    print(f"   Open: ${open_price2:.2f}")

print("\n" + "=" * 60)
print("THIS IS 100% REAL DATA FROM YAHOO FINANCE!")
print("Not simulated, not demo - these are ACTUAL stock prices")
print("Compare with https://finance.yahoo.com to verify!")
print("=" * 60)
