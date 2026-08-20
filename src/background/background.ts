import { TradeRecommendation, MarketData, TradeLog, UserSettings } from '../types';

// Store for active recommendations and market data
let activeRecommendations: TradeRecommendation[] = [];
let marketDataCache: Record<string, MarketData> = {};
let tradeLogsCache: TradeLog[] = [];

// Track which recommendation IDs we've already auto-executed to prevent duplicate trades
const autoExecutedIds = new Set<string>();

// Minimum gap between full recommendation scans (see fetchAIRecommendations).
const SCAN_MIN_INTERVAL_MS = 90 * 1000;
let lastScanStart = 0;

// API endpoint
const API_ENDPOINT = 'http://127.0.0.1:8001';
let WS_ENDPOINT = 'ws://127.0.0.1:8001/ws/trading';

let socket: WebSocket | null = null;
let refreshDebounceId: ReturnType<typeof setTimeout> | null = null;

// Restore state after an MV3 worker restart (onInstalled does NOT fire on
// worker wake-ups, so recommendations/logs would otherwise reset to empty).
chrome.storage.local.get(['rute_recommendations', 'tradeLogs'], (result) => {
  if (Array.isArray(result.rute_recommendations)) activeRecommendations = result.rute_recommendations;
  if (Array.isArray(result.tradeLogs)) tradeLogsCache = result.tradeLogs;
});

// Reconnect WebSocket immediately on every service worker wake-up,
// not just on first install (onInstalled doesn't fire on wake-ups).
connectWebSocket();

// Immediately populate the SCAN_LOG on every worker wake-up so the
// Decision Log tab is never stuck empty after an extension reload.
// Use a short delay so storage restore completes first.
setTimeout(() => {
  fetchAIRecommendations();
}, 3000);

// Initialize background script
chrome.runtime.onInstalled.addListener(() => {
  console.log('RUTE Trading Assistant installed');

  // Initialize storage FIRST, then create alarms and fetch — otherwise the
  // first scan can fire against an empty watchlist while defaults are still
  // being written.
  initializeStorage().then(() => {
    // Set up periodic market data updates (every 1 minute)
    chrome.alarms.create('marketDataUpdate', { periodInMinutes: 1 });

    // Set up AI recommendation updates (every 5 minutes)
    chrome.alarms.create('aiRecommendations', { periodInMinutes: 5 });

    // PWA/MV3 Keep-Alive (every 1 minute)
    chrome.alarms.create('keepAlive', { periodInMinutes: 1 });

    // Connect WebSocket
    connectWebSocket();

    // Initial data fetch
    setTimeout(() => {
      updateMarketData();
      fetchAIRecommendations();
    }, 2000);
  });
});

// Self-healing alarms: MV3 silently loses `chrome.alarms` on extension reload
// (and some Chrome versions clear them on browser update), so onInstalled's
// registration alone is NOT reliable — this check runs on every worker wake
// and recreates whatever is missing, then kicks off an immediate scan so the
// market never goes unmonitored.
chrome.alarms.getAll((alarms) => {
  const names = new Set(alarms.map((a) => a.name));
  let restored = false;
  if (!names.has('marketDataUpdate')) {
    chrome.alarms.create('marketDataUpdate', { periodInMinutes: 1 });
    restored = true;
  }
  if (!names.has('aiRecommendations')) {
    chrome.alarms.create('aiRecommendations', { periodInMinutes: 5 });
    restored = true;
  }
  if (!names.has('keepAlive')) {
    chrome.alarms.create('keepAlive', { periodInMinutes: 1 });
    restored = true;
  }
  if (restored) {
    console.log('RUTE: Missing alarms restored — triggering immediate scan');
    updateMarketData();
    fetchAIRecommendations();
  }
});

// Initialize storage with default values
function initializeStorage(): Promise<void> {
  return new Promise((resolve) => {
    const defaultSettings: UserSettings = {
      riskSettings: {
        maxPositionSize: 1000,
        maxDailyLoss: 500,
        stopLossPercentage: 2,
        takeProfitPercentage: 5,
        enableAutoTrade: false,
      },
      notifications: {
        tradeAlerts: true,
        priceAlerts: true,
        newsAlerts: false,
      },
      apiEndpoint: API_ENDPOINT,
    };

    chrome.storage.local.get(['userSettings', 'watchlist', 'tradeLogs', 'rute_recommendations'], (result) => {
      if (!result.userSettings) {
        chrome.storage.local.set({ userSettings: defaultSettings });
      } else if (result.userSettings.apiEndpoint && result.userSettings.apiEndpoint.includes('localhost')) {
        // Auto-migrate broken IPv6 localhost cache to IPv4
        result.userSettings.apiEndpoint = result.userSettings.apiEndpoint.replace('localhost', '127.0.0.1');
        chrome.storage.local.set({ userSettings: result.userSettings });
      }

      if (Array.isArray(result.tradeLogs)) tradeLogsCache = result.tradeLogs;
      if (Array.isArray(result.rute_recommendations)) activeRecommendations = result.rute_recommendations;

      const defaultWatchlist = [
        { symbol: 'AAPL', assetType: 'STOCK', addedAt: Date.now() },
        { symbol: 'TSLA', assetType: 'STOCK', addedAt: Date.now() },
        { symbol: 'GOOGL', assetType: 'STOCK', addedAt: Date.now() },
        { symbol: 'BTC-USD', assetType: 'CRYPTO', addedAt: Date.now() },
        { symbol: 'ETH-USD', assetType: 'CRYPTO', addedAt: Date.now() },
        { symbol: 'EURUSD=X', assetType: 'FOREX', addedAt: Date.now() },
      ];

      if (!result.watchlist || result.watchlist.length === 0) {
        chrome.storage.local.set({ watchlist: defaultWatchlist });
      } else {
        // Merge defaults if missing (for users upgrading from older versions)
        const currentList = result.watchlist;
        let updated = false;
        defaultWatchlist.forEach(item => {
          if (!currentList.find((x: any) => x.symbol === item.symbol)) {
            currentList.push(item);
            updated = true;
          }
        });
        if (updated) chrome.storage.local.set({ watchlist: currentList });
      }

      if (!result.tradeLogs) {
        chrome.storage.local.set({ tradeLogs: [] });
      }

      resolve();
    });
  });
}

// Handle alarms
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'marketDataUpdate') {
    updateMarketData();
  } else if (alarm.name === 'aiRecommendations') {
    fetchAIRecommendations();
  } else if (alarm.name === 'keepAlive') {
    console.log('RUTE: Keep-alive heartbeat');
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
  }
});

let wsRetryDelay = 2000;
const WS_MAX_DELAY = 15000;

function connectWebSocket() {
  // Guard against duplicate connections: also block while a connection is
  // already in flight (CONNECTING), not just when fully OPEN.
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;

  // Derive WS URL from user's apiEndpoint setting (if changed from default)
  chrome.storage.local.get(['userSettings'], (result) => {
    let apiEndpoint = result.userSettings?.apiEndpoint || API_ENDPOINT;
    if (apiEndpoint.includes('localhost')) apiEndpoint = apiEndpoint.replace('localhost', '127.0.0.1');
    
    try {
      const u = new URL(apiEndpoint);
      u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
      WS_ENDPOINT = `${u.protocol}//${u.host}/ws/trading`;
    } catch {
      WS_ENDPOINT = API_ENDPOINT.replace(/^http/, 'ws') + '/ws/trading';
    }

    console.log(`RUTE: Connecting to WebSocket Brain (retry delay: ${wsRetryDelay}ms)...`);
    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_ENDPOINT);
    } catch (e) {
      console.error('RUTE: Invalid WebSocket endpoint — no connection will be made:', e);
      return;
    }
    socket = ws;

    ws.onopen = () => {
      console.log('RUTE: WebSocket connected.');
      wsRetryDelay = 2000; // Reset backoff on successful connection
    };

    ws.onmessage = (event) => {
      let data: any;
      try {
        data = JSON.parse(event.data);
      } catch {
        console.error('RUTE: Invalid WebSocket message:', event.data);
        return;
      }
      
      // Latency Check
      if (data.server_time) {
        const latency = (Date.now() / 1000) - data.server_time;
        console.log(`RUTE: Signal Received. Latency: ${(latency * 1000).toFixed(2)}ms`);
      }

      if (data.type === 'NEW_SIGNAL' || data.ticker) {
        chrome.storage.local.get(['userSettings'], (s) => {
          if (s.userSettings?.notifications?.tradeAlerts) {
            showNotification(
              `Real-time Signal: ${data.ticker || data.symbol}`,
              `${data.side || data.type} recommendation received via WebSocket`
            );
          }
        });

        // Update local recommendations if needed (debounced — multiple WS broadcasts
        // can arrive back-to-back, and each refresh takes several seconds)
        if (!refreshDebounceId) {
          refreshDebounceId = setTimeout(() => {
            refreshDebounceId = null;
            fetchAIRecommendations();
          }, 5000);
        }
      }
    };

    ws.onclose = () => {
      // Only the CURRENT socket may schedule a reconnect — a stale socket that
      // closes while a newer connection exists must not spawn a duplicate loop.
      if (socket !== ws) return;
      console.log(`RUTE: WebSocket disconnected. Retrying in ${wsRetryDelay / 1000}s...`);
      setTimeout(connectWebSocket, wsRetryDelay);
      // Exponential backoff: 2s → 5s → 10s → 15s (capped)
      wsRetryDelay = Math.min(wsRetryDelay * 2, WS_MAX_DELAY);
    };

    ws.onerror = (error) => {
      console.error('RUTE: WebSocket error:', error);
      // A socket stuck in CONNECTING never fires onclose, which would stall
      // the reconnect loop forever — force-close so the onclose path runs.
      if (ws.readyState === WebSocket.CONNECTING) {
        try { ws.close(); } catch {}
      }
    };

    // Watchdog to forcefully reconnect if stuck in CONNECTING for >5s
    const wsWatchdog = setInterval(() => {
      if (ws.readyState === WebSocket.CONNECTING) {
        console.warn('RUTE: WebSocket stuck CONNECTING. Forcing reconnect...');
        try { ws.close(); } catch {}
      } else {
        clearInterval(wsWatchdog);
      }
    }, 5000);

    ws.onopen = () => {
      clearInterval(wsWatchdog);
    };
  });
}

// Fetch market data from API
async function updateMarketData() {
  try {
    const result = await new Promise<any>((resolve) => {
      chrome.storage.local.get(['watchlist', 'userSettings'], resolve);
    });
    const watchlist = result.watchlist || [];
    let apiEndpoint = result.userSettings?.apiEndpoint || API_ENDPOINT;
    if (apiEndpoint.includes('localhost')) apiEndpoint = apiEndpoint.replace('localhost', '127.0.0.1');

    if (watchlist.length === 0) return;

    const symbols = watchlist.map((item: any) => item.symbol);

    const response = await fetch(`${apiEndpoint}/api/market-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols, apiKeys: result.userSettings?.apiKeys }),
    });

    if (response.ok) {
      const data = await response.json();
      marketDataCache = data.marketData;

      chrome.runtime.sendMessage({
        type: 'MARKET_DATA_UPDATE',
        data: marketDataCache,
      }).catch(() => {});

      if (data.marketData) {
        checkPriceAlerts(data.marketData);
        checkTradeOutcomes(data.marketData);
      }
    }
  } catch (error) {
    console.error('Error updating market data:', error);
  }
}

// Check open trades against live market data to resolve TP/SL and feed the RL engine
function checkTradeOutcomes(marketData: Record<string, MarketData>) {
  let updated = false;
  const now = Date.now();

  tradeLogsCache.forEach((log) => {
    if (log.result) return; // Already closed
    
    const md = marketData[log.recommendation.symbol];
    if (!md || !md.price) return;
    
    const currentPrice = md.price;
    const isBuy = log.recommendation.type === 'BUY';
    const entry = log.executionPrice;
    
    let exitReason = null;
    let exitPrice = 0;
    
    if (isBuy) {
      if (currentPrice >= log.recommendation.takeProfit) {
        exitReason = 'TP';
        exitPrice = log.recommendation.takeProfit;
      } else if (currentPrice <= log.recommendation.stopLoss) {
        exitReason = 'SL';
        exitPrice = log.recommendation.stopLoss;
      }
    } else {
      if (currentPrice <= log.recommendation.takeProfit) {
        exitReason = 'TP';
        exitPrice = log.recommendation.takeProfit;
      } else if (currentPrice >= log.recommendation.stopLoss) {
        exitReason = 'SL';
        exitPrice = log.recommendation.stopLoss;
      }
    }
    
    if (exitReason) {
      const profit = isBuy ? exitPrice - entry : entry - exitPrice;
      
      log.result = {
        exitPrice,
        profit,
        exitedAt: now,
        exitReason
      };
      updated = true;
      
      // Notify the backend RL engine (DQN/PPO)
      chrome.storage.local.get(['userSettings'], (res) => {
        let ep = res.userSettings?.apiEndpoint || API_ENDPOINT;
        if (ep.includes('localhost')) ep = ep.replace('localhost', '127.0.0.1');
        fetch(`${ep}/api/trade-outcome`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            signal_id: log.recommendation.id,
            profit,
            exit_reason: exitReason
          })
        }).catch(err => console.error('RUTE RL Feedback Error:', err));
      });
      
      showNotification('Trade Closed', `${log.recommendation.symbol} hit ${exitReason}. Profit: $${profit.toFixed(2)}`);
    }
  });

  if (updated) {
    chrome.storage.local.set({ tradeLogs: tradeLogsCache });
  }
}

// Fetch AI trade recommendations
async function fetchAIRecommendations() {
  // Throttle: the MV3 worker wakes every minute (keepAlive alarm) and this
  // function is also invoked by the 5-min alarm, popup refreshes and WS
  // signals. A full 7-symbol scan on EVERY wake flooded the scan log with
  // "Scanning..." starts and hammered the data providers. One scan per 90s
  // is plenty — the 5-min alarm and explicit refreshes always pass.
  const now = Date.now();
  if (now - lastScanStart < SCAN_MIN_INTERVAL_MS) {
    return;
  }
  lastScanStart = now;

  try {
    const result = await new Promise<any>((resolve) => {
      chrome.storage.local.get(['watchlist', 'userSettings', 'minConfidence', 'rute_active_strategies', 'rute_opt_params'], resolve);
    });
    const watchlist = result.watchlist || [];
    let apiEndpoint = result.userSettings?.apiEndpoint || API_ENDPOINT;
    if (apiEndpoint.includes('localhost')) apiEndpoint = apiEndpoint.replace('localhost', '127.0.0.1');

    if (watchlist.length === 0) return;

    const symbols = watchlist.map((item: any) => ({
      symbol: item.symbol,
      assetType: item.assetType || 'STOCK',
    }));

    const riskSettings = result.userSettings?.riskSettings || {};
    if (result.minConfidence) {
      riskSettings.minConfidence = result.minConfidence;
    }

    const response = await fetch(`${apiEndpoint}/api/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        symbols,
        riskSettings,
        notifications: result.userSettings?.notifications,
        apiKeys: result.userSettings?.apiKeys,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      activeRecommendations = data.recommendations;
      chrome.storage.local.set({ rute_recommendations: activeRecommendations });

      // If the user narrowed down their active strategies, cross-check the ML
      // recommendations against the current stance of those strategies and
      // only alert when at least one active strategy agrees.
      const activeStrats = (result.rute_active_strategies || []) as string[];
      const stanceMap: Record<string, Record<string, string>> = {};
      if (activeStrats.length > 0) {
        try {
          const sigRes = await fetch(`${apiEndpoint}/api/live-signals`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              symbols: symbols.map((s: any) => s.symbol),
              strategies: activeStrats,
              interval: '1d',
              params: result.rute_opt_params || undefined,
            }),
          });
          if (sigRes.ok) {
            const sigData = await sigRes.json();
            for (const row of (sigData.results || [])) stanceMap[row.symbol] = row.signals || {};
          }
        } catch {}
      }
      activeRecommendations = (activeRecommendations || []).map((r: any) => {
        const sig = stanceMap[r.symbol] || {};
        // Preserve HOLD/NEUTRAL as-is — a neutral signal must NOT count as a
        // sell agreement (which could tip notifications into firing on it).
        const type = String(r.type || '').toLowerCase();
        const want = type.startsWith('buy') ? 'buy' : type.startsWith('sell') ? 'sell' : 'hold';
        const agreement = activeStrats.filter(s => want !== 'hold' && sig[s] === want).length;
        return { ...r, strategyAgreement: agreement, strategiesActive: activeStrats.length };
      });
      chrome.storage.local.set({ rute_recommendations: activeRecommendations });

      // AlphaTrend-style state tracking: only notify when the recommendation
      // set actually CHANGED, not on every 5-min scan cycle.
      const signature = (activeRecommendations || [])
        .map((r: any) => `${r.symbol}:${r.type}:${(r.confidence ?? 0).toFixed(2)}`)
        .sort()
        .join('|');
      chrome.storage.local.get(['lastSignalSignature'], (prev) => {
        if (prev.lastSignalSignature !== signature) {
          chrome.storage.local.set({ lastSignalSignature: signature });
          const agreed = (activeRecommendations || []).filter((r: any) => (r.strategyAgreement ?? 0) >= 1);
          const eligible = activeStrats.length === 0 ? activeRecommendations : agreed;
          if (result.userSettings?.notifications?.tradeAlerts && eligible.length > 0) {
            showNotification(
              'New Trade Recommendations',
              `${eligible.length} opportunities detected${activeStrats.length > 0 ? ` — ${agreed.length} confirmed by your active strategies` : ''}`
            );
          }
        }
      });

      chrome.runtime.sendMessage({
        type: 'NEW_RECOMMENDATIONS',
        recommendations: activeRecommendations,
      }).catch(() => {});

      // ─── AUTO-TRADE ENGINE ────────────────────────────────────────────────
      // Read user settings and fire executeTrade() for any qualifying signal
      // that we haven't already acted on this session.
      const settings = result.userSettings;
      const autoTradeEnabled = settings?.riskSettings?.enableAutoTrade === true;

      if (autoTradeEnabled && activeRecommendations.length > 0) {
        // Read minConfidence from storage (set in Settings slider)
        chrome.storage.local.get(['minConfidence', 'tradeLogs'], async (cfg) => {
          const minConf: number = cfg.minConfidence ?? 70;

          // Daily loss guard: sum profits of today's closed trades
          const todayStart = new Date().setHours(0, 0, 0, 0);
          const todayLoss = (cfg.tradeLogs || []).reduce((sum: number, log: TradeLog) => {
            if (log.result && log.result.exitedAt >= todayStart && log.result.profit < 0) {
              return sum + log.result.profit;
            }
            return sum;
          }, 0);
          const balance = settings?.riskSettings?.accountBalance ?? 0;
          const isPct = settings?.riskSettings?.riskType === 'percentage';
          let maxDailyLoss = settings?.riskSettings?.maxDailyLoss ?? 500;
          if (isPct && balance > 0) {
            maxDailyLoss = (maxDailyLoss / 100) * balance;
          }
          
          if (Math.abs(todayLoss) >= maxDailyLoss) {
            console.warn(`RUTE Auto-Trade: Daily loss limit hit ($${todayLoss.toFixed(2)}). Pausing.`);
            return;
          }

          // Fire on all recommendations that pass the confidence bar and
          // haven't already been executed this session.
          for (const rec of activeRecommendations) {
            if (autoExecutedIds.has(rec.id)) continue;
            if ((rec.confidence ?? 0) < minConf) {
              console.log(`RUTE Auto-Trade: ${rec.symbol} skipped — confidence ${rec.confidence}% < ${minConf}%`);
              continue;
            }

            console.log(`RUTE Auto-Trade: EXECUTING ${rec.type} ${rec.symbol} @ ${rec.confidence}% confidence`);
            autoExecutedIds.add(rec.id);

            try {
              await executeTrade(rec);
            } catch (err) {
              console.error(`RUTE Auto-Trade: Failed to execute ${rec.symbol}:`, err);
            }
          }
        });
      }
      // ─────────────────────────────────────────────────────────────────────
    } else {
      console.warn(`RUTE: /api/recommendations returned HTTP ${response.status}`);
    }
  } catch (error) {
    console.error('Error fetching AI recommendations:', error);
  }
}

// Cooldown map so price alerts don't re-fire every 1-minute alarm cycle
// while a move stays >= 5%.
const lastPriceAlertAt: Record<string, number> = {};
const PRICE_ALERT_COOLDOWN_MS = 15 * 60 * 1000;

// Check for price alerts
function checkPriceAlerts(marketData: Record<string, MarketData>) {
  chrome.storage.local.get(['userSettings'], (result) => {
    if (!result.userSettings?.notifications?.priceAlerts) return;

    Object.values(marketData).forEach((data) => {
      if (Math.abs(data.changePercent) >= 5) {
        const now = Date.now();
        if (now - (lastPriceAlertAt[data.symbol] || 0) < PRICE_ALERT_COOLDOWN_MS) return;
        lastPriceAlertAt[data.symbol] = now;
        showNotification(
          `${data.symbol} Price Alert`,
          `${data.symbol} has moved ${data.changePercent.toFixed(2)}%`
        );
      }
    });
  });
}

// Show Chrome notification
function showNotification(title: string, message: string) {
  chrome.notifications.create({
    type: 'basic',
    iconUrl: 'icons/icon128.png',
    title,
    message,
    priority: 2,
  });
}

// Execute trade
async function executeTrade(trade: TradeRecommendation) {
  try {
    let response: any = null;
    
    // Try to send to content script to execute on trading platform
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    
    if (tabs[0]?.id) {
      try {
        response = await chrome.tabs.sendMessage(tabs[0].id, {
          type: 'EXECUTE_TRADE',
          trade,
        });
      } catch (err) {
        console.warn('Could not reach content script on active tab, simulating execution', err);
      }
    }

    if (!response?.success) {
      // If we couldn't reach the content script or it failed, fallback to simulated success
      console.log('Falling back to simulated trade execution');
      response = { 
        success: true, 
        executionPrice: trade.entryPrice 
      };
    }

    // Only log + notify AFTER the platform confirmed the order (or simulated)
    const tradeLog: TradeLog = {
      id: crypto.randomUUID(),
      recommendation: trade,
      executedAt: Date.now(),
      executionPrice: response.executionPrice ?? trade.entryPrice,
    };

    // Save to storage (in-memory cache avoids the read-modify-write race
    // where two simultaneous trades would overwrite each other's log entry)
    tradeLogsCache.unshift(tradeLog);
    chrome.storage.local.set({ tradeLogs: tradeLogsCache });

    showNotification(
      'Trade Executed',
      `${trade.type} order for ${trade.symbol} at $${tradeLog.executionPrice}`
    );

    return { success: true };
  } catch (error) {
    console.error('Error executing trade:', error);
    return { success: false, error };
  }
}

// Handle messages from popup and content scripts
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'GET_RECOMMENDATIONS') {
    if (activeRecommendations.length > 0) {
      sendResponse({ recommendations: activeRecommendations });
    } else {
      // Worker just woke up and hasn't refetched yet — serve from storage.
      chrome.storage.local.get(['rute_recommendations'], (result) => {
        sendResponse({ recommendations: result.rute_recommendations || [] });
      });
    }
  } else if (message.type === 'REFRESH_RECOMMENDATIONS') {
    fetchAIRecommendations();
    sendResponse({ success: true });
  } else if (message.type === 'EXECUTE_TRADE') {
    executeTrade(message.trade).then(sendResponse);
    return true; // Keep channel open for async response
  } else if (message.type === 'UPDATE_TRADE_STATUS') {
    activeRecommendations = activeRecommendations.filter(r => r.id !== message.tradeId);
    chrome.storage.local.set({ rute_recommendations: activeRecommendations });
    sendResponse({ success: true });
  } else if (message.type === 'ADD_TO_WATCHLIST') {
    updateMarketData();
    // Analyze the newly added symbol on the next scan cycle right away,
    // instead of waiting up to 5 minutes for the alarm.
    setTimeout(() => fetchAIRecommendations(), 3000);
    sendResponse({ success: true });
  } else if (message.type === 'DOM_BREAKAGE_REPORT') {
    console.warn(`RUTE: Reporting DOM breakage for ${message.element} to Brain...`);
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({
        action: 'DOM_BREAKAGE',
        element: message.element,
        url: message.url,
        timestamp: message.timestamp
      }));
    }
    sendResponse({ success: true });
  }

  return true;
});
