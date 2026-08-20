"""MT5 Background Tasks — Auto-Retrain, Optuna (Bug #5 Fix), Micro-Learning"""
import os
import json
import time
import asyncio
import sqlite3
import logging

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.preprocessing import LabelEncoder
import optuna

from .config import (
    DB_FILE, FEATURE_COUNT, SEQ_LEN, GLOBAL_KEY,
    RETRAIN_INTERVAL_HOURS, AUTO_RETRAIN_MIN_TRADES,
    OPTUNA_MIN_TRADES, OPTUNA_CHECK_INTERVAL_HOURS, OPTUNA_N_TRIALS,
    OPTUNA_CONFIG_FILE, _tunable, model_paths,
)
from .models import (
    LSTMClassifier, train_from_db, get_model_for, _models,
    _trade_outcomes, _last_retrain_time,
)

log = logging.getLogger("mt5_engine.background")

_optuna_completed = False


def run_micro_learning(symbol: str):
    """Runs 3 epochs of online learning on the LSTM using a batch replay buffer."""
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(
            "SELECT features, outcome, trade_type FROM trade_history "
            "WHERE symbol=? AND features IS NOT NULL ORDER BY id DESC LIMIT 64",
            conn, params=(symbol,)
        )
        conn.close()

        if len(df) < 2:
            return

        X_list, y_list = [], []
        for _, row in df.iterrows():
            try:
                seq = np.frombuffer(row['features'], dtype=np.float32).reshape(SEQ_LEN, FEATURE_COUNT)
                X_list.append(seq)
                if row['outcome'] == "WIN":
                    y_list.append(row['trade_type'])
                else:
                    y_list.append("SELL" if row['trade_type'] == "BUY" else "BUY")
            except Exception:
                continue

        if len(X_list) < 2:
            return

        X_seq = np.array(X_list)
        y_arr = np.array(y_list)

        models, is_fallback = get_model_for(symbol)
        model_key = GLOBAL_KEY if is_fallback else symbol
        _, lstm_path, classes_path, _ = model_paths(model_key)

        if not os.path.exists(lstm_path) or not os.path.exists(classes_path):
            return

        with open(classes_path, "r") as f:
            classes = json.load(f)

        le = LabelEncoder()
        le.classes_ = np.array(classes)
        try:
            y_idx = le.transform(y_arr)
        except Exception:
            return

        X_t = torch.tensor(X_seq, dtype=torch.float32)
        y_t = torch.tensor(y_idx, dtype=torch.long)
        dataset = TensorDataset(X_t, y_t)
        loader = DataLoader(dataset, batch_size=16, shuffle=True)

        lstm_m = LSTMClassifier(input_size=FEATURE_COUNT, num_classes=len(classes))
        lstm_m.load_state_dict(torch.load(lstm_path, weights_only=True))
        lstm_m.train()

        optimizer = torch.optim.Adam(lstm_m.parameters(), lr=1e-4)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(3):
            for bx, by in loader:
                optimizer.zero_grad()
                out = lstm_m(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()

        torch.save(lstm_m.state_dict(), lstm_path)
        log.info(f"[Micro-Trainer] Replay batch (N={len(X_list)}) trained for {symbol}.")
    except Exception as e:
        log.error(f"Micro-learning failed: {e}")


async def auto_retrain_loop():
    """Background loop: periodically retrains models from trade history."""
    global _last_retrain_time
    while True:
        await asyncio.sleep(RETRAIN_INTERVAL_HOURS * 3600)
        try:
            if not os.path.exists(DB_FILE):
                continue

            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            from datetime import datetime, timezone
            last_dt = datetime.fromtimestamp(_last_retrain_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("SELECT DISTINCT symbol FROM trade_history WHERE features IS NOT NULL AND timestamp > ?", (last_dt,))
            symbols_to_check = [row[0] for row in cur.fetchall()]

            cur.execute("SELECT COUNT(*) FROM trade_history WHERE features IS NOT NULL AND timestamp > ?", (last_dt,))
            new_global_trades = cur.fetchone()[0]
            if GLOBAL_KEY not in symbols_to_check and new_global_trades > 0:
                symbols_to_check.append(GLOBAL_KEY)
            conn.close()

            for sym in symbols_to_check:
                conn = sqlite3.connect(DB_FILE)
                cur = conn.cursor()
                if sym == GLOBAL_KEY:
                    cur.execute("SELECT COUNT(*) FROM trade_history WHERE exit_price IS NOT NULL AND features IS NOT NULL")
                else:
                    cur.execute("SELECT COUNT(*) FROM trade_history WHERE symbol=? AND exit_price IS NOT NULL AND features IS NOT NULL", (sym,))
                total = cur.fetchone()[0]
                conn.close()

                if total >= AUTO_RETRAIN_MIN_TRADES:
                    log.info(f"[Auto-Retrain] Retraining {sym} from snapshots...")
                    try:
                        xgb_m, lstm_m, classes, scaler = await asyncio.to_thread(
                            train_from_db, None if sym == GLOBAL_KEY else sym, AUTO_RETRAIN_MIN_TRADES
                        )
                        _models[sym] = (xgb_m, lstm_m, classes, scaler)
                    except Exception as e:
                        log.error(f"Failed to retrain {sym}: {e}")

            _last_retrain_time = time.time()

            # Cleanup stale pending_predictions
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("DELETE FROM pending_predictions WHERE timestamp < datetime('now', '-1 day')")
                deleted = c.rowcount
                conn.commit()
                conn.close()
                if deleted > 0:
                    log.info(f"[Cleanup] Purged {deleted} stale pending_predictions rows.")
            except Exception as cleanup_err:
                log.error(f"[Cleanup] pending_predictions cleanup failed: {cleanup_err}")
        except Exception as e:
            log.exception(f"[Auto-Retrain] Error: {e}")


def _run_optuna_optimization():
    """
    BUG #5 FIX: Run Optuna using REAL model inference instead of synthetic noise.
    Loads actual XGBoost+LSTM models and runs ensemble predictions on stored feature snapshots.
    """
    global _optuna_completed

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(
        "SELECT trade_type, outcome, pnl, features FROM trade_history "
        "WHERE exit_price IS NOT NULL AND features IS NOT NULL",
        conn
    )
    conn.close()

    if len(df) < OPTUNA_MIN_TRADES:
        return

    records = []
    for _, row in df.iterrows():
        try:
            feats = np.frombuffer(row['features'], dtype=np.float32).reshape(SEQ_LEN, FEATURE_COUNT)
            records.append({
                "features": feats,
                "trade_type": row["trade_type"],
                "outcome": row["outcome"],
                "pnl": row["pnl"],
            })
        except Exception:
            continue

    if len(records) < OPTUNA_MIN_TRADES:
        return

    # BUG #5 FIX: Load real models for inference
    try:
        (xgb_m, lstm_m, classes, scaler), _ = get_model_for(GLOBAL_KEY)
    except Exception as e:
        log.error(f"[Optuna] Cannot load models for inference: {e}")
        return

    log.info(f"[Optuna] Starting optimization with {len(records)} trades and {OPTUNA_N_TRIALS} trials...")

    def objective(trial):
        boost_h1 = trial.suggest_float("boost_h1", 0.01, 0.10)
        boost_h4 = trial.suggest_float("boost_h4", 0.02, 0.12)
        boost_d1 = trial.suggest_float("boost_d1", 0.03, 0.15)
        threshold_mid = trial.suggest_float("threshold_mid_wr", 0.50, 0.75)
        threshold_high = trial.suggest_float("threshold_high_wr", 0.40, threshold_mid)
        threshold_low = trial.suggest_float("threshold_low_wr", threshold_mid, 0.85)
        trail_base = trial.suggest_float("trail_atr_base", 0.5, 2.0)
        trail_scale = trial.suggest_float("trail_atr_scale", 0.5, 3.0)

        total_pnl = 0.0
        trades_taken = 0
        wins = 0

        for rec in records:
            # BUG #5 FIX: Use REAL model inference
            X_flat = rec["features"][-1].reshape(1, -1)
            X_seq_t = torch.tensor(rec["features"]).unsqueeze(0).float()

            if scaler is not None:
                X_flat = scaler.transform(X_flat)

            xgb_proba = xgb_m.predict_proba(X_flat)[0]
            with torch.no_grad():
                lstm_logits = lstm_m(X_seq_t)
                lstm_proba = torch.softmax(lstm_logits, dim=1).numpy()[0]

            ensemble_proba = (xgb_proba + lstm_proba) / 2.0
            best_idx = int(np.argmax(ensemble_proba))
            real_confidence = float(ensemble_proba[best_idx])
            predicted_dir = classes[best_idx]

            # Simulate SuperTrend boost
            same_direction = (predicted_dir == rec["trade_type"])
            if same_direction:
                real_confidence += boost_h1 + boost_h4 * 0.5

            # Apply dynamic threshold
            threshold = threshold_mid
            if trades_taken > 10:
                wr = wins / trades_taken
                if wr > 0.60:
                    threshold = threshold_high
                elif wr < 0.40:
                    threshold = threshold_low

            if real_confidence >= threshold:
                trades_taken += 1
                total_pnl += rec["pnl"]
                if rec["outcome"] == "WIN":
                    wins += 1

        if trades_taken < 10:
            return -1000.0

        win_rate = wins / trades_taken
        score = total_pnl + (win_rate * trades_taken * 0.1)
        return score

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize", study_name="trading_optimizer")
    study.optimize(objective, n_trials=OPTUNA_N_TRIALS, show_progress_bar=False)

    best = study.best_params
    log.info(f"[Optuna] Optimization complete! Best score: {study.best_value:.2f}")
    log.info(f"[Optuna] Best params: {json.dumps(best, indent=2)}")

    with open(OPTUNA_CONFIG_FILE, "w") as f:
        json.dump(best, f, indent=2)

    _tunable.update(best)
    _optuna_completed = True
    log.info(f"[Optuna] Parameters applied and saved to {OPTUNA_CONFIG_FILE}")


async def auto_optuna_loop():
    """Background loop: checks trade count and auto-runs Optuna when ready."""
    global _optuna_completed
    while True:
        await asyncio.sleep(OPTUNA_CHECK_INTERVAL_HOURS * 3600)

        if _optuna_completed:
            continue

        try:
            if not os.path.exists(DB_FILE):
                continue

            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM trade_history WHERE exit_price IS NOT NULL AND features IS NOT NULL")
            count = cur.fetchone()[0]
            conn.close()

            log.info(f"[Optuna Monitor] Trade count: {count}/{OPTUNA_MIN_TRADES}")

            if count >= OPTUNA_MIN_TRADES:
                log.info("[Optuna Monitor] Threshold reached! Launching optimization...")
                await asyncio.to_thread(_run_optuna_optimization)

        except Exception as e:
            log.error(f"[Optuna Monitor] Error: {e}")
