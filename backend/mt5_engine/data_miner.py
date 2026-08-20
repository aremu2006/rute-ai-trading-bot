"""
Standalone Historical Data Miner for trades.db
Pulls real historical candle data from MT5 and simulates trades to fill
the database so the AI model can train on real market patterns.

Usage: python3.13.exe data_miner.py
  - Make sure ultimate_server.py is NOT running (MT5 only allows 1 connection)
  - Make sure MT5 terminal is open and logged into your broker
"""

import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import sqlite3
import random
import os
import time
import sys

# =====================================================================
# Configuration — must match ultimate_server.py exactly
# =====================================================================
DB_FILE = os.path.join(os.path.dirname(__file__), "trades.db")
SEQ_LEN = 30
SYMBOLS = ["BTCUSDm", "ETHUSDm", "USDJPYm", "EURUSDm", "XAUAUDm", "GBPAUDm", "BTCJPYm", "BCHUSDm"]
TOTAL_TRADES = 10000

TIMEFRAMES = [
    ("M1",  mt5.TIMEFRAME_M1,  1),
    ("M5",  mt5.TIMEFRAME_M5,  5),
    ("M15", mt5.TIMEFRAME_M15, 15),
    ("M30", mt5.TIMEFRAME_M30, 30),
    ("H1",  mt5.TIMEFRAME_H1,  60),
    ("H4",  mt5.TIMEFRAME_H4,  240),
    ("D1",  mt5.TIMEFRAME_D1,  1440),
]


# =====================================================================
# Feature Engineering (mirrors ultimate_server.py logic)
# =====================================================================
def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))


def compute_atr(high, low, close, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_supertrend(high, low, close, period=10, multiplier=3.0):
    atr = compute_atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr

    supertrend = pd.Series(0.0, index=close.index)
    direction = pd.Series(1, index=close.index)  # 1 = up (BUY), -1 = down (SELL)

    for i in range(1, len(close)):
        if close.iloc[i] > upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]
            if direction.iloc[i] == 1:
                lower.iloc[i] = max(lower.iloc[i], lower.iloc[i - 1])
            else:
                upper.iloc[i] = min(upper.iloc[i], upper.iloc[i - 1])

        supertrend.iloc[i] = lower.iloc[i] if direction.iloc[i] == 1 else upper.iloc[i]

    return supertrend, direction


def fetch_candles(symbol, timeframe_enum, n_candles):
    """Fetch candles from MT5 for a single timeframe."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe_enum, 0, n_candles)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df


def build_features_for_symbol(symbol, n_candles=1500):
    """Build a feature matrix from multi-timeframe data, matching ultimate_server.py."""
    # Get M15 as the base timeframe
    base_df = fetch_candles(symbol, mt5.TIMEFRAME_M15, n_candles)
    if base_df is None or len(base_df) < 300:
        return None

    df = base_df.copy()

    # Basic price features on base timeframe
    df['returns'] = df['close'].pct_change()
    df['rsi_14'] = compute_rsi(df['close'], 14)
    df['atr_14'] = compute_atr(df['high'], df['low'], df['close'], 14)
    df['atr_pct'] = df['atr_14'] / (df['close'] + 1e-10) * 100

    # EMAs
    for p in [9, 21, 50, 200]:
        df[f'ema_{p}'] = df['close'].ewm(span=p).mean()

    # EMA ratios
    df['ema_9_21_ratio'] = df['ema_9'] / (df['ema_21'] + 1e-10)
    df['ema_21_50_ratio'] = df['ema_21'] / (df['ema_50'] + 1e-10)
    df['price_ema200_ratio'] = df['close'] / (df['ema_200'] + 1e-10)

    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_upper'] = sma20 + 2 * std20
    df['bb_lower'] = sma20 - 2 * std20
    df['bb_pct'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

    # Volume features
    df['volume_ratio'] = df['tick_volume'] / (df['tick_volume'].rolling(20).mean() + 1e-10)

    # SuperTrend on base
    _, st_dir = compute_supertrend(df['high'], df['low'], df['close'])
    df['supertrend_dir'] = st_dir.astype(float)

    # Higher timeframe SuperTrend signals
    for tf_name, tf_enum, _ in TIMEFRAMES:
        if tf_name in ("M1", "M5", "M15"):
            continue  # skip lower timeframes
        htf = fetch_candles(symbol, tf_enum, 500)
        if htf is not None and len(htf) > 20:
            _, htf_dir = compute_supertrend(htf['high'], htf['low'], htf['close'])
            # Forward-fill the HTF direction onto the base timeframe
            htf_signal = htf_dir.iloc[-1]  # latest HTF direction
            df[f'st_{tf_name}'] = float(htf_signal)
        else:
            df[f'st_{tf_name}'] = 0.0

    # Drop NaN rows
    df = df.dropna().reset_index(drop=True)

    return df


def generate_feature_cols(df):
    """Get the feature column names (exclude time, OHLCV raw)."""
    exclude = {'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume'}
    return [c for c in df.columns if c not in exclude]


# =====================================================================
# Database Setup
# =====================================================================
def ensure_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trade_type TEXT,
            entry_price REAL,
            exit_price REAL,
            outcome TEXT,
            pnl REAL,
            features BLOB,
            prediction_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_predictions (
            prediction_id INTEGER PRIMARY KEY,
            features_blob BLOB,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


# =====================================================================
# Main Mining Loop
# =====================================================================
def mine_data():
    if not mt5.initialize():
        print("ERROR: Failed to connect to MT5. Make sure MT5 is open!")
        return

    print(f"MT5 connected: {mt5.version()}")
    ensure_db()

    # Check current count
    conn = sqlite3.connect(DB_FILE)
    existing = conn.execute("SELECT COUNT(*) FROM trade_history").fetchone()[0]
    conn.close()
    print(f"Database already has {existing} trades.")

    needed = max(0, TOTAL_TRADES - existing)
    if needed == 0:
        print(f"Already have {existing} trades (>= {TOTAL_TRADES}). No mining needed!")
        mt5.shutdown()
        return

    print(f"Mining {needed} historical trades from your MT5 broker data...")
    print("This uses your REAL broker's historical candle data.\n")

    collected = 0
    errors = 0
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Pre-fetch data for each symbol once (much faster than fetching per-trade)
    symbol_data = {}
    for sym in SYMBOLS:
        print(f"  Downloading history for {sym}...", end=" ", flush=True)
        df = build_features_for_symbol(sym, n_candles=2000)
        if df is not None and len(df) > 300:
            symbol_data[sym] = df
            print(f"OK ({len(df)} bars)")
        else:
            print(f"SKIP (not enough data)")

    if not symbol_data:
        print("\nERROR: Could not fetch data for any symbol!")
        mt5.shutdown()
        return

    available_symbols = list(symbol_data.keys())
    print(f"\nReady to mine from: {', '.join(available_symbols)}\n")

    while collected < needed:
        sym = random.choice(available_symbols)
        df = symbol_data[sym]
        feat_cols = generate_feature_cols(df)
        n_features = len(feat_cols)

        # Pick a random entry point deep enough for sequence, with room for lookahead
        start_idx = SEQ_LEN + 50
        end_idx = len(df) - 15

        if start_idx >= end_idx:
            continue

        idx = random.randint(start_idx, end_idx)

        try:
            # Get sequence of features
            feats = df.iloc[idx - SEQ_LEN: idx][feat_cols].values.astype(np.float32)

            # BUG #24 FIX: Use realistic constants instead of random noise
            spread_pct = 0.05
            vol_percentile = 50.0
            news_dist = 1440.0
            context = np.array([spread_pct, vol_percentile, news_dist], dtype=np.float32)
            total_features = n_features + 3
            feats_with_context = np.zeros((SEQ_LEN, total_features), dtype=np.float32)
            for i in range(SEQ_LEN):
                feats_with_context[i] = np.concatenate((feats[i], context))

            features_blob = feats_with_context.tobytes()

            entry_price = float(df.iloc[idx]['close'])
            trade_type = random.choice(["BUY", "SELL"])

            # BUG #35 FIX: Use wider SL/TP and longer lookahead (96 bars = 24 hours on 15m)
            sl_pct = 0.015
            tp_pct = 0.045
            if trade_type == "BUY":
                sl = entry_price * (1 - sl_pct)
                tp = entry_price * (1 + tp_pct)
            else:
                sl = entry_price * (1 + sl_pct)
                tp = entry_price * (1 - tp_pct)

            outcome = "HOLD"
            future_price = entry_price
            
            # Look ahead up to 96 bars
            for step in range(1, 97):
                if idx + step >= len(df):
                    break
                bar_high = float(df.iloc[idx + step]['high'])
                bar_low = float(df.iloc[idx + step]['low'])
                bar_close = float(df.iloc[idx + step]['close'])

                if trade_type == "BUY":
                    if bar_low <= sl:
                        outcome = "LOSS"
                        future_price = sl
                        break
                    elif bar_high >= tp:
                        outcome = "WIN"
                        future_price = tp
                        break
                else:
                    if bar_high >= sl:
                        outcome = "LOSS"
                        future_price = sl
                        break
                    elif bar_low <= tp:
                        outcome = "WIN"
                        future_price = tp
                        break
                
                future_price = bar_close

            if outcome == "HOLD":
                if trade_type == "BUY":
                    outcome = "WIN" if future_price > entry_price else "LOSS"
                else:
                    outcome = "WIN" if future_price < entry_price else "LOSS"

            if trade_type == "BUY":
                pnl = future_price - entry_price
            else:
                pnl = entry_price - future_price

            c.execute('''
                INSERT INTO trade_history (symbol, trade_type, entry_price, exit_price, outcome, pnl, features, prediction_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sym, trade_type, entry_price, future_price, outcome, round(pnl, 6), features_blob, random.randint(10000, 999999)))

            collected += 1

            if collected % 50 == 0:
                conn.commit()
                pct = round(collected / needed * 100)
                print(f"  [{pct}%] Collected {collected} / {needed} trades...")

        except Exception as e:
            errors += 1
            if errors > 100:
                print(f"\nToo many errors. Last: {e}")
                break

    conn.commit()
    conn.close()
    mt5.shutdown()

    final_conn = sqlite3.connect(DB_FILE)
    total = final_conn.execute("SELECT COUNT(*) FROM trade_history").fetchone()[0]
    wins = final_conn.execute("SELECT COUNT(*) FROM trade_history WHERE outcome='WIN'").fetchone()[0]
    final_conn.close()

    print(f"\n{'='*50}")
    print(f"DONE! Database now has {total} trades.")
    print(f"Win rate: {wins}/{total} ({round(wins/total*100, 1)}%)")
    print(f"{'='*50}")
    print(f"\nNext step: Restart ultimate_server.py and it will auto-train!")


if __name__ == "__main__":
    mine_data()
