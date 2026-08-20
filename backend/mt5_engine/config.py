"""MT5 Engine Configuration — extracted from ultimate_server.py"""
import os
import json
import logging

log = logging.getLogger("mt5_engine")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None

# RUTE is standalone: the MT5 terminal must NEVER auto-start.
# Only initialize it when the user explicitly opts in.
MT5_INIT_ALLOWED = os.environ.get("RUTE_MT5_ENABLED", "0") == "1"

# --- Core paths ---
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(_ENGINE_DIR, "trades.db")
MODEL_ROOT = os.environ.get("MT5_MODEL_ROOT", os.path.join(_ENGINE_DIR, "models"))
GLOBAL_KEY = "_global"

# --- Feature config ---
CROSS_ASSETS = ["BTCUSDm", "EURUSDm"]
# 35 TF features + 4 time + 3 sessions + 2 cross + 3 context = 47 features
FEATURE_COUNT = 35 + 7 + len(CROSS_ASSETS) + 3
SEQ_LEN = 30

# --- Training ---
RETRAIN_INTERVAL_HOURS = float(os.environ.get("RETRAIN_INTERVAL_HOURS", "24"))
AUTO_RETRAIN_MIN_TRADES = int(os.environ.get("AUTO_RETRAIN_MIN_TRADES", "100"))

# --- Security ---
_API_KEY = os.environ.get("TRADING_API_KEY")

def get_api_key() -> str:
    """Lazy API key validation — only raises when MT5 is actually used."""
    if not _API_KEY:
        raise RuntimeError("CRITICAL: TRADING_API_KEY environment variable must be set")
    return _API_KEY

def require_api_key():
    """Call this at MT5 initialization points, not at module import."""
    get_api_key()

# --- SuperTrend Boost ---
SUPERTREND_BOOST_H1 = 0.03
SUPERTREND_BOOST_H4 = 0.04
SUPERTREND_BOOST_D1 = 0.08

# --- Optuna Auto-Tuning ---
OPTUNA_MIN_TRADES = 500
OPTUNA_CHECK_INTERVAL_HOURS = 6
OPTUNA_N_TRIALS = 200
OPTUNA_CONFIG_FILE = os.path.join(_ENGINE_DIR, "optuna_best.json")

# --- Tunable Parameters (overwritten by Optuna when ready) ---
_tunable = {
    "boost_h1": SUPERTREND_BOOST_H1,
    "boost_h4": SUPERTREND_BOOST_H4,
    "boost_d1": SUPERTREND_BOOST_D1,
    "threshold_high_wr": 0.55,
    "threshold_mid_wr": 0.60,
    "threshold_low_wr": 0.70,
    "trail_atr_base": 1.0,
    "trail_atr_scale": 1.5,
}

_optuna_completed = False

def load_optuna_config():
    """Load optimized params from disk if a previous Optuna run saved them."""
    global _tunable, _optuna_completed
    if os.path.exists(OPTUNA_CONFIG_FILE):
        try:
            with open(OPTUNA_CONFIG_FILE, "r") as f:
                saved = json.load(f)
            _tunable.update(saved)
            _optuna_completed = True
            log.info(f"[Optuna] Loaded optimized params from {OPTUNA_CONFIG_FILE}")
        except Exception as e:
            log.warning(f"[Optuna] Failed to load config: {e}")

# --- Correlation Guard ---
CORRELATION_GROUPS = [
    ["BTCUSDm", "ETHUSDm", "BTCJPYm", "BCHUSDm", "AAVEUSDm"],
    ["EURUSDm", "GBPAUDm"],
]
CORRELATION_MAX_SAME_DIR = 2
CORRELATION_SIGNAL_TTL = 1800

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- MT5 Timeframes ---
if MT5_AVAILABLE:
    OMNI_TIMEFRAMES = [
        ("M1", mt5.TIMEFRAME_M1, 1),
        ("M5", mt5.TIMEFRAME_M5, 5),
        ("M15", mt5.TIMEFRAME_M15, 15),
        ("M30", mt5.TIMEFRAME_M30, 30),
        ("H1", mt5.TIMEFRAME_H1, 60),
        ("H4", mt5.TIMEFRAME_H4, 240),
        ("D1", mt5.TIMEFRAME_D1, 1440),
    ]
else:
    OMNI_TIMEFRAMES = [
        ("M1", None, 1), ("M5", None, 5), ("M15", None, 15),
        ("M30", None, 30), ("H1", None, 60), ("H4", None, 240), ("D1", None, 1440),
    ]

def model_dir(symbol: str) -> str:
    return os.path.join(MODEL_ROOT, symbol)

def model_paths(symbol: str):
    d = model_dir(symbol)
    return (
        os.path.join(d, "xgb_model.pkl"),
        os.path.join(d, "lstm_model.pt"),
        os.path.join(d, "classes.json"),
        os.path.join(d, "scaler.pkl"),  # BUG #6 FIX: Added scaler path
    )
