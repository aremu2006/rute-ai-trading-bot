import numpy as np
import pandas as pd

def add_rsi(df, length=14):
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=length-1, adjust=False).mean()
    ema_down = down.ewm(com=length-1, adjust=False).mean()
    rs = ema_up / ema_down
    df[f'RSI_{length}'] = 100 - (100 / (1 + rs))

def add_macd(df, fast=12, slow=26, signal=9):
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macds = macd.ewm(span=signal, adjust=False).mean()
    df[f'MACD_{fast}_{slow}_{signal}'] = macd
    df[f'MACDh_{fast}_{slow}_{signal}'] = macd - macds
    df[f'MACDs_{fast}_{slow}_{signal}'] = macds

def add_atr(df, length=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df[f'ATR_{length}'] = tr.ewm(span=length, min_periods=0, adjust=False).mean()

def add_ema(df, length=200):
    df[f'EMA_{length}'] = df['close'].ewm(span=length, adjust=False).mean()

def get_supertrend(df, length=7, multiplier=3.0):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(span=length, min_periods=0, adjust=False).mean()
    
    hl2 = (df['high'] + df['low']) / 2
    final_ub = hl2 + (multiplier * atr)
    final_lb = hl2 - (multiplier * atr)
    
    dir_ = pd.Series(1, index=df.index)
    supertrend = pd.Series(0.0, index=df.index)
    
    for i in range(1, len(df)):
        if df['close'].iloc[i] > final_ub.iloc[i-1]:
            dir_.iloc[i] = 1
        elif df['close'].iloc[i] < final_lb.iloc[i-1]:
            dir_.iloc[i] = -1
        else:
            dir_.iloc[i] = dir_.iloc[i-1]
            if dir_.iloc[i] == 1 and final_lb.iloc[i] < final_lb.iloc[i-1]:
                final_lb.iloc[i] = final_lb.iloc[i-1]
            if dir_.iloc[i] == -1 and final_ub.iloc[i] > final_ub.iloc[i-1]:
                final_ub.iloc[i] = final_ub.iloc[i-1]
                
        if dir_.iloc[i] == 1:
            supertrend.iloc[i] = final_lb.iloc[i]
        else:
            supertrend.iloc[i] = final_ub.iloc[i]
            
    st_df = pd.DataFrame(index=df.index)
    st_df[f'SUPERT_{length}_{multiplier}'] = supertrend
    st_df[f'SUPERTd_{length}_{multiplier}'] = dir_
    return st_df
