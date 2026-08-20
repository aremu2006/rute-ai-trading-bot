"""
Dashboard Backend Endpoints (Upgrade 3)
Provides unified stats, kill switch, and position management across MT5 + Alpaca.
"""
import sqlite3
import logging
from typing import Dict, List, Optional

log = logging.getLogger("ml_engine.dashboard_endpoints")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    mt5 = None


def get_mt5_positions() -> List[dict]:
    """Returns all currently open MT5 positions."""
    if not MT5_AVAILABLE or not mt5.terminal_info():
        return []

    positions = mt5.positions_get()
    if positions is None:
        return []

    result = []
    for pos in positions:
        result.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == 0 else "SELL",
            "volume": pos.volume,
            "entry_price": pos.price_open,
            "current_price": pos.price_current,
            "profit": pos.profit,
            "swap": pos.swap,
            "time": str(pos.time),
            "sl": pos.sl,
            "tp": pos.tp,
            "magic": pos.magic,
        })
    return result


def close_all_mt5() -> dict:
    """Emergency close all MT5 positions."""
    if not MT5_AVAILABLE or not mt5.terminal_info():
        return {"closed": 0, "error": "MT5 not connected"}

    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return {"closed": 0, "message": "No positions to close"}

    closed = 0
    errors = []

    for pos in positions:
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        symbol_info = mt5.symbol_info(pos.symbol)
        if symbol_info is None:
            errors.append(f"Symbol info unavailable for {pos.symbol}")
            continue

        price = mt5.symbol_info_tick(pos.symbol)
        if price is None:
            errors.append(f"No tick for {pos.symbol}")
            continue

        close_price = price.bid if pos.type == 0 else price.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": close_price,
            "deviation": 20,
            "magic": pos.magic,
            "comment": "KILL_SWITCH",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
        else:
            err = result.comment if result else "Unknown error"
            errors.append(f"Failed to close {pos.ticket}: {err}")

    return {"closed": closed, "errors": errors}


def close_all_alpaca(auto_trader) -> dict:
    """Emergency close all Alpaca positions."""
    if auto_trader is None:
        return {"closed": 0, "error": "AutoTrader not running"}

    try:
        # Access the Alpaca broker through auto_trader
        broker = getattr(auto_trader, 'broker', None)
        if broker is None:
            return {"closed": 0, "error": "No broker configured"}

        positions = broker.get_open_positions() if hasattr(broker, 'get_open_positions') else []
        closed = 0
        for pos in positions:
            try:
                position_id = pos.get('position_id') or pos.get('id') or pos.get('symbol')
                if position_id:
                    broker.close_position(position_id)
                    closed += 1
            except Exception as e:
                log.error(f"Failed to close Alpaca position: {e}")

        return {"closed": closed}
    except Exception as e:
        return {"closed": 0, "error": str(e)}


def kill_switch(auto_trader=None) -> dict:
    """
    EMERGENCY: Close ALL positions on ALL markets.
    Also sends Telegram alert.
    """
    mt5_result = close_all_mt5()
    alpaca_result = close_all_alpaca(auto_trader)

    total_closed = mt5_result.get("closed", 0) + alpaca_result.get("closed", 0)

    # Send Telegram notification
    try:
        from .sentiment_hub import sentiment_hub  # avoid circular import
        msg = f"🚨 KILL SWITCH ACTIVATED 🚨\nMT5 closed: {mt5_result.get('closed', 0)}\nAlpaca closed: {alpaca_result.get('closed', 0)}\nTotal: {total_closed}"
        # Use notifications module
        from ..mt5_engine.notifications import send_telegram
        send_telegram(msg)
    except Exception:
        pass

    log.warning(f"[KILL SWITCH] Closed {total_closed} positions across all markets")

    return {
        "mt5": mt5_result,
        "alpaca": alpaca_result,
        "total_closed": total_closed,
        "status": "all_positions_closed",
    }


def get_combined_stats(mt5_db_path: str = None, alpaca_trades: list = None) -> dict:
    """Get combined trading statistics across both markets."""
    stats = {
        "mt5": {"total_pnl": 0.0, "win_rate": 0.0, "trade_count": 0, "open_positions": 0},
        "alpaca": {"total_pnl": 0.0, "win_rate": 0.0, "trade_count": 0, "open_positions": 0},
        "combined": {"total_pnl": 0.0, "win_rate": 0.0, "trade_count": 0},
    }

    # MT5 stats from database
    if mt5_db_path:
        conn = None
        try:
            conn = sqlite3.connect(mt5_db_path)
            cur = conn.cursor()
            cur.execute("SELECT SUM(pnl), COUNT(*) FROM trade_history WHERE exit_price IS NOT NULL")
            row = cur.fetchone()
            if row and row[0] is not None:
                stats["mt5"]["total_pnl"] = round(row[0], 2)
                stats["mt5"]["trade_count"] = row[1]

            cur.execute("SELECT COUNT(*) FROM trade_history WHERE exit_price IS NOT NULL AND outcome='WIN'")
            wins = cur.fetchone()[0]
            if stats["mt5"]["trade_count"] > 0:
                stats["mt5"]["win_rate"] = round(wins / stats["mt5"]["trade_count"], 4)
        except Exception as e:
            log.error(f"MT5 stats error: {e}")
        finally:
            if conn is not None:
                conn.close()

    # MT5 open positions
    if MT5_AVAILABLE and mt5.terminal_info():
        positions = mt5.positions_get()
        stats["mt5"]["open_positions"] = len(positions) if positions else 0

    # Alpaca stats
    if alpaca_trades:
        for trade in alpaca_trades:
            stats["alpaca"]["total_pnl"] += trade.get("pnl", 0)
            stats["alpaca"]["trade_count"] += 1
            if trade.get("outcome") == "WIN":
                stats["alpaca"]["win_rate"] += 1

        if stats["alpaca"]["trade_count"] > 0:
            stats["alpaca"]["win_rate"] = round(
                stats["alpaca"]["win_rate"] / stats["alpaca"]["trade_count"], 4
            )
        stats["alpaca"]["total_pnl"] = round(stats["alpaca"]["total_pnl"], 2)

    # Combined
    total_trades = stats["mt5"]["trade_count"] + stats["alpaca"]["trade_count"]
    stats["combined"]["total_pnl"] = round(
        stats["mt5"]["total_pnl"] + stats["alpaca"]["total_pnl"], 2
    )
    stats["combined"]["trade_count"] = total_trades
    if total_trades > 0:
        weighted_wr = (
            stats["mt5"]["win_rate"] * stats["mt5"]["trade_count"]
            + stats["alpaca"]["win_rate"] * stats["alpaca"]["trade_count"]
        ) / total_trades
        stats["combined"]["win_rate"] = round(weighted_wr, 4)

    return stats
