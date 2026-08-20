import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Calendar, DollarSign, Compass, Info, ChevronDown, ChevronUp } from 'lucide-react';
import { TradeLog } from '../../types';
import { format } from 'date-fns';

const TradeHistory: React.FC = () => {
  const [tradeLogs, setTradeLogs] = useState<TradeLog[]>([]);
  const [stats, setStats] = useState({
    totalTrades: 0,
    profitable: 0,
    totalProfit: 0,
  });
  const [expandedTradeId, setExpandedTradeId] = useState<string | null>(null);

  useEffect(() => {
    loadTradeHistory();
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.onChanged) {
      const listener = (changes: any, area: string) => {
        if (area === 'local' && changes.tradeLogs) loadTradeHistory();
      };
      chrome.storage.onChanged.addListener(listener);
      return () => chrome.storage.onChanged.removeListener(listener);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadTradeHistory = () => {
    if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
      chrome.storage.local.get(['tradeLogs'], (result) => {
        if (result.tradeLogs) {
          const logs: TradeLog[] = result.tradeLogs;
          setTradeLogs(logs);

          const profitable = logs.filter(log => log.result && log.result.profit > 0).length;
          const totalProfit = logs.reduce((sum, log) => sum + (log.result?.profit || 0), 0);

          setStats({ totalTrades: logs.length, profitable, totalProfit });
        }
      });
    }
  };

  return (
    <div className="space-y-4 pb-20">
      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="glass-card rounded-xl p-3">
          <p className="text-xs text-muted mb-1">Trades</p>
          <p className="text-lg font-bold text-white font-mono tabular-nums">{stats.totalTrades}</p>
        </div>
        <div className="glass-card rounded-xl p-3">
          <p className="text-xs text-muted mb-1">Win Rate</p>
          <p className="text-lg font-bold text-accent font-mono tabular-nums">
            {stats.totalTrades > 0 ? ((stats.profitable / stats.totalTrades) * 100).toFixed(0) : 0}%
          </p>
        </div>
        <div className="glass-card rounded-xl p-3">
          <p className="text-xs text-muted mb-1">Total P&L</p>
          <p className={`text-lg font-bold font-mono tabular-nums ${stats.totalProfit >= 0 ? 'text-accent' : 'text-danger'}`}>
            ${stats.totalProfit.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Trade Logs */}
      <div className="space-y-2">
        {tradeLogs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 space-y-4">
            <div className="relative">
              <motion.div animate={{ rotate: 180 }} transition={{ duration: 10, repeat: Infinity, ease: "linear" }} className="w-16 h-16 border border-dashed border-muted rounded-full flex items-center justify-center opacity-50">
                <Calendar className="w-6 h-6 text-muted" />
              </motion.div>
            </div>
            <div className="text-center">
              <p className="text-white font-medium text-sm">Awaiting First Trade</p>
              <p className="text-muted/60 text-xs mt-1">Executed trades and P&L will appear here</p>
            </div>
          </div>
        ) : (
          tradeLogs.map((log, index) => {
            const isBuy = log.recommendation.type === 'BUY';
            const isProfit = log.result && log.result.profit > 0;

            return (
              <motion.div
                key={log.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
                className={`bg-surface border rounded-xl p-4 transition-colors cursor-pointer ${
                  expandedTradeId === log.id ? 'border-zinc-600' : 'border-border'
                }`}
                onClick={() => setExpandedTradeId(expandedTradeId === log.id ? null : log.id)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      isBuy ? 'bg-accent/15' : 'bg-danger/15'
                    }`}>
                      {isBuy ? (
                        <TrendingUp className="w-4 h-4 text-accent" />
                      ) : (
                        <TrendingDown className="w-4 h-4 text-danger" />
                      )}
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-white">{log.recommendation.symbol}</h4>
                      <p className="text-xs text-muted">{log.recommendation.assetType}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end space-y-1.5">
                    <div className={`px-2.5 py-0.5 rounded text-xs font-semibold ${
                      isBuy ? 'bg-accent/15 text-accent' : 'bg-danger/15 text-danger'
                    }`}>
                      {log.recommendation.type}
                    </div>
                    {expandedTradeId === log.id ? (
                      <ChevronUp className="w-3.5 h-3.5 text-muted" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-muted" />
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="bg-background border border-border rounded-lg p-2">
                    <p className="text-xs text-muted mb-0.5">Entry</p>
                    <p className="text-sm font-mono font-medium text-white tabular-nums">${log.executionPrice.toFixed(2)}</p>
                  </div>
                  {log.result && (
                    <div className="bg-background border border-border rounded-lg p-2">
                      <p className="text-xs text-muted mb-0.5">Exit</p>
                      <p className="text-sm font-mono font-medium text-white tabular-nums">${log.result.exitPrice.toFixed(2)}</p>
                    </div>
                  )}
                </div>

                {log.result && (
                  <div className={`px-3 py-2 rounded-lg flex items-center justify-between ${
                    isProfit ? 'bg-accent/8 border border-accent/20' : 'bg-danger/8 border border-danger/20'
                  }`}>
                    <div className="flex items-center space-x-2">
                      <DollarSign className={`w-3.5 h-3.5 ${isProfit ? 'text-accent' : 'text-danger'}`} />
                      <span className="text-xs text-muted">P&L</span>
                    </div>
                    <span className={`text-sm font-bold font-mono tabular-nums ${isProfit ? 'text-accent' : 'text-danger'}`}>
                      {isProfit ? '+' : ''}${log.result.profit.toFixed(2)}
                    </span>
                  </div>
                )}

                {/* Expanded Details */}
                {expandedTradeId === log.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    className="mt-4 pt-4 border-t border-border space-y-4"
                  >
                    {/* CNS Context */}
                    <div className="space-y-2">
                      <div className="flex items-center space-x-2 text-muted">
                        <Compass className="w-3.5 h-3.5" />
                        <h5 className="text-xs font-medium">Market Context</h5>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-background border border-border p-2 rounded-lg">
                          <p className="text-[10px] text-muted mb-0.5">DXY Trend</p>
                          <p className="text-xs font-mono text-white">{log.recommendation.reasoning.cnsContext?.dxy_trend ?? '—'}</p>
                        </div>
                        <div className="bg-background border border-border p-2 rounded-lg">
                          <p className="text-[10px] text-muted mb-0.5">Hurst</p>
                          <p className="text-xs font-mono text-white">{log.recommendation.reasoning.cnsContext?.hurst ?? '—'}</p>
                        </div>
                        <div className="bg-background border border-border p-2 rounded-lg">
                          <p className="text-[10px] text-muted mb-0.5">Entropy</p>
                          <p className="text-xs font-mono text-white">{log.recommendation.reasoning.cnsContext?.entropy ?? '—'}</p>
                        </div>
                        <div className="bg-background border border-border p-2 rounded-lg">
                          <p className="text-[10px] text-muted mb-0.5">Institutional</p>
                          <p className="text-xs font-mono text-white">
                            {log.recommendation.reasoning.cnsContext?.institutional_wall ? 'Wall detected' : 'Clear'}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Reasoning */}
                    <div className="space-y-2">
                      <h5 className="text-xs font-medium text-muted">Why this trade</h5>
                      <p className="text-xs leading-relaxed text-gray-300 italic">
                        "{log.recommendation.reasoning.summary}"
                      </p>
                    </div>

                    {log.result?.exitReason && (
                      <div className="space-y-1">
                        <div className="flex items-center space-x-2 text-muted">
                          <Info className="w-3.5 h-3.5" />
                          <h5 className="text-xs font-medium">Exit reason</h5>
                        </div>
                        <p className="text-xs leading-relaxed text-gray-300">
                          {log.result.exitReason}
                        </p>
                      </div>
                    )}
                  </motion.div>
                )}

                <div className="flex items-center mt-3 text-xs text-muted">
                  <Calendar className="w-3 h-3 mr-1.5" />
                  <span>{format(new Date(log.executedAt), 'MMM dd, HH:mm')}</span>
                </div>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default TradeHistory;
