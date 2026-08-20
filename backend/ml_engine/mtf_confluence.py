"""Multi-Timeframe SuperTrend confluence for the UI recommendation path.

Reuses the exact SuperTrend + EMA200 filter logic from the MT5 engine
(custom_ta / prediction.compute_mtf_supertrend) so both paths behave the same:

  - H1 / H4 / D1 SuperTrend direction (params differ for crypto, like MT5)
  - EMA200 trend filter per timeframe (BUY vetoed below EMA200, SELL above)
  - Boosts: H1 +3, H4 +4, D1 +8 (mirror mt5_engine.config SUPERTREND_BOOST_*)

Data sources, in order:
  1. MT5 (live terminal) when connected for the symbol
  2. data_providers fallback: hourly bars for H1, 4h-resampled H4, caller's daily df for D1
"""
import logging

import numpy as np
import pandas as pd

try:
    from mt5_engine import custom_ta
    from mt5_engine.prediction import compute_mtf_supertrend as _mt5_mtf
except Exception:  # pragma: no cover - engine import chain may fail on dev boxes
    custom_ta = None
    _mt5_mtf = None

from data_providers import get_historical_ohlcv

log = logging.getLogger("mtf_confluence")

TFS = ("H1", "H4", "D1")

# Mirror mt5_engine.config: SUPERTREND_BOOST_H1/H4/D1 (0.03 / 0.04 / 0.08)
BOOSTS = {"H1": 3, "H4": 4, "D1": 8}

# SuperTrend params: same tuning split used by the MT5 engine
_ST_CRYPTO = {"length": 12, "multiplier": 4.0}
_ST_DEFAULT = {"length": 10, "multiplier": 3.0}

# Enough history for EMA200 + SuperTrend warm-up (2y of hourly = 730 rows, 4h-resample = 210)
_H1_FETCH_PERIOD = "2y"
_H1_FETCH_INTERVAL = "1h"


def _mt5_symbol(symbol: str) -> str:
    """Convert extension symbol (BTC-USD / EURUSD=X) to MT5 format (BTCUSDm / EURUSD)."""
    if symbol.endswith("=X"):
        return symbol[:-2]
    if "-USD" in symbol:
        return symbol.replace("-USD", "USD").replace("-", "")
    return symbol


def _st_dir(df: pd.DataFrame, is_crypto: bool, min_bars: int = 210) -> str:
    """Return 'BUY'/'SELL'/None for a lowercase-close OHLC df after EMA200 filter."""
    if custom_ta is None or df is None or df.empty:
        return None
    if len(df) < min_bars:
        return None
    params = _ST_CRYPTO if is_crypto else _ST_DEFAULT
    try:
        st = custom_ta.get_supertrend(df, length=params["length"], multiplier=params["multiplier"])
        dir_col = [c for c in st.columns if c.startswith("SUPERTd_")]
        if not dir_col:
            return None
        custom_ta.add_ema(df, length=200)
        ema_col = [c for c in df.columns if c.startswith("EMA_200")]

        last_dir = st[dir_col[0]].iloc[-1]
        last_close = df["close"].iloc[-1]
        sig = "BUY" if last_dir == 1 else "SELL" if last_dir == -1 else None
        if sig is None:
            return None
        if ema_col and not pd.isna(df[ema_col[0]].iloc[-1]):
            ema_val = df[ema_col[0]].iloc[-1]
            if sig == "BUY" and last_close < ema_val:
                return None
            if sig == "SELL" and last_close > ema_val:
                return None
        return sig
    except Exception as e:
        log.warning(f"SuperTrend calc failed: {e}")
        return None


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Rename OHLC columns to the lowercase form custom_ta expects."""
    if df is None or df.empty:
        return df
    ren = {c: c.lower() for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns}
    return df.rename(columns=ren)


def _providers_confluence(symbol: str, daily_df: pd.DataFrame, api_keys: dict) -> dict:
    """Compute MTF signals from data providers (no MT5 needed)."""
    is_crypto = "-USD" in symbol
    sigs = {"H1": None, "H4": None, "D1": None}
    try:
        h1 = get_historical_ohlcv(symbol, _H1_FETCH_PERIOD, _H1_FETCH_INTERVAL, api_keys or {})
        if h1 is not None and not h1.empty and len(h1) >= 210:
            h1_n = _normalize(h1)
            sigs["H1"] = _st_dir(h1_n, is_crypto)
            try:
                h4 = h1.resample("4h").agg(
                    {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
                ).dropna(subset=["Close"])
                if len(h4) >= 210:
                    sigs["H4"] = _st_dir(_normalize(h4), is_crypto)
            except Exception as e:
                log.warning(f"H4 resample failed for {symbol}: {e}")
    except Exception as e:
        log.warning(f"H1 fetch failed for {symbol}: {e}")

    if daily_df is not None and not daily_df.empty and len(daily_df) >= 210:
        sigs["D1"] = _st_dir(_normalize(daily_df), is_crypto)
    return sigs


def get_mtf_confluence(symbol: str, daily_df: pd.DataFrame = None, api_keys: dict = None) -> dict:
    """Return {'H1','H4','D1': 'BUY'|'SELL'|None, 'source': ...} for a symbol.

    Tries the live MT5 engine first, then falls back to data providers.
    """
    if _mt5_mtf is not None:
        try:
            mtf = _mt5_mtf(_mt5_symbol(symbol))
            if any(mtf.get(tf) is not None for tf in TFS):
                mtf["source"] = "mt5"
                return mtf
        except Exception as e:
            log.warning(f"MT5 MTF SuperTrend failed for {symbol}: {e}")

    sigs = _providers_confluence(symbol, daily_df, api_keys or {})
    sigs["source"] = "providers"
    return sigs


def apply_mtf_boost(conf: dict, trade_type: str):
    """Apply SuperTrend confluence boosts to a direction.

    Returns (boost_delta, messages): each agreeing timeframe adds its preset
    boost; no boost when the timeframes disagree — mirrors the MT5 router.
    """
    total = 0
    matched = []
    conflicts = []
    for tf in TFS:
        sig = conf.get(tf) if conf else None
        if sig is None:
            continue
        if sig == trade_type:
            total += BOOSTS[tf]
            matched.append(tf)
        else:
            conflicts.append(tf)

    msgs = []
    if total > 0:
        msgs.append(f"MTF SuperTrend confluence ({'+'.join(matched)}) aligns with {trade_type} -> +{total}% ({conf.get('source', '?')})")
    if conflicts:
        msgs.append(f"MTF SuperTrend: {'+'.join(conflicts)} disagree -> no boost")
    if not total and not conflicts:
        msgs.append("MTF SuperTrend: no timeframe data available")

    return total, msgs