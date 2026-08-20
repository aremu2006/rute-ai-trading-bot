# backend/ml_engine/order_flow.py

import pandas as pd
import numpy as np

class OrderFlowAnalyzer:
    """
    Simulates Order Flow / Heatmap Vision.
    Calculates Volume Profile and Institutional 'Walls'.
    """
    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        
    def get_volume_profile(self, df: pd.DataFrame) -> dict:
        """
        Calculates Volume at Price (Volume Profile).
        """
        recent = df.iloc[-self.lookback:]
        
        # Define price bins (0.1% width)
        price_min = recent['Low'].min()
        price_max = recent['High'].max()
        if not np.isfinite(price_min) or not np.isfinite(price_max) or price_max <= price_min:
            # Flat/illiquid window — no meaningful profile; must not veto.
            return None
        bins = np.linspace(price_min, price_max, 20)
        
        # Calculate volume per bin
        # Note: In a real tick feed, this would be precise. 
        # Here we distribute bar volume across its range.
        profile = np.zeros(len(bins)-1)
        for _, row in recent.iterrows():
            idx = (bins[:-1] < row['High']) & (bins[1:] > row['Low'])
            if idx.any():
                profile[idx] += row['Volume'] / idx.sum()
                
        # Find Point of Control (POC) - price with most volume
        poc_idx = np.argmax(profile)
        poc_price = (bins[poc_idx] + bins[poc_idx+1]) / 2
        
        return {
            "poc": poc_price,
            "profile": profile.tolist(),
            "bins": bins.tolist(),
            "va_high": bins[min(poc_idx + 2, len(bins)-1)],
            "va_low": bins[max(poc_idx - 2, 0)]
        }

    def is_fighting_wall(self, symbol: str, current_price: float, trade_type: str, df: pd.DataFrame) -> bool:
        """
        Returns True if the trade is entering directly into a major institutional wall.
        """
        analysis = self.get_volume_profile(df)
        if analysis is None:
            return False  # flat market — no POC wall to fight
        poc = analysis['poc']
        
        # If we are BUYING right into a massive POC resistance above us
        if trade_type == "BUY" and current_price < poc and (poc - current_price) / current_price < 0.005:
            print(f"!!! ORDER FLOW VETO: Buying into POC Wall at {poc}")
            return True
            
        # If we are SELLING right into a massive POC support below us
        if trade_type == "SELL" and current_price > poc and (current_price - poc) / current_price < 0.005:
            print(f"!!! ORDER FLOW VETO: Selling into POC Support at {poc}")
            return True
            
        return False
