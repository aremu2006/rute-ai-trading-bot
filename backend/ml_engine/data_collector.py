"""
Historical Data Collection System
Collects 2+ years of historical data for model training
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
import asyncio

class HistoricalDataCollector:
    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def collect_symbol_data(self, symbol: str, period: str = "max") -> pd.DataFrame:
        """
        Collect historical data for a symbol (CCXT for Crypto, yfinance for Stocks/Forex)
        """
        try:
            print(f"Collecting data for {symbol}...")
            if "-" in symbol:
                import ccxt
                exchange = ccxt.binance()
                ccxt_symbol = symbol.replace("-", "/").replace("USD", "USDT")
                if "/" not in ccxt_symbol:
                    ccxt_symbol += "/USDT"
                    
                ohlcv = exchange.fetch_ohlcv(ccxt_symbol, timeframe='1d', limit=1000)
                if not ohlcv:
                    print(f"  No data found for {symbol}")
                    return None
                
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
            else:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period)

            if df.empty:
                print(f"  No data found for {symbol}")
                return None

            print(f"  Collected {len(df)} bars from {df.index[0]} to {df.index[-1]}")
            return df

        except Exception as e:
            print(f"  Error collecting {symbol}: {e}")
            return None

    def collect_multiple_symbols(self, symbols: list, period: str = "max") -> dict:
        """
        Collect data for multiple symbols

        Returns:
            Dictionary of {symbol: DataFrame}
        """
        data_dict = {}

        for symbol in symbols:
            df = self.collect_symbol_data(symbol, period)
            if df is not None and not df.empty:
                data_dict[symbol] = df

        return data_dict

    def save_data(self, symbol: str, df: pd.DataFrame):
        """Save data to CSV file"""
        filepath = os.path.join(self.data_dir, f"{symbol}.csv")
        df.to_csv(filepath)
        print(f"Saved {symbol} data to {filepath}")

    def load_data(self, symbol: str) -> pd.DataFrame:
        """Load data from CSV file"""
        filepath = os.path.join(self.data_dir, f"{symbol}.csv")
        if os.path.exists(filepath):
            return pd.read_csv(filepath, index_col=0, parse_dates=True)
        return None

    def collect_and_save_all(self, symbols: list, period: str = "max"):
        """Collect and save data for all symbols"""
        print(f"\nCollecting {period} of historical data for {len(symbols)} symbols...")
        print("="*60)

        data_dict = self.collect_multiple_symbols(symbols, period)

        for symbol, df in data_dict.items():
            self.save_data(symbol, df)

        print("="*60)
        print(f"Data collection complete. Collected data for {len(data_dict)} symbols.")
        return data_dict



class RealTimeStreamer:
    """Alpaca real-time streamer — requires API keys to use."""
    def __init__(self, api_key: str, secret_key: str, base_url: str = "https://paper-api.alpaca.markets"):
        try:
            from alpaca_trade_api.stream import Stream
            self.stream = Stream(api_key, secret_key, base_url=base_url, data_feed='iex')
        except ImportError:
            self.stream = None
        self.price_cache = {}

    def get_latest_tick(self, symbol: str):
        return self.price_cache.get(symbol)

if __name__ == "__main__":
    # Test data collection
    collector = HistoricalDataCollector()

    # Test symbols - mix of stocks and forex
    symbols = [
        # Stocks
        "AAPL", "TSLA", "GOOGL", "MSFT", "AMZN", "NVDA",
        "META", "NFLX", "AMD", "INTC",
        # Forex
        "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"
    ]

    collector.collect_and_save_all(symbols, period="max")
