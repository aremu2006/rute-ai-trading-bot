"""Backtest engine for RUTE.

Ported concepts:
  - freqtrade: strategy -> indicators -> entry/exit signals -> metrics
    (win rate, profit factor, max drawdown, Sharpe/Sortino/Calmar, equity curve)
    and Hyperopt-style parameter grid optimization.
  - Alphatrend_Scanner.py: AlphaTrend k1/k2 channel (ATR bands + MFI/RSI filter),
    commission-aware wallet simulation, and per-bar signal state tracking.
  - GainzAlgo-style: EMA50/200 trend filter + ATR-scaled stop/target + risk sizing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BARS_PER_YEAR = {"1m": 525600, "5m": 105120, "15m": 35040, "1h": 8760, "4h": 2190, "1d": 365, "1w": 52}


# ---------------------------------------------------------------------------
# Indicator primitives (pure pandas/numpy, no pandas_ta dependency)
# ---------------------------------------------------------------------------

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=max(2, n)).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return _sma(_true_range(high, low, close), n)


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 14) -> pd.Series:
    typical = (high + low + close) / 3
    raw = typical * volume
    pos = raw.where(typical > typical.shift(1), 0.0)
    neg = raw.where(typical < typical.shift(1), 0.0)
    pos_sum = pos.rolling(n, min_periods=1).sum()
    neg_sum = neg.rolling(n, min_periods=1).sum()
    ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    mfi = 100 - (100 / (1 + ratio))
    return mfi.fillna(50.0)


def _macd(close: pd.Series, fast: int, slow: int, signal: int) -> Tuple[pd.Series, pd.Series]:
    macd = _ema(close, fast) - _ema(close, slow)
    return macd, _ema(macd, signal)


def _alpha_trend(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
                 length: int = 14, coeff: float = 1.0) -> Tuple[np.ndarray, np.ndarray]:
    """AlphaTrend ported from Alphatrend_Scanner.py (k1 = trend line, k2 = trend line lag-2)."""
    atr = _atr(high, low, close, length).to_numpy()
    mfi = _mfi(high, low, close, volume, length).to_numpy()
    close = np.asarray(close, dtype=float)
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    n = len(close)
    upt = np.zeros(n)
    down_t = np.zeros(n)
    for i in range(n):
        upt[i] = low[i] - atr[i] * coeff if not np.isnan(atr[i]) else 0.0
        down_t[i] = high[i] + atr[i] * coeff if not np.isnan(atr[i]) else 0.0
    alpha = np.zeros(n)
    for i in range(1, n):
        if mfi[i] >= 50.0:
            alpha[i] = max(upt[i], alpha[i - 1])
        else:
            alpha[i] = min(down_t[i], alpha[i - 1])
    k2 = np.zeros(n)
    k2[2:] = alpha[:-2]
    return alpha, k2


# ---------------------------------------------------------------------------
# Signal generators: return (long_signal, short_signal) boolean arrays
# ---------------------------------------------------------------------------

def sig_rsi(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    period = int(p.get("period", 14))
    oversold = float(p.get("oversold", 30))
    overbought = float(p.get("overbought", 70))
    close = df["Close"]
    rsi = _rsi(close, period)
    long = (rsi < oversold) & (rsi.shift(1) >= oversold)
    short = (rsi > overbought) & (rsi.shift(1) <= overbought)
    return long.to_numpy(), short.to_numpy()


def sig_macd(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    fast = int(p.get("fast", 12))
    slow = int(p.get("slow", 26))
    signal = int(p.get("signal", 9))
    macd, sig = _macd(df["Close"], fast, slow, signal)
    long = (macd > sig) & (macd.shift(1) <= sig.shift(1))
    short = (macd < sig) & (macd.shift(1) >= sig.shift(1))
    return long.to_numpy(), short.to_numpy()


def sig_sma_cross(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    fast = int(p.get("fast", 20))
    slow = int(p.get("slow", 100))
    f = _sma(df["Close"], fast)
    s = _sma(df["Close"], slow)
    long = (f > s) & (f.shift(1) <= s.shift(1))
    short = (f < s) & (f.shift(1) >= s.shift(1))
    return long.to_numpy(), short.to_numpy()


def sig_bollinger(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    period = int(p.get("period", 20))
    std = float(p.get("std", 2.0))
    close = df["Close"]
    mid = _sma(close, period)
    sd = close.rolling(period, min_periods=2).std()
    upper = mid + std * sd
    lower = mid - std * sd
    long = (close < lower) & (close.shift(1) >= lower.shift(1))
    short = (close > upper) & (close.shift(1) <= upper.shift(1))
    return long.to_numpy(), short.to_numpy()


def sig_alpha_trend(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    length = int(p.get("length", 14))
    coeff = float(p.get("coeff", 1.0))
    vol = df["volume"] if "volume" in df.columns else df["Volume"]
    k1, k2 = _alpha_trend(df["High"], df["Low"], df["Close"], vol, length, coeff)
    long = (k1[:-1] <= k2[:-1]) & (k1[1:] > k2[1:])
    short = (k1[:-1] >= k2[:-1]) & (k1[1:] < k2[1:])
    return np.concatenate([[False], long]), np.concatenate([[False], short])


def sig_gainzalgo(df, p: Dict[str, float]) -> Tuple[np.ndarray, np.ndarray]:
    """GainzAlgo-style: EMA50/200 trend filter; RSI-pullback entries within the trend."""
    fast = int(p.get("fast", 50))
    slow = int(p.get("slow", 200))
    rsi_period = int(p.get("rsi_period", 14))
    pullback_max = float(p.get("pullback_max", 55.0))
    close = df["Close"]
    f = _ema(close, fast)
    s = _ema(close, slow)
    rsi = _rsi(close, rsi_period)
    uptrend = f > s
    downtrend = f < s
    long = uptrend & (rsi < pullback_max)
    short = downtrend & (rsi > (100 - pullback_max))
    return long.to_numpy(), short.to_numpy()


STRATEGIES: Dict[str, Dict] = {
    "rsi":         {"label": "RSI Reversal",  "gen": sig_rsi,          "defaults": {"period": 14, "oversold": 30, "overbought": 70},
                     "grid": {"period": [7, 14, 21], "oversold": [25, 30, 35], "overbought": [65, 70, 75]}},
    "macd":        {"label": "MACD Cross",    "gen": sig_macd,         "defaults": {"fast": 12, "slow": 26, "signal": 9},
                     "grid": {"fast": [8, 12, 16], "slow": [21, 26, 35], "signal": [7, 9, 12]}},
    "sma_cross":   {"label": "SMA Cross",     "gen": sig_sma_cross,    "defaults": {"fast": 20, "slow": 100},
                     "grid": {"fast": [10, 20, 50], "slow": [50, 100, 200]}},
    "bollinger":   {"label": "Bollinger",     "gen": sig_bollinger,    "defaults": {"period": 20, "std": 2.0},
                     "grid": {"period": [15, 20, 25], "std": [2.0, 2.5, 3.0]}},
    "alpha_trend": {"label": "AlphaTrend",    "gen": sig_alpha_trend,  "defaults": {"length": 14, "coeff": 1.0},
                     "grid": {"length": [10, 14, 20], "coeff": [1.0, 1.5, 2.0]}},
    "gainzalgo":   {"label": "GainzAlgo",     "gen": sig_gainzalgo,    "defaults": {"fast": 50, "slow": 200, "rsi_period": 14, "pullback_max": 55},
                     "grid": {"fast": [20, 50, 100], "slow": [100, 200, 350], "pullback_max": [50, 55, 60]}},
}


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    strategy: str = ""
    params: Dict[str, float] = field(default_factory=dict)
    symbol: str = ""
    interval: str = ""
    bars: int = 0
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    trade_count: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_trade_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    exposure_pct: float = 0.0
    equity_curve: List[float] = field(default_factory=list)   # downsampled to ~80 points
    final_equity: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        if isinstance(d.get("params"), dict):
            d["params"] = {k: float(v) for k, v in self.params.items()}
        return d


def run_backtest(df: pd.DataFrame, strategy: str, params: Optional[Dict[str, float]] = None,
                 commission: float = 0.00075, slippage: float = 0.0005,
                 initial_capital: float = 100.0, interval: str = "1d") -> BacktestResult:
    """Simulate a long/short strategy over OHLCV bars. df needs Close/High/Low/Volume."""
    res = BacktestResult(strategy=strategy, params=dict(params or {}), bars=len(df), interval=interval)
    try:
        if df is None or len(df) < 50:
            res.error = "Not enough historical bars (need >= 50)"
            return res

        cfg = STRATEGIES[strategy]
        p = {**cfg["defaults"], **(params or {})}
        res.params = {k: float(v) for k, v in p.items()}

        df = df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
        close = df["Close"].astype(float)
        open_p = df["Open"].astype(float)

        vol_name = "Volume" if "Volume" in df.columns else ("volume" if "volume" in df.columns else None)
        work = df.copy()
        if vol_name is not None:
            work = work.rename(columns={vol_name: "volume"})
        elif "volume" not in work.columns:
            work["volume"] = 1.0

        long_sig, short_sig = cfg["gen"](work, p)

        wallet = initial_capital
        position = 0.0          # units held
        entry_price = 0.0
        position_cost = 0.0     # cash spent to open the position (incl. buy commission)
        in_position = False     # True = long, False = flat (short-only excluded for simplicity)
        trades: List[float] = []

        equity = np.empty(len(close))
        bars_in_market = 0

        for i in range(1, len(close)):
            entry = close.iloc[i - 1]
            exit_p = close.iloc[i]
            if exit_p <= 0:
                continue
            filled = exit_p * (1 + slippage) if not in_position else exit_p * (1 - slippage)

            if long_sig[i] and not in_position:
                in_position = True
                entry_price = filled
                position_cost = wallet * (1 - commission)
                position = position_cost / filled
                wallet = 0.0
            elif short_sig[i] and in_position:
                in_position = False
                proceeds = position * filled * (1 - commission)
                if position_cost > 0:
                    trades.append((proceeds / position_cost - 1.0) * 100.0)
                wallet = proceeds
                position = 0.0
                entry_price = 0.0
                position_cost = 0.0

            if in_position:
                bars_in_market += 1
            equity[i] = wallet + position * close.iloc[i]

        # Close any open position at the last close
        if in_position:
            proceeds = position * close.iloc[-1] * (1 - commission) * (1 - slippage)
            if position_cost > 0:
                trades.append((proceeds / position_cost - 1.0) * 100.0)
            wallet = proceeds

        equity[0] = initial_capital
        final = wallet + position * close.iloc[-1]

        res.final_equity = round(final, 2)
        curve = equity[:len(close)]
        res.total_return_pct = round((final / initial_capital - 1.0) * 100.0, 2)
        if final > 0:
            years_frac = BARS_PER_YEAR.get(res.interval, 365) / max(len(close), 1)
            res.annual_return_pct = round((((final / initial_capital) ** years_frac) - 1.0) * 100.0, 2)
        res.trade_count = len(trades)
        res.win_rate_pct = round(100.0 * sum(1 for t in trades if t > 0) / len(trades), 2) if trades else 0.0

        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t < 0]
        gross_p = sum(wins)
        gross_l = -sum(losses)
        res.profit_factor = round(gross_p / gross_l, 2) if gross_l > 0 else (round(gross_p, 2) if gross_p > 0 else 0.0)
        res.avg_trade_pct = round(sum(trades) / len(trades), 2) if trades else 0.0
        res.best_trade_pct = round(max(trades), 2) if trades else 0.0
        res.worst_trade_pct = round(min(trades), 2) if trades else 0.0

        peak = np.maximum.accumulate(curve)
        drawdown = (curve - peak) / peak
        res.max_drawdown_pct = round(float(drawdown.min()) * 100.0, 2)
        res.exposure_pct = round(100.0 * bars_in_market / max(len(close) - 1, 1), 2)

        # Sharpe / Sortino on per-bar returns (annualized, approximate)
        rets = pd.Series(curve).pct_change().dropna()
        mean, std = rets.mean(), rets.std(ddof=0)
        downside = rets[rets < 0].std(ddof=0)
        years = len(close) / BARS_PER_YEAR.get(res.interval, 365)
        res.sharpe = round(float(mean / std * np.sqrt(years * BARS_PER_YEAR.get(res.interval, 365))) if std > 0 else 0.0, 2)
        res.sortino = round(float(mean / downside * np.sqrt(years * BARS_PER_YEAR.get(res.interval, 365))) if downside > 0 else 0.0, 2)
        res.calmar = round(float(res.annual_return_pct / abs(res.max_drawdown_pct)), 2) if abs(res.max_drawdown_pct) > 1e-9 else 0.0

        # Downsampled equity curve for UI sparkline
        step = max(1, len(curve) // 80)
        res.equity_curve = [round(float(x), 2) for x in curve[::step][:80]]
    except Exception as e:  # pragma: no cover
        res.error = f"{type(e).__name__}: {e}"
    return res


def optimize(df: pd.DataFrame, strategy: str, grid: Optional[Dict[str, List[float]]] = None,
             commission: float = 0.00075, slippage: float = 0.0005,
             top_n: int = 8, interval: str = "1d") -> List[BacktestResult]:
    """Grid search over strategy parameters (Hyperopt-lite), ranked by total return."""
    cfg = STRATEGIES[strategy]
    grid = grid or cfg.get("grid", {})
    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys))) if keys else [()]

    results: List[BacktestResult] = []
    for combo in combos:
        params = dict(zip(keys, combo))
        res = run_backtest(df, strategy, params, commission, slippage, interval=interval)
        if not res.error and res.trade_count > 0:
            results.append(res)

    results.sort(key=lambda r: (r.total_return_pct, r.profit_factor), reverse=True)
    for r in results[: top_n]:
        r.equity_curve = []
    return results[:top_n]


def latest_signals(df: pd.DataFrame, strategies: List[str],
                   params_map: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, str]:
    """Current stance per strategy: 'buy' | 'sell' | 'flat' (direction of the most recent cross)."""
    out: Dict[str, str] = {}
    try:
        work = df.copy()
        vol_name = "Volume" if "Volume" in df.columns else ("volume" if "volume" in df.columns else None)
        if vol_name is not None:
            work = work.rename(columns={vol_name: "volume"})
        elif "volume" not in work.columns:
            work["volume"] = 1.0

        for name in strategies:
            cfg = STRATEGIES.get(name)
            if cfg is None:
                out[name] = "flat"
                continue
            p = {**cfg["defaults"], **((params_map or {}).get(name) or {})}
            long_sig, short_sig = cfg["gen"](work, p)
            stance = "flat"
            for i in range(len(long_sig) - 1, -1, -1):
                if long_sig[i]:
                    stance = "buy"
                    break
                if short_sig[i]:
                    stance = "sell"
                    break
            out[name] = stance
    except Exception as e:  # pragma: no cover
        out["error"] = str(e)
    return out