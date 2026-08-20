"""MT5 Multi-Timeframe Feature Engineering"""
import numpy as np
import pandas as pd
import logging
from datetime import datetime

from .config import OMNI_TIMEFRAMES, CROSS_ASSETS, SEQ_LEN, FEATURE_COUNT, MT5_AVAILABLE

if MT5_AVAILABLE:
    import MetaTrader5 as mt5
    from . import custom_ta
else:
    mt5 = None
    custom_ta = None

log = logging.getLogger("mt5_engine.features")


def fetch_mtf_features_df(symbol: str, end_time: datetime = None, n_candles: int = 150):
    """Fetch multi-timeframe OHLCV data from MT5 and engineer features."""
    if not MT5_AVAILABLE or mt5 is None:
        return None

    raw_data = {}

    # 1. Fetch Primary Symbol
    mt5.symbol_select(symbol, True)
    for name, tf, mins in OMNI_TIMEFRAMES:
        needed = (n_candles // mins) + 50
        if end_time is None:
            r = mt5.copy_rates_from_pos(symbol, tf, 0, needed)
        else:
            r = mt5.copy_rates_from(symbol, tf, end_time, needed)
        if r is None or len(r) == 0:
            return None
        raw_data[name] = r

    def process_tf(r, prefix=""):
        df = pd.DataFrame(r)
        if len(df) == 0:
            return None
        df['time'] = pd.to_datetime(df['time'], unit='s')
        custom_ta.add_rsi(df, length=14)
        custom_ta.add_macd(df, fast=12, slow=26, signal=9)
        custom_ta.add_atr(df, length=14)
        df = df.dropna()
        if len(df) == 0:
            return None
        macd_cols = [c for c in df.columns if c.startswith('MACD_') and not c.startswith('MACDh_') and not c.startswith('MACDs_')]
        if not macd_cols:
            raise ValueError(f"MACD column not found in {df.columns}")
        macd_col = macd_cols[0]
        
        sig_cols = [c for c in df.columns if c.startswith('MACDs_')]
        if not sig_cols:
            raise ValueError(f"MACDs column not found in {df.columns}")
        sig_col = sig_cols[0]
        
        rsi_cols = [c for c in df.columns if c.startswith('RSI_')]
        atr_cols = [c for c in df.columns if c.startswith('ATR_')]
        if not rsi_cols or not atr_cols:
            return None
        rsi_col, atr_col = rsi_cols[0], atr_cols[0]
        res = df[['time', 'close', rsi_col, macd_col, sig_col, atr_col, 'tick_volume']].copy()
        res.columns = ['time', f'{prefix}close', f'{prefix}RSI', f'{prefix}MACD',
                       f'{prefix}MACDs', f'{prefix}ATR', f'{prefix}VOL']
        return res

    processed = {}
    for name, _tf, _mins in OMNI_TIMEFRAMES:
        df = process_tf(raw_data[name], f"{name}_")
        if df is None:
            return None
        processed[name] = df

    df_merged = processed["M1"]
    for name, _tf, _mins in OMNI_TIMEFRAMES:
        if name == "M1":
            continue
        df_merged = pd.merge_asof(df_merged, processed[name], on='time', direction='backward')

    # 2. Fetch Cross Assets
    for asset in CROSS_ASSETS:
        mt5.symbol_select(asset, True)
        if end_time is None:
            r = mt5.copy_rates_from_pos(asset, mt5.TIMEFRAME_M1, 0, n_candles + 50)
        else:
            r = mt5.copy_rates_from(asset, mt5.TIMEFRAME_M1, end_time, n_candles + 50)

        if r is not None and len(r) > 0:
            df_ca = pd.DataFrame(r)
            df_ca['time'] = pd.to_datetime(df_ca['time'], unit='s')
            df_ca = df_ca[['time', 'close']].copy()
            df_ca.columns = ['time', f'CA_{asset}_close']
            df_merged = pd.merge_asof(df_merged, df_ca, on='time', direction='backward')
        else:
            df_merged[f'CA_{asset}_close'] = 0.0

    df_merged = df_merged.dropna().reset_index(drop=True)
    if len(df_merged) < SEQ_LEN:
        return None

    # Time encoding
    df_merged['hour'] = df_merged['time'].dt.hour + df_merged['time'].dt.minute / 60.0
    df_merged['hour_sin'] = np.sin(2 * np.pi * df_merged['hour'] / 24)
    df_merged['hour_cos'] = np.cos(2 * np.pi * df_merged['hour'] / 24)
    df_merged['dow'] = df_merged['time'].dt.weekday
    df_merged['dow_sin'] = np.sin(2 * np.pi * df_merged['dow'] / 7)
    df_merged['dow_cos'] = np.cos(2 * np.pi * df_merged['dow'] / 7)

    # Session Flags
    df_merged['is_asian'] = ((df_merged['hour'] >= 23) | (df_merged['hour'] < 8)).astype(float)
    df_merged['is_london'] = ((df_merged['hour'] >= 8) & (df_merged['hour'] < 16)).astype(float)
    df_merged['is_ny'] = ((df_merged['hour'] >= 13) & (df_merged['hour'] < 21)).astype(float)

    return df_merged


def generate_feature_cols():
    """Generate the list of feature column names."""
    cols = []
    for name, _tf, _mins in OMNI_TIMEFRAMES:
        cols.extend([f"{name}_RSI", f"{name}_MACD", f"{name}_MACDs", f"{name}_ATR", f"{name}_VOL"])
    cols.extend(['hour_sin', 'hour_cos', 'dow_sin', 'dow_cos', 'is_asian', 'is_london', 'is_ny'])
    for asset in CROSS_ASSETS:
        cols.append(f'CA_{asset}_close')
    return cols
