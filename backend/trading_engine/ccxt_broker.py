import logging
import ccxt
from typing import Dict, List
from .broker_interface import BrokerInterface, TradeOrder

logger = logging.getLogger(__name__)

class CCXTBroker(BrokerInterface):
    """CCXT universal crypto broker integration"""
    
    def __init__(self, api_key: str, api_secret: str, api_server: str = "binance", paper_trading: bool = True):
        super().__init__(api_key, api_secret, paper_trading)
        self.exchange_name = api_server.lower() if api_server else "binance"
        self.exchange = None
        
    def connect(self) -> bool:
        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            self.exchange = exchange_class({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot'
                }
            })
            
            if self.paper_trading:
                if 'test' in self.exchange.urls:
                    self.exchange.set_sandbox_mode(True)
                else:
                    logger.warning(f"Sandbox mode not supported by CCXT for {self.exchange_name}")

            self.exchange.load_markets()
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"CCXT connection failed: {str(e)}")
            self.connected = False
            return False
            
    def disconnect(self):
        self.connected = False
        
    def get_account_balance(self) -> Dict:
        if not self.connected:
            self.connect()
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {})
            return {
                "balance": usdt_balance.get('total', 0.0),
                "equity": usdt_balance.get('total', 0.0),
                "currency": "USDT"
            }
        except Exception as e:
            logger.error(f"Failed to fetch balance: {str(e)}")
            return {"balance": 0.0, "equity": 0.0, "currency": "USD"}
            
    def execute_trade(self, order: TradeOrder) -> Dict:
        if not self.connected:
            self.connect()
        try:
            symbol = order.symbol
            if not '/' in symbol:
                if symbol.endswith('USDT'):
                    symbol = symbol[:-4] + '/USDT'
                elif symbol.endswith('USD'):
                    symbol = symbol[:-3] + '/USD'

            side = 'buy' if order.action == 'BUY' else 'sell'
            result = self.exchange.create_market_order(symbol, side, order.quantity)
            
            order.order_id = result['id']
            order.status = "filled"
            
            return {"success": True, "order_id": order.order_id, "filled_price": result.get('price', 0.0)}
        except Exception as e:
            logger.error(f"CCXT Trade failed: {str(e)}")
            return {"success": False, "error": str(e)}
            
    def get_open_positions(self) -> List[Dict]:
        return []
        
    def close_position(self, position_id: str) -> bool:
        return False
        
    def modify_position(self, position_id: str, stop_loss: float, take_profit: float) -> bool:
        return False
