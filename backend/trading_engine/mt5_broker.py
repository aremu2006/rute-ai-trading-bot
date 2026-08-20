import logging
import MetaTrader5 as mt5
from typing import Dict, Optional, List
from .broker_interface import BrokerInterface, TradeOrder

logger = logging.getLogger(__name__)

class MT5Broker(BrokerInterface):
    """MetaTrader 5 broker integration"""
    
    def __init__(self, api_key: str, api_secret: str, api_server: str = "", terminal_path: str = "", paper_trading: bool = True):
        # api_key is login (int), api_secret is password, api_server is server
        super().__init__(api_key, api_secret, paper_trading)
        self.api_server = api_server
        self.terminal_path = terminal_path
        self.login = int(api_key) if api_key.isdigit() else 0
        self.password = api_secret
        
    def connect(self) -> bool:
        if self.terminal_path:
            init_success = mt5.initialize(path=self.terminal_path)
        else:
            init_success = mt5.initialize()

        if not init_success:
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
            
        # Try logging in if credentials are provided
        if self.login > 0 and self.password and self.api_server:
            authorized = mt5.login(self.login, password=self.password, server=self.api_server)
            if not authorized:
                logger.error(f"MT5 login failed: {mt5.last_error()}")
                self.connected = False
                return False
                
        self.connected = True
        return True
        
    def disconnect(self):
        mt5.shutdown()
        self.connected = False
        
    def get_account_balance(self) -> Dict:
        if not self.connected:
            self.connect()
        acc = mt5.account_info()
        if not acc:
            return {"balance": 0.0, "equity": 0.0, "currency": "USD"}
        return {
            "balance": acc.balance,
            "equity": acc.equity,
            "currency": acc.currency
        }
        
    def execute_trade(self, order: TradeOrder) -> Dict:
        if not self.connected:
            self.connect()
            
        symbol = order.symbol.replace("-", "").replace("=X", "")
        
        # Ensure symbol is visible
        if not mt5.symbol_select(symbol, True):
            return {"success": False, "error": f"Symbol {symbol} not found"}
            
        symbol_info = mt5.symbol_info(symbol)
        if not symbol_info:
            return {"success": False, "error": f"Failed to get info for {symbol}"}
            
        order_type = mt5.ORDER_TYPE_BUY if order.action == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return {"success": False, "error": f"Failed to get ticks for {symbol}"}
            
        price = tick.ask if order.action == "BUY" else tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(order.quantity),
            "type": order_type,
            "price": price,
            "sl": float(order.stop_loss),
            "tp": float(order.take_profit),
            "deviation": 20,
            "magic": 234000,
            "comment": "RUTE AI Auto-Trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "Unknown error"
            return {"success": False, "error": f"Order failed: {err}"}
            
        order.order_id = str(result.order)
        order.status = "filled"
        return {"success": True, "order_id": order.order_id, "filled_price": result.price}
        
    def get_open_positions(self) -> List[Dict]:
        if not self.connected:
            self.connect()
        positions = mt5.positions_get()
        if not positions:
            return []
            
        return [{
            "id": str(p.ticket),
            "symbol": p.symbol,
            "side": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "quantity": p.volume,
            "entry_price": p.price_open,
            "current_price": p.price_current,
            "profit": p.profit,
            "unrealized_pl": p.profit,
            "unrealized_plpc": (p.profit / (p.price_open * p.volume)) * 100 if p.price_open > 0 else 0,
            "stop_loss": p.sl,
            "take_profit": p.tp
        } for p in positions]
        
    def close_position(self, position_id: str) -> bool:
        if not self.connected:
            self.connect()
        pos = mt5.positions_get(ticket=int(position_id))
        if not pos:
            return False
        p = pos[0]
        
        tick = mt5.symbol_info_tick(p.symbol)
        if not tick: return False
        
        order_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
        
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": order_type,
            "position": p.ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": "RUTE AI Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    def modify_position(self, position_id: str, stop_loss: float, take_profit: float) -> bool:
        if not self.connected:
            self.connect()
            
        pos = mt5.positions_get(ticket=int(position_id))
        if not pos:
            return False
            
        p = pos[0]
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": p.symbol,
            "position": p.ticket,
            "sl": float(stop_loss),
            "tp": float(take_profit),
        }
        res = mt5.order_send(req)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
