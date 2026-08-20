import pandas as pd
import numpy as np
from typing import List

class HurstCalculator:
    """
    Calculates the Hurst Exponent (H) to identify market persistence.
    H < 0.5: Mean-Reverting (Anti-persistent)
    H = 0.5: Random Walk (Noise)
    H > 0.5: Trending (Persistent)
    """
    @staticmethod
    def compute_hurst(series: pd.Series, lags: List[int] = None) -> float:
        """
        Compute Hurst exponent using R/S analysis or simplified variance method.
        """
        if lags is None:
            lags = [2, 4, 8, 16, 32, 64]
            
        # Simplified estimate using variance of price differences
        # See: 'Testing for the Hurst Exponent in Financial Time Series'
        series = np.log(series)
        tau = []
        for lag in lags:
            diff = series.diff(lag).dropna()
            std = diff.std()
            tau.append(std)
            
        tau = np.array(tau)
        tau = np.maximum(tau, 1e-10)  # FIX #15: Guard against zero/negative values
        # Log-log regression
        reg = np.polyfit(np.log(lags), np.log(tau), 1)
        return reg[0]

class EntropyCalculator:
    """
    Calculates Shannon Entropy to measure price-action disorder.
    High Entropy = High Noise/Randomness.
    """
    @staticmethod
    def compute_entropy(series: pd.Series, bins: int = 10) -> float:
        """
        Calculates Shannon Entropy of price returns.
        """
        returns = series.pct_change().dropna()
        if returns.empty:
            return 0.0
            
        counts, _ = np.histogram(returns, bins=bins)
        probs = counts / len(returns)
        # Remove zero probabilities for log
        probs = probs[probs > 0]
        return -np.sum(probs * np.log2(probs))

class RegimeClassifier:
    """Classifies market as TRENDING or CHOPPY using ADX"""
    @staticmethod
    def get_regime(adx_value: float, hurst_value: float = None) -> str:
        # 1. Check for Hurst Persistence (if available)
        if hurst_value is not None:
            if 0.45 <= hurst_value <= 0.55:
                return "RANDOM_WALK"  # Total Noise
            elif hurst_value < 0.45:
                return "MEAN_REVERTING"
            elif hurst_value > 0.55:
                return "TRENDING"

        # 2. Fallback to ADX
        if adx_value > 25:
            return "TRENDING"
        elif adx_value < 20:
            return "CHOPPY"
        else:
            return "NEUTRAL"

    @staticmethod
    def should_veto(adx_value: float, hurst_value: float = None, entropy_value: float = None) -> bool:
        """Veto trade if choppy, random walk, OR high entropy (Deep Hibernate)"""
        # 1. Random Walk Veto (Hurst)
        if hurst_value is not None and 0.45 <= hurst_value <= 0.55:
            return True
            
        # 2. Deep Hibernate (Entropy)
        # Shannon Entropy typically ranges 0-3 for market data; > 2.5 is extremely chaotic
        if entropy_value is not None and entropy_value > 2.5:
            print(f"!!! DEEP HIBERNATE: High Entropy Detected ({entropy_value:.2f})")
            return True
            
        return adx_value < 20

class AdaptiveRiskManager:
    """Calculates volatility-adjusted SL/TP targets using ATR"""
    @staticmethod
    def calculate_exits(entry_price: float, side: str, atr_value: float, multiplier: float = 2.0):
        """
        Calculates SL and TP based on ATR
        SL is 2*ATR away from entry.
        TP is 6*ATR away (to maintain 3:1 RR).
        Returns (None, None) when ATR is missing/invalid so callers can fall back.
        """
        if atr_value is None or not np.isfinite(atr_value) or atr_value <= 0 or entry_price is None:
            return None, None

        sl_dist = atr_value * multiplier
        tp_dist = sl_dist * 3.0  # 3:1 Risk/Reward
        
        if side.upper() == "BUY":
            sl = entry_price - sl_dist
            tp = entry_price + tp_dist
        else: # SELL
            sl = entry_price + sl_dist
            tp = entry_price - tp_dist
            
        return round(sl, 5), round(tp, 5)
