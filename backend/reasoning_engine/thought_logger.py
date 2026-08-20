"""
RUTE Thought Logger
Logs every decision, reasoning, and learning from mistakes
This is what makes RUTE truly intelligent and valuable
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThoughtLogger:
    """
    Logs RUTE's complete thought process for every trade decision
    - WHY it made the trade
    - WHAT indicators influenced it
    - HOW confident it was
    - WHAT it learned from the outcome
    """

    def __init__(self, log_dir="reasoning_engine/thoughts"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def log_analysis_thought(self, symbol: str, thought: Dict):
        """
        Log RUTE's initial market analysis thoughts

        Example thought:
        {
            "symbol": "AAPL",
            "timestamp": "2024-01-15 10:23:45",
            "observation": "AAPL price at $150.00, down 2.3% from yesterday",
            "technical_analysis": {
                "rsi": 42.3,
                "rsi_interpretation": "RSI at 42.3 suggests oversold conditions, potential reversal",
                "macd": 1.25,
                "macd_interpretation": "MACD above signal line indicates bullish momentum building",
                "moving_averages": "SMA 20 ($148) < SMA 50 ($152) - downtrend, but price approaching support"
            },
            "ml_analysis": {
                "prediction": "BUY",
                "confidence": 68,
                "reasoning": "ML model trained on 45 years sees pattern similar to 234 past recoveries",
                "contributing_factors": [
                    "Price bouncing off 50-day SMA support (weight: 0.23)",
                    "Volume spike 1.45x average (weight: 0.18)",
                    "RSI divergence detected (weight: 0.15)"
                ]
            },
            "market_context": {
                "broader_market": "S&P 500 up 0.5%, tech sector leading",
                "news_sentiment": "Neutral - no major catalysts detected",
                "sector_correlation": "Tech stocks showing strength"
            }
        }
        """
        thought["type"] = "analysis"
        thought["symbol"] = symbol
        thought["timestamp"] = datetime.now().isoformat()
        self._save_thought(symbol, "analysis", thought)

    def log_decision_thought(self, symbol: str, decision: Dict):
        """
        Log RUTE's decision-making process

        Example decision:
        {
            "symbol": "AAPL",
            "decision": "EXECUTE_BUY",
            "reasoning_chain": [
                "Step 1: ML model predicts BUY with 68% confidence",
                "Step 2: Technical indicators confirm (RSI oversold, MACD bullish)",
                "Step 3: Risk assessment: Account balance sufficient ($5,230)",
                "Step 4: Position sizing: Risk 2% of account = $104.60",
                "Step 5: Stop loss calculation: $150 - 2% = $147",
                "Step 6: Take profit calculation: $150 + 6% = $159",
                "Step 7: Risk/Reward ratio: 3:1 - ACCEPTABLE",
                "Step 8: Daily loss check: $0 / $500 limit - OK",
                "Step 9: Confidence check: 68% >= 60% threshold - PASSED",
                "Step 10: FINAL DECISION: Execute trade"
            ],
            "alternatives_considered": [
                {
                    "option": "WAIT for RSI < 40",
                    "pros": "Stronger oversold signal",
                    "cons": "May miss entry point, price could reverse",
                    "rejected_because": "Current setup already strong, waiting adds risk"
                },
                {
                    "option": "INCREASE position size to 3%",
                    "pros": "Higher profit potential",
                    "cons": "Violates risk management rules",
                    "rejected_because": "Exceeds 2% per-trade risk limit"
                }
            ],
            "confidence_breakdown": {
                "ml_model": 68,
                "technical_confirmation": +10,
                "volume_confirmation": +5,
                "final_confidence": 83
            }
        }
        """
        decision["type"] = "decision"
        decision["symbol"] = symbol
        decision["timestamp"] = datetime.now().isoformat()
        self._save_thought(symbol, "decision", decision)

    def log_execution_thought(self, symbol: str, execution: Dict):
        """
        Log the actual trade execution details

        Example execution:
        {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 7,
            "entry_price": 150.00,
            "stop_loss": 147.00,
            "take_profit": 159.00,
            "order_id": "abc123-456def",
            "execution_timestamp": "2024-01-15 10:24:12",
            "execution_thoughts": {
                "order_type": "MARKET",
                "why_market_order": "Strong signal, immediate execution preferred over price optimization",
                "expected_slippage": "$0.05 max",
                "actual_fill_price": 150.02,
                "slippage_analysis": "Filled $0.02 above target, within acceptable range"
            },
            "position_management": {
                "stop_loss_strategy": "Hard stop at -2%, protects against sudden drops",
                "take_profit_strategy": "Limit order at +6%, locks in gains automatically",
                "monitoring_plan": "Check every 15 minutes for trend changes"
            }
        }
        """
        execution["type"] = "execution"
        execution["symbol"] = symbol
        execution["timestamp"] = datetime.now().isoformat()
        self._save_thought(symbol, "execution", execution)

    def log_monitoring_thought(self, symbol: str, monitoring: Dict):
        """
        Log ongoing position monitoring thoughts

        Example monitoring:
        {
            "symbol": "AAPL",
            "position_status": "ACTIVE",
            "entry_price": 150.00,
            "current_price": 153.50,
            "unrealized_pl": 24.50,
            "unrealized_pl_pct": 2.33,
            "time_in_trade": "2 hours 15 minutes",
            "observations": [
                "Price moved up 2.33%, approaching halfway to take profit target",
                "Volume remains elevated (1.3x average) - institutional interest",
                "RSI now at 55, moved from oversold to neutral - expected",
                "Support held at $152, confirms bullish bias"
            ],
            "risk_assessment": {
                "distance_to_stop": "$6.50 (4.33%)",
                "distance_to_target": "$5.50 (3.67%)",
                "r_r_remaining": "0.85:1",
                "trailing_stop_consideration": "Not yet - need 4% profit to trail stop"
            },
            "potential_actions": [
                {
                    "action": "HOLD",
                    "reasoning": "Trend intact, no reversal signals, let it run to target",
                    "probability": "80%"
                },
                {
                    "action": "PARTIAL_PROFIT",
                    "reasoning": "Lock in 50% at current level, let rest run",
                    "probability": "15%"
                },
                {
                    "action": "CLOSE",
                    "reasoning": "Only if reversal pattern appears",
                    "probability": "5%"
                }
            ]
        }
        """
        monitoring["type"] = "monitoring"
        monitoring["symbol"] = symbol
        monitoring["timestamp"] = datetime.now().isoformat()
        self._save_thought(symbol, "monitoring", monitoring)

    def log_outcome_thought(self, symbol: str, outcome: Dict):
        """
        Log trade outcome and what RUTE learned

        Example outcome (WIN):
        {
            "symbol": "AAPL",
            "trade_id": "abc123-456def",
            "outcome": "WIN",
            "entry_price": 150.00,
            "exit_price": 159.00,
            "exit_reason": "TAKE_PROFIT_HIT",
            "profit_loss": 63.00,
            "profit_loss_pct": 6.00,
            "time_in_trade": "1 day 3 hours",
            "what_worked": [
                "ML prediction was accurate - 68% confidence justified",
                "RSI oversold signal correctly identified reversal",
                "Entry timing was good - caught bounce off SMA 50 support",
                "Risk management worked - 3:1 R:R delivered as planned",
                "Patience paid off - didn't exit early during consolidation"
            ],
            "learning_points": [
                "REINFORCEMENT: RSI 40-45 + SMA support = high probability setup",
                "PATTERN: Similar to trade #142 (GOOGL 2024-01-10) - same pattern",
                "CONFIDENCE_CALIBRATION: 68% ML confidence → 100% win rate (update: trust this level more)",
                "MARKET_REGIME: Uptrend + pullback + support = reliable entry"
            ],
            "model_feedback": {
                "features_that_mattered_most": [
                    {"feature": "rsi_14", "importance": 0.23},
                    {"feature": "volume_ratio", "importance": 0.18},
                    {"feature": "price_to_sma_50", "importance": 0.15}
                ],
                "update_model": "Yes - reinforce this pattern with positive outcome"
            }
        }

        Example outcome (LOSS):
        {
            "symbol": "TSLA",
            "trade_id": "xyz789-012ghi",
            "outcome": "LOSS",
            "entry_price": 220.00,
            "exit_price": 215.60,
            "exit_reason": "STOP_LOSS_HIT",
            "profit_loss": -30.80,
            "profit_loss_pct": -2.00,
            "time_in_trade": "45 minutes",
            "what_went_wrong": [
                "Failed to account for broader market weakness (S&P down 1.2%)",
                "Volume was elevated but it was SELLING volume, not buying",
                "Ignored news: CEO tweet caused negative sentiment spike",
                "ML model missed sector rotation out of tech",
                "Entry was too aggressive - should have waited for confirmation"
            ],
            "mistakes_identified": [
                "MISTAKE #1: Ignored macro market context - S&P weakness",
                "MISTAKE #2: Misinterpreted volume - didn't check buy/sell ratio",
                "MISTAKE #3: News sentiment filter not working - CEO tweet missed",
                "MISTAKE #4: Too quick to execute - should add 15min confirmation delay"
            ],
            "corrective_actions": [
                "ADD FILTER: Check S&P 500 direction before individual stock trades",
                "IMPROVE FEATURE: Add buy/sell volume ratio indicator",
                "INTEGRATE NEWS: Real-time news sentiment check before execution",
                "UPDATE RULE: Require 15-minute price confirmation above entry level",
                "RETRAIN MODEL: Add recent tech sector rotation data"
            ],
            "learning_points": [
                "PATTERN_TO_AVOID: High volume + market weakness = trap, not opportunity",
                "CONFIDENCE_ADJUSTMENT: Reduce confidence when macro diverges from stock signal",
                "RISK_LESSON: Stop loss worked perfectly - kept loss to exactly -2%"
            ],
            "model_feedback": {
                "features_that_failed": [
                    {"feature": "volume_ratio", "actual_importance": 0.18, "should_be": 0.05, "why": "Didn't distinguish buy vs sell volume"},
                    {"feature": "rsi_14", "was_misleading": true, "context": "RSI oversold but market structure was breaking"}
                ],
                "update_model": "Yes - add negative example for this pattern combination"
            }
        }
        """
        outcome["type"] = "outcome"
        outcome["symbol"] = symbol
        outcome["timestamp"] = datetime.now().isoformat()
        self._save_thought(symbol, "outcome", outcome)

        # This is critical - log to learning database
        self._update_learning_database(outcome)

    def get_trade_reasoning_chain(self, symbol: str, trade_id: str) -> List[Dict]:
        """
        Get complete reasoning chain for a specific trade
        Returns: [analysis → decision → execution → monitoring → outcome]
        """
        thoughts = []
        symbol_dir = os.path.join(self.log_dir, symbol)

        if os.path.exists(symbol_dir):
            for filename in sorted(os.listdir(symbol_dir)):
                if trade_id in filename:
                    filepath = os.path.join(symbol_dir, filename)
                    with open(filepath, 'r') as f:
                        thoughts.append(json.load(f))

        return thoughts

    def get_learning_insights(self, days: int = 30) -> Dict:
        """
        Analyze learning from past trades
        """
        insights = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "patterns_learned": [],
            "mistakes_corrected": [],
            "confidence_calibration": {},
            "feature_importance_evolution": {}
        }

        # Scan all outcome logs
        for symbol_dir in os.listdir(self.log_dir):
            outcome_dir = os.path.join(self.log_dir, symbol_dir, "outcome")
            if os.path.exists(outcome_dir):
                for filename in os.listdir(outcome_dir):
                    filepath = os.path.join(outcome_dir, filename)
                    with open(filepath, 'r') as f:
                        outcome = json.load(f)

                    outcome_val = outcome.get("outcome")
                    if outcome_val is None:
                        continue
                    insights["total_trades"] += 1
                    if outcome_val == "WIN":
                        insights["wins"] += 1
                        insights["patterns_learned"].extend(outcome.get("learning_points", []))
                    else:
                        insights["losses"] += 1
                        insights["mistakes_corrected"].extend(outcome.get("corrective_actions", []))

        insights["win_rate"] = (insights["wins"] / insights["total_trades"] * 100) if insights["total_trades"] > 0 else 0

        return insights

    def _save_thought(self, symbol: str, thought_type: str, data: Dict):
        """Save thought to JSONL file (Fix #20)"""
        symbol_dir = os.path.join(self.log_dir, symbol)
        os.makedirs(symbol_dir, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"{symbol}_{thought_type}s_{date_str}.jsonl"
        filepath = os.path.join(symbol_dir, filename)

        with open(filepath, 'a') as f:
            f.write(json.dumps(data) + '\n')

        logger.info(f"💭 Thought logged: {symbol} - {thought_type}")

    def _update_learning_database(self, outcome: Dict):
        """
        Update centralized learning database with outcomes
        This is how RUTE gets smarter over time
        """
        learning_db_path = os.path.join(self.log_dir, "learning_database.json")

        # Load existing database
        if os.path.exists(learning_db_path):
            with open(learning_db_path, 'r') as f:
                learning_db = json.load(f)
        else:
            learning_db = {
                "patterns_learned": [],
                "mistakes_to_avoid": [],
                "confidence_calibration": {},
                "feature_importance": {},
                "winning_setups": [],
                "losing_setups": []
            }

        # Add outcome to database
        if outcome["outcome"] == "WIN":
            learning_db["winning_setups"].append({
                "symbol": outcome["symbol"],
                "pattern": outcome.get("learning_points", []),
                "timestamp": outcome["timestamp"]
            })
        else:
            learning_db["losing_setups"].append({
                "symbol": outcome["symbol"],
                "mistakes": outcome.get("mistakes_identified", []),
                "corrections": outcome.get("corrective_actions", []),
                "timestamp": outcome["timestamp"]
            })

        # Save updated database
        with open(learning_db_path, 'w') as f:
            json.dump(learning_db, f, indent=2)

        logger.info(f"📚 Learning database updated with {outcome['symbol']} outcome")
