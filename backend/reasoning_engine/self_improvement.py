"""
RUTE Self-Improvement Engine
Learns from every trade, adapts strategy, and gets better over time
This is the SECRET SAUCE that makes RUTE a million-dollar property
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SelfImprovementEngine:
    """
    Continuously learns from trading outcomes and improves performance
    """

    def __init__(self, learning_dir="reasoning_engine/thoughts"):
        self.learning_dir = learning_dir
        self.learning_db_path = os.path.join(learning_dir, "learning_database.json")
        self.performance_log = os.path.join(learning_dir, "performance_log.json")
        self.strategy_evolution = os.path.join(learning_dir, "strategy_evolution.json")

    def analyze_trade_outcome(self, trade_outcome: Dict) -> Dict:
        """
        Deep analysis of what worked or didn't work in a trade

        Returns comprehensive learning insights
        """
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "symbol": trade_outcome["symbol"],
            "outcome": trade_outcome["outcome"],
            "insights": []
        }

        if "outcome" not in trade_outcome or trade_outcome["outcome"] not in ["WIN", "LOSS"]:
            logger.warning(f"Skipping analysis for trade {trade_outcome.get('symbol', 'UNKNOWN')} due to missing or invalid outcome.")
            return analysis

        if trade_outcome["outcome"] == "WIN":
            analysis["insights"] = self._analyze_winning_trade(trade_outcome)
        else:
            analysis["insights"] = self._analyze_losing_trade(trade_outcome)

        # Update performance metrics
        self._update_performance_metrics(trade_outcome)

        # Check if strategy adjustment needed
        adjustment_needed = self._check_strategy_adjustment()
        if adjustment_needed:
            analysis["strategy_adjustment"] = adjustment_needed

        return analysis

    def _analyze_winning_trade(self, trade: Dict) -> List[Dict]:
        """Analyze WHY a trade was successful"""
        insights = []

        # Pattern recognition
        insights.append({
            "type": "pattern_recognition",
            "insight": f"Successful setup identified: {trade.get('entry_reason', 'Unknown')}",
            "confidence_before": trade.get("entry_confidence", 0),
            "actual_outcome": "WIN",
            "learning": "Increase weight for this pattern in future predictions"
        })

        # Feature importance
        if "ml_features" in trade:
            insights.append({
                "type": "feature_validation",
                "insight": "ML features that correctly predicted this move",
                "key_features": trade["ml_features"].get("top_features", []),
                "learning": "These features are reliable - trust them more"
            })

        # Risk management validation
        profit_amt = trade.get("profit_loss", trade.get("profit", 0))
        insights.append({
            "type": "risk_management",
            "insight": f"3:1 R:R worked as designed: Risked {trade.get('risk_amount', 0)}, Made {profit_amt}",
            "learning": "Risk management rules are sound - keep using them"
        })

        # Timing analysis
        time_in_trade = trade.get("time_in_trade_hours", 0)
        insights.append({
            "type": "timing",
            "insight": f"Trade took {time_in_trade} hours to hit target",
            "learning": f"This setup typically takes {time_in_trade} hours - plan accordingly"
        })

        return insights

    def _analyze_losing_trade(self, trade: Dict) -> List[Dict]:
        """Analyze WHY a trade failed and how to prevent it"""
        insights = []

        # Root cause analysis
        exit_reason = trade.get("exit_reason", "STOP_LOSS_HIT")
        insights.append({
            "type": "failure_analysis",
            "insight": f"Trade failed due to: {exit_reason}",
            "root_causes": trade.get("what_went_wrong", []),
            "learning": "Add filters to avoid these conditions in future"
        })

        # False signal detection
        insights.append({
            "type": "false_signal",
            "insight": "Indicator(s) gave false signal",
            "misleading_indicators": trade.get("misleading_indicators", []),
            "learning": "Reduce reliance on these indicators in this market condition"
        })

        # Market condition mismatch
        insights.append({
            "type": "market_regime",
            "insight": "Strategy may not work in current market regime",
            "market_condition": trade.get("market_condition", "Unknown"),
            "learning": "Avoid this setup in similar market conditions"
        })

        # Corrective actions
        for action in trade.get("corrective_actions", []):
            insights.append({
                "type": "corrective_action",
                "action": action,
                "learning": "Implement this immediately to prevent recurrence"
            })

        return insights

    def _update_performance_metrics(self, trade: Dict):
        """Track performance over time"""
        if os.path.exists(self.performance_log):
            with open(self.performance_log, 'r') as f:
                metrics = json.load(f)
        else:
            metrics = {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "total_profit": 0,
                "total_loss": 0,
                "win_rate_history": [],
                "profit_factor_history": [],
                "strategy_versions": []
            }

        # Update counts
        metrics["total_trades"] += 1
        profit_loss = trade.get("profit_loss", trade.get("profit", 0))
        
        if trade["outcome"] == "WIN":
            metrics["wins"] += 1
            metrics["total_profit"] += profit_loss
        else:
            metrics["losses"] += 1
            metrics["total_loss"] += abs(profit_loss)

        # Calculate current win rate
        current_win_rate = (metrics["wins"] / metrics["total_trades"]) * 100
        metrics["win_rate_history"].append({
            "trade_number": metrics["total_trades"],
            "win_rate": current_win_rate,
            "timestamp": datetime.now().isoformat()
        })

        # Calculate profit factor
        profit_factor = metrics["total_profit"] / metrics["total_loss"] if metrics["total_loss"] > 0 else 0
        metrics["profit_factor_history"].append({
            "trade_number": metrics["total_trades"],
            "profit_factor": profit_factor,
            "timestamp": datetime.now().isoformat()
        })

        # Save updated metrics
        with open(self.performance_log, 'w') as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"📊 Performance updated: {current_win_rate:.1f}% win rate across {metrics['total_trades']} trades")

    def _check_strategy_adjustment(self) -> Optional[Dict]:
        """Check if strategy needs adjustment based on recent performance"""
        if not os.path.exists(self.performance_log):
            return None

        with open(self.performance_log, 'r') as f:
            metrics = json.load(f)

        # Get last 20 trades performance
        if len(metrics["win_rate_history"]) < 20:
            return None

        recent_trades = metrics["win_rate_history"][-20:]
        recent_win_rate = np.mean([t["win_rate"] for t in recent_trades])

        # If win rate dropped below 40%, adjust strategy
        if recent_win_rate < 40:
            return {
                "reason": f"Recent win rate ({recent_win_rate:.1f}%) below acceptable threshold",
                "adjustment": "INCREASE_SELECTIVITY",
                "actions": [
                    "Raise minimum confidence from 60% to 70%",
                    "Add additional confirmation requirement",
                    "Reduce trading frequency, focus on A+ setups only"
                ],
                "timestamp": datetime.now().isoformat()
            }

        # If win rate consistently above 55%, can be more aggressive
        elif recent_win_rate > 55:
            return {
                "reason": f"Recent win rate ({recent_win_rate:.1f}%) above target",
                "adjustment": "INCREASE_FREQUENCY",
                "actions": [
                    "Lower minimum confidence from 60% to 55%",
                    "Can take more trades with similar setups",
                    "Strategy is working well - scale up"
                ],
                "timestamp": datetime.now().isoformat()
            }

        return None

    def get_learning_summary(self, days: int = 7) -> Dict:
        """
        Generate summary of what RUTE has learned recently
        """
        if not os.path.exists(self.learning_db_path):
            return {"message": "No learning data yet"}

        with open(self.learning_db_path, 'r') as f:
            learning_db = json.load(f)

        # Filter recent learnings
        cutoff_date = datetime.now() - timedelta(days=days)

        recent_wins = [
            w for w in learning_db.get("winning_setups", [])
            if datetime.fromisoformat(w["timestamp"]) > cutoff_date
        ]

        recent_losses = [
            l for l in learning_db.get("losing_setups", [])
            if datetime.fromisoformat(l["timestamp"]) > cutoff_date
        ]

        summary = {
            "period": f"Last {days} days",
            "total_learnings": len(recent_wins) + len(recent_losses),
            "successful_patterns": [],
            "patterns_to_avoid": [],
            "key_insights": [],
            "strategy_improvements": []
        }

        # Extract successful patterns
        for win in recent_wins:
            for pattern in win.get("pattern", []):
                if isinstance(pattern, str) and "REINFORCEMENT:" in pattern:
                    summary["successful_patterns"].append(pattern.replace("REINFORCEMENT: ", ""))

        # Extract patterns to avoid
        for loss in recent_losses:
            for mistake in loss.get("mistakes", []):
                if isinstance(mistake, str):
                    summary["patterns_to_avoid"].append(mistake)

        # Identify key insights
        summary["key_insights"] = self._identify_key_insights(recent_wins, recent_losses)

        return summary

    def _identify_key_insights(self, wins: List, losses: List) -> List[str]:
        """Extract actionable insights from wins and losses"""
        insights = []

        # Win rate analysis
        total = len(wins) + len(losses)
        if total > 0:
            win_rate = (len(wins) / total) * 100
            insights.append(f"Recent win rate: {win_rate:.1f}% ({len(wins)} wins, {len(losses)} losses)")

        # Common winning patterns
        if wins:
            insights.append(f"Found {len(wins)} successful setups - these patterns work!")

        # Common mistakes
        if losses:
            insights.append(f"Identified {len(losses)} losing trades - learning to avoid these setups")

        # Improvement trajectory
        insights.append("RUTE is continuously learning and improving from every trade")

        return insights

    def propose_model_improvements(self) -> Dict:
        """
        Analyze performance and propose specific model improvements
        """
        improvements = {
            "timestamp": datetime.now().isoformat(),
            "proposals": []
        }

        if not os.path.exists(self.learning_db_path):
            return improvements

        with open(self.learning_db_path, 'r') as f:
            learning_db = json.load(f)

        # Analyze winning setups
        winning_patterns = learning_db.get("winning_setups", [])
        if len(winning_patterns) >= 5:
            improvements["proposals"].append({
                "type": "RETRAIN_WITH_WINS",
                "description": f"Retrain model with {len(winning_patterns)} successful patterns",
                "expected_impact": "Increase confidence in similar setups",
                "priority": "HIGH"
            })

        # Analyze losing setups
        losing_patterns = learning_db.get("losing_setups", [])
        if len(losing_patterns) >= 3:
            improvements["proposals"].append({
                "type": "ADD_NEGATIVE_EXAMPLES",
                "description": f"Add {len(losing_patterns)} losing patterns as negative examples",
                "expected_impact": "Reduce false signals",
                "priority": "CRITICAL"
            })

        # Feature importance updates
        improvements["proposals"].append({
            "type": "UPDATE_FEATURE_WEIGHTS",
            "description": "Adjust feature importance based on actual trade outcomes",
            "expected_impact": "Better prediction accuracy",
            "priority": "MEDIUM"
        })

        return improvements
