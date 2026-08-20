"""
Sentiment Hub — VADER-based local sentiment analysis (zero API keys, zero cost)
Replaces Gemini LLM with free local VADER sentiment from NLTK/vaderSentiment.
"""
import os
import time
import asyncio
import logging
from typing import Dict, List, Optional
from statistics import mean

log = logging.getLogger("ml_engine.sentiment_hub")

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    log.warning("[SentimentHub] vaderSentiment not installed. Run: pip install vaderSentiment")

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    log.warning("[SentimentHub] feedparser not installed. News scraping disabled.")


class SentimentHub:
    """Multi-source sentiment analysis using RSS news feeds and VADER."""

    NEWS_FEEDS = {
        "macro": "https://feeds.reuters.com/reuters/businessNews",
        "forex": "https://www.forexlive.com/feed/",
        "crypto": "https://cointelegraph.com/rss",
    }

    ASSET_KEYWORDS = {
        "BTCUSDm": ["bitcoin", "btc", "crypto", "digital asset", "cryptocurrency"],
        "ETHUSDm": ["ethereum", "eth", "defi"],
        "EURUSDm": ["euro", "ecb", "eurozone", "european central bank"],
        "GBPUSDm": ["pound", "sterling", "boe", "bank of england", "uk economy"],
        "USDJPYm": ["yen", "boj", "bank of japan", "japanese"],
        "XAUUSDm": ["gold", "precious metal", "safe haven", "bullion"],
        "AAPL": ["apple", "iphone", "tim cook", "app store"],
        "TSLA": ["tesla", "elon musk", "ev", "electric vehicle"],
        "NVDA": ["nvidia", "gpu", "ai chip", "jensen huang"],
        "GOOGL": ["google", "alphabet", "search engine"],
        "MSFT": ["microsoft", "windows", "azure", "satya nadella"],
    }

    def __init__(self):
        self._headline_cache: Dict[str, List[dict]] = {}
        self._sentiment_cache: Dict[str, dict] = {}
        self._cache_ttl = 300

        if VADER_AVAILABLE:
            self._analyzer = SentimentIntensityAnalyzer()
            log.info("[SentimentHub] VADER sentiment analyzer initialized.")
        else:
            self._analyzer = None
            log.warning("[SentimentHub] VADER not available — all sentiment returns neutral.")

    async def scrape_headlines(self):
        if not FEEDPARSER_AVAILABLE:
            return

        for category, url in self.NEWS_FEEDS.items():
            try:
                feed = await asyncio.to_thread(feedparser.parse, url)
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    title_lower = title.lower()

                    for asset, keywords in self.ASSET_KEYWORDS.items():
                        if any(kw in title_lower for kw in keywords):
                            self._headline_cache.setdefault(asset, [])
                            if len(self._headline_cache[asset]) >= 20:
                                self._headline_cache[asset] = self._headline_cache[asset][-19:]
                            self._headline_cache[asset].append({
                                "title": title,
                                "published": entry.get("published", ""),
                                "source": category,
                            })
            except Exception as e:
                log.warning(f"[SentimentHub] Failed to parse {category} feed: {e}")

    async def analyze_sentiment(self, symbol: str, direction: str) -> dict:
        """
        Analyze sentiment using VADER on recent headlines.
        Returns: { score: float (-1 to +1), reasoning: str, veto: bool }
        """
        cache_key = f"{symbol}_{direction}"
        cached = self._sentiment_cache.get(cache_key)
        if cached and (time.time() - cached.get("timestamp", 0)) < self._cache_ttl:
            return cached

        headlines = list(self._headline_cache.get(symbol, []))[-20:]
        # Drop stale headlines (older than 48h) — a week-old panic headline
        # must not veto a fresh signal.
        if headlines:
            fresh = []
            now = time.time()
            for h in headlines:
                parsed = h.get("published_parsed") or h.get("updated_parsed")
                if parsed is None:
                    fresh.append(h)  # no date — keep (can't judge)
                    continue
                try:
                    ts = time.mktime(parsed)
                except (ValueError, OverflowError, TypeError):
                    fresh.append(h)
                    continue
                if now - ts <= 48 * 3600:
                    fresh.append(h)
            headlines = fresh[-10:]
        if not headlines:
            result = {"score": 0.0, "reasoning": "No recent news found", "veto": False, "timestamp": time.time()}
            self._sentiment_cache[cache_key] = result
            return result

        if self._analyzer is None:
            result = {"score": 0.0, "reasoning": "VADER not installed", "veto": False, "timestamp": time.time()}
            self._sentiment_cache[cache_key] = result
            return result

        scores = []
        for h in headlines:
            vs = self._analyzer.polarity_scores(h["title"])
            scores.append(vs["compound"])

        avg_score = mean(scores) if scores else 0.0

        # Veto logic: strongly negative sentiment for BUY, strongly positive for SELL
        veto = False
        if direction == "BUY" and avg_score < -0.5:
            veto = True
        elif direction == "SELL" and avg_score > 0.5:
            veto = True

        result = {
            "score": round(avg_score, 4),
            "reasoning": f"VADER sentiment over {len(scores)} headlines: {avg_score:.3f}",
            "veto": veto,
            "timestamp": time.time(),
        }
        self._sentiment_cache[cache_key] = result
        return result

    def get_ticker_sentiment(self, symbol: str) -> float:
        for direction in ["BUY", "SELL"]:
            cached = self._sentiment_cache.get(f"{symbol}_{direction}")
            if cached:
                return cached.get("score", 0.0)
        return 0.0

    def filter_signal(self, symbol: str, direction: str) -> bool:
        cache_key = f"{symbol}_{direction}"
        cached = self._sentiment_cache.get(cache_key)
        if not cached:
            return False
        return cached.get("veto", False)

    def get_headline_count(self, symbol: str) -> int:
        return len(self._headline_cache.get(symbol, []))


sentiment_hub = SentimentHub()


async def news_scraper_loop():
    while True:
        try:
            await sentiment_hub.scrape_headlines()
            total = sum(len(v) for v in sentiment_hub._headline_cache.values())
            log.info(f"[SentimentHub] Scraped {total} headlines across {len(sentiment_hub._headline_cache)} assets")
        except Exception as e:
            log.error(f"[SentimentHub] Scraper error: {e}")
        await asyncio.sleep(300)
