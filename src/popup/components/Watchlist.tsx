import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Plus, Trash2, TrendingUp, TrendingDown } from 'lucide-react';
import { WatchlistItem, MarketData } from '../../types';

const Watchlist: React.FC = () => {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [marketData, setMarketData] = useState<Record<string, MarketData>>({});
  const [newSymbol, setNewSymbol] = useState('');
  const [assetType, setAssetType] = useState<'FOREX' | 'STOCK'>('STOCK');
  const [addError, setAddError] = useState('');
  const [scanLog, setScanLog] = useState<any[]>([]);
  const [minConfidence, setMinConfidence] = useState(60);

  const fetchScanLog = async () => {
    try {
      const settings: any = await new Promise((resolve) => {
        if (typeof chrome !== 'undefined' && chrome.storage?.local) {
          chrome.storage.local.get(['userSettings', 'minConfidence'], resolve);
        } else {
          resolve({});
        }
      });
      const endpoint = settings.userSettings?.apiEndpoint || 'http://127.0.0.1:8001';
      if (settings.minConfidence) setMinConfidence(settings.minConfidence);
      const res = await fetch(`${endpoint}/api/scan-log?limit=60`);
      if (res.ok) {
        const data = await res.json();
        setScanLog(data.events || []);
      }
    } catch {
      // backend offline — keep last known status
    }
  };

  useEffect(() => {
    loadWatchlist();
    fetchScanLog();
    const scanInterval = setInterval(fetchScanLog, 10000);

    if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
      const listener = (message: any) => {
        if (message.type === 'MARKET_DATA_UPDATE') {
          setMarketData(message.data);
        }
      };
      chrome.runtime.onMessage.addListener(listener);
      return () => {
        chrome.runtime.onMessage.removeListener(listener);
        clearInterval(scanInterval);
      };
    }
    return () => clearInterval(scanInterval);
  }, []);

  interface SymbolStatus {
    type: 'signal' | 'skip' | 'none';
    action?: string;
    confidence?: number;
    ts?: string;
  }

  const getSymbolStatus = (symbol: string): SymbolStatus => {
    const events = scanLog
      .filter((e) => e.symbol === symbol && (e.type === 'signal' || e.type === 'skip'))
      .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
    const latest = events[0];
    if (!latest) return { type: 'none' };
    if (latest.type === 'signal') {
      return { type: 'signal', action: latest.action, confidence: latest.confidence, ts: latest.ts };
    }
    return { type: 'skip', confidence: latest.confidence, ts: latest.ts };
  };

  const ageText = (ts?: string): string => {
    if (!ts || isNaN(new Date(ts).getTime())) return 'waiting for next scan (every ~5 min)';
    const seconds = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000));
    if (seconds < 60) return `checked ${seconds}s ago`;
    return `checked ${Math.round(seconds / 60)}m ago`;
  };

  const loadWatchlist = () => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['watchlist'], (result) => {
        if (result.watchlist) {
          setWatchlist(result.watchlist);
        }
      });
    }
  };

  const addToWatchlist = () => {
    if (!newSymbol.trim()) return;

    const symbol = newSymbol.trim().toUpperCase();
    if (watchlist.some(w => w.symbol.toUpperCase() === symbol)) {
      setAddError(`${symbol} is already in your watchlist`);
      return;
    }

    const item: WatchlistItem = {
      symbol,
      assetType,
      addedAt: Date.now(),
    };

    setAddError('');
    const updated = [...watchlist, item];
    setWatchlist(updated);

    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.set({ watchlist: updated });
    }

    setNewSymbol('');

    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'ADD_TO_WATCHLIST', symbol: item.symbol });
    }
  };

  const removeFromWatchlist = (symbol: string) => {
    const updated = watchlist.filter(item => item.symbol !== symbol);
    setWatchlist(updated);
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.set({ watchlist: updated });
    }
  };

  return (
    <div className="space-y-4 pb-4">
      {/* Add Symbol Form */}
      <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-white mb-3">Add Symbol</h3>
        <div className="space-y-3">
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => {
              setNewSymbol(e.target.value);
              if (addError) setAddError('');
            }}
            placeholder="Enter symbol (e.g., AAPL, EUR/USD)"
            className="w-full px-4 py-2 bg-slate-900/50 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            onKeyDown={(e) => e.key === 'Enter' && addToWatchlist()}
          />
          {addError && (
            <p className="text-xs text-red-400">{addError}</p>
          )}
          <div className="flex space-x-3">
            <div className="flex space-x-2">
              <button
                onClick={() => setAssetType('STOCK')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  assetType === 'STOCK'
                    ? 'bg-blue-500 text-white'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                Stock
              </button>
              <button
                onClick={() => setAssetType('FOREX')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  assetType === 'FOREX'
                    ? 'bg-blue-500 text-white'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                Forex
              </button>
            </div>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={addToWatchlist}
              className="flex-1 px-4 py-2 bg-gradient-to-r from-blue-500 to-cyan-500 rounded-lg text-sm font-semibold text-white"
            >
              <Plus className="w-4 h-4 inline mr-1" />
              Add
            </motion.button>
          </div>
        </div>
      </div>

      {/* Watchlist Items */}
      <div className="space-y-2">
        {watchlist.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-400 text-sm">Your watchlist is empty</p>
            <p className="text-slate-500 text-xs mt-1">Add symbols to monitor market data</p>
          </div>
        ) : (
          watchlist.map((item, index) => {
            const data = marketData[item.symbol];
            const isPositive = data && data.change >= 0;

            return (
              <motion.div
                key={item.symbol}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      isPositive ? 'bg-green-500/20' : 'bg-red-500/20'
                    }`}>
                      {isPositive ? (
                        <TrendingUp className="w-5 h-5 text-green-400" />
                      ) : (
                        <TrendingDown className="w-5 h-5 text-red-400" />
                      )}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-white">{item.symbol}</h4>
                      <p className="text-xs text-slate-400">{item.assetType}</p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-4">
                    {data ? (
                      <div className="text-right">
                        <span className="text-white text-base font-bold tabular-nums">
                          ${(data?.price ?? 0).toFixed(2)}
                        </span>
                        <span className={`text-xs font-semibold tabular-nums px-1.5 py-0.5 rounded ${
                          isPositive ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                        }`}>
                          {isPositive ? '+' : ''}{(data?.changePercent ?? 0).toFixed(2)}%
                        </span>
                      </div>
                    ) : (
                      <div className="text-right">
                        <p className="text-xs text-slate-500">Loading...</p>
                      </div>
                    )}

                    <button
                      onClick={() => removeFromWatchlist(item.symbol)}
                      className="p-2 hover:bg-slate-700 rounded-lg transition-colors"
                    >
                      <Trash2 className="w-4 h-4 text-slate-400 hover:text-red-400" />
                    </button>
                  </div>
                </div>

                {/* Monitoring status — shows RUTE is actively checking this market */}
                {(() => {
                  const st = getSymbolStatus(item.symbol);
                  const matched = st.confidence !== undefined && st.confidence >= minConfidence;
                  return (
                    <div className="mt-2 flex items-center gap-2 text-[10px]">
                      {st.type === 'signal' ? (
                        <span className={`px-2 py-0.5 rounded font-bold border ${
                          matched
                            ? 'bg-green-500/20 text-green-400 border-green-500/30'
                            : 'bg-amber-500/15 text-amber-400 border-amber-500/30'
                        }`}>
                          SIGNAL: {st.action} {st.confidence}%{matched ? ` · matched threshold ${minConfidence}%` : ` · below threshold ${minConfidence}%`}
                        </span>
                      ) : st.type === 'skip' ? (
                        <span className="px-2 py-0.5 rounded bg-slate-700/40 text-slate-300 border border-slate-600/50">
                          CHECKED{st.confidence !== undefined ? ` · ${st.confidence}%` : ''} · no signal
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20 animate-pulse">
                          MONITORING · first scan pending
                        </span>
                      )}
                      <span className="text-slate-500">{ageText(st.ts)}</span>
                    </div>
                  );
                })()}
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default Watchlist;
