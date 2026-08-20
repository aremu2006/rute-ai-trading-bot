"""
Kelly Criterion Dynamic Capital Allocator (Upgrade 4)
Uses Half-Kelly formula to size positions based on historical performance.
"""
import logging
import numpy as np
from collections import deque
from typing import Dict

log = logging.getLogger("ml_engine.capital_allocator")


class RollingStats:
    """Tracks rolling trade statistics for Kelly calculations."""

    def __init__(self, window: int = 50):
        self.window = window
        self._outcomes = deque(maxlen=window)    # "WIN" or "LOSS"
        self._pnls = deque(maxlen=window)        # raw P&L values
        self._rr_ratios = deque(maxlen=window)   # risk/reward ratios

    def update(self, outcome: str, pnl: float, rr_ratio: float = 1.5):
        self._outcomes.append(outcome)
        self._pnls.append(pnl)
        self._rr_ratios.append(max(rr_ratio, 0.01))

    @property
    def total_trades(self) -> int:
        return len(self._outcomes)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.5
        return sum(1 for o in self._outcomes if o == "WIN") / self.total_trades

    @property
    def avg_rr_ratio(self) -> float:
        if len(self._rr_ratios) == 0:
            return 1.5
        return sum(self._rr_ratios) / len(self._rr_ratios)

    @property
    def avg_pnl(self) -> float:
        if len(self._pnls) == 0:
            return 0.0
        return sum(self._pnls) / len(self._pnls)

    @property
    def sharpe_proxy(self) -> float:
        """Simple Sharpe-like metric: mean/std of P&L."""
        if len(self._pnls) < 5:
            return 0.0
        arr = list(self._pnls)
        std = max(np.std(arr), 1e-10)
        return np.mean(arr) / std


class KellyAllocator:
    """
    Manages dynamic risk allocation across MT5 and Alpaca using Half-Kelly.

    Half-Kelly formula: f* = max(0, (p*b - q) / (2*b))
    where:
        p = win probability
        q = 1 - p (loss probability)
        b = average reward-to-risk ratio
    """

    MAX_TOTAL_RISK = 0.04     # 4% max total risk across all markets
    DEFAULT_RISK = 0.01       # 1% default until enough data
    MIN_TRADES_FOR_KELLY = 10  # Minimum trades before using Kelly

    def __init__(self):
        self.mt5_stats = RollingStats(window=50)
        self.alpaca_stats = RollingStats(window=50)

    def update_mt5(self, outcome: str, pnl: float, rr_ratio: float = 1.5):
        """Record an MT5 trade outcome."""
        self.mt5_stats.update(outcome, pnl, rr_ratio)
        log.debug(f"[Kelly] MT5 updated: WR={self.mt5_stats.win_rate:.2%} "
                  f"trades={self.mt5_stats.total_trades}")

    def update_alpaca(self, outcome: str, pnl: float, rr_ratio: float = 1.5):
        """Record an Alpaca trade outcome."""
        self.alpaca_stats.update(outcome, pnl, rr_ratio)
        log.debug(f"[Kelly] Alpaca updated: WR={self.alpaca_stats.win_rate:.2%} "
                  f"trades={self.alpaca_stats.total_trades}")

    def _half_kelly(self, stats: RollingStats) -> float:
        """Calculate Half-Kelly fraction for a market."""
        if stats.total_trades < self.MIN_TRADES_FOR_KELLY:
            return self.DEFAULT_RISK

        p = stats.win_rate
        q = 1.0 - p
        b = stats.avg_rr_ratio

        # Half-Kelly formula
        kelly = (p * b - q) / (2 * b)

        # Clamp to [0, MAX_TOTAL_RISK]
        kelly = max(0.0, min(kelly, self.MAX_TOTAL_RISK))

        return round(kelly, 4)

    def get_allocation(self) -> Dict[str, float]:
        """
        Returns dynamic risk allocation percentages.
        Total risk is capped at MAX_TOTAL_RISK.
        """
        mt5_risk = self._half_kelly(self.mt5_stats)
        alpaca_risk = self._half_kelly(self.alpaca_stats)

        # Cap total risk
        total = mt5_risk + alpaca_risk
        if total > self.MAX_TOTAL_RISK:
            scale = self.MAX_TOTAL_RISK / total
            mt5_risk = round(mt5_risk * scale, 4)
            alpaca_risk = round(alpaca_risk * scale, 4)

        return {
            "mt5_risk_pct": mt5_risk,
            "alpaca_risk_pct": alpaca_risk,
            "total_risk_pct": round(mt5_risk + alpaca_risk, 4),
            "mt5_win_rate": round(self.mt5_stats.win_rate, 4),
            "alpaca_win_rate": round(self.alpaca_stats.win_rate, 4),
            "mt5_trades": self.mt5_stats.total_trades,
            "alpaca_trades": self.alpaca_stats.total_trades,
            "mt5_sharpe": round(self.mt5_stats.sharpe_proxy, 2),
            "alpaca_sharpe": round(self.alpaca_stats.sharpe_proxy, 2),
        }


# Global instance
capital_allocator = KellyAllocator()
