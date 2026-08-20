import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowUpRight, ArrowDownRight, RefreshCw, X } from 'lucide-react';
import MarketSearch from './MarketSearch';
import { Skeleton } from '@/components/ui/skeleton';

interface MarketTicker {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  lastUpdate: number;
}

interface WatchlistItem {
  symbol: string;
  name: string;
  type: 'forex' | 'stock' | 'crypto';
  assetType?: string;
  addedAt?: number;
}

// Normalize any item shape to the shared watchlist format.
const normalizeItem = (w: any): WatchlistItem => {
  const symbol = w.symbol;
  let type = w.type;
  if (!type) {
    type = symbol.endsWith('-USD') ? 'crypto' : symbol.endsWith('=X') ? 'forex' : 'stock';
  }
  return {
    symbol,
    name: w.name || symbol,
    type,
    assetType: w.assetType || type.toUpperCase(),
    addedAt: w.addedAt || Date.now(),
  };
};

const DEFAULT_SYMBOLS: WatchlistItem[] = [
  { symbol: 'EURUSD=X', name: 'EUR/USD', type: 'forex' },
  { symbol: 'GBPUSD=X', name: 'GBP/USD', type: 'forex' },
  { symbol: 'USDJPY=X', name: 'USD/JPY', type: 'forex' },
  { symbol: 'AAPL', name: 'Apple Inc.', type: 'stock' },
  { symbol: 'TSLA', name: 'Tesla Inc.', type: 'stock' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', type: 'stock' },
  { symbol: 'BTC-USD', name: 'Bitcoin', type: 'crypto' },
  { symbol: 'ETH-USD', name: 'Ethereum', type: 'crypto' },
  { symbol: 'SOL-USD', name: 'Solana', type: 'crypto' },
];

const TYPE_STYLE: Record<WatchlistItem['type'], { chip: string; text: string; label: string }> = {
  crypto: { chip: 'bg-amber-500/15 border-amber-500/30 text-amber-400', text: 'text-amber-400', label: 'C' },
  stock: { chip: 'bg-blue-500/15 border-blue-500/30 text-blue-400', text: 'text-blue-400', label: 'S' },
  forex: { chip: 'bg-violet-500/15 border-violet-500/30 text-violet-400', text: 'text-violet-400', label: 'F' },
};

const LiveMarket: React.FC = () => {
  const [marketData, setMarketData] = useState<MarketTicker[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>(DEFAULT_SYMBOLS);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState<'all' | 'forex' | 'stock' | 'crypto'>('all');
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Load the shared watchlist (the same list the background scanner uses).
  // Migrates the old marketWatchlist into it if present.
  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(['watchlist', 'marketWatchlist'], (result) => {
        let list: WatchlistItem[] | null = null;
        if (result.watchlist && Array.isArray(result.watchlist) && result.watchlist.length > 0) {
          list = result.watchlist.map(normalizeItem);
        } else if (result.marketWatchlist && Array.isArray(result.marketWatchlist) && result.marketWatchlist.length > 0) {
          list = result.marketWatchlist.map(normalizeItem);
          chrome.storage.local.remove('marketWatchlist');
        }
        if (list) {
          setWatchlist(list);
        } else {
          // Seed the scanner's list with the defaults so it is never empty.
          saveWatchlist(DEFAULT_SYMBOLS.map(normalizeItem));
        }
      });
    }
  }, []);

  const saveWatchlist = (newList: WatchlistItem[], onSaved?: () => void) => {
    setWatchlist(newList);
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.set({ watchlist: newList }, () => onSaved?.());
    } else {
      onSaved?.();
    }
  };



  const handleRemoveSymbol = (symbolToRemove: string) => {
    saveWatchlist(watchlist.filter(s => s.symbol !== symbolToRemove));
  };

  // Shared abort controller so effect cleanup can cancel in-flight requests
  // (prevents stale responses from spawning duplicate polling loops).
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let timeoutId: number;

    const loop = async () => {
      await fetchMarketData();
      if (autoRefresh) {
        timeoutId = window.setTimeout(loop, 60000);
      }
    };

    loop();

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      abortRef.current?.abort();
    };
  }, [autoRefresh, watchlist]);

  const fetchMarketData = async () => {
    try {
      setLoading(true);

      let apiEndpoint = 'http://127.0.0.1:8001';
      let apiKeys = undefined;

      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        try {
          const result = await new Promise<any>((resolve) => {
            chrome.storage.local.get(['userSettings'], resolve);
          });
          if (result?.userSettings?.apiEndpoint) {
            apiEndpoint = result.userSettings.apiEndpoint;
          }
          if (result?.userSettings?.apiKeys) {
            apiKeys = result.userSettings.apiKeys;
          }
        } catch {
          // use default
        }
      }

      try {
        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const response = await fetch(`${apiEndpoint}/market/live`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            symbols: watchlist.map(s => s.symbol),
            apiKeys: apiKeys
          }),
          signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
          const data = await response.json();
          if (data.marketData && data.marketData.length > 0) {
            setMarketData(data.marketData.map((d: any) => ({ ...d, simulated: !!d.simulated })));
          } else {
            setMarketData(generateSimulatedData(watchlist));
          }
        } else {
          setMarketData(generateSimulatedData(watchlist));
        }
      } catch (err: any) {
        // Ignore aborts — a newer watchlist/effect owns the next fetch now.
        if (err?.name === 'AbortError') return;
        setMarketData(generateSimulatedData(watchlist));
      }
      setLoading(false);
    } catch {
      setMarketData(generateSimulatedData(watchlist));
      setLoading(false);
    }
  };

  const generateSimulatedData = (currentWatchlist: WatchlistItem[]) => {
    return currentWatchlist.map(s => {
      const basePrice = s.type === 'crypto' ? 50000 : s.type === 'forex' ? 1.1 : 150;
      const change = (Math.random() * 2 - 1) * (basePrice * 0.02);
      return {
        symbol: s.symbol,
        name: s.name,
        simulated: true,
        price: basePrice + change,
        change,
        changePercent: (change / basePrice) * 100,
        volume: Math.floor(Math.random() * 10000000),
        high: basePrice + Math.abs(change) * 0.5,
        low: basePrice - Math.abs(change) * 0.5,
        lastUpdate: Date.now(),
      };
    });
  };

  const filteredData = marketData.filter(item => {
    if (selectedType === 'all') return true;
    return watchlist.find(s => s.symbol === item.symbol)?.type === selectedType;
  });

  const fmtPrice = (num: number) => {
    if (!Number.isFinite(num)) return '—';
    if (num < 0.0001) return num.toFixed(8);
    if (num < 0.01) return num.toFixed(6);
    if (num < 1) return num.toFixed(4);
    return num.toFixed(2);
  };

  const fmt = (num: number, decimals = 2) => (Number.isFinite(num) ? num.toFixed(decimals) : '—');

  const fmtVolume = (v: number) => {
    if (!Number.isFinite(v)) return '—';
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
    return v.toString();
  };

  const typeOf = (symbol: string) => watchlist.find(s => s.symbol === symbol)?.type ?? 'stock';

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-white tracking-tight">Live Market</h2>
        <motion.button
          whileTap={{ scale: 0.9, rotate: 180 }}
          onClick={fetchMarketData}
          className="p-1.5 glass-card rounded-lg"
          title="Refresh"
        >
          <RefreshCw className="w-3.5 h-3.5 text-muted" />
        </motion.button>
      </div>

      {/* Add Symbol via Search */}
      <div className="relative z-50">
        <MarketSearch 
          onAdd={(market) => {
            if (!watchlist.find(s => s.symbol === market.symbol)) {
              saveWatchlist([...watchlist, { symbol: market.symbol, name: market.name, type: market.type }], () => {
                // Only ping the background AFTER the storage write completes,
                // so its scan reads the updated watchlist (not the stale one).
                if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
                  chrome.runtime.sendMessage({ type: 'ADD_TO_WATCHLIST', symbol: market.symbol });
                }
              });
            }
          }}
          onBulkAdd={(markets) => {
            const toAdd = markets.filter(m => !watchlist.find(w => w.symbol === m.symbol));
            if (toAdd.length > 0) {
              saveWatchlist([...watchlist, ...toAdd], () => {
                if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
                  chrome.runtime.sendMessage({ type: 'ADD_TO_WATCHLIST', symbol: toAdd.map(m => m.symbol).join(',') });
                }
              });
            }
          }}
          existingSymbols={watchlist.map(w => w.symbol)}
        />
      </div>

      {/* Type Filter */}
      <div className="flex space-x-1.5">
        {(['all', 'forex', 'stock', 'crypto'] as const).map((type) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            className={`px-3 py-1.5 rounded-full text-[11px] font-medium capitalize transition-all ${
              selectedType === type
                ? 'bg-gradient-to-r from-blue-500/25 to-violet-500/25 text-white border border-primary/30 shadow-[0_0_10px_rgba(59,130,246,0.15)]'
                : 'glass-card text-zinc-500 hover:text-white'
            }`}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Market Table */}
      <div className="glass-panel rounded-xl overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-[1fr_88px_64px_52px] items-center gap-2 px-3 py-2 border-b border-white/[0.07] bg-white/[0.02]">
          <span className="text-[9px] uppercase tracking-[0.12em] text-muted font-semibold">Symbol</span>
          <span className="text-[9px] uppercase tracking-[0.12em] text-muted font-semibold text-right">Price</span>
          <span className="text-[9px] uppercase tracking-[0.12em] text-muted font-semibold text-right">24h</span>
          <span className="text-[9px] uppercase tracking-[0.12em] text-muted font-semibold text-right">Vol</span>
        </div>

        {loading && marketData.length === 0 ? (
          <div className="space-y-1 py-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_88px_64px_52px] items-center gap-2 px-3 py-2.5"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <Skeleton className="w-6 h-6 rounded-md" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-2.5 w-14" />
                  </div>
                </div>
                <div className="justify-self-end">
                  <Skeleton className="h-3.5 w-14" />
                </div>
                <div className="justify-self-end">
                  <Skeleton className="h-4 w-10 rounded-md" />
                </div>
                <div className="justify-self-end">
                  <Skeleton className="h-3 w-10" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <AnimatePresence mode="popLayout" initial={false}>
            {filteredData.map((item) => {
              const isPositive = item.change >= 0;
              const PosIcon = isPositive ? ArrowUpRight : ArrowDownRight;
              const posColor = isPositive ? 'text-emerald-400' : 'text-red-400';
              const posPill = isPositive
                ? 'bg-emerald-500/[0.08] border-emerald-500/20 text-emerald-400'
                : 'bg-red-500/[0.08] border-red-500/20 text-red-400';
              const type = typeOf(item.symbol);
              const tStyle = TYPE_STYLE[type];

              return (
                <motion.div
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.96 }}
                  key={item.symbol}
                  className="group relative grid grid-cols-[1fr_88px_64px_52px] items-center gap-2 px-3 py-2.5 border-b border-white/[0.04] last:border-b-0 hover:bg-white/[0.04] transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className={`w-6 h-6 shrink-0 rounded-md border flex items-center justify-center text-[10px] font-bold ${tStyle.chip}`}>
                      {tStyle.label}
                    </span>
                    <div className="min-w-0">
                      <h3 className="text-[13px] font-semibold text-white leading-tight truncate flex items-center gap-1.5">
                        {item.symbol}
                        {(item as any).simulated && (
                          <span className="px-1 py-px rounded bg-amber-500/15 border border-amber-500/40 text-amber-300 text-[8px] font-bold tracking-wide uppercase shrink-0"
                            title="Backend unreachable — fabricated quote for demo purposes only">
                            SIM
                          </span>
                        )}
                      </h3>
                      <p className="text-[10px] text-muted leading-tight truncate">{item.name || item.symbol}</p>
                    </div>
                  </div>

                  <div className="text-right">
                    <p className="text-[13px] font-semibold text-white font-mono tabular-nums leading-tight">
                      {fmtPrice(item.price)}
                    </p>
                  </div>

                  <div className="text-right">
                    <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-semibold border tabular-nums ${posPill}`}>
                      <PosIcon className="w-2.5 h-2.5" />
                      {isPositive ? '+' : ''}{fmt(item.changePercent)}%
                    </span>
                  </div>

                  <div className="text-right">
                    <p className="text-[10px] text-zinc-500 font-mono tabular-nums leading-tight">{fmtVolume(item.volume)}</p>
                  </div>

                  <button
                    onClick={() => handleRemoveSymbol(item.symbol)}
                    className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 p-1 text-zinc-500 hover:text-red-400 transition-all rounded-md hover:bg-red-500/10"
                    title="Remove from watchlist"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </motion.div>
              );
            })}
          </AnimatePresence>
        )}

        {!loading && filteredData.length === 0 && (
          <div className="text-center py-8">
            <p className="text-xs text-muted">No symbols found in this category.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveMarket;