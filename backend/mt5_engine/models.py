"""MT5 Engine Models — XGBoost + LSTM Ensemble with StandardScaler (Bug #6 Fix)"""
import os
import json
import time
import sqlite3
import logging
from collections import deque
from datetime import datetime

import numpy as np
import pandas as pd
import joblib
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import LabelEncoder, StandardScaler
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader

from .config import (
    DB_FILE, MODEL_ROOT, GLOBAL_KEY, FEATURE_COUNT, SEQ_LEN,
    AUTO_RETRAIN_MIN_TRADES, MT5_AVAILABLE, model_dir, model_paths
)
from .features import fetch_mtf_features_df, generate_feature_cols

if MT5_AVAILABLE:
    import MetaTrader5 as mt5

log = logging.getLogger("mt5_engine.models")

# --- State Tracking ---
_trade_outcomes = deque(maxlen=20)
_models: dict = {}
_last_retrain_time = time.time()
_active_signals: dict = {}


class LSTMClassifier(nn.Module):
    def __init__(self, input_size=FEATURE_COUNT, hidden_size=64, num_classes=3):
        super(LSTMClassifier, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers=2, batch_first=True, dropout=0.1)
        self.fc = nn.Linear(hidden_size, num_classes)

    def forward(self, x):
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out


def fit_and_save(X_seq, X_flat, y, symbol: str):
    """Train XGBoost + LSTM ensemble and save models with scaler (Bug #6 Fix)."""
    le = LabelEncoder()
    y_idx = le.fit_transform(y)
    classes = list(le.classes_)

    # BUG #6 FIX: Fit a StandardScaler on the flat features
    scaler = StandardScaler()
    X_flat_scaled = scaler.fit_transform(X_flat)

    # 1. XGBoost (on scaled flat features)
    xgb_base = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, tree_method='hist')
    xgb_calibrated = CalibratedClassifierCV(xgb_base, method="isotonic", cv=3)
    xgb_calibrated.fit(X_flat_scaled, y_idx)

    # 2. LSTM (on scaled sequences)
    # Scale each timestep in the sequence using the same scaler
    X_seq_scaled = np.zeros_like(X_seq)
    for i in range(X_seq.shape[0]):
        X_seq_scaled[i] = scaler.transform(X_seq[i])

    train_data = TensorDataset(
        torch.tensor(X_seq_scaled, dtype=torch.float32),
        torch.tensor(y_idx, dtype=torch.long)
    )
    train_loader = DataLoader(train_data, batch_size=32, shuffle=True)

    lstm_model = LSTMClassifier(input_size=X_seq.shape[2], num_classes=len(classes))
    optimizer = torch.optim.Adam(lstm_model.parameters(), lr=0.005)
    criterion = nn.CrossEntropyLoss()

    lstm_model.train()
    for epoch in range(20):
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            loss = criterion(lstm_model(batch_x), batch_y)
            loss.backward()
            optimizer.step()

    lstm_model.eval()

    # Save all artifacts
    d = model_dir(symbol)
    os.makedirs(d, exist_ok=True)
    xgb_path, lstm_path, cls_path, scaler_path = model_paths(symbol)

    joblib.dump(xgb_calibrated, xgb_path)
    torch.save(lstm_model.state_dict(), lstm_path)
    with open(cls_path, "w") as f:
        json.dump(classes, f)
    joblib.dump(scaler, scaler_path)  # BUG #6 FIX: Save scaler

    return xgb_calibrated, lstm_model, classes, scaler


def generate_synthetic_data(n=500):
    log.warning("Generating SYNTHETIC data for fallback bootstrap.")
    X_seq = np.random.randn(n, SEQ_LEN, FEATURE_COUNT).astype(np.float32)
    X_flat = X_seq[:, -1, :]
    y = np.random.choice(["BUY", "SELL"], size=n)
    return X_seq, X_flat, y


def bootstrap_data(n=500):
    if not MT5_AVAILABLE or not mt5.terminal_info():
        return generate_synthetic_data(n)

    df = fetch_mtf_features_df("EURUSDm", n_candles=n + 150)
    if df is None:
        symbols = mt5.symbols_get()
        if symbols:
            for s in symbols:
                df = fetch_mtf_features_df(s.name, n_candles=n + 150)
                if df is not None:
                    log.info(f"Using {s.name} for bootstrap data instead of EURUSD.")
                    break

    if df is None:
        log.error("MT5 connected but no symbol has enough data.")
        return generate_synthetic_data(n)

    feature_cols = generate_feature_cols()
    X_seq, X_flat, y = [], [], []
    for i in range(SEQ_LEN, len(df) - 1):
        direction = "BUY" if df.iloc[i + 1]['M1_close'] > df.iloc[i]['M1_close'] else "SELL"
        slice_df = df.iloc[i - SEQ_LEN:i]
        feats = slice_df[feature_cols].values

        # Context features with realistic variance
        synthetic_spread = max(0.01, np.random.normal(0.05, 0.02))
        synthetic_vol = max(1.0, min(100.0, np.random.normal(50.0, 20.0)))
        synthetic_news = max(1.0, np.random.normal(1440.0, 500.0))
        context = np.array([synthetic_spread, synthetic_vol, synthetic_news], dtype=np.float32)

        padded_feats = np.zeros((feats.shape[0], FEATURE_COUNT), dtype=np.float32)
        for j in range(feats.shape[0]):
            padded_feats[j] = np.concatenate((feats[j], context))

        X_seq.append(padded_feats)
        X_flat.append(padded_feats[-1])
        y.append(direction)

    return np.array(X_seq, dtype=np.float32), np.array(X_flat, dtype=np.float32), np.array(y)


def train_bootstrap(symbol: str = None):
    symbol = symbol or GLOBAL_KEY
    log.info(f"[{symbol}] Training bootstrap model...")
    X_seq, X_flat, y = bootstrap_data(n=1000)
    return fit_and_save(X_seq, X_flat, y, symbol)


def train_from_db(symbol=None, min_trades=100):
    if not os.path.exists(DB_FILE):
        raise RuntimeError("No trade history to train on.")

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    query = "SELECT trade_type, outcome, features FROM trade_history WHERE exit_price IS NOT NULL AND features IS NOT NULL"
    if symbol:
        cur.execute(query + " AND symbol = ? ORDER BY timestamp ASC", (symbol,))
    else:
        cur.execute(query + " ORDER BY timestamp ASC")
    rows = cur.fetchall()
    conn.close()

    if len(rows) < min_trades:
        raise RuntimeError(f"Only {len(rows)} usable trades with features, need >= {min_trades}.")

    X_seq, X_flat, y = [], [], []
    for t_type, outcome, f_blob in rows:
        try:
            feats = np.frombuffer(f_blob, dtype=np.float32).reshape((SEQ_LEN, FEATURE_COUNT))
            if outcome == "WIN":
                y.append(t_type)
            else:
                y.append("SELL" if t_type == "BUY" else "BUY")
            X_seq.append(feats)
            X_flat.append(feats[-1])
        except Exception:
            continue

    if len(y) < min_trades:
        raise RuntimeError(f"Not enough valid historical sequences extracted ({len(y)}).")

    key = symbol if symbol else GLOBAL_KEY
    log.info(f"[{key}] Training on {len(X_seq)} real logged trade snapshots.")
    return fit_and_save(np.array(X_seq), np.array(X_flat), np.array(y), key)


def load_all_models():
    """Load all saved models from disk into memory."""
    global _models
    _models = {}
    if os.path.isdir(MODEL_ROOT):
        for entry in os.listdir(MODEL_ROOT):
            xp, lp, cp, sp = model_paths(entry)
            if os.path.exists(xp) and os.path.exists(lp) and os.path.exists(cp):
                xgb_m = joblib.load(xp)
                with open(cp) as f:
                    classes = json.load(f)
                lstm_m = LSTMClassifier(input_size=FEATURE_COUNT, num_classes=len(classes))
                lstm_m.load_state_dict(torch.load(lp, weights_only=True))
                lstm_m.eval()
                # BUG #6 FIX: Load scaler if available
                scaler = joblib.load(sp) if os.path.exists(sp) else None
                _models[entry] = (xgb_m, lstm_m, classes, scaler)
                log.info(f"Loaded Ensemble model for '{entry}' (scaler={'yes' if scaler else 'no'})")

    if GLOBAL_KEY not in _models:
        log.warning("No global fallback model found. Bootstrapping...")
        try:
            xgb_m, lstm_m, classes, scaler = train_bootstrap(GLOBAL_KEY)
            _models[GLOBAL_KEY] = (xgb_m, lstm_m, classes, scaler)
        except Exception as e:
            log.error(f"Bootstrap failed: {e}")


def get_model_for(symbol: str):
    """Get model tuple for a symbol, falling back to global."""
    key = symbol if symbol in _models else GLOBAL_KEY
    if key not in _models:
        raise RuntimeError("No models available.")
    return _models[key], key != symbol
