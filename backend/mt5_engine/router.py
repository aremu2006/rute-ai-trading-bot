"""MT5 Engine FastAPI Router — /predict, /log_trade, /notify endpoints"""
import os
import sys
import time
import asyncio
import sqlite3
import hmac
import json
import logging

import numpy as np
from collections import deque
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional

from .config import (
    DB_FILE, get_api_key, _tunable, GLOBAL_KEY, MT5_AVAILABLE,
    MT5_INIT_ALLOWED, load_optuna_config,
)
from .db import init_db
from .models import load_all_models, _trade_outcomes, _models
from .prediction import run_prediction, compute_mtf_supertrend
from .guards import check_correlation_block, register_signal, cleanup_expired_signals
from .notifications import send_telegram
from .background import auto_retrain_loop, auto_optuna_loop, run_micro_learning

if MT5_AVAILABLE:
    import MetaTrader5 as mt5

log = logging.getLogger("mt5_engine.router")

# --- Pydantic Models ---
class PredictionRequest(BaseModel):
    symbol: str
    spread_pct: float = 0.0
    vol_percentile: float = 50.0
    news_distance_mins: float = 1440.0

class TradeLogRequest(BaseModel):
    symbol: str
    trade_type: str
    entry_price: float
    exit_price: Optional[float] = None
    outcome: str
    pnl: float
    prediction_id: Optional[int] = None

class NotifyRequest(BaseModel):
    message: str


# --- API Key Verification ---
def verify_api_key(x_api_key: str = Header(default=None)):
    key = get_api_key()
    if not x_api_key or not hmac.compare_digest(x_api_key, key):
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return True


# --- Lifespan for standalone usage ---
@asynccontextmanager
async def mt5_lifespan(app: FastAPI):
    """Lifespan manager: initializes MT5 ONLY when explicitly enabled."""
    if MT5_AVAILABLE and MT5_INIT_ALLOWED:
        if not mt5.initialize():
            log.error("MT5 init failed! Will use synthetic data if bootstrapping.")
    elif MT5_AVAILABLE and not MT5_INIT_ALLOWED:
        log.info("MT5 terminal NOT started — standalone mode. Set RUTE_MT5_ENABLED=1 to enable MT5 integration.")
    init_db()
    load_optuna_config()
    if "--train" not in sys.argv:
        load_all_models()
    retrain_task = asyncio.create_task(auto_retrain_loop())
    optuna_task = asyncio.create_task(auto_optuna_loop())
    yield
    retrain_task.cancel()
    optuna_task.cancel()
    if MT5_AVAILABLE and MT5_INIT_ALLOWED:
        mt5.shutdown()


# --- Router ---
mt5_router = APIRouter(tags=["MT5 Trading"])


@mt5_router.post("/predict")
async def predict(req: PredictionRequest, _auth: bool = Depends(verify_api_key)):
    try:
        import uuid
        pred_id = abs(uuid.uuid4().int) % 9223372036854775807

        result = await asyncio.to_thread(
            run_prediction, req.symbol, req.spread_pct,
            req.vol_percentile, req.news_distance_mins, pred_id
        )

        # Dynamic Confidence Engine
        wr = 0.5
        if len(_trade_outcomes) >= 5:
            wins = sum(1 for o in _trade_outcomes if o == "WIN")
            wr = wins / len(_trade_outcomes)

        dyn_threshold = _tunable["threshold_mid_wr"]
        if wr > 0.60:
            dyn_threshold = _tunable["threshold_high_wr"]
        elif wr < 0.40:
            dyn_threshold = _tunable["threshold_low_wr"]

        # AI-Optimized Trailing ATR
        vol_factor = req.vol_percentile / 100.0
        optimal_trail_atr = _tunable["trail_atr_base"] + (vol_factor * _tunable["trail_atr_scale"])

        result["prediction_id"] = pred_id
        result["dynamic_threshold"] = dyn_threshold
        result["win_rate"] = wr
        result["optimal_trail_atr"] = round(optimal_trail_atr, 2)

        # Multi-Timeframe SuperTrend Confluence Engine
        mtf_signals = await asyncio.to_thread(compute_mtf_supertrend, req.symbol)

        ai_direction = result["direction"]
        total_boost = 0.0
        confluences = []

        if mtf_signals["H1"] == ai_direction:
            total_boost += _tunable["boost_h1"]
            confluences.append("H1")
        if mtf_signals["H4"] == ai_direction:
            total_boost += _tunable["boost_h4"]
            confluences.append("H4")
        if mtf_signals["D1"] == ai_direction:
            total_boost += _tunable["boost_d1"]
            confluences.append("D1")

        st_confluence = "AGREE" if total_boost > 0 else "DISAGREE"

        if total_boost > 0:
            original_conf = result["confidence"]
            boosted_conf = min(1.0, original_conf + total_boost)
            result["confidence"] = round(boosted_conf, 4)
            log.info(f"[MTF SuperTrend] AI={ai_direction} ST={'+'.join(confluences)} → {st_confluence} | Conf: {original_conf:.4f} → {boosted_conf:.4f}")
        else:
            log.info(f"[MTF SuperTrend] AI={ai_direction} ST={mtf_signals} → DISAGREE | No boost")

        result["trade_approved"] = bool(result["confidence"] >= dyn_threshold)
        result["supertrend_signals"] = mtf_signals
        result["supertrend_confluence"] = st_confluence

        # Correlation Guard
        cleanup_expired_signals()
        correlation_blocked = False
        if result["trade_approved"]:
            if check_correlation_block(req.symbol, ai_direction):
                result["trade_approved"] = False
                correlation_blocked = True
                log.warning(f"[Correlation Guard] BLOCKED {ai_direction} {req.symbol}")
            else:
                register_signal(req.symbol, ai_direction)
        result["correlation_blocked"] = correlation_blocked

        return result
    except Exception as e:
        log.exception("Prediction failed")
        raise HTTPException(status_code=500, detail=str(e))


@mt5_router.post("/notify")
async def notify(req: NotifyRequest, _auth: bool = Depends(verify_api_key)):
    asyncio.create_task(asyncio.to_thread(send_telegram, req.message))
    return {"status": "ok"}


@mt5_router.post("/log_trade")
async def log_trade(req: TradeLogRequest, _auth: bool = Depends(verify_api_key)):
    try:
        data = req.model_dump()
        _trade_outcomes.append(data["outcome"])

        def insert():
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            feats_blob = None
            if req.prediction_id:
                c.execute("SELECT features_blob FROM pending_predictions WHERE prediction_id = ?",
                          (req.prediction_id,))
                row = c.fetchone()
                if row:
                    feats_blob = row[0]
                    c.execute("DELETE FROM pending_predictions WHERE prediction_id = ?",
                              (req.prediction_id,))

            c.execute("""
                INSERT INTO trade_history (symbol, trade_type, entry_price, exit_price, outcome, pnl, features, prediction_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data["symbol"], data["trade_type"], data["entry_price"],
                  data.get("exit_price"), data["outcome"], data["pnl"],
                  feats_blob, req.prediction_id))
            conn.commit()
            conn.close()

        await asyncio.to_thread(insert)

        if req.prediction_id:
            await asyncio.to_thread(run_micro_learning, data["symbol"])

        return {"status": "success"}
    except Exception as e:
        log.exception("Log failed")
        raise HTTPException(status_code=500, detail=str(e))
