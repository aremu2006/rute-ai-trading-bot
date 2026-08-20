"""MT5 Prediction Engine with TTL-cached SuperTrend (Fix #9)"""
import time
import sqlite3
import logging

import numpy as np
import pandas as pd
import torch

from .config import (
    DB_FILE, FEATURE_COUNT, SEQ_LEN, MT5_AVAILABLE, model_paths,
)
from .features import generate_feature_cols
from .models import get_model_for

if MT5_AVAILABLE:
    import MetaTrader5 as mt5
    from . import custom_ta

log = logging.getLogger("mt5_engine.prediction")

# --- FIX #9: TTL Cache for SuperTrend ---
_st_cache = {}  # key: (symbol, tf_name) -> {"data": signals, "timestamp": float}
_ST_TTL = {"H1": 60, "H4": 300, "D1": 1800}  # seconds


def compute_mtf_supertrend(symbol: str):
    """Calculate SuperTrend on H1, H4, D1 with EMA200 trend filter. Uses TTL cache."""
    if not MT5_AVAILABLE:
        return {"H1": None, "H4": None, "D1": None}

    is_crypto = symbol.endswith("m") and any(x in symbol for x in ["BTC", "ETH", "AAVE"])
    period = 12 if is_crypto else 10
    multiplier = 4.0 if is_crypto else 3.0

    signals = {"H1": None, "H4": None, "D1": None}
    tfs = {"H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1}

    now = time.time()

    for tf_name, tf_val in tfs.items():
        # FIX #9: Check cache first
        cache_key = (symbol, tf_name)
        cached = _st_cache.get(cache_key)
        if cached and (now - cached["timestamp"]) < _ST_TTL.get(tf_name, 60):
            signals[tf_name] = cached["data"]
            continue

        try:
            rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, 300)
            if rates is None or len(rates) < 210:
                continue
            df = pd.DataFrame(rates)
            df.columns = [c.lower() for c in df.columns]
            st = custom_ta.get_supertrend(df, length=period, multiplier=multiplier)
            if st is None or st.empty:
                continue
            dir_col = [c for c in st.columns if c.startswith("SUPERTd_")]
            if not dir_col:
                continue

            custom_ta.add_ema(df, length=200)
            ema_col = [c for c in df.columns if c.startswith("EMA_200")]

            last_dir = st[dir_col[0]].iloc[-1]
            last_close = df['close'].iloc[-1]

            sig = "BUY" if last_dir == 1 else "SELL" if last_dir == -1 else None

            if sig and ema_col and not pd.isna(df[ema_col[0]].iloc[-1]):
                ema_val = df[ema_col[0]].iloc[-1]
                if sig == "BUY" and last_close < ema_val:
                    sig = None
                if sig == "SELL" and last_close > ema_val:
                    sig = None

            signals[tf_name] = sig
            # FIX #9: Update cache
            _st_cache[cache_key] = {"data": sig, "timestamp": now}
        except Exception as e:
            log.warning(f"[MTF SuperTrend] {tf_name} failed for {symbol}: {e}")

    return signals


def run_prediction(symbol: str, spread_pct: float, vol_percentile: float,
                   news_distance_mins: float, pred_id: int):
    """Run full ensemble inference with feature scaling."""
    (xgb_m, lstm_m, classes, scaler), used_fallback = get_model_for(symbol)

    from .features import fetch_mtf_features_df
    df = fetch_mtf_features_df(symbol, n_candles=SEQ_LEN + 100)
    if df is None:
        raise ValueError(f"Could not fetch enough MT5 data for {symbol}.")

    feature_cols = generate_feature_cols()
    feats = df.tail(SEQ_LEN)[feature_cols].values.astype(np.float32)

    # Inject Market Context
    context = np.array([spread_pct, vol_percentile, news_distance_mins], dtype=np.float32)
    feats_with_context = np.zeros((SEQ_LEN, FEATURE_COUNT), dtype=np.float32)
    for i in range(SEQ_LEN):
        feats_with_context[i] = np.concatenate((feats[i], context))

    # Snapshot for retraining
    features_bytes = feats_with_context.tobytes()

    def save_pending():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO pending_predictions (prediction_id, features_blob) VALUES (?, ?)",
                  (pred_id, features_bytes))
        conn.commit()
        conn.close()

    save_pending()

    # BUG #6 FIX: Apply scaler before inference
    if scaler is not None:
        X_flat = scaler.transform(feats_with_context[-1].reshape(1, -1))
        X_seq_scaled = np.zeros_like(feats_with_context)
        for i in range(SEQ_LEN):
            X_seq_scaled[i] = scaler.transform(feats_with_context[i].reshape(1, -1))[0]
        X_seq = torch.tensor(X_seq_scaled).unsqueeze(0).float()
    else:
        X_flat = feats_with_context[-1].reshape(1, -1)
        X_seq = torch.tensor(feats_with_context).unsqueeze(0).float()

    # Inference
    xgb_proba = xgb_m.predict_proba(X_flat)[0]
    with torch.no_grad():
        lstm_logits = lstm_m(X_seq)
        lstm_proba = torch.softmax(lstm_logits, dim=1).numpy()[0]

    ensemble_proba = (xgb_proba + lstm_proba) / 2.0
    best_idx = int(np.argmax(ensemble_proba))

    return {
        "direction": classes[best_idx],
        "confidence": round(float(ensemble_proba[best_idx]), 4),
        "model_used": "global_fallback" if used_fallback else symbol,
    }
