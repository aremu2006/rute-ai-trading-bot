"""
Cross-Market Leading Indicator AI (Upgrade 1)
Detects when moves in US equities predict Forex/Crypto moves.
"""
import time
import asyncio
import logging
import pandas as pd
from typing import Dict, Optional
import numpy as np



try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from data_providers import get_historical_ohlcv

log = logging.getLogger("ml_engine.cross_market")


class CrossMarketEngine:
    """Detects leading signals between US equities and Forex/Crypto."""

    # Leaders (yfinance tickers) → Followers (MT5 symbols)
    LEADING_PAIRS = {
        "NQ=F":     ["BTCUSDm", "ETHUSDm"],        # Nasdaq futures → Crypto
        "DX-Y.NYB": ["EURUSDm", "GBPUSDm"],         # Dollar Index → Forex
        "^TNX":     ["XAUUSDm"],                     # 10Y Yield → Gold
        "^VIX":     ["BTCUSDm", "EURUSDm", "GBPUSDm"],  # Fear Index → Everything
    }

    # How many periods of history to track for Z-score
    LOOKBACK_PERIODS = 60  # ~60 minutes of 1-min data for intraday

    def __init__(self):
        self._score_cache: Dict[str, float] = {}  # symbol → modifier
        self._leader_data: Dict[str, dict] = {}   # leader → {prices, roc, zscore, timestamp}
        self._correlator_model = None
        self._last_update = 0.0

    def compute_cross_features(self):
        """Fetch latest data for all leading indicators and compute Z-scores."""
        now = time.time()
        for leader in self.LEADING_PAIRS:
            try:
                hist = get_historical_ohlcv(leader, period="5d", interval="5m")
                if hist is None or hist.empty or len(hist) < 20:
                    continue

                closes = hist['Close'].values
                # Rate of change at multiple windows
                roc_5 = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
                roc_15 = (closes[-1] / closes[-3] - 1) * 100 if len(closes) >= 3 else 0
                roc_60 = (closes[-1] / closes[-12] - 1) * 100 if len(closes) >= 12 else 0

                # Z-score of the latest move (how unusual is it?)
                closes_safe = np.asarray(closes, dtype=float)
                prev = closes_safe[-self.LOOKBACK_PERIODS:-1]
                curr = closes_safe[-self.LOOKBACK_PERIODS:]
                with np.errstate(divide='ignore', invalid='ignore'):
                    returns = np.where(prev == 0, np.nan, np.diff(curr) / prev)
                returns = returns[np.isfinite(returns)]
                if len(returns) > 5:
                    mean_ret = np.mean(returns)
                    std_ret = np.std(returns)
                    latest_ret = returns[-1] if len(returns) > 0 else 0
                    # Guard against zero/NaN std (e.g. flat or broken price series)
                    if np.isfinite(std_ret) and std_ret > 0:
                        z_score = (latest_ret - mean_ret) / std_ret
                    else:
                        z_score = 0.0
                else:
                    z_score = 0.0

                self._leader_data[leader] = {
                    "roc_5": roc_5,
                    "roc_15": roc_15,
                    "roc_60": roc_60,
                    "z_score": z_score,
                    "last_close": closes[-1],
                    "timestamp": now,
                }

            except Exception as e:
                log.warning(f"[CrossMarket] Failed to fetch {leader}: {e}")
                # Drop stale data — an old z-score must not keep modifying
                # live confidence indefinitely after a data outage.
                self._leader_data.pop(leader, None)

        # Update score cache for followers
        self._update_scores()
        self._last_update = now

    def _update_scores(self):
        """Calculate signal modifiers for each follower symbol."""
        new_scores: Dict[str, float] = {}

        for leader, followers in self.LEADING_PAIRS.items():
            data = self._leader_data.get(leader)
            if data is None:
                continue

            z = data["z_score"]
            roc_60 = data["roc_60"]

            # Only act on significant moves (|Z| > 1.5)
            if abs(z) < 1.5:
                continue

            for follower in followers:
                modifier = 0.0

                if leader == "DX-Y.NYB":
                    # Dollar strength is INVERSE to EUR/GBP
                    if z > 2.0:  # Dollar surging
                        modifier = -0.15  # Penalize BUY on EUR/GBP
                    elif z < -2.0:  # Dollar crashing
                        modifier = 0.10   # Boost BUY on EUR/GBP

                elif leader == "NQ=F":
                    # Nasdaq crash → Crypto follows
                    if z < -2.0:  # Nasdaq panic sell
                        modifier = -0.20  # Strong penalty for BUY crypto
                    elif z > 2.0:  # Nasdaq rally
                        modifier = 0.10   # Mild boost for BUY crypto

                elif leader == "^VIX":
                    # VIX spike → risk-off everywhere
                    if z > 2.5:  # Fear spike
                        modifier = -0.15  # Penalize BUY on risk assets
                    elif z < -1.5:  # Calm returning
                        modifier = 0.05   # Mild boost

                elif leader == "^TNX":
                    # Yield spike → Gold drops
                    if z > 2.0:
                        modifier = -0.12  # Penalize BUY gold
                    elif z < -2.0:
                        modifier = 0.08   # Boost BUY gold

                # Aggregate: take the strongest signal per follower
                current = new_scores.get(follower, 0.0)
                if abs(modifier) > abs(current):
                    new_scores[follower] = modifier

        self._score_cache = new_scores

    def get_signal_modifier(self, symbol: str, direction: str = "BUY") -> float:
        """
        Returns a confidence modifier for a symbol based on cross-market signals.
        Positive = cross-market supports the trade direction.
        Negative = cross-market warns of incoming reversal.
        """
        modifier = self._score_cache.get(symbol, 0.0)

        # If the modifier is negative, it penalizes BUY. For SELL, it's a boost.
        if direction == "SELL":
            modifier = -modifier

        return round(modifier, 4)

    def get_active_alerts(self) -> list:
        """Return list of currently active cross-market alerts."""
        alerts = []
        for leader, data in self._leader_data.items():
            if data and abs(data["z_score"]) >= 2.0:
                alerts.append({
                    "leader": leader,
                    "z_score": round(data["z_score"], 2),
                    "roc_60min": round(data["roc_60"], 3),
                    "followers": self.LEADING_PAIRS[leader],
                })
        return alerts

    def train_correlator(self):
        """Train an XGBoost model on historical cross-market correlations."""
        if not XGB_AVAILABLE:
            log.warning("[CrossMarket] Cannot train: missing xgboost")
            return

        log.info("[CrossMarket] Training cross-market correlator...")
        # This would fetch 1 year of aligned daily data and train
        # For now, the rule-based Z-score system handles it
        log.info("[CrossMarket] Using rule-based Z-score system (correlator training TBD)")


# Global instance
cross_market_engine = CrossMarketEngine()


async def cross_market_scanner_loop():
    """Background task that runs every 60 seconds to update cross-market signals."""
    while True:
        try:
            await asyncio.to_thread(cross_market_engine.compute_cross_features)
            alerts = cross_market_engine.get_active_alerts()
            if alerts:
                log.info(f"[CrossMarket] Active alerts: {len(alerts)}")
                for a in alerts:
                    log.info(f"  {a['leader']} Z={a['z_score']} ROC60={a['roc_60min']}% → affects {a['followers']}")
        except Exception as e:
            log.error(f"[CrossMarket] Scanner error: {e}")
        await asyncio.sleep(60)
