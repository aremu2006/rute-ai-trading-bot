
export const initChromePolyfill = () => {
  if (typeof window === 'undefined') return;

  const needsPolyfill = !window.chrome || !window.chrome.runtime || !window.chrome.storage;
  if (!needsPolyfill) return;

  console.log('[RUTE] Initializing Chrome API Polyfill for Preview Mode');

  const mockStorage = {
    userSettings: {
      apiEndpoint: 'http://127.0.0.1:8001',
      riskSettings: {
        maxPositionSize: 1000,
        maxDailyLoss: 500,
        stopLossPercentage: 2,
        takeProfitPercentage: 5,
        enableAutoTrade: false,
      },
      notifications: { tradeAlerts: true, priceAlerts: true, newsAlerts: false },
      mt5Url: 'https://trade.mql5.com/trade',
    },
    watchlist: [
      { symbol: 'EURUSD', assetType: 'FOREX', addedAt: Date.now() },
      { symbol: 'BTCUSD', assetType: 'STOCK', addedAt: Date.now() },
      { symbol: 'AAPL', assetType: 'STOCK', addedAt: Date.now() },
    ],
    tradeLogs: [
      {
        id: 'log-1',
        recommendation: {
          id: 'past-1',
          symbol: 'NVDA',
          type: 'BUY',
          assetType: 'STOCK',
          entryPrice: 480.50,
          stopLoss: 475.00,
          takeProfit: 495.00,
          confidence: 88,
          timestamp: Date.now() - 86400000,
          status: 'executed',
          reasoning: {
            summary: 'AI trend continuation',
            marketTrend: 'BULLISH',
            sentiment: 'BULLISH',
            technicalIndicators: ['MA Cross', 'RSI Bullish'],
          },
        },
        executedAt: Date.now() - 86000000,
        executionPrice: 480.60,
        result: { exitPrice: 492.20, profit: 1160.00, exitedAt: Date.now() - 80000000 },
      },
    ],
  };

  const mockRecommendations = [
    {
      id: 'demo-1',
      symbol: 'EURUSD',
      type: 'BUY',
      assetType: 'FOREX',
      entryPrice: 1.0850,
      stopLoss: 1.0820,
      takeProfit: 1.0950,
      confidence: 88,
      timestamp: Date.now(),
      status: 'ACTIVE',
      reasoning: {
        summary: 'Strong bullish momentum detected with RSI divergence.',
        marketTrend: 'BULLISH',
        sentiment: 'BULLISH',
        technicalIndicators: ['RSI < 30', 'MACD Crossover', 'Above EMA 200'],
      },
    },
    {
      id: 'demo-2',
      symbol: 'XAUUSD',
      type: 'SELL',
      assetType: 'COMMODITY',
      entryPrice: 2045.50,
      stopLoss: 2055.00,
      takeProfit: 2020.00,
      confidence: 92,
      timestamp: Date.now(),
      status: 'ACTIVE',
      reasoning: {
        summary: 'Rejection at major resistance level.',
        marketTrend: 'BEARISH',
        sentiment: 'BEARISH',
        technicalIndicators: ['Double Top', 'Bearish Engulfing'],
      },
    },
  ];

  // Tracks the active mock market-data interval so it can be cleaned up
  let marketUpdateInterval: ReturnType<typeof setInterval> | null = null;

  const mockChrome = {
    runtime: {
      sendMessage: async (msg: any, cb: any) => {
        if (msg.type === 'GET_RECOMMENDATIONS') {
          try {
            const apiEndpoint = mockStorage.userSettings.apiEndpoint;
            const symbols = mockStorage.watchlist.map(item => ({ symbol: item.symbol, assetType: item.assetType }));
            const riskSettings = mockStorage.userSettings.riskSettings || {};
            const response = await fetch(`${apiEndpoint}/api/recommendations`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ symbols, riskSettings }),
            });
            if (response.ok) {
              const data = await response.json();
              cb && cb({ recommendations: data.recommendations });
              return;
            }
          } catch {
            // Backend unreachable — use mock data
          }
          setTimeout(() => cb && cb({ recommendations: mockRecommendations }), 500);
        } else if (msg.type === 'EXECUTE_TRADE') {
          setTimeout(() => cb && cb({ success: true }), 500);
        } else {
          cb && cb({ success: true });
        }
      },
      lastError: undefined as any,
      onMessage: {
        addListener: (callback: any) => {
          if (marketUpdateInterval) clearInterval(marketUpdateInterval);

          const updateMarketData = async () => {
            try {
              const apiEndpoint = mockStorage.userSettings.apiEndpoint;
              const symbols = mockStorage.watchlist.map(item => item.symbol);
              const response = await fetch(`${apiEndpoint}/api/market-data`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbols }),
              });
              if (response.ok) {
                const data = await response.json();
                callback({ type: 'MARKET_DATA_UPDATE', data: data.marketData });
                return;
              }
            } catch {
              // Fallback
            }
            callback({
              type: 'MARKET_DATA_UPDATE',
              data: {
                EURUSD: { symbol: 'EURUSD', price: 1.0860 + (Math.random() * 0.002 - 0.001), change: 0.0010, changePercent: 0.09, volume: 0, timestamp: Date.now() },
                AAPL: { symbol: 'AAPL', price: 185.50 + (Math.random() * 1 - 0.5), change: 2.30, changePercent: 1.25, volume: 0, timestamp: Date.now() },
              },
            });
          };

          setTimeout(updateMarketData, 2000);
          marketUpdateInterval = setInterval(updateMarketData, 30000);
        },
        removeListener: () => {
          if (marketUpdateInterval) {
            clearInterval(marketUpdateInterval);
            marketUpdateInterval = null;
          }
        },
      },
    },
    storage: {
      local: {
        get: (keys: string[] | string | null, cb: any) => {
          if (keys === null) {
            cb(mockStorage);
          } else {
            const result: any = {};
            const arr = Array.isArray(keys) ? keys : [keys];
            arr.forEach((k: string) => {
              if (k in mockStorage) result[k] = (mockStorage as any)[k];
            });
            cb(result);
          }
        },
        set: (data: any, cb?: any) => {
          Object.assign(mockStorage, data);
          cb && cb();
        },
      },
    },
    alarms: {
      create: () => {},
      onAlarm: { addListener: () => {} },
    },
  };

  try {
    if (!window.chrome) {
      // @ts-ignore
      window.chrome = mockChrome;
    } else {
      // @ts-ignore
      if (!window.chrome.runtime) window.chrome.runtime = mockChrome.runtime;
      // @ts-ignore
      if (!window.chrome.storage) window.chrome.storage = mockChrome.storage;
      // @ts-ignore
      if (!window.chrome.alarms) window.chrome.alarms = mockChrome.alarms;
    }
  } catch (e) {
    console.error('[RUTE] Failed to initialize Chrome polyfill:', e);
  }
};
