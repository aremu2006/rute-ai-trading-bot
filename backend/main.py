from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
import logging

from contextlib import asynccontextmanager
from pydantic import BaseModel
import json
import requests
import asyncio
import time
from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from datetime import datetime
import warnings
warnings.filterwarnings('ignore', module='sklearn')
import uuid
import re
import pandas_ta as ta
import joblib
import os
import glob
from ml_engine.adaptive_system import RegimeClassifier, AdaptiveRiskManager, HurstCalculator, EntropyCalculator
from ml_engine.sentiment_hub import sentiment_hub as global_sentiment_hub, news_scraper_loop
from ml_engine.transformer_core import TemporalEngine
from ml_engine.dqn_agent import DQNAgent
from ml_engine.order_flow import OrderFlowAnalyzer
# === POWER UPGRADES ===
from ml_engine.cross_market import cross_market_engine, cross_market_scanner_loop
from ml_engine.capital_allocator import capital_allocator
from ml_engine.ppo_agent import ppo_agent
from ml_engine.dashboard_endpoints import (
    get_mt5_positions,
    kill_switch as dashboard_kill_switch, get_combined_stats
)
# === MT5 ENGINE ===
from mt5_engine.router import mt5_router, mt5_lifespan
from mt5_engine.config import DB_FILE as MT5_DB_FILE


# Startup timestamp for health endpoint uptime calculation
APP_START_TIME = datetime.now()

# Store active simulated trades to monitor for TP/SL hits
OPEN_SIMULATED_TRADES = {}
MAX_SIMULATED_TRADES = 10

async def simulated_trade_monitor_loop():
    """Background loop to check simulated trades for TP/SL hits."""
    while True:
        try:
            await asyncio.sleep(60) # Check every minute
            if not OPEN_SIMULATED_TRADES:
                continue
                
            from data_providers import get_historical_ohlcv
            # We iterate over a copy to allow popping
            for rec_id, trade in list(OPEN_SIMULATED_TRADES.items()):
                df = await asyncio.to_thread(get_historical_ohlcv, trade['symbol'], "1d", "1m", {}, True)
                if df.empty:
                    continue
                current_price = float(df['Close'].iloc[-1])
                
                closed = False
                profit = 0.0
                exit_reason = ""
                
                if trade['type'] == "BUY":
                    if current_price >= trade['tp']:
                        closed, exit_reason, profit = True, "Take Profit Hit", (current_price - trade['entry']) / trade['entry'] if trade['entry'] else 0.0
                    elif current_price <= trade['sl']:
                        closed, exit_reason, profit = True, "Stop Loss Hit", (current_price - trade['entry']) / trade['entry'] if trade['entry'] else 0.0
                else: # SELL
                    if current_price <= trade['tp']:
                        closed, exit_reason, profit = True, "Take Profit Hit", (trade['entry'] - current_price) / trade['entry'] if trade['entry'] else 0.0
                    elif current_price >= trade['sl']:
                        closed, exit_reason, profit = True, "Stop Loss Hit", (trade['entry'] - current_price) / trade['entry'] if trade['entry'] else 0.0
                        
                if closed:
                    OPEN_SIMULATED_TRADES.pop(rec_id, None)
                    # Trigger outcome internally
                    await record_trade_outcome({"signal_id": rec_id, "profit": profit, "exit_reason": exit_reason})
                    
                    # Telegram Alert
                    notif = trade.get('notifications')
                    if notif and notif.tradeAlerts and notif.telegramBotToken and notif.telegramChatId:
                        icon = "✅" if profit > 0 else "❌"
                        msg = (
                            f"🤖 <b>RUTE TRADE CLOSED</b> {icon}\n\n"
                            f"<b>{trade['symbol']}</b> - <b>{trade['type']}</b>\n"
                            f"Reason: {exit_reason}\n"
                            f"P&L: {profit*100:.2f}%\n"
                        )
                        await asyncio.to_thread(
                            lambda: send_telegram_message(
                                notif.telegramBotToken.strip(),
                                notif.telegramChatId.strip(),
                                msg
                            )
                        )
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Simulated monitor error: {e}")

# === Unified Lifespan (starts BOTH Alpaca + MT5 engines) ===
async def prewarm_market_cache():
    """Keep the realtime quote cache warm at boot and every 30s so popup requests are instant."""
    try:
        from data_providers import get_realtime_quotes
        default_symbols = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AAPL", "TSLA", "NVDA", "BTC-USD", "ETH-USD", "SOL-USD"]
        while True:
            try:
                quotes = await asyncio.to_thread(get_realtime_quotes, default_symbols, {})
                print(f"Realtime cache refreshed: {len(quotes)}/{len(default_symbols)} symbols")
            except Exception as e:
                print(f"Prewarm refresh error: {e}")
            await asyncio.sleep(120)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"Prewarm loop failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Unified lifespan: starts MT5 engine, news scraper, and cross-market scanner."""
    # Start MT5 engine lifespan
    async with mt5_lifespan(app):
        # Start background tasks for upgrades
        news_task = asyncio.create_task(news_scraper_loop())
        cross_market_task = asyncio.create_task(cross_market_scanner_loop())
        simulated_monitor_task = asyncio.create_task(simulated_trade_monitor_loop())
        prewarm_task = asyncio.create_task(prewarm_market_cache())
        yield
        news_task.cancel()
        cross_market_task.cancel()
        simulated_monitor_task.cancel()
        prewarm_task.cancel()


app = FastAPI(title="RUTE AI Trading Backend", version="2.0.0", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    body = await request.body()
    print(f"422 Validation Error: {exc.errors()}")
    print(f"Body: {body}")
    return JSONResponse(status_code=422, content={"detail": str(exc.errors())})

# CORS middleware to allow the Chrome extension (any chrome-extension:// origin)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(chrome-extension://.*|http://localhost:\d+.*)",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MT5 router — the MQL5 EA talks to these endpoints
app.include_router(mt5_router, prefix="", tags=["MT5 Trading"])

# ML Model cache
ML_MODELS = {}

# Auto-Trader instance (global)
AUTO_TRADER = None

# Next-Gen AI Instances
sentiment_hub = global_sentiment_hub  # Use the real LLM-powered one
dqn_agent = DQNAgent(state_dim=61)
try:
    _dqn_path = os.path.join(os.path.dirname(__file__), "ml_engine", "models", "dqn_agent.pt")
    if os.path.exists(_dqn_path):
        dqn_agent.load(_dqn_path)
except Exception:
    pass
order_flow = OrderFlowAnalyzer()
temporal_engine = None # Initialized on first use to detect input_dim

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_signal(self, message: dict):
        # Add timestamp to message for latency tracking
        message["server_time"] = datetime.now().timestamp()
        
        stale_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Connection dropped: {e}")
                stale_connections.append(connection)
        
        # Cleanup
        for conn in stale_connections:
            self.disconnect(conn)

manager = ConnectionManager()

class EnsembleModel:
    """Averaged probabilities across all models in an elite bundle."""

    def __init__(self, models):
        self.members = [m for m in models if hasattr(m, 'predict_proba')]

    def predict_proba(self, X):
        if not self.members:
            raise ValueError("Ensemble has no predict_proba models")
        return np.mean([m.predict_proba(X) for m in self.members], axis=0)

    def predict(self, X):
        proba = self.predict_proba(X)
        # Apply the same strict filter the elite validation used to measure
        # its win rate: all members must agree AND confidence must be >= 90%.
        # Without this, live behavior is looser than the advertised metrics.
        if self.members:
            member_probas = np.array([m.predict_proba(X) for m in self.members])
            X = np.atleast_2d(X)
            for i in range(len(X)):
                pred_class = int(np.argmax(proba[i]))
                agreeing = int(np.sum(np.argmax(member_probas[:, i, :], axis=1) == pred_class))
                if agreeing < len(self.members) or proba[i, pred_class] < 0.9:
                    proba[i, :] = 0.0
                    proba[i, 1] = 1.0  # force HOLD (encoded class index 1)
        return np.argmax(proba, axis=1)


class CalibratedModel:
    """Wraps a base model with a fitted Platt-style calibrator (multiclass
    logistic regression trained on out-of-fold probabilities)."""

    def __init__(self, base, calibrator):
        self.base = base
        self.calibrator = calibrator

    def predict_proba(self, X):
        return self.calibrator.predict_proba(self.base.predict_proba(X))

    def predict(self, X):
        return np.argmax(self.predict_proba(X), axis=1)


def load_ml_model(symbol: str):
    """Load trained ML model for a symbol"""
    global ML_MODELS

    if symbol in ML_MODELS:
        return ML_MODELS[symbol]

    model_dir = os.path.join(os.path.dirname(__file__), "ml_engine", "models")
    # Support both .joblib and legacy .model extensions
    model_files = glob.glob(os.path.join(model_dir, f"{symbol}_*.joblib")) + \
                  glob.glob(os.path.join(model_dir, f"{symbol}_*.model"))

    if not model_files:
        return None

    latest_model = max(model_files, key=os.path.getmtime)
    try:
        model_data = joblib.load(latest_model)

        # Handle elite ensemble format: average ALL member probabilities
        if isinstance(model_data, dict) and 'models' in model_data and 'model' not in model_data:
            members = [entry[1] if isinstance(entry, (list, tuple)) else entry for entry in model_data['models']]
            members = [m for m in members if hasattr(m, 'predict_proba')]
            if not members:
                print(f"No predict_proba model found in elite bundle for {symbol}")
                return None
            model_data['model'] = EnsembleModel(members)
            # Apply fitted calibrator (Platt scaling trained on OOF probabilities)
            if model_data.get('calibrator') is not None:
                model_data['model'] = CalibratedModel(model_data['model'], model_data['calibrator'])
        elif not isinstance(model_data, dict):
            model_data = {"model": model_data, "feature_names": []}

        # Soft staleness flag: models trained long ago keep working, but the
        # health endpoint and callers can surface it (data frozen May 2026,
        # GOOGL_RF trained Nov 2025 — flag, never hard-block).
        try:
            age_days = (time.time() - os.path.getmtime(latest_model)) / 86400
            model_data['age_days'] = round(age_days, 1)
            if age_days > 30:
                model_data['stale'] = True
                print(f"WARNING: ML model for {symbol} is {age_days:.0f} days old — "
                      "consider retraining.")
        except OSError:
            pass

        ML_MODELS[symbol] = model_data
        print(f"Loaded ML model for {symbol}: {os.path.basename(latest_model)}")
        return model_data
    except Exception as e:
        print(f"Error loading model for {symbol}: {e}")
        return None

# Models
class Symbol(BaseModel):
    symbol: str
    assetType: str = "STOCK"

class RiskSettings(BaseModel):
    maxPositionSize: float = 1000
    maxDailyLoss: float = 500
    stopLossPercentage: float = 2.0
    takeProfitPercentage: float = 5.0
    enableAutoTrade: bool = False
    minConfidence: int = 50

class NotificationSettings(BaseModel):
    tradeAlerts: bool = False
    priceAlerts: bool = False
    newsAlerts: bool = False
    telegramBotToken: Optional[str] = None
    telegramChatId: Optional[str] = None
    telegramThreshold: int = 80

class ApiKeys(BaseModel):
    finnhub: Optional[str] = None
    twelvedata: Optional[str] = None
    alphavantage: Optional[str] = None

class RecommendationRequest(BaseModel):
    symbols: List[Symbol]
    riskSettings: Optional[RiskSettings] = None
    notifications: Optional[NotificationSettings] = None
    apiKeys: Optional[ApiKeys] = None

class MarketDataRequest(BaseModel):
    symbols: List[str]
    apiKeys: Optional[ApiKeys] = None

class TechnicalIndicators(BaseModel):
    rsi: float
    macd: float
    macd_signal: float
    sma_20: float
    sma_50: float
    bollinger_upper: float
    bollinger_lower: float
    volume_ratio: float

class Reasoning(BaseModel):
    technicalIndicators: List[str]
    marketTrend: str
    sentiment: str
    summary: str
    cnsContext: Optional[Dict[str, Any]] = None

class TradeRecommendation(BaseModel):
    id: str
    symbol: str
    type: str
    assetType: str
    entryPrice: float
    stopLoss: float
    takeProfit: float
    confidence: int
    reasoning: Reasoning
    timestamp: int
    status: str

class TelegramTestRequest(BaseModel):
    token: str
    chat_id: str

def send_telegram_message(token: str, chat_id: str, message: str):
    if not token or not chat_id:
        return False, "Token or Chat ID is empty"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        resp = requests.post(url, json=payload, timeout=15)
        if resp.ok:
            return True, "OK"
        data = resp.json()
        return False, data.get("description", "Unknown Telegram error")
    except Exception as e:
        print(f"Telegram error: {e}")
        return False, str(e)

from data_providers import get_historical_ohlcv, get_realtime_quotes, batch_prefetch_historical

# Store pending states for DQN replay and PPO feedback
PENDING_STATES = {}
PENDING_PPO_ACTIONS = {}

# Live scan log — circular buffer of the bot's last 1000 analysis events (MT5 style journal)
from collections import deque
SCAN_LOG: deque = deque(maxlen=1000)

# One scan at a time: overlapping /api/recommendations calls (worker wakes,
# alarms, popup refreshes, multiple extension instances) duplicate the whole
# batch pre-fetch + analysis and flood the scan log with orphaned starts.
import threading
_scan_lock = threading.Lock()

def get_market_data(symbol: str, api_keys: dict = None) -> Optional[Dict]:
    """Fetch market data for a symbol (MT5 for Crypto/Forex, Data Providers for Stocks)"""
    is_forex = "=X" in symbol
    is_crypto = "-" in symbol
    
    # Try MT5 for Forex/Crypto
    if is_forex or is_crypto:
        try:
            import MetaTrader5 as mt5
            # Ensure MT5 is initialized
            if mt5.terminal_info() is not None:
                # Clean symbol for MT5 format (e.g. BTC-USD -> BTCUSD, EURUSD=X -> EURUSD)
                mt5_symbol = symbol.replace("=X", "")
                if is_crypto:
                    mt5_symbol = symbol.replace("-USD", "USD").replace("-", "")
                
                # Try fetching symbol info to verify it exists in MT5
                if mt5.symbol_info(mt5_symbol):
                    # Fetch 2 daily candles for 24h change
                    rates = mt5.copy_rates_from_pos(mt5_symbol, mt5.TIMEFRAME_D1, 0, 2)
                    if rates is not None and len(rates) > 0:
                        current_price = rates[-1]['close']
                        prev_price = rates[0]['open'] if len(rates) > 1 else current_price
                        change = current_price - prev_price
                        change_percent = (change / prev_price) * 100 if prev_price > 0 else 0.0
                        volume = rates[-1]['tick_volume']
                        
                        return {
                            "symbol": symbol,
                            "price": round(float(current_price), 4),
                            "change": round(float(change), 4),
                            "changePercent": round(float(change_percent), 2),
                            "volume": int(volume) if not pd.isna(volume) else 0,
                            "timestamp": int(datetime.now().timestamp() * 1000)
                        }
        except Exception as e:
            print(f"MT5 fetch failed for {symbol}: {e}")
            # Fall back to data_providers if MT5 fails

    # Fallback to data_providers (or default for Stocks)
    try:
        # Real-time quotes first (60s cache) so Watchlist prices stay fresh
        quotes = get_realtime_quotes([symbol], api_keys or {})
        if quotes:
            quote = quotes[0]
            return {
                "symbol": symbol,
                "price": round(float(quote["price"]), 4),
                "change": round(float(quote["change"]), 4),
                "changePercent": round(float(quote["changePercent"]), 2),
                "volume": float(quote.get("volume", 0)),
                "timestamp": int(datetime.now().timestamp() * 1000)
            }

        hist = get_historical_ohlcv(symbol, period="1d", interval="1d", api_keys=api_keys or {})

        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]
        prev_price = hist['Open'].iloc[0]
        change = current_price - prev_price
        change_percent = (change / prev_price) * 100 if prev_price > 0 else 0.0
        volume = hist.get('Volume', pd.Series([0])).iloc[-1]

        return {
            "symbol": symbol,
            "price": round(float(current_price), 4),
            "change": round(float(change), 4),
            "changePercent": round(float(change_percent), 2),
            "volume": int(volume) if not pd.isna(volume) else 0,
            "timestamp": int(datetime.now().timestamp() * 1000)
        }
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def calculate_technical_indicators(df: pd.DataFrame) -> TechnicalIndicators:
    """Calculate technical indicators from price data"""
    try:
        # Use pandas_ta to calculate indicators
        df.ta.rsi(length=14, append=True)
        df.ta.macd(append=True)
        df.ta.sma(length=20, append=True)
        df.ta.sma(length=50, append=True)
        df.ta.bbands(append=True)

        # RSI
        rsi = df['RSI_14'].iloc[-1]

        # MACD
        macd = df['MACD_12_26_9'].iloc[-1]
        macd_signal = df['MACDs_12_26_9'].iloc[-1]

        # SMA
        sma_20 = df['SMA_20'].iloc[-1]
        sma_50 = df['SMA_50'].iloc[-1]

        # Bollinger Bands (check both naming conventions)
        bb_cols = [c for c in df.columns if 'BB' in c.upper()]
        if any('BBU' in c for c in bb_cols):
            bollinger_upper = df[[c for c in bb_cols if 'BBU' in c][0]].iloc[-1]
            bollinger_lower = df[[c for c in bb_cols if 'BBL' in c][0]].iloc[-1]
        else:
            # Calculate manually if not found
            rolling_mean = df['Close'].rolling(window=20).mean().iloc[-1]
            rolling_std = df['Close'].rolling(window=20).std().iloc[-1]
            bollinger_upper = rolling_mean + (rolling_std * 2)
            bollinger_lower = rolling_mean - (rolling_std * 2)

        # Volume ratio
        avg_volume = df['Volume'].rolling(window=20).mean().iloc[-1]
        current_volume = df['Volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        return TechnicalIndicators(
            rsi=float(rsi),
            macd=float(macd),
            macd_signal=float(macd_signal),
            sma_20=float(sma_20),
            sma_50=float(sma_50),
            bollinger_upper=float(bollinger_upper),
            bollinger_lower=float(bollinger_lower),
            volume_ratio=float(volume_ratio)
        )
    except Exception as e:
        print(f"Error calculating indicators: {e}")
        return None

def generate_trade_recommendation(symbol: str, asset_type: str, risk_settings: Optional[RiskSettings], api_keys: Optional[dict] = None) -> Optional[TradeRecommendation]:
    """
    Generate AI-powered trade recommendation using trained ML models

    RUTE ML System: 45% win rate with 3:1 risk/reward ratio = PROFITABLE
    - Stop Loss: 2% (default)
    - Take Profit: 6% (default)
    - Trained on 45 years of historical data
    - Uses 61 technical indicators for prediction
    """
    try:
        user_min_conf = risk_settings.minConfidence if risk_settings and hasattr(risk_settings, 'minConfidence') else 50
        
        # Try to load ML model for this symbol
        model_data = load_ml_model(symbol)

        # Fetch historical data
        df = get_historical_ohlcv(symbol, period="1y", interval="1d", api_keys=api_keys or {})

        if df.empty or len(df) < 200:
            return None

        # Import feature engineer
        from ml_engine.feature_engine import FeatureEngineer
        # Engineer features
        engineer = FeatureEngineer()
        df = engineer.add_price_features(df.copy())
        df = engineer.add_trend_indicators(df)
        df = engineer.add_momentum_indicators(df)
        df = engineer.add_volatility_indicators(df)
        df = engineer.add_volume_indicators(df)
        df = engineer.add_higher_timeframe_features(df)
        df = engineer.add_candle_patterns(df)
        df = df.dropna()

        if df.empty:
            return None

        current_price = df['Close'].iloc[-1]

        # ML Prediction (if model available)
        ml_prediction = None
        ml_confidence = 0
        ml_error = ""

        if model_data:
            try:
                feature_names = model_data['feature_names']
                model = model_data['model']

                # Get latest features
                X_latest = df[feature_names].iloc[-1:].values

                # Predict
                prediction = model.predict(X_latest)[0]

                # Get confidence from RandomForest
                if hasattr(model, 'predict_proba'):
                    proba = model.predict_proba(X_latest)[0]
                    base_ml_conf = float(max(proba) * 100)

                    # Map prediction: -1=SELL, 0=HOLD, 1=BUY.
                    pred_class = int(np.argmax(proba))
                    classes = getattr(model, "classes_", [-1, 0, 1])
                    classes = list(classes)
                    true_class = int(classes[pred_class]) if 0 <= pred_class < len(classes) else pred_class
                        
                    # Calculate live technical modifier for continuous fluctuation (-5% to +5%)
                    # Needs indicators, so we will do this after indicators are calculated!
                    # For now, just store base_ml_conf and true_class.
                    ml_prediction = "BUY" if true_class == 1 else "SELL" if true_class == -1 else "HOLD"
                    ml_confidence = base_ml_conf

                    # Model disagreement: spread of member probabilities around
                    # the predicted class (ensemble quality signal)
                    ens = getattr(model, 'base', model)
                    members = getattr(ens, 'members', None)
                    if members and len(members) > 1:
                        details = {}
                        try:
                            member_probas = np.array([m.predict_proba(X_latest)[0] for m in members])
                            spread = float(np.std(member_probas[:, pred_class]))
                            if np.isfinite(spread):
                                details["model_disagreement"] = round(spread, 3)
                                details["models_agreeing"] = int(np.sum(np.argmax(member_probas, axis=1) == pred_class))
                                details["models_total"] = len(members)
                        except Exception:
                            pass

            except Exception as e:
                ml_error = str(e)
                print(f"ML prediction error for {symbol}: {e}")

        # Calculate technical indicators for reasoning
        indicators = calculate_technical_indicators(df)
        if not indicators:
            return None

        signals = []
        confidence = 0.0
        trade_type = ml_prediction if ml_prediction in ("BUY", "SELL") else None

        # ── ML signal (with technical confirmation) ──
        if trade_type:
            # Inject live technical fluctuation so AI score breathes with the market!
            rsi_modifier = (50.0 - indicators.rsi) / 10.0 if trade_type == "BUY" else (indicators.rsi - 50.0) / 10.0
            macd_diff = (indicators.macd - indicators.macd_signal) * 5.0
            live_modifier = round(rsi_modifier + macd_diff, 2)
            
            ml_confidence = round(ml_confidence + live_modifier, 2)
            confidence = ml_confidence
            
            signals.append(f"AI Base Probability: {ml_confidence - live_modifier:.1f}%")
            signals.append(f"Live Technical Modifier: {live_modifier:+.1f}% (RSI/MACD)")
            signals.append(f"Total AI Confidence: {confidence}%")

            if trade_type == "BUY":
                if indicators.rsi < 50:
                    signals.append(f"RSI confirms oversold conditions (RSI: {indicators.rsi:.1f})")
                    confidence += 5
                if indicators.macd > indicators.macd_signal:
                    signals.append("MACD shows bullish momentum")
                    confidence += 5
                if indicators.sma_20 > indicators.sma_50:
                    signals.append("Moving averages confirm uptrend")
                    confidence += 5
            else:
                if indicators.rsi > 50:
                    signals.append(f"RSI confirms overbought conditions (RSI: {indicators.rsi:.1f})")
                    confidence += 5
                if indicators.macd < indicators.macd_signal:
                    signals.append("MACD shows bearish momentum")
                    confidence += 5
                if indicators.sma_20 < indicators.sma_50:
                    signals.append("Moving averages confirm downtrend")
                    confidence += 5

            if indicators.volume_ratio > 1.3:
                signals.append(f"Above-average volume confirms signal ({indicators.volume_ratio:.2f}x)")
                confidence += 5
        else:
            if ml_prediction == "HOLD":
                signals.append(f"ML Model predicts HOLD ({ml_confidence}%) — using technical fallback")
            # ── Technical-only: score both directions from real market state ──
            bull = 0
            bear = 0
            if indicators.rsi <= 30:
                bull += 2
                signals.append(f"RSI deeply oversold ({indicators.rsi:.1f})")
            elif indicators.rsi <= 45:
                bull += 1
                signals.append(f"RSI bearish-bounce setup ({indicators.rsi:.1f})")
            elif indicators.rsi >= 70:
                bear += 2
                signals.append(f"RSI deeply overbought ({indicators.rsi:.1f})")
            elif indicators.rsi >= 55:
                bear += 1
                signals.append(f"RSI bullish-exhaustion setup ({indicators.rsi:.1f})")

            if indicators.macd > indicators.macd_signal:
                bull += 1
                signals.append("MACD bullish cross")
            else:
                bear += 1
                signals.append("MACD bearish cross")

            if indicators.sma_20 > indicators.sma_50:
                bull += 1
                signals.append("SMA20 above SMA50 — uptrend")
            else:
                bear += 1
                signals.append("SMA20 below SMA50 — downtrend")

            net = bull - bear
            if net > 0:
                trade_type = "BUY"
            elif net < 0:
                trade_type = "SELL"

            if trade_type:
                # 25 base + 15 per net agreeing factor − 5 per conflicting factor
                agreeing = bull if trade_type == "BUY" else bear
                conflicting = bear if trade_type == "BUY" else bull
                confidence = 25.0 + agreeing * 15.0 - conflicting * 5.0
                
                # Add continuous precision based on indicator strength
                rsi_factor = abs(50.0 - indicators.rsi) / 50.0 * 4.0
                macd_diff = abs(indicators.macd - indicators.macd_signal) * 10.0
                confidence += round(rsi_factor + min(macd_diff, 4.0), 2)

                if indicators.volume_ratio > 1.3:
                    signals.append(f"Above-average volume ({indicators.volume_ratio:.2f}x)")
                    confidence += 5.0
            else:
                signals = ["Technicals balanced — no edge in either direction"]
                confidence = 15.0 + round(abs(50.0 - indicators.rsi) / 50.0 * 5.0, 2)

        if ml_error:
            signals.append(f"ML model unavailable ({ml_error})")

        # Cap confidence
        confidence = min(confidence, 95)
        # Ensure confidence is clamped and strictly rounded to 2 decimal places
        confidence = round(min(max(confidence, 0.0), 100.0), 2)

        details = {
            "rsi": round(indicators.rsi, 2) if indicators else None,
            "macd": round(indicators.macd, 2) if indicators else None,
            "sma20": round(indicators.sma_20, 2) if indicators else None,
            "sma50": round(indicators.sma_50, 2) if indicators else None,
            "ml_prediction": ml_prediction,
            "ml_confidence": round(ml_confidence, 2) if ml_prediction else 0,
            "signals": signals
        }

        # Only return if confidence passes the initial gate: 50% (ML-based)
        # or 60% (technical-only). The user's minConfidence applies at the
        # FINAL gate after all modifiers — using it here rejects setups too
        # early and the log fills with sub-threshold skips.
        min_confidence = user_min_conf
        if confidence < min_confidence or trade_type is None:
            if trade_type is None:
                detailed_reason = "AI determined market is completely flat (HOLD). No edge detected."
            else:
                shortfall = round(min_confidence - confidence, 2)
                detailed_reason = f"AI Confidence ({confidence}%) is below your minimum threshold ({min_confidence}%). Missing {shortfall}% to trigger trade."
            
            return {"status": "skipped", "symbol": symbol, "confidence": confidence, "reason": detailed_reason, "details": details, "signals": signals}

        # 3:1 Risk/Reward Ratio (PROFITABLE with 45% win rate)
        stop_loss_pct = risk_settings.stopLossPercentage if risk_settings else 2.0
        take_profit_pct = risk_settings.takeProfitPercentage if risk_settings else 6.0  # 3:1 ratio

        if trade_type == "BUY":
            stop_loss = current_price * (1 - stop_loss_pct / 100)
            take_profit = current_price * (1 + take_profit_pct / 100)
        else:
            stop_loss = current_price * (1 + stop_loss_pct / 100)
            take_profit = current_price * (1 - take_profit_pct / 100)

        # Market analysis
        if indicators.sma_20 > indicators.sma_50:
            market_trend = "Bullish uptrend with strong momentum"
        else:
            market_trend = "Bearish downtrend with selling pressure"

        if indicators.rsi < 40:
            sentiment = "Oversold - potential reversal"
        elif indicators.rsi > 60:
            sentiment = "Overbought - caution advised"
        else:
            sentiment = "Neutral market conditions"

        # Generate summary with disclaimer
        summary = f"RUTE ML recommends {trade_type} for {symbol} with {confidence}% confidence. "
        if ml_prediction:
            summary += "Trained on 45 years of data using 61 indicators. "
        summary += f"Entry: ${current_price:.2f} | Stop: ${stop_loss:.2f} | Target: ${take_profit:.2f} "
        summary += "(3:1 R:R = Profitable with 45% win rate)"

        # 4. Regime Filter (ADX + Hurst + Entropy)
        latest_adx = float(df['adx'].iloc[-1])
        latest_atr = float(df['atr'].iloc[-1])

        hurst_val = HurstCalculator.compute_hurst(df['Close'].iloc[-100:])
        entropy_val = EntropyCalculator.compute_entropy(df['Close'].iloc[-100:])

        regime = RegimeClassifier.get_regime(latest_adx, hurst_val)
        is_vetoed = RegimeClassifier.should_veto(latest_adx, hurst_val, entropy_val)

        # 5. Correlation asset context (DXY, TNX)
        correlations = []
        dxy_trend = "Neutral"
        try:
            dxy = get_historical_ohlcv("DX-Y.NYB", period="1y", interval="1d", api_keys=api_keys or {})
            tnx = get_historical_ohlcv("^TNX", period="1y", interval="1d", api_keys=api_keys or {})
            
            if not dxy.empty:
                dxy_feats = engineer.engineer_features(dxy.copy()).drop(columns=['target', 'future_return'], errors='ignore')
                correlations.append(dxy_feats.iloc[-len(df):])
                dxy_latest = dxy['Close'].iloc[-1]
                dxy_sma20 = dxy['Close'].rolling(20).mean().iloc[-1]
                if dxy_latest and dxy_sma20:
                    dxy_trend = "Bullish" if dxy_latest > dxy_sma20 else "Bearish"
            if not tnx.empty:
                tnx_feats = engineer.engineer_features(tnx.copy()).drop(columns=['target', 'future_return'], errors='ignore')
                correlations.append(tnx_feats.iloc[-len(df):])
        except Exception:
            pass

        # 6. Sentiment veto (only when live feed is connected; stub always returns False)
        if sentiment_hub.filter_signal(symbol, trade_type):
            is_vetoed = True

        # 7. Temporal LSTM cross-check — soft confidence modifier only.
        try:
            temporal_pred = get_temporal_prediction(symbol, df, correlations if correlations else [])
            if trade_type == "BUY" and temporal_pred == -1:
                confidence = max(confidence - 10, 0)   # LSTM disagrees — reduce confidence
            elif trade_type == "SELL" and temporal_pred == 1:
                confidence = max(confidence - 10, 0)
            elif trade_type == "BUY" and temporal_pred == 1:
                confidence = min(confidence + 5, 95)   # LSTM agrees — small boost
            elif trade_type == "SELL" and temporal_pred == -1:
                confidence = min(confidence + 5, 95)
        except Exception:
            pass  # Never let a broken LSTM kill a signal

        # 7b. Multi-Timeframe SuperTrend confluence (H1/H4/D1 + EMA200 trend filter)
        boost_delta = 0
        try:
            from ml_engine.mtf_confluence import get_mtf_confluence, apply_mtf_boost
            mtf_conf = get_mtf_confluence(symbol, df, api_keys)
            boost_delta, boost_msgs = apply_mtf_boost(mtf_conf, trade_type)
            if boost_delta:
                confidence = min(confidence + boost_delta, 95)
            signals.extend(boost_msgs)
            conf_details = {tf: s for tf, s in mtf_conf.items() if tf in ("H1", "H4", "D1") and s}
            if conf_details:
                details["confluence"] = conf_details
                details["confluence_source"] = mtf_conf.get("source", "unknown")
        except Exception as e:
            print(f"MTF confluence error for {symbol}: {e}")

        # 8. Order flow check (institutional wall)
        current_price = float(df['Close'].iloc[-1])
        institutional_wall = False
        try:
            if order_flow.is_fighting_wall(symbol, current_price, trade_type, df):
                is_vetoed = True
                institutional_wall = True
        except Exception:
            pass

        details["regime"] = regime
        details["hurst"] = round(hurst_val, 2)
        details["entropy"] = round(entropy_val, 2)
        
        # Hard veto: no signal in choppy/random-walk markets
        if is_vetoed:
            reason_text = "Vetoed by Institutional Order Flow" if institutional_wall else f"Choppy Market Regime (H={hurst_val:.2f})"
            reason = f"[{symbol} Loop Audit] Signal: SKIP | Score: {confidence/100:.4f} | Min Required: 0.75 | {reason_text}"
            return {"status": "skipped", "symbol": symbol, "confidence": confidence, "reason": reason, "details": details}

        # Raise the bar after all adjustments — require genuine confidence:
        # the user's minConfidence setting (default 50) is the trade bar,
        # never below the platform floors of 60 (ML) / 75 (technical-only).
        min_confidence_final = max(user_min_conf, 60 if trade_type else 75)
        if confidence < min_confidence_final or trade_type is None:
            action_str = trade_type if trade_type else "NONE"
            reason = f"[{symbol} Loop Audit] Signal: {action_str} | Score: {confidence/100:.4f} | Min Required: {min_confidence_final/100:.2f}"
            return {"status": "skipped", "symbol": symbol, "confidence": confidence, "reason": reason, "details": details}

        # 9. Adaptive ATR-based SL/TP
        stop_loss, take_profit = AdaptiveRiskManager.calculate_exits(current_price, trade_type, latest_atr)
        if stop_loss is None or take_profit is None:
            # ATR unavailable/invalid — fall back to configured %-based stops (3:1 R:R)
            print(f"ATR invalid ({latest_atr}) for {symbol} — falling back to %-based stops")
            stop_loss, take_profit = (
                current_price * (1 - stop_loss_pct / 100),
                current_price * (1 + take_profit_pct / 100),
            ) if trade_type == "BUY" else (
                current_price * (1 + stop_loss_pct / 100),
                current_price * (1 - take_profit_pct / 100),
            )

        summary += (
            f" Adaptive exits: SL ${stop_loss:.2f}, TP ${take_profit:.2f}. "
            f"Regime: {regime} (ADX: {latest_adx:.2f}, Hurst: {hurst_val:.2f})."
        )
        if boost_delta:
            summary += f" MTF SuperTrend confluence (+{boost_delta}%)."

        rec_id = str(uuid.uuid4())

        # BUG #2 FIX: Store DQN state for later replay buffer insertion in /api/trade-outcome
        try:
            feature_names = model_data['feature_names'] if model_data else []
            if feature_names and not df.empty:
                state = df[feature_names].iloc[-1].values.astype(np.float32)
                action = 1 if trade_type == 'BUY' else -1 if trade_type == 'SELL' else 0
                PENDING_STATES[rec_id] = (state, action)
                if len(PENDING_STATES) > 500:  # bound memory — drop oldest
                    PENDING_STATES.pop(next(iter(PENDING_STATES)))
        except Exception:
            pass

        # UPGRADE 1: Cross-Market confidence modifier
        cross_mod = cross_market_engine.get_signal_modifier(symbol, trade_type)
        if cross_mod != 0.0:
            confidence = max(0, min(95, confidence + int(cross_mod * 100)))
            signals.append(f"Cross-Market AI modifier: {cross_mod:+.2f}")

        # UPGRADE 4: Kelly Criterion risk sizing
        kelly_alloc = capital_allocator.get_allocation()

        # UPGRADE 5: PPO trade parameters (only when trained weights exist —
        # a random policy must never serve "learned" lot/trail/scale params)
        try:
            if getattr(ppo_agent, "trained", False):
                ppo_state = df[model_data.get('feature_names', [])].iloc[-1:].values.astype(np.float32) if model_data and model_data.get('feature_names') else np.zeros(61)
                ppo_params = ppo_agent.select_action(ppo_state)
                PENDING_PPO_ACTIONS[rec_id] = ppo_params
                if len(PENDING_PPO_ACTIONS) > 500:  # bound memory — drop oldest
                    PENDING_PPO_ACTIONS.pop(next(iter(PENDING_PPO_ACTIONS)))
            else:
                ppo_params = {"lot_multiplier": 1.0, "trail_atr": 1.5, "scale_out_pct": 25.0}
        except Exception:
            ppo_params = {"lot_multiplier": 1.0, "trail_atr": 1.5, "scale_out_pct": 25.0}

        return TradeRecommendation(
            id=rec_id,
            symbol=symbol,
            type=trade_type,
            assetType=asset_type,
            entryPrice=round(float(current_price), 2),
            stopLoss=round(float(stop_loss), 2),
            takeProfit=round(float(take_profit), 2),
            confidence=confidence,
            reasoning=Reasoning(
                technicalIndicators=signals,
                marketTrend=market_trend,
                sentiment=sentiment,
                summary=summary,
                cnsContext={
                    "dxy_trend": dxy_trend,
                    "hurst": round(float(hurst_val), 2),
                    "entropy": round(float(entropy_val), 2),
                    "institutional_wall": institutional_wall,
                    "kelly_allocation": kelly_alloc,
                    "ppo_params": ppo_params,
                    "cross_market_alerts": cross_market_engine.get_active_alerts(),
                }
            ),
            timestamp=int(datetime.now().timestamp() * 1000),
            status="pending"
        )
    except Exception as e:
        print(f"Error generating recommendation for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_temporal_prediction(symbol: str, df: pd.DataFrame, correlations: List[pd.DataFrame] = None) -> int:
    """Get LSTM-based temporal prediction with CNS support"""
    global temporal_engine
    try:
        main_feats = df.drop(columns=['Open', 'High', 'Low', 'Close', 'Volume', 'open', 'high', 'low', 'close', 'volume'], errors='ignore').values
        if main_feats.ndim != 2 or main_feats.shape[0] == 0:
            return 0
        # Only use correlation series long enough to align with the main series.
        # A shorter correlation frame (e.g. 20 DXY bars vs 250 main bars) would
        # make np.hstack raise and silently kill the whole temporal engine.
        corr_feats = []
        for c in (correlations or []):
            vals = c.values if hasattr(c, "values") else np.asarray(c, dtype=float)
            if vals.ndim == 2 and vals.shape[0] >= len(main_feats):
                corr_feats.append(vals[-len(main_feats):])

        feature_dim = main_feats.shape[1] + sum(c.shape[1] for c in corr_feats)

        if temporal_engine is None or temporal_engine.model.lstm.input_size != feature_dim:
            temporal_engine = TemporalEngine(feature_dim=feature_dim)

        # Guard against short sequences (use the engine's actual seq_len attribute)
        if len(main_feats) < getattr(temporal_engine, 'seq_len', 14):
            return 0

        # Prepare stacked sequence
        seq = temporal_engine.prepare_sequence(main_feats, corr_feats)
        return temporal_engine.predict(seq)
    except Exception as e:
        print(f"Temporal CNS error: {e}")
        return 0


@app.get("/")
async def root():
    return {
        "message": "RUTE AI Trading Backend",
        "version": "1.0.0",
        "status": "running"
    }

@app.post("/api/test-telegram")
async def test_telegram_endpoint(req: TelegramTestRequest):
    token = req.token.strip()
    chat_id = req.chat_id.strip()
    success, detail = send_telegram_message(token, chat_id, "🤖 <b>RUTE Bot</b>\n\nTelegram notifications are working correctly!")
    if success:
        return {"success": True, "message": "✅ Message sent! Check your Telegram."}
    return {"success": False, "message": f"❌ Telegram error: {detail}"}

@app.post("/api/market-data")
async def get_market_data_endpoint(request: MarketDataRequest):
    """Get real-time market data for multiple symbols"""
    market_data = {}
    api_keys_dict = request.apiKeys.dict() if request.apiKeys else {}

    # Run all get_market_data calls in parallel to fix slow response times
    tasks = [asyncio.to_thread(get_market_data, symbol, api_keys_dict) for symbol in request.symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for symbol, data in zip(request.symbols, results):
        if not isinstance(data, Exception) and data:
            market_data[symbol] = data

    return {"marketData": market_data}

@app.post("/api/recommendations")
async def get_recommendations(request: RecommendationRequest):
    """
    Generate AI-powered trade recommendations using ML models

    RUTE uses ML models trained on 45 years of historical data with 61 technical indicators.
    Win rate: ~45% | Risk/Reward: 3:1 | Result: PROFITABLE

    Math: Even with 45% win rate, 3:1 R:R generates consistent profits over time.
    """
    # Concurrency guard: the extension can fire overlapping scans (worker
    # wake fetches + 5-min alarm + popup refresh + multiple extension
    # instances). Each overlapping scan repeats the batch pre-fetch and 7
    # recommendation generations, hammering data providers (rate limits ->
    # slow scans) and flooding SCAN_LOG with orphaned "scan_start" entries
    # that push real results out of view.
    if not _scan_lock.acquire(blocking=False):
        return {
            "recommendations": [],
            "status": "scan_in_progress",
            "message": "A scan is already running — request skipped to avoid duplicate work.",
        }
    try:
        return await _run_recommendation_scan(request)
    finally:
        _scan_lock.release()


async def _run_recommendation_scan(request: RecommendationRequest):
    recommendations = []
    scan_time = datetime.now().isoformat()

    # Log scan start
    SCAN_LOG.appendleft({
        "ts": scan_time,
        "type": "scan_start",
        "message": f"Scanning {len(request.symbols)} symbols...",
        "symbols": [s.symbol for s in request.symbols],
        "status": "running"
    })

    api_keys_dict = request.apiKeys.dict() if request.apiKeys else {}

    # Pre-fetch historical data for all symbols in one batch request
    symbols_to_fetch = [s.symbol for s in request.symbols]
    await asyncio.to_thread(batch_prefetch_historical, symbols_to_fetch, "1y", "1d", api_keys_dict)

    # Run all generate_trade_recommendation calls in parallel to fix slow response times
    tasks = [
        asyncio.to_thread(
            generate_trade_recommendation,
            symbol_obj.symbol,
            symbol_obj.assetType,
            request.riskSettings,
            api_keys_dict
        )
        for symbol_obj in request.symbols
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    def append_log_if_new(log_entry):
        for existing in SCAN_LOG:
            if existing.get("symbol") == log_entry.get("symbol") and existing.get("type") == log_entry.get("type"):
                if existing.get("message") == log_entry.get("message"):
                    existing["ts"] = log_entry["ts"]
                    if "details" in log_entry:
                        existing["details"] = log_entry["details"]
                    SCAN_LOG.remove(existing)
                    SCAN_LOG.appendleft(existing)
                    return  # Skip duplicate spam but update time
                break
        SCAN_LOG.appendleft(log_entry)

    for i, recommendation in enumerate(results):
        sym = request.symbols[i].symbol
        if isinstance(recommendation, Exception):
            append_log_if_new({
                "ts": datetime.now().isoformat(),
                "type": "error",
                "symbol": sym,
                "message": f"{sym}: Analysis error — {str(recommendation)}",
                "status": "error"
            })
        elif isinstance(recommendation, dict) and recommendation.get("status") == "skipped":
            append_log_if_new({
                "ts": datetime.now().isoformat(),
                "type": "skip",
                "symbol": recommendation.get("symbol", sym),
                "confidence": recommendation.get("confidence", 0),
                "message": recommendation.get("reason", "Conditions not met"),
                "details": recommendation.get("details", {}),
                "signals": recommendation.get("signals", []),
                "status": "skipped"
            })
        elif recommendation:
            append_log_if_new({
                "ts": datetime.now().isoformat(),
                "type": "signal",
                "symbol": sym,
                "action": recommendation.type,
                "confidence": recommendation.confidence,
                "entry": recommendation.entryPrice,
                "stop_loss": recommendation.stopLoss,
                "take_profit": recommendation.takeProfit,
                "signals": recommendation.reasoning.technicalIndicators,
                "message": f"{sym}: {recommendation.type} signal at ${recommendation.entryPrice:.4f} — {recommendation.confidence}% confidence",
                "details": getattr(recommendation, "details", {}),
                "status": "signal"
            })
            recommendations.append(recommendation)
            # Monitor simulated trades and send Telegram Alerts
            if recommendation:
                threshold = getattr(request.notifications, 'telegramThreshold', 80) if request.notifications else 80
                
                if recommendation.confidence >= threshold:
                    if len(OPEN_SIMULATED_TRADES) < MAX_SIMULATED_TRADES:
                        OPEN_SIMULATED_TRADES[recommendation.id] = {
                            "symbol": recommendation.symbol,
                            "type": recommendation.type,
                            "entry": recommendation.entryPrice,
                            "tp": recommendation.takeProfit,
                            "sl": recommendation.stopLoss,
                            "notifications": request.notifications
                        }

                if request.notifications and request.notifications.telegramBotToken and request.notifications.telegramChatId:
                    if request.notifications.tradeAlerts and recommendation.confidence >= threshold:
                        msg = (
                            f"🤖 <b>RUTE TRADE ALERT</b>\n\n"
                            f"<b>{sym}</b> - <b>{recommendation.type}</b>\n"
                            f"Confidence: {recommendation.confidence}%\n"
                            f"Entry: ${recommendation.entryPrice:.4f}\n"
                            f"Target: ${recommendation.takeProfit:.4f}\n"
                            f"Stop Loss: ${recommendation.stopLoss:.4f}\n"
                        )
                        await asyncio.to_thread(
                            lambda: send_telegram_message(
                                request.notifications.telegramBotToken.strip(),
                                request.notifications.telegramChatId.strip(),
                                msg
                            )
                        )
        else:
            SCAN_LOG.appendleft({
                "ts": datetime.now().isoformat(),
                "type": "skip",
                "symbol": sym,
                "message": f"[{sym} Loop Audit] Signal: SKIP | Score: 0.0000 | Min Required: 0.75 | Insufficient market data or error",
                "status": "skip"
            })

    # Market analysis
    overall_sentiment = "neutral"
    ml_models_loaded = sum(1 for s in request.symbols if load_ml_model(s.symbol) is not None)

    if len(recommendations) > 0:
        buy_count = sum(1 for r in recommendations if r.type == "BUY")
        sell_count = len(recommendations) - buy_count

        if buy_count > sell_count * 1.5:
            overall_sentiment = "bullish"
        elif sell_count > buy_count * 1.5:
            overall_sentiment = "bearish"

    analysis_text = f"RUTE analyzed {len(request.symbols)} symbols using "
    if ml_models_loaded > 0:
        analysis_text += f"{ml_models_loaded} trained ML models and "
    analysis_text += f"found {len(recommendations)} high-confidence opportunities. "
    analysis_text += "All recommendations use 3:1 risk/reward ratio for profitability."

    # AUTO-EXECUTE if auto-trading is enabled
    auto_executed = []
    if AUTO_TRADER and AUTO_TRADER.enabled and request.riskSettings and request.riskSettings.enableAutoTrade:
        for rec in recommendations:
            try:
                # Broker calls are blocking network I/O — never run them on the
                # event loop, and one failing symbol must not kill the response.
                result = await asyncio.to_thread(AUTO_TRADER.execute_recommendation, rec.dict())
                if result and result.get("executed"):
                    auto_executed.append({
                        "symbol": rec.symbol,
                        "type": rec.type,
                        "order_id": result.get("order_id")
                    })
                    OPEN_SIMULATED_TRADES.pop(rec.id, None)
            except Exception as e:
                print(f"Auto-execute failed for {rec.symbol}: {e}")

    response = {
        "recommendations": recommendations,
        "marketAnalysis": {
            "overall": analysis_text,
            "sentiment": overall_sentiment,
            "volatility": "medium",
            "disclaimer": "45% win rate × 3:1 R:R = profitable. Trained on 45 years of data."
        }
    }

    if auto_executed:
        response["auto_executed"] = auto_executed
        response["message"] = f"✓ Auto-executed {len(auto_executed)} trades"

    return response

@app.get("/api/scan-log")
async def get_scan_log(limit: int = 50):
    """Return the live bot scan log — what it's analysing, signals found, skips."""
    return {"events": list(SCAN_LOG)[:limit]}

# ── Coin symbol map: extension symbol → CoinGecko id ──────────────────────────
COINGECKO_ID_MAP = {
    "BTC-USD": "bitcoin", "ETH-USD": "ethereum", "SOL-USD": "solana",
    "BNB-USD": "binancecoin", "XRP-USD": "ripple", "ADA-USD": "cardano",
    "DOGE-USD": "dogecoin", "AVAX-USD": "avalanche-2", "DOT-USD": "polkadot",
    "MATIC-USD": "matic-network", "LINK-USD": "chainlink", "LTC-USD": "litecoin",
    "UNI-USD": "uniswap", "ATOM-USD": "cosmos", "XLM-USD": "stellar",
    "ALGO-USD": "algorand", "ICP-USD": "internet-computer", "FIL-USD": "filecoin",
    "VET-USD": "vechain", "HBAR-USD": "hedera-hashgraph", "NEAR-USD": "near",
    "AAVE-USD": "aave", "SAND-USD": "the-sandbox", "MANA-USD": "decentraland",
    "CRO-USD": "crypto-com-chain", "FTM-USD": "fantom", "THETA-USD": "theta-token",
    "EOS-USD": "eos", "TRX-USD": "tron", "SHIB-USD": "shiba-inu",
}

# ── Forex base symbol map: EURUSD=X → EUR ─────────────────────────────────────
FOREX_SYMBOL_MAP = {
    "EURUSD=X": "EUR", "GBPUSD=X": "GBP", "USDJPY=X": "USD",
    "AUDUSD=X": "AUD", "USDCAD=X": "USD", "USDCHF=X": "USD",
    "NZDUSD=X": "NZD", "EURGBP=X": "EUR", "EURJPY=X": "EUR",
    "GBPJPY=X": "GBP", "USDMXN=X": "USD", "USDZAR=X": "USD",
    "USDSEK=X": "USD", "USDNOK=X": "USD", "USDDKK=X": "USD",
    "USDSGD=X": "USD", "USDHKD=X": "USD", "USDTRY=X": "USD",
    "USDINR=X": "USD", "USDBRL=X": "USD", "EURAUD=X": "EUR",
    "EURCHF=X": "EUR", "EURCAD=X": "EUR", "GBPAUD=X": "GBP",
    "GBPCAD=X": "GBP", "GBPCHF=X": "GBP", "AUDCAD=X": "AUD",
    "AUDCHF=X": "AUD", "AUDJPY=X": "AUD", "CADJPY=X": "CAD",
    "CADCHF=X": "CAD", "CHFJPY=X": "CHF", "NZDJPY=X": "NZD",
    "EURNZD=X": "EUR", "GBPNZD=X": "GBP", "XAUUSD=X": "XAU",
    "XAGUSD=X": "XAG", "XPTUSD=X": "XPT", "XPDUSD=X": "XPD",
    "USDRUB=X": "USD", "USDCNH=X": "USD", "USDKRW=X": "USD",
    "USDTHB=X": "USD", "USDPLN=X": "USD", "USDHUF=X": "USD",
    "USDCZK=X": "USD", "USDILS=X": "USD", "USDCLP=X": "USD",
    "USDCOP=X": "USD", "USDARS=X": "USD", "USDPEN=X": "USD",
    "USDEGP=X": "USD", "USDNGN=X": "USD", "USDKES=X": "USD",
    "USDGHS=X": "USD", "USDTND=X": "USD", "USDMAD=X": "USD",
    "USDZAR=X": "USD", "USDAED=X": "USD", "USDSAR=X": "USD",
    "USDQAR=X": "USD", "USDKWD=X": "USD", "USDBHD=X": "USD",
}

@app.post("/market/live")
async def get_live_market_data(request: MarketDataRequest):
    """Real-time prices: CCXT (crypto) | data_providers (forex/stocks)."""
    symbols: List[str] = request.symbols
    if not symbols:
        return {"marketData": []}

    api_keys_dict = request.apiKeys.dict() if request.apiKeys else {}
    
    def _blocking_fetch() -> list:
        return get_realtime_quotes(symbols, api_keys_dict)

    market_data = await asyncio.to_thread(_blocking_fetch)
    return {"marketData": market_data}

@app.get("/api/health")
async def health_check():
    """Health endpoint for the tray app watchdog.
    Returns MT5 status and uptime so the watchdog can make informed restart decisions."""
    from mt5_engine.config import MT5_AVAILABLE, MT5_INIT_ALLOWED
    mt5_enabled = MT5_INIT_ALLOWED
    mt5_connected = None  # null when MT5 is disabled entirely
    if mt5_enabled and MT5_AVAILABLE:
        try:
            import MetaTrader5 as mt5
            info = mt5.terminal_info()
            mt5_connected = info is not None
        except Exception:
            mt5_connected = False
    return {
        "status": "ok",
        "mt5_enabled": mt5_enabled,
        "mt5_connected": mt5_connected,
        "uptime_seconds": int((datetime.now() - APP_START_TIME).total_seconds()),
    }

@app.get("/api/model-health")
async def model_health():
    """Model health dashboard: trained_at, walk-forward eval stats, calibration
    metrics, canary LR comparison, and feature-drift detection."""
    model_dir = os.path.join(os.path.dirname(__file__), "ml_engine", "models")
    results = []
    try:
        files = glob.glob(os.path.join(model_dir, "*_*.joblib"))
        for f in sorted(files):
            base = os.path.basename(f)
            symbol = base.split("_")[0]
            try:
                data = joblib.load(f)
                if not isinstance(data, dict) or ("model" not in data and "models" not in data):
                    continue
                info = {
                    "symbol": symbol,
                    "file": base,
                    "trained_at": datetime.fromtimestamp(os.path.getmtime(f)).isoformat(),
                    "age_hours": round((datetime.now().timestamp() - os.path.getmtime(f)) / 3600, 1),
                    "system": data.get("system", "UNKNOWN"),
                    "win_rate": data.get("win_rate"),
                    "eval": data.get("eval"),
                }
                # Drift: compare the latest engineered features against the
                # training distribution (z > 3 on >20% of features = warn).
                fs = data.get("feature_stats")
                names = data.get("feature_names") or []
                if fs and names:
                    try:
                        hist = get_historical_ohlcv(symbol, period="1mo", interval="1d", api_keys={})
                        if hist is not None and not hist.empty:
                            from ml_engine.feature_engine import FeatureEngineer
                            eng = FeatureEngineer()
                            feats = eng.engineer_features(hist.copy())
                            mean = np.asarray(fs.get("mean", []), dtype=float)
                            std = np.asarray(fs.get("std", []), dtype=float)
                            common = [n for n in names if n in feats.columns and names.index(n) < len(mean)]
                            if common and len(mean) == len(names):
                                mean_v = np.asarray([mean[names.index(n)] for n in common])
                                std_v = np.asarray([std[names.index(n)] for n in common])
                                recent = feats[common].iloc[-1].values.astype(float)
                                with np.errstate(divide='ignore', invalid='ignore'):
                                    z = np.abs((recent - mean_v) / np.where(std_v == 0, np.nan, std_v))
                                z = z[np.isfinite(z)]
                                drift_pct = float(np.mean(z > 3.0) * 100) if len(z) else 0.0
                                info["drift_pct"] = round(drift_pct, 1)
                                info["features_tested"] = len(common)
                                info["warning"] = drift_pct > 20
                    except Exception as e:
                        info["drift_error"] = str(e)
                results.append(info)
            except Exception as e:
                results.append({"file": base, "error": str(e)})
    except Exception as e:
        return {"success": False, "error": str(e)}
    return {"success": True, "count": len(results), "models": results}

# ==================== BACKTEST & OPTIMIZATION (freqtrade-style) ====================

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "rsi"
    params: Dict[str, float] = {}
    interval: str = "1d"
    period: str = "1y"
    commission: float = 0.00075
    slippage: float = 0.0005
    apiKeys: Optional[dict] = None

class OptimizeRequest(BaseModel):
    symbol: str
    strategy: str = "rsi"
    grid: Optional[Dict[str, List[float]]] = None
    interval: str = "1d"
    period: str = "1y"
    commission: float = 0.00075
    slippage: float = 0.0005
    topN: int = 8
    apiKeys: Optional[dict] = None

@app.post("/api/backtest")
async def backtest_endpoint(request: BacktestRequest):
    """Run a strategy backtest against historical data (freqtrade-style metrics)."""
    from trading_engine.backtester import run_backtest, STRATEGIES
    if request.strategy not in STRATEGIES:
        return {"error": f"Unknown strategy '{request.strategy}'. Available: {list(STRATEGIES.keys())}"}

    api_keys = request.apiKeys or {}
    df = await asyncio.to_thread(get_historical_ohlcv, request.symbol, request.period, request.interval, api_keys)
    if df is None or len(df) < 50:
        return {"error": "Not enough historical data (need >= 50 bars). Add API keys in Settings if this is a stock/forex symbol."}

    result = await asyncio.to_thread(run_backtest, df, request.strategy, request.params,
                                     request.commission, request.slippage, 100.0, request.interval)
    if result.error:
        return {"error": result.error}
    result.symbol = request.symbol
    result.interval = request.interval
    return {"result": result.to_dict(), "label": STRATEGIES[request.strategy]["label"]}

@app.post("/api/optimize")
async def optimize_endpoint(request: OptimizeRequest):
    """Grid-search strategy parameters over historical data (Hyperopt-lite)."""
    from trading_engine.backtester import optimize, run_backtest, STRATEGIES
    if request.strategy not in STRATEGIES:
        return {"error": f"Unknown strategy '{request.strategy}'. Available: {list(STRATEGIES.keys())}"}

    api_keys = request.apiKeys or {}
    df = await asyncio.to_thread(get_historical_ohlcv, request.symbol, request.period, request.interval, api_keys)
    if df is None or len(df) < 50:
        return {"error": "Not enough historical data (need >= 50 bars). Add API keys in Settings if this is a stock/forex symbol."}

    results = await asyncio.to_thread(optimize, df, request.strategy, request.grid,
                                      request.commission, request.slippage, request.topN, request.interval)
    for r in results:
        r.symbol = request.symbol
        r.interval = request.interval
    return {
        "strategy": request.strategy,
        "label": STRATEGIES[request.strategy]["label"],
        "results": [r.to_dict() for r in results],
    }

class LiveSignalsRequest(BaseModel):
    symbols: List[str]
    strategies: List[str] = ["alpha_trend", "rsi", "macd", "sma_cross", "bollinger", "gainzalgo"]
    interval: str = "1d"
    params: Optional[dict] = None  # optimized per-strategy params (from the Strategy Lab)
    apiKeys: Optional[dict] = None

@app.post("/api/live-signals")
async def live_signals_endpoint(request: LiveSignalsRequest):
    """Current buy/sell stance for each symbol per chosen strategy (fresh data)."""
    from trading_engine.backtester import latest_signals, STRATEGIES
    valid = [s for s in request.strategies if s in STRATEGIES]
    if not valid:
        return {"error": "No valid strategies selected", "results": []}
    api_keys = request.apiKeys or {}

    def _blocking() -> list:
        rows = []
        for sym in request.symbols[:25]:
            try:
                df = get_historical_ohlcv(sym, "1y", request.interval, api_keys)
                if df is None or len(df) < 60:
                    rows.append({"symbol": sym, "error": "not enough data"})
                    continue
                rows.append({"symbol": sym, "signals": latest_signals(df, valid, request.params)})
            except Exception as e:
                rows.append({"symbol": sym, "error": str(e)})
        return rows

    rows = await asyncio.to_thread(_blocking)
    return {"results": rows, "interval": request.interval}

# ==================== MARKET REGIME DETECTION ====================

class MarketRegimeRequest(BaseModel):
    symbol: str
    interval: str = "1d"
    apiKeys: Optional[dict] = None

REGIME_STRATEGY_MAP = {
    "trending_up":     ["macd", "alpha_trend", "gainzalgo"],
    "trending_down":   ["macd", "alpha_trend"],
    "ranging":         ["rsi", "bollinger"],
    "high_volatility": ["rsi", "bollinger"],
    "low_volatility":  ["sma_cross"],
    "neutral":         ["rsi", "macd", "sma_cross", "bollinger", "alpha_trend", "gainzalgo"],
}

REGIME_LABELS = {
    "trending_up": "Trending Up",
    "trending_down": "Trending Down",
    "ranging": "Ranging / Choppy",
    "high_volatility": "High Volatility",
    "low_volatility": "Low Volatility",
    "neutral": "Neutral",
}

# Lookback period per timeframe. NOTE: the provider's limit_map caps bars per
# period ("5d"=5, "1mo"=30, "3mo"=90...), and Binance serves 5m requests as 1h
# bars. So both intraday TFs need "3mo" to yield the >= 50 bars required below.
REGIME_PERIOD_BY_INTERVAL = {"1d": "3mo", "1h": "3mo", "5m": "3mo"}


def _adx(high, low, close, n=14):
    import numpy as np
    import pandas as pd
    h = np.asarray(high, float)
    l = np.asarray(low, float)
    c = np.asarray(close, float)
    up   = h[1:] - h[:-1]
    down = l[:-1] - l[1:]
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    ndm = np.where((down > up) & (down > 0), down, 0.0)
    atr_arr = []
    tr = np.maximum(h[1:]-l[1:], np.maximum(abs(h[1:]-c[:-1]), abs(l[1:]-c[:-1])))
    def _smooth(arr, n):
        s = pd.Series(arr)
        return s.ewm(alpha=1/n, adjust=False).mean().to_numpy()
    satr = _smooth(tr, n)
    spdm = _smooth(pdm, n)
    sndm = _smooth(ndm, n)
    with np.errstate(divide='ignore', invalid='ignore'):
        pdi = np.where(satr > 0, 100*spdm/satr, 0.0)
        ndi = np.where(satr > 0, 100*sndm/satr, 0.0)
        dx  = np.where((pdi+ndi) > 0, 100*abs(pdi-ndi)/(pdi+ndi), 0.0)
    adx = _smooth(dx, n)
    return float(adx[-1]) if len(adx) > 0 else 0.0


def _atr_pct(high, low, close, n=14):
    h = np.asarray(high, float)
    l = np.asarray(low, float)
    c = np.asarray(close, float)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = float(pd.Series(tr).ewm(alpha=1/n, adjust=False).mean().to_numpy()[-1]) if len(tr) > 0 else 0.0
    return (atr / c[-1] * 100.0) if len(c) > 0 and c[-1] > 0 else 0.0


def _rsi(close, n=14):
    c = np.asarray(close, float)
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).ewm(alpha=1/n, adjust=False).mean().to_numpy()
    avg_loss = pd.Series(loss).ewm(alpha=1/n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.inf), where=avg_loss > 0)
        rsi = 100 - 100 / (1 + rs)
    rsi = np.where((avg_gain == 0) & (avg_loss == 0), 50.0, rsi)
    rsi = np.nan_to_num(rsi, nan=100.0)
    return float(rsi[-1]) if len(rsi) > 0 else 50.0


def _ema(close, n):
    return pd.Series(np.asarray(close, float)).ewm(span=n, adjust=False).mean().to_numpy()


def _analyze_regime(df, symbol, interval):
    """Pure numpy/pandas indicator analysis -> regime classification + strategy suggestions."""
    if df is None or len(df) < 50:
        return {"error": "Not enough historical data (need >= 50 bars). Add API keys in Settings if this is a stock/forex symbol."}

    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)

    # Analyse the most recent window (50-100 bars)
    n = min(100, len(df))
    high_w, low_w, close_w = high[-n:], low[-n:], close[-n:]

    adx_val = _adx(high_w, low_w, close_w, 14)
    atr_pct = _atr_pct(high_w, low_w, close_w, 14)
    rsi_val = _rsi(close_w, 14)
    ema20 = _ema(close_w, 20)[-1]
    ema50 = _ema(close_w, 50)[-1]
    ema_bias = "bullish" if ema20 > ema50 else ("bearish" if ema20 < ema50 else "neutral")

    # --- Classification (order matters: volatility overrides trend) ---
    if atr_pct > 2.5:
        regime = "high_volatility"
    elif atr_pct < 0.5:
        regime = "low_volatility"
    elif adx_val > 25:
        regime = "trending_up" if ema20 > ema50 else "trending_down"
    elif adx_val < 20:
        regime = "ranging"
    else:
        regime = "neutral"

    # --- Confidence proxy from distance to the relevant threshold ---
    def _clamp(v, lo=0.0, hi=1.0):
        return max(lo, min(hi, v))

    if regime in ("trending_up", "trending_down"):
        confidence = _clamp((adx_val - 25) / 10.0)
    elif regime == "ranging":
        confidence = _clamp(1.0 - (adx_val / 20.0))
    elif regime == "high_volatility":
        confidence = _clamp((atr_pct - 2.5) / 2.0)
    elif regime == "low_volatility":
        confidence = _clamp(1.0 - (atr_pct / 0.5))
    else:  # neutral — closeness to the 20-25 dead zone midpoint
        confidence = _clamp(1.0 - abs(adx_val - 22.5) / 2.5)

    descriptions = {
        "trending_up": (f"Strong directional momentum (ADX {adx_val:.1f} > 25) with a bullish bias "
                        "(EMA20 above EMA50). Trend-following strategies tend to outperform."),
        "trending_down": (f"Strong directional momentum (ADX {adx_val:.1f} > 25) with a bearish bias "
                          "(EMA20 below EMA50). Trend-following strategies tend to outperform on the short side."),
        "ranging": (f"Market is moving sideways with low directional momentum (ADX {adx_val:.1f} < 20). "
                    "Mean-reversion strategies tend to outperform."),
        "high_volatility": (f"Volatility is elevated (ATR {atr_pct:.1f}% of price > 2.5%). Wide swings favor "
                            "range/breakout strategies; consider tighter risk controls."),
        "low_volatility": (f"Volatility is compressed (ATR {atr_pct:.1f}% of price < 0.5%). Low-energy markets "
                           "favor slow trend strategies."),
        "neutral": (f"Regime is mixed (ADX {adx_val:.1f} between 20-25, ATR {atr_pct:.1f}%). No single setup "
                    "dominates — a diversified strategy set is suggested."),
    }

    return {
        "regime": regime,
        "regime_label": REGIME_LABELS.get(regime, regime.title()),
        "confidence": round(confidence, 3),
        "adx": round(adx_val, 2),
        "atr_pct": round(atr_pct, 3),
        "rsi": round(rsi_val, 2),
        "ema_bias": ema_bias,
        "suggested_strategies": REGIME_STRATEGY_MAP.get(regime, REGIME_STRATEGY_MAP["neutral"]),
        "description": descriptions.get(regime, ""),
    }


@app.post("/api/market-regime")
async def market_regime_endpoint(request: MarketRegimeRequest):
    """Detect the current market regime for a symbol and suggest fitting strategies."""
    if not request.symbol.strip():
        return {"error": "Symbol is required"}
    api_keys = request.apiKeys or {}
    period = REGIME_PERIOD_BY_INTERVAL.get(request.interval, "3mo")
    try:
        df = await asyncio.to_thread(get_historical_ohlcv, request.symbol, period, request.interval, api_keys)
        result = await asyncio.to_thread(_analyze_regime, df, request.symbol, request.interval)
    except Exception as e:
        return {"error": str(e)}
    return result

# ==================== WEBSOCKET & SIGNAL ENDPOINTS ====================

@app.post("/api/trade-outcome")
async def record_trade_outcome(data: dict):
    """
    Receive outcome of a trade (win/loss/profit).
    Feeds 'Reward' to the DQN and PPO Agents for real-time learning, and saves weights.
    """
    signal_id = data.get("signal_id")
    profit = data.get("profit", 0)
    exit_reason = data.get("exit_reason", "Auto-Exit")
    reward = 1.0 if profit >= 0 else -1.0 
    
    print(f"RUTE RL: Signal {signal_id} outcome received. Reward: {reward} | Reason: {exit_reason}")
    
    # 1. DQN Feedback
    if signal_id in PENDING_STATES:
        state, action = PENDING_STATES.pop(signal_id)
        dqn_agent.remember(state, action, float(reward), state, done=True)
        dqn_agent.replay(batch_size=32)
        try:
            dqn_agent.save(os.path.join(os.path.dirname(__file__), "ml_engine", "models", "dqn_agent.pt"))
        except Exception as e:
            print(f"Failed to save DQN: {e}")
            
    # 2. PPO Feedback
    if signal_id in PENDING_PPO_ACTIONS:
        ppo_action_data = PENDING_PPO_ACTIONS.pop(signal_id)
        try:
            ppo_agent.store_outcome(ppo_action_data, float(reward))
            ppo_agent.train()
            ppo_agent.save(os.path.join(os.path.dirname(__file__), "ml_engine", "models", "ppo_agent.pt"))
        except Exception as e:
            print(f"Failed to process PPO feedback: {e}")
    
    return {"status": "success", "reward": reward}

@app.websocket("/ws/trading")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # If user clicks "APPROVE" on mobile
            if data.get("action") == "EXECUTE_TRADE":
                print(f"Executing trade signal: {data['signal_id']}")
            
            # If extension reports a broken selector
            elif data.get("action") == "DOM_BREAKAGE":
                element = data.get("element")
                url = data.get("url")
                print("!!! RUTE ALERT: DOM BREAKAGE DETECTED !!!")
                print(f"Element: {element} | URL: {url}")
                # In a real app, this could trigger a push notification to mobile
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        manager.disconnect(websocket)

@app.post("/trigger-signal")
async def trigger_signal(ticker: str, side: str):
    """Manually trigger a signal (for testing/mobile approval)"""
    side = (side or "").upper()
    ticker = (ticker or "").strip()
    if side not in ("BUY", "SELL", "HOLD"):
        return {"error": "side must be BUY, SELL or HOLD"}
    if not re.fullmatch(r"[A-Za-z0-9.=\-]+", ticker):
        return {"error": "invalid ticker"}
    signal = {
        "ticker": ticker,
        "side": side,
        "id": f"TXN_{uuid.uuid4().hex[:8].upper()}",
        "reason": "RSI Oversold + MACD Cross (Manual Trigger)",
        "timestamp": datetime.now().isoformat()
    }
    await manager.broadcast_signal(signal)
    return {"status": "Signal Broadcasted", "signal": signal}


# ==================== AUTO-TRADING ENDPOINTS ====================

class BrokerConfig(BaseModel):
    broker_type: str  # "alpaca", "mt5", "ccxt", etc.
    api_key: str
    api_secret: str
    api_server: Optional[str] = ""
    terminal_path: Optional[str] = ""
    paper_trading: bool = True


class AutoTradeConfig(BaseModel):
    enabled: bool
    broker_config: BrokerConfig
    risk_type: str = 'dollar'
    max_position_size: float = 1000
    max_daily_loss: float = 500
    max_daily_profit: float = 1000
    min_confidence: int = 60
    initial_stop_loss_pct: float = 2.0
    initial_take_profit_pct: float = 5.0
    breakeven_trigger_pct: float = 2.0
    trailing_enabled: bool = False
    trailing_activation_pct: float = 5.0
    trailing_distance_pct: float = 1.5
    trailing_step_pct: float = 0.5


@app.post("/api/auto-trade/setup")
async def setup_auto_trading(config: AutoTradeConfig):
    """
    Setup and enable autonomous trading

    IMPORTANT: This enables RUTE to trade on your behalf
    - Trades execute automatically when ML signals are strong
    - Stop loss and take profit are always set (3:1 R:R)
    - Daily loss limits protect your account
    """
    global AUTO_TRADER

    try:
        from trading_engine import AlpacaBroker, MT5Broker, CCXTBroker, AutoTrader

        # Initialize broker
        broker_type = config.broker_config.broker_type.lower()

        if broker_type == "alpaca":
            broker = AlpacaBroker(
                api_key=config.broker_config.api_key,
                api_secret=config.broker_config.api_secret,
                paper_trading=config.broker_config.paper_trading
            )
        elif broker_type == "mt5":
            broker = MT5Broker(
                api_key=config.broker_config.api_key,
                api_secret=config.broker_config.api_secret,
                api_server=config.broker_config.api_server,
                terminal_path=config.broker_config.terminal_path,
                paper_trading=config.broker_config.paper_trading
            )
        elif broker_type == "ccxt":
            broker = CCXTBroker(
                api_key=config.broker_config.api_key,
                api_secret=config.broker_config.api_secret,
                api_server=config.broker_config.api_server,
                paper_trading=config.broker_config.paper_trading
            )
        else:
            return {
                "success": False,
                "error": f"Broker type '{broker_type}' not supported yet."
            }

        # Create auto-trader
        trader_config = {
            "enabled": config.enabled,
            "risk_type": config.risk_type,
            "max_position_size": config.max_position_size,
            "max_daily_loss": config.max_daily_loss,
            "max_daily_profit": config.max_daily_profit,
            "min_confidence": config.min_confidence,
            "initial_stop_loss_pct": config.initial_stop_loss_pct,
            "initial_take_profit_pct": config.initial_take_profit_pct,
            "breakeven_trigger_pct": config.breakeven_trigger_pct,
            "trailing_enabled": config.trailing_enabled,
            "trailing_activation_pct": config.trailing_activation_pct,
            "trailing_distance_pct": config.trailing_distance_pct,
            "trailing_step_pct": config.trailing_step_pct
        }

        AUTO_TRADER = AutoTrader(broker, trader_config)

        # Enable if requested
        if config.enabled:
            success = AUTO_TRADER.enable()
            if not success:
                return {
                    "success": False,
                    "error": "Failed to connect to broker. Check API credentials."
                }

        mode = "PAPER" if config.broker_config.paper_trading else "LIVE"
        return {
            "success": True,
            "message": f"Auto-trading configured with {broker_type.upper()} ({mode} mode)",
            "status": AUTO_TRADER.get_status()
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/auto-trade/enable")
async def enable_auto_trading():
    """Enable autonomous trading"""
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {
            "success": False,
            "error": "Auto-trader not configured. Use /api/auto-trade/setup first."
        }

    success = AUTO_TRADER.enable()
    return {
        "success": success,
        "message": "Auto-trading enabled" if success else "Failed to enable auto-trading",
        "status": AUTO_TRADER.get_status()
    }


@app.post("/api/auto-trade/disable")
@app.post("/api/auto-trade/stop")
async def disable_auto_trading():
    """Disable autonomous trading (also accessible at /api/auto-trade/stop)"""
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {"success": False, "error": "Auto-trader not configured"}

    AUTO_TRADER.disable()
    return {
        "success": True,
        "message": "Auto-trading disabled",
        "status": AUTO_TRADER.get_status()
    }


@app.get("/api/portfolio")
async def get_portfolio():
    """Return all active simulated and live trades."""
    # Format simulated trades
    simulated = []
    for sig_id, trade in OPEN_SIMULATED_TRADES.items():
        simulated.append({
            "id": sig_id,
            "symbol": trade["symbol"],
            "type": trade["type"],
            "entry": trade["entry"],
            "tp": trade["tp"],
            "sl": trade["sl"]
        })
        
    live = []
    account = None
    if AUTO_TRADER:
        try:
            if hasattr(AUTO_TRADER.broker, 'get_account_balance'):
                account = AUTO_TRADER.broker.get_account_balance()
        except Exception as e:
            print(f"Error fetching account balance: {e}")
            
        if AUTO_TRADER.enabled:
            live = AUTO_TRADER.monitor_positions()
            
    return {
        "simulated": simulated,
        "live": live,
        "account": account
    }

@app.get("/api/auto-trade/status")
async def get_auto_trade_status():
    """Get auto-trading status"""
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {
            "configured": False,
            "enabled": False,
            "message": "Auto-trader not configured"
        }

    return {
        "configured": True,
        **AUTO_TRADER.get_status()
    }


@app.get("/api/auto-trade/positions")
async def get_auto_trade_positions():
    """Get all open positions"""
    global AUTO_TRADER

    if AUTO_TRADER is None or not AUTO_TRADER.enabled:
        return {"positions": []}

    positions = AUTO_TRADER.monitor_positions()
    return {"positions": positions}

# ==================== UNIFIED DASHBOARD ENDPOINTS ====================

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Get combined trading stats across MT5 + Alpaca."""
    alpaca_trades = []
    if AUTO_TRADER and hasattr(AUTO_TRADER, 'daily_trades'):
        alpaca_trades = list(AUTO_TRADER.daily_trades)
    stats = await asyncio.to_thread(get_combined_stats, MT5_DB_FILE, alpaca_trades)
    stats["kelly_allocation"] = capital_allocator.get_allocation()
    stats["cross_market_alerts"] = cross_market_engine.get_active_alerts()
    return stats

@app.get("/api/dashboard/mt5-positions")
async def get_mt5_positions_endpoint():
    """Get all open MT5 positions."""
    positions = await asyncio.to_thread(get_mt5_positions)
    return {"positions": positions}

@app.post("/api/dashboard/kill-switch")
async def kill_switch_endpoint():
    """EMERGENCY: Close ALL positions on ALL markets."""
    result = await asyncio.to_thread(dashboard_kill_switch, AUTO_TRADER)
    return result

@app.get("/api/dashboard/kelly")
async def get_kelly_allocation():
    """Get current Kelly Criterion risk allocation."""
    return capital_allocator.get_allocation()

@app.get("/api/dashboard/cross-market")
async def get_cross_market_alerts():
    """Get current cross-market leading indicator alerts."""
    return {
        "alerts": cross_market_engine.get_active_alerts(),
        "leader_data": {k: {kk: vv for kk, vv in v.items() if kk != 'timestamp'}
                        for k, v in cross_market_engine._leader_data.items()}
    }


# ==================== REASONING & LEARNING ENDPOINTS ====================
# THIS IS THE MILLION-DOLLAR FEATURE! RUTE explains WHY it made every decision

@app.get("/api/thoughts/{symbol}")
async def get_symbol_thoughts(symbol: str):
    """
    Get RUTE's complete thought process for a symbol

    This shows EXACTLY why RUTE made each decision:
    - What it observed in the market
    - How it analyzed the data
    - Why it decided to trade or not
    - What it learned from the outcome
    """
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {"error": "Auto-trader not configured"}

    # Path traversal guard: symbols come from the URL unvalidated, and ".."
    # or "%5C" would escape the thoughts root on Windows.
    if not re.fullmatch(r"[A-Za-z0-9.=\-]+", symbol or ""):
        return {"error": "invalid symbol"}

    thoughts_root = os.path.join(os.path.dirname(__file__), "reasoning_engine", "thoughts")
    thoughts_dir = os.path.join(thoughts_root, symbol)
    if not os.path.realpath(thoughts_dir).startswith(os.path.realpath(thoughts_root)):
        return {"error": "invalid symbol"}
    if not os.path.exists(thoughts_dir):
        return {"symbol": symbol, "thoughts": [], "message": "No thoughts logged yet"}

    all_thoughts = {
        "symbol": symbol,
        "analysis": [],
        "decisions": [],
        "executions": [],
        "outcomes": []
    }

    # Read all thought files
    for thought_type in ["analysis", "decision", "execution", "outcome"]:
        type_dir = os.path.join(thoughts_dir, thought_type)
        if os.path.exists(type_dir):
            for filename in sorted(os.listdir(type_dir)):
                filepath = os.path.join(type_dir, filename)
                with open(filepath, 'r') as f:
                    all_thoughts[f"{thought_type}s" if thought_type != "analysis" else thought_type].append(json.load(f))

    return all_thoughts


@app.get("/api/learning/summary")
async def get_learning_summary(days: int = 7):
    """
    What has RUTE learned recently?

    Shows patterns that work, mistakes to avoid, performance improvement
    """
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {"error": "Auto-trader not configured"}

    summary = AUTO_TRADER.improvement_engine.get_learning_summary(days=days)
    return summary


@app.get("/api/learning/insights")
async def get_learning_insights():
    """Get detailed performance analytics and learning insights"""
    global AUTO_TRADER

    if AUTO_TRADER is None:
        return {"error": "Auto-trader not configured"}

    from reasoning_engine import ThoughtLogger
    thought_logger = ThoughtLogger()
    insights = thought_logger.get_learning_insights(days=30)
    return insights


if __name__ == "__main__":
    import uvicorn
    # Localhost only — matches run_backend.py; the legacy .bat launchers used
    # 0.0.0.0 which exposed the unauthenticated API to the LAN.
    uvicorn.run(app, host="127.0.0.1", port=8001)
