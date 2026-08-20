import React, { useEffect, useState } from 'react';
import { Briefcase, Target, Shield, AlertTriangle, Activity, BrainCircuit, XCircle, CheckCircle } from 'lucide-react';

interface Trade {
  id: string;
  symbol: string;
  type: 'BUY' | 'SELL';
  entry: number;
  tp: number;
  sl: number;
}

interface PortfolioData {
  simulated: Trade[];
  live: any[];
  account?: {
    balance: number;
    equity: number;
    currency: string;
  } | null;
}

const Portfolio: React.FC = () => {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [scannerLogs, setScannerLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [viewMode, setViewMode] = useState<'positions' | 'scanner'>('positions');

  useEffect(() => {
    const fetchData = async () => {
      try {
        const settings = await new Promise<{ apiEndpoint: string }>((resolve) => {
          chrome.storage.local.get(['userSettings'], (res) => {
            let ep = res.userSettings?.apiEndpoint ?? 'http://127.0.0.1:8001';
            if (ep.includes('localhost')) ep = ep.replace('localhost', '127.0.0.1');
            resolve({ apiEndpoint: ep });
          });
        });
        
        // Fetch Portfolio Data
        const resPort = await fetch(`${settings.apiEndpoint}/api/portfolio`);
        if (resPort.ok) {
          setData(await resPort.json());
        }

        // Fetch Scanner Logs
        const resScan = await fetch(`${settings.apiEndpoint}/api/scan-log?limit=500`);
        if (resScan.ok) {
          const scanJson = await resScan.json();
          setScannerLogs(scanJson.events || []);
          setError('');
        }
      } catch (err: any) {
        setError(err.message || 'Connection error');
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
    const interval = setInterval(fetchData, 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <Activity className="w-8 h-8 text-primary animate-pulse" />
        <span className="text-muted">Loading portfolio...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <AlertTriangle className="w-8 h-8 text-red-400 mb-4" />
        <p className="text-red-400">{error}</p>
        <p className="text-muted text-sm mt-2">Ensure the backend is running.</p>
      </div>
    );
  }

  const allTrades = [...(data?.live || []), ...(data?.simulated || [])].map((t: any) => ({
    ...t,
    id: t.id ?? t.position_id,
    type: t.type || (t.side === 'long' ? 'BUY' : t.side === 'short' ? 'SELL' : t.side) || '—',
    entry: t.entry ?? t.entry_price,
    tp: t.tp ?? t.take_profit,
    sl: t.sl ?? t.stop_loss,
  }));
  // Filter logs to only show AI decisions (skip or signal)
  const decisionLogs = scannerLogs.filter(log => log.type === 'skip' || log.type === 'signal' || log.type === 'error');

  return (
    <div className="space-y-4">
      {/* Top Toggle */}
      <div className="flex bg-surface p-1 rounded-lg border border-border">
        <button
          onClick={() => setViewMode('positions')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 text-xs font-semibold rounded-md transition-all ${
            viewMode === 'positions' ? 'bg-gradient-to-r from-blue-500/25 to-violet-500/25 text-white border border-primary/30' : 'text-muted hover:text-zinc-300'
          }`}
        >
          <Briefcase className="w-4 h-4" />
          Open Positions
        </button>
        <button
          onClick={() => setViewMode('scanner')}
          className={`flex-1 flex items-center justify-center gap-2 py-2 text-xs font-semibold rounded-md transition-all ${
            viewMode === 'scanner' ? 'bg-gradient-to-r from-blue-500/25 to-violet-500/25 text-white border border-primary/30' : 'text-muted hover:text-zinc-300'
          }`}
        >
          <BrainCircuit className="w-4 h-4" />
          Decision Log
        </button>
      </div>

      {viewMode === 'positions' ? (
        <>
          {/* Header Stats */}
          <div className="glass-card p-4 rounded-xl flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Briefcase className="w-5 h-5 text-primary" />
                  Active Positions
                </h2>
                <p className="text-sm text-muted mt-1">
                  {data?.live?.length ? 'Live Auto-Trading' : 'Simulated Paper Trading'}
                </p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-mono font-bold text-white tabular-nums">{allTrades.length}</p>
                <p className="text-xs text-muted">Open Trades</p>
              </div>
            </div>
            
            {/* Account Info if Connected */}
            {data?.account && (
                      <div className="pt-3 border-t border-border/50 grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-[10px] text-muted uppercase tracking-wider mb-1">Balance</p>
                          <p className="font-mono text-sm text-white tabular-nums">
                            {(data.account.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {data.account.currency}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-[10px] text-muted uppercase tracking-wider mb-1">Equity</p>
                          <p className="font-mono text-sm text-white tabular-nums">
                            {(data.account.equity ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {data.account.currency}
                          </p>
                        </div>
                      </div>
                    )}
          </div>

          {allTrades.length === 0 ? (
            <div className="bg-surface/50 border border-border border-dashed rounded-xl p-8 text-center flex flex-col items-center">
              <Briefcase className="w-8 h-8 text-muted mb-3 opacity-50" />
              <p className="text-muted">No active positions</p>
              <p className="text-xs text-muted/70 mt-1">The AI is scanning for the next optimal entry.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {allTrades.map((trade: any, idx: number) => {
                const isBuy = trade.type === 'BUY';
                return (
                  <div key={trade.id || idx} className="glass-card rounded-xl p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isBuy ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'
                        }`}>
                          {trade.type}
                        </span>
                        <span className="font-bold text-white tracking-wide">{trade.symbol}</span>
                      </div>
                      <span className="text-[10px] bg-white/5 text-muted px-2 py-0.5 rounded border border-white/10">
                        {data?.live?.find((t: any) => t.id === trade.id) ? 'LIVE' : 'SIMULATED'}
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2">
                      <div className="bg-background rounded-lg p-2 flex flex-col items-center justify-center">
                        <span className="text-[10px] text-muted mb-1 uppercase tracking-wider">Entry</span>
                        <span className="font-mono text-xs text-white tabular-nums">{trade.entry != null ? trade.entry.toFixed(4) : '—'}</span>
                      </div>
                      <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-2 flex flex-col items-center justify-center">
                        <span className="text-[10px] text-green-400/70 flex items-center gap-1 mb-1 uppercase tracking-wider">
                          <Target className="w-3 h-3" /> TP
                        </span>
                        <span className="font-mono text-xs text-green-400 tabular-nums">{trade.tp != null ? trade.tp.toFixed(4) : '—'}</span>
                      </div>
                      <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-2 flex flex-col items-center justify-center">
                        <span className="text-[10px] text-red-400/70 flex items-center gap-1 mb-1 uppercase tracking-wider">
                          <Shield className="w-3 h-3" /> SL
                        </span>
                        <span className="font-mono text-xs text-red-400 tabular-nums">{trade.sl != null ? trade.sl.toFixed(4) : '—'}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      ) : (
        <div className="space-y-3">
          {decisionLogs.length === 0 ? (
            <div className="bg-surface/50 border border-border border-dashed rounded-xl p-8 text-center flex flex-col items-center">
              <BrainCircuit className="w-8 h-8 text-muted mb-3 opacity-50" />
              <p className="text-muted">No decisions logged yet.</p>
              <p className="text-xs text-muted/70 mt-1">Wait a few seconds for the next scan cycle.</p>
            </div>
          ) : (
            <>
              {scannerLogs.length > 0 && scannerLogs[0].type === 'scan_start' && (
                <div className="flex items-center gap-2 mt-2 px-3 py-1.5 bg-blue-500/10 border border-blue-500/20 rounded-md">
                  <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  <span className="text-blue-200">
                    Scanner Active: {scannerLogs[0].message}
                  </span>
                  <span className="ml-auto text-blue-400/50 font-mono">
                    {new Date(scannerLogs[0].ts).toLocaleTimeString()}
                  </span>
                </div>
              )}
              <div className="flex flex-col gap-3 h-[400px] overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent">
              {decisionLogs.map((log: any, idx: number) => {
                const isSignal = log.type === 'signal';
                const timeStr = new Date(log.ts).toLocaleTimeString();
                
                return (
                  <div key={idx} className={`border rounded-xl p-4 transition-all ${isSignal ? 'bg-green-500/10 border-green-500/30' : 'bg-surface border-border'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-2">
                        {isSignal ? (
                          <CheckCircle className="w-5 h-5 text-green-400" />
                        ) : (
                          <XCircle className="w-5 h-5 text-zinc-500" />
                        )}
                        <span className="font-bold text-white text-lg tracking-wide">{log.symbol}</span>
                      </div>
                      <div className="text-xs text-muted/70 font-mono">{timeStr}</div>
                    </div>

                    {log.type === 'skip' && (
                      <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Shield className="w-4 h-4 text-red-400" />
                          <span className="text-red-400 font-bold text-xs uppercase tracking-wider">Trade Rejected</span>
                        </div>
                        <p className="text-red-200/90 text-sm leading-relaxed font-medium">
                          {log.message}
                        </p>
                        {log.signals && log.signals.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-red-500/20 grid grid-cols-1 gap-1">
                            {log.signals.map((sig: string, i: number) => (
                              <div key={i} className="text-xs font-mono text-red-300/80">• {sig}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    
                    {log.type === 'error' && (
                      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-3 mb-3">
                        <div className="flex items-center gap-2 mb-1">
                          <AlertTriangle className="w-4 h-4 text-amber-400" />
                          <span className="text-amber-400 font-bold text-xs uppercase tracking-wider">Scan Error</span>
                        </div>
                        <p className="text-amber-200/90 text-sm leading-relaxed font-medium">
                          {log.message}
                        </p>
                      </div>
                    )}

                    {isSignal && (
                      <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-3 mb-3">
                        <div className="flex items-center gap-2 mb-1">
                          <CheckCircle className="w-4 h-4 text-green-400" />
                          <span className="text-green-400 font-bold text-xs uppercase tracking-wider">Trade Executed</span>
                        </div>
                        <p className="text-green-200/90 text-sm leading-relaxed font-medium">
                          {log.message}
                        </p>
                      </div>
                    )}
                    
                    {/* RICH DETAILS */}
                    {isSignal && log.details && Object.keys(log.details).length > 0 && (
                      <div className="grid grid-cols-2 gap-2 text-[10px]">
                        {log.details.rsi !== null && (
                          <div className="bg-background rounded p-2 flex justify-between items-center border border-white/5">
                            <span className="text-muted uppercase font-semibold">RSI</span>
                            <span className={log.details.rsi < 40 ? 'text-green-400' : log.details.rsi > 60 ? 'text-red-400' : 'text-white font-mono'}>{log.details.rsi}</span>
                          </div>
                        )}
                        {log.details.macd !== null && (
                          <div className="bg-background rounded p-2 flex justify-between items-center border border-white/5">
                            <span className="text-muted uppercase font-semibold">MACD</span>
                            <span className="text-white font-mono">{log.details.macd}</span>
                          </div>
                        )}
                        {log.details.hurst !== null && (
                          <div className="bg-background rounded p-2 flex justify-between items-center border border-white/5">
                            <span className="text-muted uppercase font-semibold">Hurst</span>
                            <span className={log.details.hurst < 0.5 ? 'text-red-400' : 'text-green-400 font-mono'}>{log.details.hurst}</span>
                          </div>
                        )}
                        {log.details.entropy !== null && (
                          <div className="bg-background rounded p-2 flex justify-between items-center border border-white/5">
                            <span className="text-muted uppercase font-semibold">Entropy</span>
                            <span className="text-white font-mono">{log.details.entropy}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default Portfolio;
