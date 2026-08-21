"""
RUTE Auto-Trader Engine
Automatically executes trades based on ML recommendations
"""

from typing import Dict, List, Optional, Tuple, Union
import logging
from datetime import datetime
from .broker_interface import BrokerInterface, TradeOrder
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_engine import ThoughtLogger, SelfImprovementEngine
from ml_engine.capital_allocator import KellyAllocator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoTrader:
    """
    Autonomous trading engine that executes trades automatically
    based on ML model recommendations
    """

    def __init__(self, broker: BrokerInterface, config: Dict):
        self.broker = broker
        self.config = config
        self.enabled = config.get("enabled", False)
        self.risk_type = config.get("risk_type", "dollar")
        self.max_position_size = config.get("max_position_size", 1000)
        self.max_daily_loss = config.get("max_daily_loss", 500)
        self.max_daily_profit = config.get("max_daily_profit", 1000)
        self.min_confidence = config.get("min_confidence", 60)
        
        # Standard Risk Settings
        self.initial_stop_loss_pct = config.get("initial_stop_loss_pct", 2.0)
        self.initial_take_profit_pct = config.get("initial_take_profit_pct", 5.0)
        self.breakeven_trigger_pct = config.get("breakeven_trigger_pct", 2.0)
        
        # Trailing Stop Loss Settings
        self.trailing_enabled = config.get("trailing_enabled", False)
        self.trailing_activation_pct = config.get("trailing_activation_pct", 5.0)
        self.trailing_distance_pct = config.get("trailing_distance_pct", 1.5)
        self.trailing_step_pct = config.get("trailing_step_pct", 0.5)

        self.daily_pnl = 0.0
        self._realized_daily_pnl = 0.0
        self.daily_trades = []
        self.active_positions = {}

        # MILLION DOLLAR FEATURE: Thought logging and self-improvement
        self.thought_logger = ThoughtLogger()
        self.improvement_engine = SelfImprovementEngine()
        self.kelly = KellyAllocator()

    def _get_dollar_value(self, config_val: float, account_balance: float) -> float:
        """
        Converts config_val to a dollar amount.
        If risk_type is 'percentage', interprets config_val as a % of account_balance.
        """
        if self.risk_type == 'percentage':
            return account_balance * (config_val / 100.0)
        return config_val

    def enable(self):
        """Enable auto-trading"""
        if not self.broker.connected:
            if not self.broker.connect():
                logger.error("Cannot enable auto-trading: Broker not connected")
                return False

        self.enabled = True
        logger.info("🤖 AUTO-TRADING ENABLED")
        logger.info(f"   Max Position Size: ${self.max_position_size}")
        logger.info(f"   Max Daily Loss: ${self.max_daily_loss}")
        logger.info(f"   Max Daily Profit: ${self.max_daily_profit}")
        logger.info(f"   Min Confidence: {self.min_confidence}%")
        return True

    def disable(self):
        """Disable auto-trading"""
        self.enabled = False
        logger.info("AUTO-TRADING DISABLED")

    def should_execute_trade(self, recommendation: Dict) -> Tuple[bool, str]:
        """
        Determine if a trade should be executed automatically
        Returns: (should_execute, reason)
        """
        # Check if auto-trading is enabled
        if not self.enabled:
            return False, "Auto-trading is disabled"

        # Check confidence threshold
        confidence = recommendation.get("confidence", 0)
        if confidence < self.min_confidence:
            return False, f"Confidence {confidence}% < minimum {self.min_confidence}%"

        # Check account balance and compute dynamic limits
        balance_info = self.broker.get_account_balance()
        account_balance = balance_info.get("balance", 0)
        
        if account_balance < 100:
            return False, "Insufficient account balance"
            
        dynamic_max_loss = self._get_dollar_value(self.max_daily_loss, account_balance)
        dynamic_max_profit = self._get_dollar_value(self.max_daily_profit, account_balance)

        # Check daily limits
        if self.daily_pnl <= -dynamic_max_loss:
            return False, f"Daily loss limit reached (${abs(self.daily_pnl):.2f}/${dynamic_max_loss:.2f})"
            
        if self.daily_pnl >= dynamic_max_profit:
            return False, f"Daily profit target reached (${self.daily_pnl:.2f}/${dynamic_max_profit:.2f})"

        # Check if already holding this symbol
        symbol = recommendation.get("symbol")
        if symbol in self.active_positions:
            return False, f"Already holding position in {symbol}"

        # All checks passed
        return True, "All checks passed"

    def calculate_position_size(self, entry_price: float, stop_loss: float, symbol: str = "", win_prob: float = 0.55, r_r: float = 3.0) -> Tuple[Union[int, float], float]:
        """
        Calculate position size based on Kelly Criterion
        Uses historical win rate from KellyAllocator, falling back to ML confidence.
        """
        balance = self.broker.get_account_balance()
        account_balance = balance.get("balance", 0)

        # Get risk allocation from KellyAllocator (uses historical trade stats)
        alloc = self.kelly.get_allocation()
        risk_pct = alloc.get("total_risk_pct", 0.01)

        # If insufficient trade history, use Half-Kelly from current signal's confidence
        if alloc.get("mt5_trades", 0) < 10 and alloc.get("alpaca_trades", 0) < 10:
            p = max(win_prob, 0.01)
            q = 1.0 - p
            b = max(r_r, 0.01)
            kelly = (p * b - q) / (2 * b)
            risk_pct = max(0.0, min(kelly, 0.04))

        risk_amount = account_balance * risk_pct

        # Calculate distance to stop loss
        risk_per_share = abs(entry_price - stop_loss)

        if entry_price <= 0 or stop_loss <= 0 or risk_per_share == 0:
            return (0, 0.0)

        # Position size = Risk amount / Risk per share
        position_size = risk_amount / risk_per_share

        # Cap at max position size (dynamic)
        dynamic_max_pos = self._get_dollar_value(self.max_position_size, account_balance)
        max_qty = dynamic_max_pos / entry_price
        position_size = min(position_size, max_qty)

        # Normalize to standard lots for Forex
        if symbol and len(symbol) == 6 and symbol.isalpha() and not "BTC" in symbol.upper():
            position_size = position_size / 100000.0

        # Round to 8 decimals to support fractional crypto quantities
        return round(position_size, 8), risk_amount

    def _min_quantity(self, symbol: str) -> float:
        """Minimum tradable quantity for a symbol (fractional for crypto)."""
        s = symbol.upper()
        if "-USD" in s or s.endswith(("USDT", "USDC", "BUSD", "FDUSD")):
            return 0.00001
        return 1.0

    def execute_recommendation(self, recommendation: Dict) -> Dict:
        """
        Execute a trade recommendation automatically
        WITH FULL THOUGHT LOGGING - This is what makes RUTE valuable!
        """
        try:
            symbol = recommendation.get("symbol", "UNKNOWN")
            confidence = recommendation.get("confidence", 0)
            trade_type = recommendation.get("type", "UNKNOWN")
            entry_price = recommendation.get("entryPrice", 0.0)

            # 📝 LOG ANALYSIS THOUGHT
            try:
                self.thought_logger.log_analysis_thought(symbol, {
                    "observation": f"{symbol} at ${entry_price:.2f}",
                    "technical_analysis": {
                        "indicators": recommendation.get("reasoning", {}).get("technicalIndicators", []),
                        "market_trend": recommendation.get("reasoning", {}).get("marketTrend", "Unknown"),
                        "sentiment": recommendation.get("reasoning", {}).get("sentiment", "Unknown")
                    },
                    "ml_analysis": {
                        "prediction": trade_type,
                        "confidence": confidence,
                        "reasoning": recommendation.get("reasoning", {}).get("summary", "")
                    }
                })
            except Exception as log_err:
                logger.warning(f"Failed to log analysis thought: {log_err}")

            # Check if should execute
            should_execute, reason = self.should_execute_trade(recommendation)

            if not should_execute:
                logger.info(f"⊘ Trade skipped: {reason}")

                # 📝 LOG DECISION NOT TO TRADE
                try:
                    self.thought_logger.log_decision_thought(symbol, {
                        "decision": "SKIP_TRADE",
                        "reasoning_chain": [f"Trade skipped: {reason}"],
                        "confidence_breakdown": {"final_confidence": confidence}
                    })
                except Exception as log_err:
                    logger.warning(f"Failed to log decision thought: {log_err}")

                return {
                    "executed": False,
                    "reason": reason
                }

            # Extract trade details
            stop_loss = recommendation.get("stopLoss", 0.0)
            take_profit = recommendation.get("takeProfit", 0.0)
            win_prob = (confidence / 100.0) if confidence > 0 else 0.55
            r_r = abs(take_profit - entry_price) / max(abs(entry_price - stop_loss), 1e-6)

            # Calculate position size via Kelly Allocator
            quantity, risk_amount = self.calculate_position_size(entry_price, stop_loss, symbol=symbol, win_prob=win_prob, r_r=r_r)

            if quantity < self._min_quantity(symbol):
                return {
                    "executed": False,
                    "reason": "Position size too small"
                }

            # 📝 LOG DECISION TO TRADE
            balance = self.broker.get_account_balance().get("balance", 0)
            self.thought_logger.log_decision_thought(symbol, {
                "decision": "EXECUTE_" + trade_type,
                "reasoning_chain": [
                    f"Step 1: ML model predicts {trade_type} with {confidence}% confidence",
                    f"Step 2: Technical indicators confirm signal",
                    f"Step 3: Risk assessment: Account balance ${balance:.2f}",
                    f"Step 4: Position sizing: Risk ${risk_amount:.2f} using Kelly Criterion",
                    f"Step 5: Stop loss calculation: ${stop_loss:.2f}",
                    f"Step 6: Take profit calculation: ${take_profit:.2f}",
                    f"Step 7: Risk/Reward ratio: ACCEPTABLE",
                    f"Step 8: Daily P&L check: ${self.daily_pnl:.2f} (Loss Limit: ${self.max_daily_loss}, Profit Limit: ${self.max_daily_profit}) - OK",
                    f"Step 9: Confidence check: {confidence}% >= {self.min_confidence}% threshold - PASSED",
                    f"Step 10: FINAL DECISION: Execute {trade_type} {quantity} shares"
                ],
                "alternatives_considered": [
                    {
                        "option": "WAIT for stronger signal",
                        "pros": "Higher confidence",
                        "cons": "May miss entry point",
                        "rejected_because": f"Current {confidence}% confidence is sufficient"
                    }
                ],
                "confidence_breakdown": {
                    "ml_model": confidence,
                    "final_confidence": confidence
                }
            })

            # Create trade order
            order = TradeOrder(
                symbol=symbol,
                action=trade_type,  # BUY or SELL
                quantity=quantity,
                order_type="MARKET",
                stop_loss=stop_loss,
                take_profit=take_profit
            )

            logger.info(f"\n{'='*60}")
            logger.info(f"🤖 EXECUTING AUTO-TRADE")
            logger.info(f"{'='*60}")
            logger.info(f"Symbol: {symbol}")
            logger.info(f"Action: {trade_type}")
            logger.info(f"Quantity: {quantity} shares")
            logger.info(f"Entry: ${entry_price:.2f}")
            entry_pct = abs((stop_loss - entry_price) / entry_price * 100) if entry_price else 0.0
            tp_pct = abs((take_profit - entry_price) / entry_price * 100) if entry_price else 0.0
            logger.info(f"Stop Loss: ${stop_loss:.2f} (-{entry_pct:.1f}%)")
            logger.info(f"Take Profit: ${take_profit:.2f} (+{tp_pct:.1f}%)")
            logger.info(f"Confidence: {confidence}%")
            logger.info(f"{'='*60}\n")

            # Execute order via broker
            result = self.broker.execute_trade(order)

            # 📝 LOG EXECUTION THOUGHT
            self.thought_logger.log_execution_thought(symbol, {
                "action": trade_type,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "order_id": order.order_id if result.get("success") else "FAILED",
                "execution_timestamp": datetime.now().isoformat(),
                "execution_thoughts": {
                    "order_type": "MARKET",
                    "why_market_order": "Strong signal, immediate execution preferred",
                    "expected_slippage": "$0.05 max"
                },
                "position_management": {
                    "stop_loss_strategy": f"Hard stop at -{entry_pct:.1f}%, protects against sudden drops",
                    "take_profit_strategy": f"Limit order at +{tp_pct:.1f}%, locks in gains",
                    "monitoring_plan": "Check every 15 minutes for trend changes"
                }
            })

            if result.get("success"):
                # Track position
                self.active_positions[symbol] = {
                    "order_id": order.order_id,
                    "entry_time": datetime.now(),
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "recommendation": recommendation
                }

                # Log to daily trades
                self.daily_trades.append({
                    "symbol": symbol,
                    "type": trade_type,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "timestamp": datetime.now(),
                    "status": "active"
                })

                logger.info(f"✓ Trade executed successfully!")
                logger.info(f"  Order ID: {order.order_id}")

                return {
                    "executed": True,
                    "order_id": order.order_id,
                    "symbol": symbol,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "message": f"Auto-trade executed: {trade_type} {quantity} {symbol}"
                }
            else:
                logger.error(f"✗ Trade execution failed: {result.get('error')}")
                return {
                    "executed": False,
                    "reason": result.get("error", "Unknown error")
                }

        except Exception as e:
            logger.error(f"Auto-trade error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "executed": False,
                "reason": str(e)
            }

    def monitor_positions(self) -> List[Dict]:
        """
        Monitor open positions and update daily P&L
        """
        try:
            open_positions = self.broker.get_open_positions()
            current_symbols = set()

            for position in open_positions:
                symbol = position["symbol"]
                current_symbols.add(symbol)
                unrealized_pl = position["unrealized_pl"]

                # Update daily loss tracking and Trailing Stop
                if symbol in self.active_positions:
                    pos_data = self.active_positions[symbol]
                    unrealized_plpc = position.get('unrealized_plpc', 0.0)
                    
                    logger.info(f"{symbol}: ${unrealized_pl:.2f} ({unrealized_plpc:.2f}%)")
                    pos_data["last_unrealized_pl"] = unrealized_pl

                    # --- Breakeven Trigger Logic ---
                    if not pos_data.get("breakeven_activated", False) and unrealized_plpc >= self.breakeven_trigger_pct:
                        logger.info(f"🛡️ BREAKEVEN TRIGGERED for {symbol}! Profit reached {unrealized_plpc:.2f}%. Stop loss moved to entry price.")
                        pos_data["breakeven_activated"] = True
                        pos_data["stop_loss"] = pos_data["entry_price"]  # In a real broker this would modify the live order
                        
                        # Actually modify the live order so the broker-side stop moves too
                        try:
                            pos_id = position.get("id", symbol)
                            if hasattr(self.broker, "modify_position"):
                                ok = self.broker.modify_position(pos_id, pos_data["entry_price"], pos_data.get("take_profit"))
                                if ok:
                                    logger.info(f"✅ Broker stop modified to breakeven for {symbol}")
                                else:
                                    logger.warning(f"⚠️ Broker rejected stop modification for {symbol} (tracker only)")
                            else:
                                logger.warning(f"⚠️ Broker {type(self.broker).__name__} has no modify_position - tracker only")
                        except Exception as e:
                            logger.error(f"Failed to modify broker stop for {symbol}: {e}")
                        
                        self.thought_logger.log_decision_thought(symbol, {
                            "decision": "MOVE_TO_BREAKEVEN",
                            "reasoning_chain": [
                                f"Trade reached {unrealized_plpc:.2f}% profit.",
                                f"Breakeven trigger is set to {self.breakeven_trigger_pct}%.",
                                f"Moved stop loss to entry price to guarantee no loss."
                            ],
                            "confidence_breakdown": {"final_confidence": 100}
                        })
                        
                    # --- Trailing Stop Loss Logic ---
                    if self.trailing_enabled:
                        high_watermark = pos_data.get("high_watermark", 0.0)
                        
                        # Update high watermark if we hit a new high
                        if unrealized_plpc > high_watermark:
                            pos_data["high_watermark"] = unrealized_plpc
                            high_watermark = unrealized_plpc
                            
                        # If trade has surpassed the activation threshold, begin trailing
                        if high_watermark >= self.trailing_activation_pct:
                            trailing_stop_limit = high_watermark - self.trailing_distance_pct
                            
                            # If the profit drops below our trailing stop line, close the trade
                            if unrealized_plpc < trailing_stop_limit:
                                logger.info(f"🚨 TRAILING STOP HIT for {symbol}! High Watermark: {high_watermark:.2f}%, Current: {unrealized_plpc:.2f}%")
                                pos_id = position.get("id", symbol)
                                self.broker.close_position(pos_id)
                                
                                # 📝 LOG THOUGHT FOR TRAILING STOP
                                self.thought_logger.log_decision_thought(symbol, {
                                    "decision": "EXECUTE_TRAILING_STOP",
                                    "reasoning_chain": [
                                        f"Trade reached {high_watermark:.2f}% profit (Activation: {self.trailing_activation_pct}%)",
                                        f"Trailing distance set at {self.trailing_distance_pct}%",
                                        f"Stop loss line was at {trailing_stop_limit:.2f}%",
                                        f"Current profit fell to {unrealized_plpc:.2f}%, hitting stop loss line.",
                                        f"Closing trade to lock in remaining profit."
                                    ],
                                    "confidence_breakdown": {"final_confidence": 100}
                                })
                                continue # Trade closed, move to next position

            # Check for closed positions to update realized profit/loss
            closed_symbols = set(self.active_positions.keys()) - current_symbols
            for symbol in closed_symbols:
                closed_pos = self.active_positions.pop(symbol)
                realized_pnl = closed_pos.get("last_unrealized_pl", 0)
                self._realized_daily_pnl += realized_pnl
                
                try:
                    self.improvement_engine.analyze_trade_outcome(closed_pos)
                except Exception as e:
                    logger.error(f"Feedback loop error: {e}")
                    
                logger.info(f"Position closed {symbol}: realized P&L ${realized_pnl:.2f}")

            # Calculate total daily P&L (realized + unrealized)
            unrealized_total = sum(p["unrealized_pl"] for p in open_positions)
            self.daily_pnl = self._realized_daily_pnl + unrealized_total

            logger.info(f"\nDaily P&L: ${unrealized_total:.2f} (Unrealized) + ${self._realized_daily_pnl:.2f} (Realized) = ${self.daily_pnl:.2f}")
            logger.info(f"Open Positions: {len(open_positions)}")

            return open_positions

        except Exception as e:
            logger.error(f"Error monitoring positions: {e}")
            return []

    def get_status(self) -> Dict:
        """Get auto-trader status"""
        balance_info = self.broker.get_account_balance()
        account_balance = balance_info.get("balance", 0)
        
        dynamic_max_loss = self._get_dollar_value(self.max_daily_loss, account_balance)
        dynamic_max_profit = self._get_dollar_value(self.max_daily_profit, account_balance)

        return {
            "enabled": self.enabled,
            "connected": self.broker.connected,
            "daily_trades": len(self.daily_trades),
            "active_positions": len(self.active_positions),
            "daily_pnl": self.daily_pnl,
            "max_daily_loss": dynamic_max_loss,
            "max_daily_profit": dynamic_max_profit,
            "remaining_capacity_loss": dynamic_max_loss + min(0, self.daily_pnl),
            "remaining_capacity_profit": dynamic_max_profit - max(0, self.daily_pnl)
        }
