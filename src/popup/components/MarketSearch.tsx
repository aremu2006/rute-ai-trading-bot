import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Plus, TrendingUp, Bitcoin, BarChart2, ChevronRight } from 'lucide-react';
import { TOP_MARKETS, MarketSymbol } from '../utils/market-symbols';

interface MarketSearchProps {
  onAdd: (symbol: MarketSymbol) => void;
  onBulkAdd?: (symbols: MarketSymbol[]) => void;
  existingSymbols: string[];
}

const CATEGORY_CONFIG = {
  all:    { label: 'All',    color: 'text-white',        bg: 'bg-white/10',            border: 'border-white/20'          },
  crypto: { label: 'Crypto', color: 'text-orange-400',   bg: 'bg-orange-500/15',       border: 'border-orange-500/30'     },
  forex:  { label: 'Forex',  color: 'text-blue-400',     bg: 'bg-blue-500/15',         border: 'border-blue-500/30'       },
  stock:  { label: 'Stocks', color: 'text-emerald-400',  bg: 'bg-emerald-500/15',      border: 'border-emerald-500/30'    },
} as const;

type CategoryKey = keyof typeof CATEGORY_CONFIG;

const BadgeColors: Record<string, string> = {
  crypto: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  forex:  'bg-blue-500/20 text-blue-400 border-blue-500/30',
  stock:  'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
};

const MarketSearch: React.FC<MarketSearchProps> = ({ onAdd, onBulkAdd, existingSymbols }) => {
  const [query, setQuery]         = useState('');
  const [isOpen, setIsOpen]       = useState(false);
  const [activeTab, setActiveTab] = useState<CategoryKey>('all');
  const containerRef              = useRef<HTMLDivElement>(null);
  const queryRef                  = useRef(query);
  useEffect(() => { queryRef.current = query; }, [query]);

  // Clicking outside closes the dropdown — but only when nothing is typed,
  // so the dropdown stays open while typing even if you click elsewhere.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (queryRef.current.trim()) return;
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Leaving the search area with the mouse also closes it — but only when
  // the search box is empty; while typing it stays put.
  const handleMouseLeave = () => {
    if (!queryRef.current.trim()) setIsOpen(false);
  };

  // Filter markets based on query + active tab
  const getResults = (): MarketSymbol[] => {
    let pool = TOP_MARKETS.filter(m => !existingSymbols.includes(m.symbol));

    if (activeTab !== 'all') {
      pool = pool.filter(m => m.type === activeTab);
    }

    if (query.trim()) {
      const q = query.toLowerCase();
      pool = pool.filter(
        m => m.symbol.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
      );
    }

    return pool.slice(0, 30); // Show up to 30 results
  };

  const results = getResults();

  const handleSelect = (market: MarketSymbol) => {
    onAdd(market);
    setQuery('');
    setIsOpen(false);
  };

  const counts = {
    all:    TOP_MARKETS.filter(m => !existingSymbols.includes(m.symbol)).length,
    crypto: TOP_MARKETS.filter(m => m.type === 'crypto' && !existingSymbols.includes(m.symbol)).length,
    forex:  TOP_MARKETS.filter(m => m.type === 'forex'  && !existingSymbols.includes(m.symbol)).length,
    stock:  TOP_MARKETS.filter(m => m.type === 'stock'  && !existingSymbols.includes(m.symbol)).length,
  };

  return (
    <div className="relative w-full z-50" ref={containerRef} onMouseLeave={handleMouseLeave}>
      {/* Search Input */}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <Search className="h-4 w-4 text-muted" />
        </div>
        <input
          type="text"
          className="w-full bg-surface/60 border border-border/60 text-white rounded-xl pl-10 pr-10 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/60 transition-all placeholder:text-muted/60 shadow-inner text-sm"
          placeholder="Search 100 markets: BTC, EUR/USD, AAPL..."
          value={query}
          onChange={(e) => { setQuery(e.target.value); setIsOpen(true); }}
          onFocus={() => setIsOpen(true)}
        />
        {isOpen && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
            <ChevronRight className="h-3.5 w-3.5 text-muted/50 rotate-90" />
          </div>
        )}
      </div>

      {/* Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="absolute top-full left-0 right-0 mt-2 bg-[#111318]/98 backdrop-blur-2xl border border-white/10 rounded-2xl shadow-2xl overflow-hidden"
            style={{ maxHeight: '360px' }}
          >
            {/* Category Tabs */}
            <div className="flex items-center gap-1 p-2 border-b border-white/8 bg-white/3">
              {(Object.keys(CATEGORY_CONFIG) as CategoryKey[]).map(tab => {
                const cfg = CATEGORY_CONFIG[tab];
                const isActive = activeTab === tab;
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wide transition-all ${
                      isActive
                        ? `${cfg.bg} ${cfg.color} border ${cfg.border}`
                        : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                    }`}
                  >
                    {tab === 'crypto' && <Bitcoin className="w-3 h-3" />}
                    {tab === 'forex'  && <BarChart2 className="w-3 h-3" />}
                    {tab === 'stock'  && <TrendingUp className="w-3 h-3" />}
                    {tab === 'all'    && <Search className="w-3 h-3" />}
                    {cfg.label}
                    <span className={`text-[9px] px-1 py-0.5 rounded ml-0.5 ${isActive ? 'bg-white/20' : 'bg-white/8 text-gray-600'}`}>
                      {counts[tab]}
                    </span>
                  </button>
                );
              })}
              
              {activeTab !== 'all' && counts[activeTab] > 0 && onBulkAdd && (
                <button
                  onClick={() => {
                    const toAdd = TOP_MARKETS.filter(m => m.type === activeTab && !existingSymbols.includes(m.symbol));
                    onBulkAdd(toAdd);
                    setIsOpen(false);
                  }}
                  className="ml-auto flex items-center gap-1 px-2 py-1 rounded border border-primary/40 text-[10px] font-bold text-primary hover:bg-primary/10 transition-colors uppercase"
                >
                  <Plus className="w-3 h-3" /> Add All {counts[activeTab]}
                </button>
              )}
            </div>

            {/* Results List */}
            <div className="overflow-y-auto" style={{ maxHeight: '300px' }}>
              {results.length > 0 ? (
                <div className="py-1">
                  {results.map((market, idx) => (
                    <motion.button
                      key={market.symbol}
                      initial={{ opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: idx * 0.012 }}
                      onClick={() => handleSelect(market)}
                      className="w-full text-left px-3.5 py-2.5 hover:bg-white/6 flex items-center justify-between group transition-colors"
                    >
                      <div className="flex items-center space-x-3">
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-[10px] font-bold border ${BadgeColors[market.type]}`}>
                          {market.symbol.replace('=X', '').replace('-USD', '').slice(0, 3)}
                        </div>
                        <div>
                          <div className="flex items-center space-x-1.5">
                            <span className="text-sm font-semibold text-white leading-none">
                              {market.name}
                            </span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded-full border uppercase tracking-wider font-bold ${BadgeColors[market.type]}`}>
                              {market.type}
                            </span>
                          </div>
                          <span className="text-[10px] text-gray-500 mt-0.5 block">
                            {market.symbol.replace('=X', '').replace('-', '/')}
                          </span>
                        </div>
                      </div>
                      <div className="opacity-0 group-hover:opacity-100 transition-all w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center">
                        <Plus className="w-3.5 h-3.5 text-primary" />
                      </div>
                    </motion.button>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-8 text-center">
                  <Search className="w-6 h-6 text-muted/30 mx-auto mb-2" />
                  <p className="text-sm text-muted">No markets found</p>
                  <p className="text-xs text-muted/50 mt-1">All markets in this category may already be in your watchlist</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MarketSearch;
