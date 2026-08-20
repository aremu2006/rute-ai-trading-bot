"""
Alpaca Broker Integration
Commission-free US stock trading
Sign up: https://alpaca.markets
"""

from typing import Dict, List
import requests
from .broker_interface import BrokerInterface, TradeOrder
import logging

logger = logging.getLogger(__name__)


class AlpacaBroker(BrokerInterface):
    """
    Alpaca API Integration for US Stocks
    - Commission-free trading
    - $0 minimum to start (paper trading)
    - Real-time data and execution
    """

    def __init__(self, api_key: str, api_secret: str, paper_trading: bool = True):
        super().__init__(api_key, api_secret, paper_trading)

        # API endpoints
        if paper_trading:
            self.base_url = "https://paper-api.alpaca.markets"
            self.data_url = "https://data.alpaca.markets"
        else:
            self.base_url = "https://api.alpaca.markets"
            self.data_url = "https://data.alpaca.markets"

        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret
        }

    def connect(self) -> bool:
        """Connect and verify Alpaca API credentials"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=self.headers
            )
            if response.status_code == 200:
                self.connected = True
                account_data = response.json()
                mode = "PAPER" if self.paper_trading else "LIVE"
                logger.info(f"Connected to Alpaca ({mode} trading)")
                logger.info(f"Account Balance: ${account_data['cash']}")
                logger.info(f"Buying Power: ${account_data['buying_power']}")
                return True
            else:
                logger.error(f"Failed to connect to Alpaca: {response.text}")
                return False
        except Exception as e:
            logger.error(f"Alpaca connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from Alpaca"""
        self.connected = False
        logger.info("Disconnected from Alpaca")

    def get_account_balance(self) -> Dict:
        """Get account balance and equity"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/account",
                headers=self.headers
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "balance": float(data["cash"]),
                    "equity": float(data["equity"]),
                    "buying_power": float(data["buying_power"]),
                    "currency": "USD"
                }
            return {}
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {}

    def execute_trade(self, order: TradeOrder) -> Dict:
        """
        Execute trade on Alpaca
        Automatically includes stop loss and take profit orders
        """
        try:
            # Calculate position size based on account balance
            balance = self.get_account_balance()
            buying_power = balance.get("buying_power", 0)

            # Use order quantity or calculate from position size
            qty = round(float(order.quantity), 4)

            # Build order payload
            payload = {
                "symbol": order.symbol,
                "qty": qty,
                "side": order.action.lower(),  # "buy" or "sell"
                "type": order.order_type.lower(),  # "market" or "limit"
                "time_in_force": "gtc",  # Good 'til canceled
            }

            # Add stop loss and take profit as bracket order
            if order.stop_loss and order.take_profit:
                payload["order_class"] = "bracket"
                payload["stop_loss"] = {"stop_price": order.stop_loss}
                payload["take_profit"] = {"limit_price": order.take_profit}

            # Execute order
            response = requests.post(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                json=payload
            )

            if response.status_code == 200:
                result = response.json()
                order.order_id = result["id"]
                order.status = result["status"]

                logger.info(f"✓ Order executed: {order.action} {qty} {order.symbol}")
                logger.info(f"  Order ID: {order.order_id}")
                logger.info(f"  Stop Loss: ${order.stop_loss}")
                logger.info(f"  Take Profit: ${order.take_profit}")

                return {
                    "success": True,
                    "order_id": order.order_id,
                    "status": order.status,
                    "message": f"{order.action} order placed for {order.symbol}"
                }
            else:
                logger.error(f"Order failed: {response.text}")
                return {
                    "success": False,
                    "error": response.text
                }
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return {"success": False, "error": str(e)}

    def get_open_positions(self) -> List[Dict]:
        """Get all open positions"""
        try:
            response = requests.get(
                f"{self.base_url}/v2/positions",
                headers=self.headers
            )
            if response.status_code == 200:
                positions = response.json()
                return [{
                    "position_id": p["asset_id"],
                    "symbol": p["symbol"],
                    "quantity": float(p["qty"]),
                    "side": p["side"],
                    "entry_price": float(p["avg_entry_price"]),
                    "current_price": float(p["current_price"]),
                    "unrealized_pl": float(p["unrealized_pl"]),
                    "unrealized_plpc": float(p["unrealized_plpc"]) * 100
                } for p in positions]
            return []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    def close_position(self, position_id: str) -> bool:
        """Close a specific position"""
        try:
            response = requests.delete(
                f"{self.base_url}/v2/positions/{position_id}",
                headers=self.headers
            )
            if response.status_code == 200:
                logger.info(f"Position {position_id} closed")
                return True
            return False
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    def modify_position(self, position_id: str, stop_loss: float, take_profit: float) -> bool:
        """Modify stop loss and take profit (via new bracket order)"""
        # Alpaca doesn't support modifying existing orders directly
        # Close and reopen with new parameters
        logger.warning("Position modification requires closing and reopening on Alpaca")
        return False
