import time
import copy
import logging
import threading
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SynchronizedCache:
    """
    Thread-safe synchronized cache using threading.RLock.
    Guarantees thread-safe reads, writes, expirations, and defensive copying
    to prevent concurrent mutations across worker threads.
    """
    def __init__(self, ttl: float, max_entries: int = 500):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._ttl = ttl
        self._max_entries = max_entries

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a defensive copy of cached data if present and unexpired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry.get("timestamp", 0) > self._ttl:
                self._cache.pop(key, None)
                return None
            data = entry.get("data")
            if isinstance(data, pd.DataFrame):
                return data.copy(deep=True)
            elif isinstance(data, dict):
                return copy.deepcopy(data)
            elif isinstance(data, list):
                return copy.deepcopy(data)
            return data

    def set(self, key: str, data: Any, timestamp: Optional[float] = None) -> None:
        """Store a defensive copy of data in the cache with timestamp."""
        with self._lock:
            if len(self._cache) >= self._max_entries:
                self._sweep_locked()
            ts = timestamp if timestamp is not None else time.time()
            data_to_store = (
                data.copy(deep=True) if isinstance(data, pd.DataFrame)
                else copy.deepcopy(data) if isinstance(data, (dict, list))
                else data
            )
            self._cache[key] = {"timestamp": ts, "data": data_to_store}

    def contains(self, key: str) -> bool:
        """Check if a valid unexpired key exists in the cache."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if time.time() - entry.get("timestamp", 0) > self._ttl:
                self._cache.pop(key, None)
                return False
            return True

    def pop(self, key: str, default=None) -> Any:
        """Atomically remove and return an entry from cache."""
        with self._lock:
            entry = self._cache.pop(key, None)
            if entry is None:
                return default
            data = entry.get("data")
            return (
                data.copy(deep=True) if isinstance(data, pd.DataFrame)
                else copy.deepcopy(data) if isinstance(data, (dict, list))
                else data
            )

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()

    def _sweep_locked(self) -> None:
        """Internal sweep helper when lock is already acquired."""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now - v.get("timestamp", 0) > self._ttl]
        for k in expired:
            self._cache.pop(k, None)
        if len(self._cache) >= self._max_entries:
            sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k].get("timestamp", 0))
            for k in sorted_keys[:max(1, len(self._cache) - self._max_entries + 10)]:
                self._cache.pop(k, None)

    def sweep(self) -> None:
        """Drop expired entries safely."""
        with self._lock:
            self._sweep_locked()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        return self.contains(key)

    def __getitem__(self, key: str) -> Dict[str, Any]:
        with self._lock:
            val = self.get(key)
            if val is None:
                raise KeyError(key)
            entry = self._cache.get(key)
            return {"timestamp": entry.get("timestamp", 0), "data": val}

    def __setitem__(self, key: str, value: Any) -> None:
        if isinstance(value, dict) and "data" in value:
            self.set(key, value["data"], value.get("timestamp"))
        else:
            self.set(key, value)


class YahooCircuitBreaker:
    """
    Circuit breaker with exponential backoff for unauthenticated Yahoo Finance requests.
    Prevents threadpool starvation and repetitive HTTP 429 timeouts when rate-limited.
    """
    def __init__(self, failure_threshold: int = 3, base_cooldown: float = 30.0, max_cooldown: float = 300.0):
        self._lock = threading.RLock()
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._base_cooldown = base_cooldown
        self._max_cooldown = max_cooldown
        self._cooldown_until = 0.0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN

    def allow_request(self) -> bool:
        with self._lock:
            now = time.time()
            if self._state == "OPEN":
                if now >= self._cooldown_until:
                    self._state = "HALF-OPEN"
                    logger.info("Yahoo Circuit Breaker transitioned to HALF-OPEN (probing single request)")
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            if self._failure_count > 0 or self._state != "CLOSED":
                logger.info("Yahoo Circuit Breaker restored to CLOSED on successful response")
            self._failure_count = 0
            self._state = "CLOSED"
            self._cooldown_until = 0.0

    def record_failure(self, status_code: Optional[int] = None) -> None:
        with self._lock:
            self._failure_count += 1
            if status_code == 429 or self._failure_count >= self._failure_threshold:
                self._state = "OPEN"
                backoff_factor = min(self._failure_count - self._failure_threshold, 4)
                cooldown = min(self._base_cooldown * (2 ** max(backoff_factor, 0)), self._max_cooldown)
                self._cooldown_until = time.time() + cooldown
                logger.warning(
                    f"Yahoo Circuit Breaker OPEN (failures={self._failure_count}, status={status_code}). "
                    f"Cooling down for {cooldown:.1f}s until {time.strftime('%H:%M:%S', time.localtime(self._cooldown_until))}"
                )


# Cache TTLs
REALTIME_TTL = 60  # 60 seconds
HISTORICAL_TTL = 4 * 3600  # 4 hours

# Module-level Thread-Safe Synchronized Caches & Circuit Breaker
_realtime_cache = SynchronizedCache(ttl=REALTIME_TTL, max_entries=500)
_historical_cache = SynchronizedCache(ttl=HISTORICAL_TTL, max_entries=500)
_missing_keys_warned = set()
_yahoo_circuit_breaker = YahooCircuitBreaker(failure_threshold=3, base_cooldown=30.0, max_cooldown=300.0)


def _sweep_cache(cache: Any, ttl: int) -> None:
    """Drop expired entries safely (supports both SynchronizedCache and plain dict)."""
    if isinstance(cache, SynchronizedCache):
        cache.sweep()
    elif isinstance(cache, dict):
        now = time.time()
        expired = [k for k, v in cache.items() if now - v.get('timestamp', 0) > ttl]
        for k in expired:
            cache.pop(k, None)

_CRYPTO_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD", "DAI", "BTC", "ETH", "BNB")
_CRYPTO_QUOTES_HYPHEN = _CRYPTO_QUOTES + ("EUR", "TRY")

def _is_crypto(symbol: str) -> bool:
    """Check if a symbol is a crypto symbol (supports -USD, ETH-EUR, BTCUSDT forms)."""
    if "-USD" in symbol:
        return True
    if "=X" in symbol or "/" in symbol:
        return False
    if "-" in symbol:
        base, quote = symbol.split("-", 1)
        return bool(base) and base.isalnum() and quote in _CRYPTO_QUOTES_HYPHEN
    base = symbol.upper()
    # 6-char pure-alpha codes are forex conventions (EURUSD), 7+ char with a
    # known quote suffix are crypto pairs (BTCUSDT, SOLUSDT, ETHEUR...).
    return len(base) >= 7 and base.isalnum() and base.endswith(_CRYPTO_QUOTES)

def _format_binance_symbol(symbol: str) -> str:
    """Format symbol for Binance API (e.g., BTC-USD -> BTCUSDT, ETH-EUR -> ETHEUR)."""
    symbol = symbol.upper()
    if "-USD" in symbol:
        return symbol.replace("-USD", "USDT")
    if "-" in symbol:
        return symbol.replace("-", "")
    return symbol

def _format_finnhub_symbol(symbol: str) -> str:
    """Format symbol for Finnhub API (e.g., EURUSD=X -> EURUSD)."""
    if symbol.endswith("=X"):
        return symbol.replace("=X", "")
    return symbol

def _format_twelvedata_symbol(symbol: str) -> str:
    """Format symbol for Twelve Data API (e.g., EURUSD=X -> EUR/USD)."""
    if symbol.endswith("=X"):
        base = symbol[:-2]
        if len(base) == 6:
            return f"{base[:3]}/{base[3:]}"
    return symbol

def _yahoo_symbol(symbol: str) -> str:
    """Yahoo chart API accepts raw symbols as-is (AAPL, EURUSD=X, ^TNX, ...)."""
    return symbol

_YAHOO_INTERVAL_MAP = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m", "1d": "1d"}
_YAHOO_RANGE_MAP = {"1d": "1d", "5d": "5d", "1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y"}

def _yahoo_chart_url(symbol: str, interval: str, period: str = None) -> str:
    """Build a Yahoo Finance chart API URL (public endpoint, no API key needed)."""
    y_int = _YAHOO_INTERVAL_MAP.get(interval, "1d")
    if period and _YAHOO_RANGE_MAP.get(period):
        return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={_YAHOO_RANGE_MAP[period]}&interval={y_int}"
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval={y_int}"

def get_realtime_quotes(symbols: List[str], api_keys: dict) -> List[dict]:
    """
    Get real-time quotes for a mix of crypto and stock/forex symbols.
    Thread-safe and returns independent defensive copies of quote dictionaries.
    
    Args:
        symbols: List of ticker symbols
        api_keys: Dictionary containing 'finnhub', 'twelvedata', 'alphavantage' keys
        
    Returns:
        List of dictionaries containing quote data
    """
    now = time.time()
    results = []
    to_fetch = []
    
    # Check thread-safe cache
    for sym in symbols:
        cached = _realtime_cache.get(sym)
        if cached is not None:
            results.append(cached)
        else:
            to_fetch.append(sym)
            
    if not to_fetch:
        return results
        
    crypto_symbols = [s for s in to_fetch if _is_crypto(s)]
    stock_symbols = [s for s in to_fetch if not _is_crypto(s)]
    
    # 1. Fetch Crypto (Binance REST batch ticker)
    if crypto_symbols:
        binance_symbols = [_format_binance_symbol(s) for s in crypto_symbols]
        try:
            symbols_param = '["' + '","'.join(binance_symbols) + '"]'
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={symbols_param}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "code" in data:
                    logger.error(f"Binance API error: {data}")
                else:
                    for item in data:
                        orig_sym = next((s for s, b in zip(crypto_symbols, binance_symbols) if b == item['symbol']), item['symbol'])
                        quote = {
                            "symbol": orig_sym,
                            "name": orig_sym,
                            "price": float(item['lastPrice']),
                            "change": float(item['priceChange']),
                            "changePercent": float(item['priceChangePercent']),
                            "volume": float(item['volume']),
                            "high": float(item['highPrice']),
                            "low": float(item['lowPrice']),
                            "lastUpdate": int(now)
                        }
                        _realtime_cache.set(orig_sym, quote, now)
                        results.append(copy.deepcopy(quote))
        except Exception as e:
            logger.error(f"Error fetching Binance quotes: {e}")

    # 2. Fetch Stocks/Forex (Finnhub, or Yahoo chart API fallback when no key configured)
    #    Parallelised — one HTTP round-trip instead of N sequential calls.
    finnhub_key = api_keys.get("finnhub")
    if stock_symbols:
        if not finnhub_key:
            with ThreadPoolExecutor(max_workers=min(8, len(stock_symbols))) as pool:
                fetched = list(pool.map(lambda s: _fetch_yahoo_quote(s, now), stock_symbols))
            for quote in fetched:
                if quote:
                    sym = quote["symbol"]
                    _realtime_cache.set(sym, quote, now)
                    results.append(copy.deepcopy(quote))
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(stock_symbols))) as pool:
                fetched = list(pool.map(lambda s: _fetch_finnhub_quote(s, now, finnhub_key), stock_symbols))
            for quote in fetched:
                if quote:
                    sym = quote["symbol"]
                    _realtime_cache.set(sym, quote, now)
                    results.append(copy.deepcopy(quote))

    return results


def _fetch_yahoo_quote(sym: str, now: float, api_keys=None):
    """Fetch a single Yahoo quote protected by YahooCircuitBreaker."""
    if not _yahoo_circuit_breaker.allow_request():
        logger.debug(f"Yahoo quote request for {sym} skipped: Circuit Breaker is OPEN")
        return None
    try:
        url = _yahoo_chart_url(sym, "1d")
        import random
        ua = random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
        ])
        resp = requests.get(url, timeout=10, headers={"User-Agent": ua})
        if resp.status_code != 200:
            _yahoo_circuit_breaker.record_failure(status_code=resp.status_code)
            logger.error(f"Yahoo quote {sym}: HTTP {resp.status_code}")
            return None
        payload = resp.json()
        meta = payload.get("chart", {}).get("result", [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        if price is None:
            _yahoo_circuit_breaker.record_failure()
            return None
        _yahoo_circuit_breaker.record_success()
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        change = price - prev_close
        return {
            "symbol": sym,
            "name": sym,
            "price": float(price),
            "change": round(float(change), 4),
            "changePercent": round((change / prev_close) * 100, 2) if prev_close else 0.0,
            "volume": float(meta.get("regularMarketVolume") or 0.0),
            "high": float(meta.get("regularMarketDayHigh") or price),
            "low": float(meta.get("regularMarketDayLow") or price),
            "lastUpdate": int(now)
        }
    except Exception as e:
        _yahoo_circuit_breaker.record_failure()
        logger.error(f"Error fetching Yahoo quote for {sym}: {e}")
        return None


def _fetch_finnhub_quote(sym: str, now: float, finnhub_key: str):
    """Fetch a single Finnhub quote — safe to run inside a thread pool."""
    try:
        fh_sym = _format_finnhub_symbol(sym)
        url = f"https://finnhub.io/api/v1/quote?symbol={fh_sym}&token={finnhub_key}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("d") is not None:
                return {
                    "symbol": sym,
                    "name": sym,
                    "price": float(data.get("c", 0.0)),
                    "change": float(data.get("d", 0.0)),
                    "changePercent": float(data.get("dp", 0.0)),
                    "volume": 0.0,  # Finnhub basic quote doesn't provide volume
                    "high": float(data.get("h", 0.0)),
                    "low": float(data.get("l", 0.0)),
                    "lastUpdate": int(now)
                }
    except Exception as e:
        logger.error(f"Error fetching Finnhub quote for {sym}: {e}")
    return None

def get_historical_ohlcv(symbol: str, period: str = "1y", interval: str = "1d", api_keys: dict = None,
                         bypass_cache: bool = False) -> pd.DataFrame:
    """
    Get historical OHLCV data, trying Twelve Data first, then Alpha Vantage for stocks.
    Crypto relies on Binance. Returns an independent defensive copy of the DataFrame.
    
    Args:
        symbol: Ticker symbol
        period: Time period (e.g., "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y")
        interval: Granularity (e.g., "1d")
        api_keys: Dictionary containing API keys
        bypass_cache: When True, fetch fresh data even if a cached copy exists
        
    Returns:
        Pandas DataFrame with Open, High, Low, Close, Volume columns and DatetimeIndex.
    """
    if api_keys is None:
        api_keys = {}
        
    now = time.time()
    cache_key = f"{symbol.upper()}_{period}_{interval}"
    
    # Check thread-safe cache
    if not bypass_cache:
        cached_df = _historical_cache.get(cache_key)
        if cached_df is not None and not cached_df.empty:
            return cached_df.copy(deep=True)
        
    df = pd.DataFrame()
    
    # Helper to convert period string to outputsize limit
    days_map = {
        "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, 
        "6mo": 180, "1y": 365, "2y": 730
    }
    days = days_map.get(period, 365)
    
    multiplier_map = {"1m": 1440, "5m": 288, "15m": 96, "1h": 24, "1d": 1}
    multiplier = multiplier_map.get(interval, 1)
    
    limit = min(days * multiplier, 5000)
    
    if _is_crypto(symbol):
        # Crypto -> Binance
        b_sym = _format_binance_symbol(symbol)
        b_interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}
        b_interval = b_interval_map.get(interval, "1d")
        b_limit = min(limit, 1000) # Binance max is 1000
        
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={b_sym}&interval={b_interval}&limit={b_limit}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and ("code" in data or "msg" in data):
                    # Binance error payload (e.g. invalid symbol) - return empty
                    logger.warning(f"Binance error for {b_sym}: {data.get('msg', data)}")
                else:
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'Open', 'High', 'Low', 'Close', 'Volume',
                        'close_time', 'quote_asset_volume', 'number_of_trades',
                        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                    ])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                        df[col] = df[col].astype(float)
                    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception as e:
            logger.error(f"Error fetching Binance historical data for {symbol}: {e}")
            
    else:
        # Stock/Forex -> Twelve Data, fallback to Alpha Vantage
        td_key = api_keys.get("twelvedata")
        av_key = api_keys.get("alphavantage")
        success = False
        
        if td_key:
            td_sym = _format_twelvedata_symbol(symbol)
            td_interval_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "1d": "1day"}
            td_interval = td_interval_map.get(interval, "1day")
            try:
                url = f"https://api.twelvedata.com/time_series?symbol={td_sym}&interval={td_interval}&outputsize={limit}&apikey={td_key}"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    if "values" in data and len(data["values"]) > 0:
                        df = pd.DataFrame(data["values"])
                        df['datetime'] = pd.to_datetime(df['datetime'])
                        df.set_index('datetime', inplace=True)
                        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                        for col in ['Open', 'High', 'Low', 'Close']:
                            df[col] = df[col].astype(float)
                        if 'Volume' in df.columns:
                            df['Volume'] = df['Volume'].astype(float)
                        else:
                            df['Volume'] = 0.0
                        df = df.sort_index()
                        success = True
                    else:
                        logger.warning(f"TwelveData warning for {symbol}: {data}")
            except Exception as e:
                logger.error(f"Error fetching TwelveData for {symbol}: {e}")
                
        if not success and av_key:
            try:
                if symbol.endswith("=X"):
                    base = symbol[:-2]
                    from_sym = base[:3]
                    to_sym = base[3:]
                    url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_sym}&to_symbol={to_sym}&outputsize=full&apikey={av_key}"
                else:
                    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&outputsize=full&apikey={av_key}"
                    
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    key = next((k for k in data.keys() if "Time Series" in k), None)
                    if key:
                        ts = data[key]
                        df = pd.DataFrame.from_dict(ts, orient='index')
                        df.index = pd.to_datetime(df.index)
                        df.rename(columns={
                            '1. open': 'Open',
                            '2. high': 'High',
                            '3. low': 'Low',
                            '4. close': 'Close',
                            '5. volume': 'Volume'
                        }, inplace=True)
                        for col in df.columns:
                            df[col] = df[col].astype(float)
                        if 'Volume' not in df.columns:
                            df['Volume'] = 0.0
                        df = df.sort_index()
                        df = df.tail(limit)
                        success = True
                    else:
                        logger.warning(f"AlphaVantage warning for {symbol}: {data}")
            except Exception as e:
                logger.error(f"Error fetching AlphaVantage for {symbol}: {e}")

        if not success and _yahoo_circuit_breaker.allow_request():
            try:
                url = _yahoo_chart_url(symbol, interval, period)
                import random
                ua = random.choice([
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15"
                ])
                resp = requests.get(url, timeout=10, headers={"User-Agent": ua})
                if resp.status_code == 200:
                    payload = resp.json()
                    result = payload.get("chart", {}).get("result", [None])[0]
                    if result and result.get("timestamp") and result.get("indicators", {}).get("quote"):
                        ts = result["timestamp"]
                        q = result["indicators"]["quote"][0]
                        df = pd.DataFrame({
                            "Open": q.get("open"),
                            "High": q.get("high"),
                            "Low": q.get("low"),
                            "Close": q.get("close"),
                            "Volume": q.get("volume"),
                        }, index=pd.to_datetime(ts, unit="s"))
                        df = df.dropna(subset=["Close"])
                        df = df[~df.index.duplicated(keep="last")].sort_index()
                        df = df.tail(limit)
                        if not df.empty:
                            _yahoo_circuit_breaker.record_success()
                            success = True
                        else:
                            _yahoo_circuit_breaker.record_failure()
                    else:
                        _yahoo_circuit_breaker.record_failure()
                else:
                    _yahoo_circuit_breaker.record_failure(status_code=resp.status_code)
                    logger.error(f"Yahoo historical {symbol}: HTTP {resp.status_code}")
            except Exception as e:
                _yahoo_circuit_breaker.record_failure()
                logger.error(f"Error fetching Yahoo historical for {symbol}: {e}")

        if not td_key and not av_key and not success:
            if symbol not in _missing_keys_warned:
                _missing_keys_warned.add(symbol)
                logger.warning(
                    f"Both TwelveData and AlphaVantage keys missing for {symbol}. "
                    f"Add API keys in the extension Settings to enable historical data for this symbol."
                )
            
    if not df.empty:
        _historical_cache.set(cache_key, df, now)
        
    return df.copy(deep=True) if isinstance(df, pd.DataFrame) else df

def batch_prefetch_historical(symbols: List[str], period: str = "1y", interval: str = "1d", api_keys: dict = None) -> None:
    """
    Pre-warm cache for multiple symbols. Skips crypto (handled by Binance on-demand).
    Fetches in parallel via Twelve Data / Alpha Vantage (provider rate limits
    are respected inside get_historical_ohlcv itself; a full batch of stock
    symbols used to take N x per-symbol time sequentially).
    
    Args:
        symbols: List of ticker symbols
        period: Time period to prefetch
        interval: Data interval
        api_keys: API keys dictionary
    """
    if api_keys is None:
        api_keys = {}
        
    # Skip crypto symbols as requested
    stock_symbols = [s for s in symbols if not _is_crypto(s)]
    if not stock_symbols:
        return

    with ThreadPoolExecutor(max_workers=min(6, len(stock_symbols))) as pool:
        futures = [
            pool.submit(get_historical_ohlcv, sym, period, interval, api_keys)
            for sym in stock_symbols
        ]
        for f in futures:
            try:
                f.result()
            except Exception as e:
                logger.warning(f"batch_prefetch_historical: {e}")
