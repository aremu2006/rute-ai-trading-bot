import React, { useEffect, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FlaskConical, Play, RotateCw, AlertCircle, TrendingUp, TrendingDown, Minus, ScanLine, ChevronDown, ChevronUp, Zap, CheckCircle2 } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface BacktestResult {
  strategy: string;
  params: Record<string, number>;
  symbol: string;
  interval: string;
  bars: number;
  total_return_pct: number;
  annual_return_pct: number;
  trade_count: number;
  win_rate_pct: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_trade_pct: number;
  best_trade_pct: number;
  worst_trade_pct: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  exposure_pct: number;
  equity_curve: number[];
  final_equity: number;
  error?: string;
}

interface LiveRow {
  symbol: string;
  signals?: Record<string, string>;
  error?: string;
}

interface RegimeResult {
  regime: string;
  regime_label: string;
  confidence: number;
  suggested_strategies: string[];
  description: string;
  adx: number;
  atr_pct: number;
  rsi: number;
  ema_bias: string;
  symbol: string;
  interval: string;
}

const REGIME_BADGE_CLS: Record<string, string> = {
  trending_up:     'bg-emerald-500/15 border border-emerald-500/40 text-emerald-300',
  trending_down:   'bg-red-500/15 border border-red-500/40 text-red-300',
  ranging:         'bg-blue-500/15 border border-blue-500/40 text-blue-300',
  low_volatility:  'bg-blue-500/15 border border-blue-500/40 text-blue-300',
  high_volatility: 'bg-amber-500/15 border border-amber-500/40 text-amber-300',
  neutral:         'bg-zinc-500/10 border border-zinc-500/30 text-zinc-400',
};

const STRATEGIES = [
  { id: 'rsi',         label: 'RSI Reversal' },
  { id: 'macd',        label: 'MACD Cross' },
  { id: 'sma_cross',   label: 'SMA Cross' },
  { id: 'bollinger',   label: 'Bollinger' },
  { id: 'alpha_trend', label: 'AlphaTrend' },
  { id: 'gainzalgo',   label: 'GainzAlgo' },
];

const INTERVALS = ['1d', '1h', '5m'];
const ACTIVE_KEY     = 'rute_active_strategies';
const OPT_PARAMS_KEY = 'rute_opt_params';

// Auto-cap lookback by interval — 5m over 2y = 105k bars, too slow
const PERIODS_BY_INTERVAL: Record<string, string[]> = {
  '5m': ['1d', '5d', '1mo'],
  '1h': ['1mo', '3mo', '6m'],
  '1d': ['6m', '1y', '2y', '5y'],
};
const DEFAULT_PERIOD_BY_INTERVAL: Record<string, string> = {
  '5m': '5d', '1h': '3mo', '1d': '2y',
};

// ---------------------------------------------------------------------------
// Storage helpers — always chrome.storage.local, never localStorage
// ---------------------------------------------------------------------------
const chromeGet = <T,>(keys: string[]): Promise<Record<string, T>> =>
  new Promise((resolve) => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(keys, (r) => resolve(r as Record<string, T>));
    } else { resolve({}); }
  });

const chromeSet = (data: Record<string, unknown>) => {
  if (typeof chrome !== 'undefined' && chrome.storage?.local) {
    chrome.storage.local.set(data);
  }
};

const getSettings = async (): Promise<{ apiEndpoint: string; apiKeys?: Record<string, string> }> => {
  const res = await chromeGet<{ apiEndpoint?: string; apiKeys?: Record<string, string> }>(['userSettings']);
  return {
    apiEndpoint: res.userSettings?.apiEndpoint ?? 'http://127.0.0.1:8001',
    apiKeys: res.userSettings?.apiKeys,
  };
};

const loadActive = async (): Promise<string[]> => {
  const res = await chromeGet<string[]>([ACTIVE_KEY]);
  const stored = res[ACTIVE_KEY];
  if (Array.isArray(stored) && stored.length > 0) {
    return (stored as string[]).filter((s) => STRATEGIES.some((x) => x.id === s));
  }
  return STRATEGIES.map((s) => s.id);
};

const saveActive = (list: string[]) => chromeSet({ [ACTIVE_KEY]: list });

const Metric: React.FC<{ label: string; value: string; tone?: 'good' | 'bad' | 'neutral' }> = ({ label, value, tone = 'neutral' }) => {
  const toneCls = tone === 'good' ? 'text-emerald-400' : tone === 'bad' ? 'text-red-400' : 'text-white';
  return (
    <div className="glass-card rounded-xl px-2.5 py-2">
      <p className="text-[9px] uppercase tracking-wider text-muted">{label}</p>
      <p className={`text-sm font-mono font-bold tabular-nums ${toneCls}`}>{value}</p>
    </div>
  );
};

const Sparkline: React.FC<{ points: number[] }> = ({ points }) => {
  if (!points || points.length < 2) return null;
  const w = 100;
  const h = 32;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const stepX = w / (points.length - 1);
  const coords = points.map((p, i) => `${(i * stepX).toFixed(1)},${(h - 3 - ((p - min) / span) * (h - 6)).toFixed(1)}`);
  const up = points[points.length - 1] >= points[0];
  const color = up ? '#34d399' : '#f87171';
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-8" preserveAspectRatio="none">
      <defs>
        <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${h} ${coords.join(' ')} ${w},${h}`} fill="url(#sparkFill)" />
      <polyline points={coords.join(' ')} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
};

const SignalBadge: React.FC<{ signal: string }> = ({ signal }) => {
  if (signal === 'buy')
    return <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[9px] font-bold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 uppercase"><TrendingUp className="w-2.5 h-2.5" />Buy</span>;
  if (signal === 'sell')
    return <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[9px] font-bold bg-red-500/15 border border-red-500/30 text-red-400 uppercase"><TrendingDown className="w-2.5 h-2.5" />Sell</span>;
  return <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[9px] font-bold bg-zinc-500/10 border border-zinc-500/25 text-zinc-500 uppercase"><Minus className="w-2.5 h-2.5" />Flat</span>;
};

/** Consensus badge — fires when >= threshold strategies agree on the same direction */
const ConsensusTag: React.FC<{
  signals: Record<string, string>;
  active: string[];
  threshold?: number;
}> = ({ signals, active, threshold = 3 }) => {
  const buys  = active.filter((s) => signals[s] === 'buy').length;
  const sells = active.filter((s) => signals[s] === 'sell').length;
  if (buys >= threshold)
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/20 border border-emerald-400/50 text-emerald-300"><Zap className="w-3 h-3" />{buys}/{active.length} BUY</span>;
  if (sells >= threshold)
    return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-red-500/20 border border-red-400/50 text-red-300"><Zap className="w-3 h-3" />{sells}/{active.length} SELL</span>;
  return null;
};

const Backtest: React.FC = () => {
  const [symbol,       setSymbol]       = useState('BTC-USD');
  const [interval,     setIntervalVal]  = useState('1d');
  const [period,       setPeriod]       = useState('2y');
  const [strategies,   setStrategies]   = useState<string[]>(STRATEGIES.map((s) => s.id));
  const [activeStrats, setActiveStrats] = useState<string[]>(STRATEGIES.map((s) => s.id));
  const [watchlist,    setWatchlist]    = useState<string[]>([]);
  const [loading,      setLoading]      = useState(false);
  const [optimizing,   setOptimizing]   = useState(false);
  const [scanning,     setScanning]     = useState(false);
  const [error,        setError]        = useState('');
  const [results,      setResults]      = useState<BacktestResult[]>([]);
  const [resultsMeta,  setResultsMeta]  = useState<{ symbol: string; interval: string; period: string } | null>(null);
  const [optResults,   setOptResults]   = useState<BacktestResult[] | null>(null);
  const [optExpanded,  setOptExpanded]  = useState(false);
  const [expanded,     setExpanded]     = useState<string | null>(null);
  const [liveRows,     setLiveRows]     = useState<LiveRow[] | null>(null);
  const [appliedIdx,   setAppliedIdx]   = useState<number | null>(null);
  const [optimizeFor,  setOptimizeFor]  = useState<string>(STRATEGIES[0].id);
  const [regime,       setRegime]       = useState<RegimeResult | null>(null);
  const [regimeLoading,setRegimeLoading] = useState(false);

  // Sync period when interval changes so it stays valid for that TF
  const handleIntervalChange = useCallback((iv: string) => {
    setIntervalVal(iv);
    setPeriod(DEFAULT_PERIOD_BY_INTERVAL[iv] ?? '2y');
  }, []);

  const activeLoadedRef = useRef(false);

  // Persist only user-driven changes — the initial all-6 default must NOT
  // overwrite the user's stored selection before loadActive() resolves.
  useEffect(() => {
    if (!activeLoadedRef.current) return;
    saveActive(activeStrats);
  }, [activeStrats]);

  useEffect(() => {
    chromeGet<any>(['watchlist']).then((res) => {
      const syms = ((res.watchlist as any[]) || []).map((w: any) => w.symbol).filter(Boolean);
      if (syms.length > 0) setWatchlist(syms);
    });
    loadActive().then((list) => {
      activeLoadedRef.current = true;
      setActiveStrats(list);
    });
  }, []);

  const toggleStrategy = (id: string) => {
    setStrategies(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  const toggleActive = (id: string) => {
    setActiveStrats(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  // Core API caller — reads endpoint + apiKeys from chrome.storage on every call
  const api = async (path: string, body: Record<string, unknown>) => {
    const { apiEndpoint, apiKeys } = await getSettings();
    const res = await fetch(`${apiEndpoint}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, apiKeys: apiKeys ?? {} }),
    });
    return res.json();
  };

  const applyOptParams = async (idx: number) => {
    if (!optResults?.[idx]) return;
    const params = optResults[idx].params;
    const res = await chromeGet<Record<string, Record<string, number>>>([OPT_PARAMS_KEY]);
    const current = res[OPT_PARAMS_KEY] ?? {};
    chromeSet({ [OPT_PARAMS_KEY]: { ...current, [optimizeFor]: params } });
    setAppliedIdx(idx);
  };

  const runBacktest = async () => {
    if (strategies.length === 0) return;
    const snap = { symbol: symbol.trim().toUpperCase(), interval, period };
    setLoading(true);
    setError('');
    setResults([]);
    setResultsMeta(null);
    setOptResults(null);
    try {
      const out = await Promise.all(
        strategies.map(async (s) => {
          const data = await api('/api/backtest', { symbol: snap.symbol, strategy: s, interval: snap.interval, period: snap.period });
          return data.error ? { strategy: s, error: data.error } as BacktestResult : data.result as BacktestResult;
        })
      );
      out.sort((a, b) => (b.total_return_pct ?? -999) - (a.total_return_pct ?? -999));
      const firstErr = out.find(r => r.error);
      if (firstErr) setError(firstErr.error || '');
      const ok = out.filter(r => !r.error);
      setResults(ok);
      if (ok.length > 0) setResultsMeta(snap);  // results stay labeled with the params they were computed for
    } catch (e: any) {
      setError(`Backend unreachable — start it with start_backend.bat (${e.message})`);
    } finally {
      setLoading(false);
    }
  };

  const runOptimize = async () => {
    if (!optimizeFor || !symbol.trim()) return;
    setOptimizing(true); setError(''); setAppliedIdx(null);
    try {
      const data = await api('/api/optimize', { symbol: symbol.trim().toUpperCase(), strategy: optimizeFor, interval, period, topN: 5 });
      if (data.error) setError(data.error);
      else { setOptResults(data.results); setOptExpanded(true); }
    } catch (e: any) {
      setError(`Backend unreachable — is the tray app running? (${e.message})`);
    } finally { setOptimizing(false); }
  };

  const runLiveScan = async () => {
    if (activeStrats.length === 0) return;
    const stored = await chromeGet<any>(['watchlist']);
    let symbols: string[] = ((stored.watchlist as any[]) || []).map((w: any) => w.symbol).slice(0, 25);
    if (symbols.length === 0) symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'EURUSD=X', 'GBPUSD=X', 'AAPL', 'TSLA'];
    setScanning(true); setError(''); setLiveRows(null);
    try {
      // apiKeys are injected automatically by the api() helper from chrome.storage
      const data = await api('/api/live-signals', { symbols, strategies: activeStrats, interval });
      if (data.error) setError(data.error);
      else setLiveRows(data.results);
    } catch (e: any) {
      setError(`Backend unreachable — is the tray app running? (${e.message})`);
    } finally { setScanning(false); }
  };

  const availablePeriods = PERIODS_BY_INTERVAL[interval] ?? ['6m', '1y', '2y', '5y'];

  const fetchRegime = async () => {
    if (!symbol.trim()) return;
    const sym = symbol.trim().toUpperCase();
    const iv = interval;
    setRegimeLoading(true);
    setError('');
    try {
      const data = await api('/api/market-regime', { symbol: sym, interval: iv });
      if (data.error) { setError(data.error); return; }
      // Ignore stale responses: the user may have switched symbol/interval
      // while this request was in flight.
      if (sym === symbol.trim().toUpperCase() && iv === interval) {
        setRegime({ ...(data as RegimeResult), symbol: sym, interval: iv });
      }
    } catch (e: any) {
      if (sym === symbol.trim().toUpperCase() && iv === interval) {
        setError(`Backend unreachable — is the tray app running? (${e.message})`);
      }
    } finally {
      if (sym === symbol.trim().toUpperCase() && iv === interval) {
        setRegimeLoading(false);
      }
    }
  };

  return (
    <div className="space-y-3">
      {/* Header */}
      <div>
        <h2 className="text-sm font-bold text-white flex items-center gap-1.5">
          <FlaskConical className="w-4 h-4 text-primary" /> Strategy Lab
        </h2>
        <p className="text-[10px] text-muted mt-0.5">Backtest strategies head-to-head, optimise params, or scan your watchlist live.</p>
      </div>

      {/* ── Controls panel ── */}
      <div className="glass-panel rounded-2xl p-2.5 space-y-2.5">

        {/* Symbol dropdown from watchlist */}
        <div className="space-y-1.5 relative">
          <label className="text-[9px] uppercase tracking-wider text-muted font-semibold">Symbol</label>
          <div className="relative">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-surface/60 border border-border/60 text-white rounded-xl px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-primary/40 appearance-none cursor-pointer"
            >
              {watchlist.length > 0 ? (
                watchlist.map((w) => (
                  <option key={w} value={w} className="bg-surface text-white">
                    {w}
                  </option>
                ))
              ) : (
                <option value="BTC-USD" className="bg-surface text-white">BTC-USD</option>
              )}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-muted">
              <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </div>
          </div>
        </div>

        {/* Timeframe + Lookback period — auto-capped by interval */}
        <div className="flex gap-2">
          <div className="flex-1 space-y-1">
            <label className="text-[9px] uppercase tracking-wider text-muted font-semibold">Timeframe</label>
            <div className="flex gap-1">
              {INTERVALS.map((iv) => (
                <button key={iv} onClick={() => handleIntervalChange(iv)}
                  className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold transition-all ${
                    interval === iv ? 'bg-primary/20 border border-primary/40 text-white' : 'glass-card text-zinc-500 hover:text-white'
                  }`}>{iv}</button>
              ))}
            </div>
          </div>
          <div className="flex-1 space-y-1">
            <label className="text-[9px] uppercase tracking-wider text-muted font-semibold">Lookback</label>
            <div className="flex gap-1">
              {availablePeriods.map((p) => (
                <button key={p} onClick={() => setPeriod(p)}
                  className={`flex-1 py-1.5 rounded-lg text-[10px] font-bold transition-all ${
                    period === p ? 'bg-primary/20 border border-primary/40 text-white' : 'glass-card text-zinc-500 hover:text-white'
                  }`}>{p}</button>
              ))}
            </div>
          </div>
        </div>

        {/* Strategy chips — test set */}
        <div className="space-y-1">
          <label className="text-[9px] uppercase tracking-wider text-muted font-semibold">Test strategies ({strategies.length} selected)</label>
          <div className="flex flex-wrap gap-1.5">
            {STRATEGIES.map((s) => {
              const active = strategies.includes(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => toggleStrategy(s.id)}
                  title={active ? 'Remove from test' : 'Add to test'}
                  className={`px-2.5 py-1 rounded-lg text-[10px] font-semibold transition-all ${
                    active
                      ? 'bg-gradient-to-r from-blue-500/25 to-violet-500/25 text-white border border-primary/30'
                      : 'glass-card text-zinc-500 hover:text-white'
                  }`}
                >
                  {s.label}
                </button>
              );
            })}
          </div>
        </div>
        {/* Actions — Backtest all selected + Optimize (with explicit strategy picker) */}
        <div className="flex gap-2">
          <button
            onClick={runBacktest}
            disabled={loading || strategies.length === 0 || !symbol.trim()}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold bg-gradient-to-r from-blue-500 to-violet-500 text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            <Play className="w-3.5 h-3.5" /> {loading ? 'Backtesting…' : `Backtest (${strategies.length})`}
          </button>
          <div className="flex gap-1">
            <select
              value={optimizeFor}
              onChange={(e) => setOptimizeFor(e.target.value)}
              className="bg-surface/60 border border-border/60 text-white rounded-xl px-2 text-[10px] focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              {STRATEGIES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
            <button
              onClick={runOptimize}
              disabled={optimizing || loading || !symbol.trim()}
              className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-40 whitespace-nowrap"
            >
              <RotateCw className={`w-3.5 h-3.5 ${optimizing ? 'animate-spin' : ''}`} /> Optimize
            </button>
          </div>
        </div>
        {error && (
          <div className="flex items-start gap-1.5 text-[11px] text-red-400 bg-red-500/10 border border-red-500/25 rounded-xl px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" /> <span>{error}</span>
          </div>
        )}
      </div>

      {/* ── Market regime panel ── */}
      <div className="glass-panel rounded-2xl p-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[9px] uppercase tracking-wider text-muted font-semibold">Market conditions</p>
          <button
            onClick={fetchRegime}
            disabled={regimeLoading || !symbol.trim()}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-40"
          >
            <RotateCw className={`w-3 h-3 ${regimeLoading ? 'animate-spin' : ''}`} /> {regimeLoading ? 'Analysing…' : 'Analyse'}
          </button>
        </div>

        {regimeLoading && (
          <div className="space-y-1.5">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-44" />
          </div>
        )}

        {!regimeLoading && regime === null && (
          <p className="text-[10px] text-muted/60 italic">Tap Analyse to detect current market regime</p>
        )}

        {!regimeLoading && regime !== null && regime.symbol === symbol.trim().toUpperCase() && regime.interval === interval && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold flex-shrink-0 ${REGIME_BADGE_CLS[regime.regime] ?? REGIME_BADGE_CLS.neutral}`}>
                {regime.regime_label}
              </span>
              <div className="flex-1 h-1 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, Math.round(regime.confidence * 100)))}%` }}
                />
              </div>
              <span className="text-[10px] font-mono text-muted tabular-nums flex-shrink-0">{Math.round(regime.confidence * 100)}%</span>
            </div>
            <p className="text-[10px] text-muted/80">{regime.description}</p>
            <p className="text-[9px] text-muted/60 font-mono">
              ADX {regime.adx.toFixed(1)} · ATR {regime.atr_pct.toFixed(2)}% · RSI {regime.rsi.toFixed(1)} · EMA {regime.ema_bias === 'bullish' ? '20>50' : regime.ema_bias === 'bearish' ? '20<50' : '20≈50'}
            </p>
            <div className="space-y-1">
              <p className="text-[9px] uppercase tracking-wider text-muted/70 font-semibold">Suggested for these conditions</p>
              <div className="flex flex-wrap gap-1.5">
                {regime.suggested_strategies.map((id) => (
                  <span key={id} className="px-2.5 py-1 rounded-lg text-[10px] font-bold bg-blue-500/10 border border-blue-500/25 text-blue-300/90">
                    {STRATEGIES.find((s) => s.id === id)?.label ?? id}
                  </span>
                ))}
              </div>
            </div>
            <button
              onClick={() => { setError(''); setActiveStrats(regime.suggested_strategies); saveActive(regime.suggested_strategies); }}
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold border border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10 transition-colors"
            >
              <Zap className="w-3.5 h-3.5" /> Apply suggestion
            </button>
          </div>
        )}
      </div>

      {/* Strategies in use NOW — feeds the live scan & notifications */}
      <div className="glass-panel rounded-2xl p-2.5 space-y-2">
        <p className="text-xs font-bold text-white flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Strategies in use now
        </p>
        <p className="text-[9px] text-muted/70">
          The live signal scan and trade notifications only use these. Turn one off to leave it out of live decisions.
        </p>
        <div className="flex flex-wrap gap-1.5">
          {STRATEGIES.map((s) => {
            const on = activeStrats.includes(s.id);
            const hasRegime = regime !== null && regime.symbol === symbol.trim().toUpperCase() && regime.interval === interval;
            const fits = hasRegime && regime.suggested_strategies.includes(s.id);
            return (
              <button
                key={s.id}
                onClick={() => toggleActive(s.id)}
                className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition-all flex items-center gap-1 ${
                  on
                    ? 'bg-emerald-500/15 border border-emerald-500/40 text-emerald-300'
                    : 'bg-zinc-500/5 border border-zinc-500/15 text-zinc-600 line-through hover:text-zinc-400'
                }`}
                title={on ? 'Enabled for live use — click to leave out' : 'Disabled — click to enable'}
              >
                {on ? '● ' : '○ '}{s.label}
                {hasRegime && (
                  fits
                    ? <span className="text-emerald-400 font-bold" title="Fits current market regime">✓</span>
                    : <span className="text-[8px] text-zinc-500 font-semibold" title="Not ideal for current market regime">[not ideal]</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Backtest loading skeleton */}
      {loading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-1.5">
          <div className="flex items-center gap-2 px-1">
            <Skeleton className="h-3 w-28" />
            <Skeleton className="h-3 w-12" />
          </div>
          {Array.from({ length: Math.max(strategies.length, 2) }).map((_, i) => (
            <div key={i} className="glass-panel rounded-2xl px-3 py-3 flex items-center gap-3">
              <Skeleton className="h-3.5 w-16" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-3 flex-1" />
            </div>
          ))}
        </motion.div>
      )}

      {/* ── Backtest results ── */}
      <AnimatePresence>
      {results.length > 0 && !loading && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-1.5">
          <p className="text-[10px] uppercase tracking-wider text-muted font-semibold px-1">
            {resultsMeta ? `${resultsMeta.symbol} · ${resultsMeta.interval} · ${resultsMeta.period} · ranked by return` : ''}
          </p>
          {results.map((r) => {
            const open = expanded === r.strategy;
            const ret = r.total_return_pct;
            return (
              <div key={r.strategy} className="glass-panel rounded-2xl overflow-hidden">
                <button
                  onClick={() => setExpanded(open ? null : r.strategy)}
                  className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-white/5 transition-colors"
                >
                  <span className="w-16 text-left text-[11px] font-bold text-white flex-shrink-0">
                    {STRATEGIES.find(s => s.id === r.strategy)?.label}
                  </span>
                  <span className={`text-sm font-mono font-bold tabular-nums w-20 text-left ${ret > 0 ? 'text-emerald-400' : ret < 0 ? 'text-red-400' : 'text-white'}`}>
                    {ret > 0 ? '+' : ''}{ret}%
                  </span>
                  <span className="flex-1 flex items-center gap-3 text-[10px] text-muted">
                    <span>Win <b className="text-zinc-300">{r.win_rate_pct}%</b></span>
                    <span>PF <b className="text-zinc-300">{r.profit_factor}</b></span>
                    <span>DD <b className="text-zinc-300">{r.max_drawdown_pct}%</b></span>
                    <span>Sharpe <b className="text-zinc-300">{r.sharpe}</b></span>
                    <span>{r.trade_count} trades</span>
                  </span>
                  {open ? <ChevronUp className="w-3.5 h-3.5 text-muted flex-shrink-0" /> : <ChevronDown className="w-3.5 h-3.5 text-muted flex-shrink-0" />}
                </button>
                {open && (
                  <div className="px-3 pb-3 space-y-2">
                    <Sparkline points={r.equity_curve} />
                    <div className="grid grid-cols-3 gap-1.5">
                      <Metric label="Annual %" value={`${r.annual_return_pct > 0 ? '+' : ''}${r.annual_return_pct}%`} tone={r.annual_return_pct > 0 ? 'good' : r.annual_return_pct < 0 ? 'bad' : 'neutral'} />
                      <Metric label="Sortino" value={`${r.sortino}`} tone={r.sortino >= 1 ? 'good' : r.sortino < 0 ? 'bad' : 'neutral'} />
                      <Metric label="Calmar" value={`${r.calmar}`} tone={r.calmar >= 1 ? 'good' : r.calmar < 0 ? 'bad' : 'neutral'} />
                      <Metric label="Avg trade" value={`${r.avg_trade_pct > 0 ? '+' : ''}${r.avg_trade_pct}%`} tone={r.avg_trade_pct > 0 ? 'good' : 'bad'} />
                      <Metric label="Exposure" value={`${r.exposure_pct}%`} />
                      <Metric label="Best/Worst" value={`+${r.best_trade_pct}/${r.worst_trade_pct}%`} />
                    </div>
                    <p className="text-[9px] text-muted/70">
                      {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' · ')} · {r.bars} bars · final ${r.final_equity}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </motion.div>
      )}
      </AnimatePresence>

      {/* ── Optimization loading skeleton ── */}
      {optimizing && (
        <div className="glass-panel rounded-2xl p-3 space-y-2">
          <Skeleton className="h-3.5 w-48" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
        </div>
      )}

      {/* ── Optimization results + Apply-params button ── */}
      <AnimatePresence>
      {optResults && optResults.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="glass-panel rounded-2xl p-3 space-y-2">
          <button onClick={() => setOptExpanded((v) => !v)} className="w-full flex items-center justify-between text-xs font-bold text-white">
            <span className="flex items-center gap-1.5"><RotateCw className="w-3.5 h-3.5 text-primary" /> Best params — {STRATEGIES.find((s) => s.id === optimizeFor)?.label}</span>
            <span className="text-muted">{optExpanded ? '▲' : '▼'}</span>
          </button>
          {optExpanded && (
            <div className="space-y-1.5">
              {optResults.map((r, i) => (
                <div key={i} className="flex items-center gap-2 bg-surface/50 border border-border/40 rounded-xl px-2.5 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] font-mono text-zinc-400 truncate">
                      {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' · ')}
                    </p>
                    <p className="text-[9px] text-muted">
                      {r.trade_count} trades · win {r.win_rate_pct}% · PF {r.profit_factor} · DD {r.max_drawdown_pct}%
                    </p>
                  </div>
                  <span className={`text-sm font-mono font-bold tabular-nums flex-shrink-0 ${r.total_return_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {r.total_return_pct > 0 ? '+' : ''}{r.total_return_pct}%
                  </span>
                  <button
                    onClick={() => applyOptParams(i)}
                    title="Save these params for the live signal scan"
                    className={`flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded-lg text-[9px] font-bold transition-all ${
                      appliedIdx === i
                        ? 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-300'
                        : 'border border-border/50 text-muted hover:border-primary/40 hover:text-primary'
                    }`}
                  >
                    {appliedIdx === i ? <><CheckCircle2 className="w-2.5 h-2.5" /> Applied</> : 'Use'}
                  </button>
                </div>
              ))}
              <p className="text-[9px] text-muted/50 pt-0.5">"Use" saves params to chrome.storage. Live scan picks them up on next run.</p>
            </div>
          )}
        </motion.div>
      )}
      </AnimatePresence>

      {/* Live strategy scan */}
      <div className="glass-panel rounded-2xl p-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold text-white flex items-center gap-1.5">
            <ScanLine className="w-3.5 h-3.5 text-primary" /> Live signal scan
          </p>
          <span className="text-[9px] text-muted">
            uses your {activeStrats.length} active strateg{activeStrats.length === 1 ? 'y' : 'ies'} · {interval} TF
          </span>
        </div>
        <p className="text-[9px] text-muted/70">
          Current stance of your selected strategies on each symbol — fresh data, commission excluded.
        </p>
        <button
          onClick={runLiveScan}
          disabled={scanning || activeStrats.length === 0}
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold border border-primary/40 text-primary hover:bg-primary/10 transition-colors disabled:opacity-40"
        >
          <ScanLine className={`w-3.5 h-3.5 ${scanning ? 'animate-pulse' : ''}`} /> {scanning ? 'Scanning...' : `Scan — ${activeStrats.length} active strategy${activeStrats.length === 1 ? '' : 's'}`}
        </button>
        {scanning && !liveRows && (
          <div className="space-y-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center justify-between bg-surface/50 border border-border/40 rounded-xl px-2.5 py-1.5">
                <Skeleton className="h-3 w-20" />
                <div className="flex gap-1">
                  <Skeleton className="h-4 w-9 rounded-md" />
                  <Skeleton className="h-4 w-9 rounded-md" />
                  <Skeleton className="h-4 w-9 rounded-md" />
                </div>
              </div>
            ))}
          </div>
        )}
        {liveRows && (
          <div className="space-y-1">
            {liveRows.map((row) => (
              <div key={row.symbol} className="flex items-center gap-2 bg-surface/50 border border-border/40 rounded-xl px-2.5 py-1.5">
                <span className="text-[11px] font-bold text-white w-20 truncate flex-shrink-0">{row.symbol}</span>
                {row.error ? (
                  <span className="text-[9px] text-muted italic flex-1">{row.error}</span>
                ) : (
                  <div className="flex items-center gap-1 flex-wrap justify-end flex-1">
                    {/* activeStrats = same list sent to backend, so signals always align */}
                    {activeStrats.map((s) => (
                      <SignalBadge key={s} signal={row.signals?.[s] ?? 'flat'} />
                    ))}
                    {/* Consensus badge — fires when majority agree on direction */}
                    {row.signals && (
                      <ConsensusTag
                        signals={row.signals}
                        active={activeStrats}
                        threshold={Math.max(2, Math.ceil(activeStrats.length / 2))}
                      />
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="text-[9px] text-muted/50 px-1">
        Strategies ported from AlphaTrend Scanner, freqtrade patterns & GainzAlgo-style logic. Backtests assume 0.075% commission + 0.05% slippage. Past performance ≠ future results.
      </p>
    </div>
  );
};

export default Backtest;