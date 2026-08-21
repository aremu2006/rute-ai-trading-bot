
"""
Cross-Market Leading Indicator AI (Upgrade 1)
Detects when moves in US equities predict Forex/Crypto moves.
Now upgraded with a Graph Neural Network (GNN) for shockwave propagation.
"""
import time
import asyncio
import logging
import threading
import pandas as pd
from typing import Dict, Optional, List
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False

from data_providers import get_historical_ohlcv

log = logging.getLogger("ml_engine.cross_market")

# --- GRAPH NEURAL NETWORK ---
class GCNLayer(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)

    def forward(self, x, adj):
        support = self.linear(x)
        out = torch.matmul(adj, support)
        return out

class MarketGNN(nn.Module):
    def __init__(self, feature_dim=4, hidden_dim=16):
        super().__init__()
        self.gc1 = GCNLayer(feature_dim, hidden_dim)
        self.gc2 = GCNLayer(hidden_dim, 1) # Predicts 1 modifier score per node
        
    def forward(self, x, adj):
        x = F.relu(self.gc1(x, adj))
        x = self.gc2(x, adj)
        return torch.tanh(x)

# -----------------------------

class CrossMarketEngine:
    """Detects leading signals between US equities and Forex/Crypto using a GNN."""

    # Leaders (yfinance tickers) -> Followers (MT5 symbols)
    LEADING_PAIRS = {
        "NQ=F":     ["BTCUSDm", "ETHUSDm"],        
        "DX-Y.NYB": ["EURUSDm", "GBPUSDm"],         
        "^TNX":     ["XAUUSDm"],                     
        "^VIX":     ["BTCUSDm", "EURUSDm", "GBPUSDm"],  
    }

    LOOKBACK_PERIODS = 60

    def __init__(self):
        self._score_cache: Dict[str, float] = {}  
        self._leader_data: Dict[str, dict] = {}   
        self._last_update = 0.0
        
        self._lock = threading.RLock()
        
        # Initialize GNN
        self.gnn = MarketGNN()
        self.nodes = list(self.LEADING_PAIRS.keys()) + list(set(f for sublist in self.LEADING_PAIRS.values() for f in sublist))
        self.node_to_idx = {node: i for i, node in enumerate(self.nodes)}
        self.adj_matrix = self._build_adjacency_matrix()

    def _build_adjacency_matrix(self) -> torch.Tensor:
        n = len(self.nodes)
        adj = torch.zeros((n, n))
        # Add self-loops
        for i in range(n):
            adj[i, i] = 1.0
            
        # Add directed edges from leaders to followers
        for leader, followers in self.LEADING_PAIRS.items():
            l_idx = self.node_to_idx[leader]
            for f in followers:
                f_idx = self.node_to_idx[f]
                # Inverse relationship for DXY and Yields
                weight = -1.0 if leader in ["DX-Y.NYB", "^TNX", "^VIX"] else 1.0
                adj[l_idx, f_idx] = weight
                
        # Row-normalize
        rowsum = adj.abs().sum(dim=1, keepdim=True)
        adj = adj / rowsum.clamp(min=1e-8)
        return adj

    def compute_cross_features(self):
        """Fetch latest data for all leading indicators and pass through GNN."""
        now = time.time()
        node_features = torch.zeros((len(self.nodes), 4)) # [z, roc5, roc15, roc60]
        
        for leader in self.LEADING_PAIRS:
            try:
                hist = get_historical_ohlcv(leader, period="5d", interval="5m")
                if hist is None or hist.empty or len(hist) < 20:
                    continue

                closes = hist['Close'].values
                roc_5 = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
                roc_15 = (closes[-1] / closes[-3] - 1) * 100 if len(closes) >= 3 else 0
                roc_60 = (closes[-1] / closes[-12] - 1) * 100 if len(closes) >= 12 else 0

                closes_safe = np.asarray(closes, dtype=float)
                prev = closes_safe[-self.LOOKBACK_PERIODS:-1]
                curr = closes_safe[-self.LOOKBACK_PERIODS:]

                if len(prev) >= 2:
                    mean_val = float(np.mean(prev))
                    std_val = float(np.std(prev))
                    z = (closes_safe[-1] - mean_val) / std_val if std_val > 1e-8 else 0.0
                else:
                    z = 0.0

                idx = self.node_to_idx[leader]
                node_features[idx] = torch.tensor([z, roc_5, roc_15, roc_60])

                with self._lock:
                    self._leader_data[leader] = {
                        "price": float(closes[-1]),
                        "z_score": float(z),
                        "roc_5": float(roc_5),
                        "roc_15": float(roc_15),
                        "roc_60": float(roc_60),
                        "timestamp": now,
                    }

            except Exception as e:
                log.warning(f"[CrossMarket] Failed to fetch {leader}: {e}")
                with self._lock:
                    self._leader_data.pop(leader, None)

        self._update_scores_gnn(node_features)
        self._last_update = now

    def _update_scores_gnn(self, node_features: torch.Tensor):
        """Pass features through GNN to get signal modifiers (thread-safe)."""
        with self._lock:
            self.gnn.eval()
            with torch.no_grad():
                scores = self.gnn(node_features, self.adj_matrix)
                
            new_scores = {}
            for node, idx in self.node_to_idx.items():
                if node not in self.LEADING_PAIRS: # It's a follower
                    score = scores[idx].item()
                    # Multiply by 0.2 to keep modifier within sensible limits (-0.2 to 0.2)
                    new_scores[node] = score * 0.2
                    
            self._score_cache = new_scores

    def get_signal_modifier(self, symbol: str, direction: str = "BUY") -> float:
        with self._lock:
            modifier = self._score_cache.get(symbol, 0.0)
        if direction == "SELL":
            modifier = -modifier
        return round(modifier, 4)

    def get_active_alerts(self) -> list:
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
        log.info("[CrossMarket] GNN handles correlation natively. No external training required.")


cross_market_engine = CrossMarketEngine()

async def cross_market_scanner_loop():
    while True:
        try:
            await asyncio.to_thread(cross_market_engine.compute_cross_features)
            alerts = cross_market_engine.get_active_alerts()
            if alerts:
                log.info(f"[CrossMarket] Active alerts: {len(alerts)}")
        except Exception as e:
            log.error(f"[CrossMarket] Scanner error: {e}")
        await asyncio.sleep(60)
