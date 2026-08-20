import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Save, Shield, Bell, Server, Key, AlertCircle, CheckCircle, Wallet, Target, TrendingDown, Sparkles } from 'lucide-react';
import { UserSettings, RiskSettings } from '../../types';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '../../components/ui/select';

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
    telegramThreshold: 80,
  },
  apiEndpoint: 'http://127.0.0.1:8001',
  mt5Url: '',
  marketDataSources: [
    'Alpha Vantage',
    'Polygon.io',
    'Finnhub',
    'IEX Cloud',
    'Twelve Data',
    'Yahoo Finance (Built-in)',
  ],
};

interface BrokerConfig {
  broker_type: 'alpaca' | 'mt5' | 'ccxt';
  api_key: string;
  api_secret: string;
  api_server?: string;
  terminal_path?: string;
  paper_trading: boolean;
}

const inputCls = 'w-full px-3 py-2 bg-background border border-border rounded-lg text-white text-sm focus:outline-none focus:border-zinc-500 transition-colors';
const labelCls = 'text-xs text-muted mb-1.5 block';

/**
 * Number input with a $/% unit adornment.
 * Wheel-scrolling never edits the value (the page scrolls instead) — this is the
 * behaviour users expect: their scroll-wheel moves the page, not the numbers.
 */
const UnitInput: React.FC<{
  value: number;
  onChange: (v: number) => void;
  unit?: '$' | '%';
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}> = ({ value, onChange, unit, min, max, step, disabled }) => (
  <div className="relative">
    {unit === '$' && (
      <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted text-xs pointer-events-none select-none">$</span>
    )}
    <input
      type="number"
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      onWheel={(e) => (e.currentTarget as HTMLInputElement).blur()}
      className={`${inputCls} ${unit === '$' ? 'pl-6' : unit === '%' ? 'pr-7' : ''}`}
    />
    {unit === '%' && (
      <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted text-xs pointer-events-none select-none">%</span>
    )}
  </div>
);

const Toggle: React.FC<{ checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }> = ({ checked, onChange, disabled }) => (
  <label className="relative inline-flex items-center cursor-pointer">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="sr-only peer"
      disabled={disabled}
    />
    <div className="w-10 h-5 bg-zinc-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary disabled:opacity-50"></div>
  </label>
);

const computeSuggestions = (balance: number, stopLossPct: number) => {
  if (!Number.isFinite(balance) || !Number.isFinite(stopLossPct) || balance <= 0 || stopLossPct <= 0) return null;
  const positionSize = (balance * 1) / stopLossPct;
  const positionPct = Math.round((positionSize / balance) * 10000) / 100;
  // A stop tighter than 1% implies leverage above 1x — never suggest a
  // position larger than the account balance (no silent leverage).
  const capped = positionPct > 100;
  return {
    positionSize: capped ? Math.round(balance * 100) / 100 : Math.round(positionSize * 100) / 100,
    positionPct: capped ? 100 : positionPct,
    dailyLoss: Math.round(balance * 0.01 * 100) / 100,
    dailyProfit: Math.round(balance * 0.02 * 100) / 100,
    takeProfit: Math.round(stopLossPct * 3 * 100) / 100,
  };
};

const Settings: React.FC = () => {
  const [settings, setSettings] = useState<UserSettings>(defaultSettings);
  const [saved, setSaved] = useState(false);
  const [brokerConfig, setBrokerConfig] = useState<BrokerConfig>({
    broker_type: 'alpaca',
    api_key: '',
    api_secret: '',
    api_server: '',
    paper_trading: true,
  });
  const [autoTradeStatus, setAutoTradeStatus] = useState<'idle' | 'configuring' | 'active' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [minConfidence, setMinConfidence] = useState(60);
  const [liveBalance, setLiveBalance] = useState<number | null>(null);
  const [balanceSource, setBalanceSource] = useState<'live' | 'manual'>('manual');

  useEffect(() => {
    loadSettings();
  }, []);

  const checkAutoTradeStatus = async (apiEndpoint: string) => {
    try {
      const api = apiEndpoint || defaultSettings.apiEndpoint;
      const response = await fetch(`${api}/api/auto-trade/status`);
      const data = await response.json();
      if (data.enabled) {
        setAutoTradeStatus('active');
        setStatusMessage('Auto-trading is active');
      }
    } catch {
      // Backend not reachable — stay idle
    }
  };

  const fetchAccountBalance = async (apiEndpoint: string) => {
    try {
      const api = apiEndpoint || defaultSettings.apiEndpoint;
      const res = await fetch(`${api}/api/portfolio`);
      if (!res.ok) return;
      const data = await res.json();
      const bal = data.account ? Number(data.account.balance ?? data.account.equity) : NaN;
      if (Number.isFinite(bal) && bal > 0) {
        setLiveBalance(bal);
        setBalanceSource('live');
      }
    } catch {
      // Backend unreachable — fall back to manual balance
    }
  };

  const loadSettings = () => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['userSettings', 'brokerConfig', 'minConfidence'], (result) => {
        const loadedSettings = {
          ...defaultSettings,
          ...(result.userSettings || {}),
          notifications: {
            ...defaultSettings.notifications,
            ...(result.userSettings?.notifications || {})
          },
          riskSettings: {
            ...defaultSettings.riskSettings,
            ...(result.userSettings?.riskSettings || {})
          }
        };
        setSettings(loadedSettings);
        if (result.brokerConfig) setBrokerConfig(result.brokerConfig);
        if (result.minConfidence) setMinConfidence(result.minConfidence);
        // Older saved settings may lack apiEndpoint — never fetch from "undefined/..."
        const ep = loadedSettings.apiEndpoint || defaultSettings.apiEndpoint;
        checkAutoTradeStatus(ep);
        fetchAccountBalance(ep);
      });
    }
  };

  const saveSettings = (newSettings?: UserSettings) => {
    const baseSettings = newSettings || settings;
    
    // Parse any temporary string states back to strict numbers before saving
    const parsedRiskSettings = { ...baseSettings.riskSettings };
    for (const key of Object.keys(parsedRiskSettings) as (keyof RiskSettings)[]) {
      if (key !== 'riskType' && key !== 'enableAutoTrade' && key !== 'trailingEnabled') {
        const val = parsedRiskSettings[key];
        parsedRiskSettings[key] = typeof val === 'string' ? (parseFloat(val) || 0) : (val ?? 0);
      }
    }
    
    const toSave = { ...baseSettings, riskSettings: parsedRiskSettings as RiskSettings };

    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.set({ userSettings: toSave, brokerConfig, minConfidence }, () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      });
    } else {
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  const setupAutoTrading = async () => {
    if (!brokerConfig.api_key || !brokerConfig.api_secret) {
      setStatusMessage('Please enter API credentials');
      setAutoTradeStatus('error');
      return;
    }

    setAutoTradeStatus('configuring');
    setStatusMessage('Setting up auto-trading...');

    try {
      const api = settings.apiEndpoint || defaultSettings.apiEndpoint;
      const isPct = settings.riskSettings.riskType === 'percentage';
      const balance = balanceSource === 'live' && liveBalance !== null ? liveBalance : (settings.riskSettings.accountBalance ?? 0);

      // Convert percentages to dollars for the backend (backend always expects standard dollars)
      const max_position_size = isPct && balance > 0 ? (settings.riskSettings.maxPositionSize || 0) / 100 * balance : (settings.riskSettings.maxPositionSize || 0);
      const max_daily_loss = isPct && balance > 0 ? (settings.riskSettings.maxDailyLoss || 0) / 100 * balance : (settings.riskSettings.maxDailyLoss || 0);
      const max_daily_profit = isPct && balance > 0 ? (settings.riskSettings.maxDailyProfit || 0) / 100 * balance : (settings.riskSettings.maxDailyProfit || 1000);

      const response = await fetch(`${api}/api/auto-trade/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: true,
          broker_config: brokerConfig,
          risk_type: settings.riskSettings.riskType || 'dollar',
          max_position_size: max_position_size,
          max_daily_loss: max_daily_loss,
          max_daily_profit: max_daily_profit,
          min_confidence: minConfidence,
          initial_stop_loss_pct: settings.riskSettings.stopLossPercentage,
          initial_take_profit_pct: settings.riskSettings.takeProfitPercentage,
          breakeven_trigger_pct: settings.riskSettings.breakevenTriggerPct || 2.0,
          trailing_enabled: true,
          trailing_activation_pct: settings.riskSettings.trailingActivationPct || 5.0,
          trailing_distance_pct: settings.riskSettings.trailingDistancePct || 1.5,
          trailing_step_pct: settings.riskSettings.trailingStepPct || 0.5,
        }),
      });

      const data = await response.json();

      if (data.success) {
        setAutoTradeStatus('active');
        setStatusMessage('Auto-trading activated.');
        const updatedSettings = {
          ...settings,
          riskSettings: { ...settings.riskSettings, enableAutoTrade: true },
        };
        setSettings(updatedSettings);
        saveSettings(updatedSettings);
      } else {
        setAutoTradeStatus('error');
        setStatusMessage(data.error || data.message || 'Failed to setup auto-trading');
      }
    } catch (error) {
      setAutoTradeStatus('error');
      setStatusMessage(`Connection error: ${error}`);
    }
  };

  const stopAutoTrading = async () => {
    try {
      const api = settings.apiEndpoint || defaultSettings.apiEndpoint;
      const response = await fetch(`${api}/api/auto-trade/disable`, { method: 'POST' });
      const data = await response.json();

      if (data.success) {
        setAutoTradeStatus('idle');
        setStatusMessage('Auto-trading stopped');
        updateRiskSettings('enableAutoTrade', false);
      }
    } catch (error) {
      setStatusMessage(`Error stopping: ${error}`);
    }
  };

  const updateRiskSettings = (key: keyof RiskSettings, value: number | boolean | 'dollar' | 'percentage' | string) => {
    setSettings(prev => {
      let riskSettings = { ...prev.riskSettings, [key]: value };

      if (key === 'riskType') {
        const balance = balanceSource === 'live' && liveBalance !== null ? liveBalance : (prev.riskSettings.accountBalance ?? 0);
        if (balance > 0) {
          const isNowPct = value === 'percentage';
          const pos = prev.riskSettings.maxPositionSize || 0;
          const dl = prev.riskSettings.maxDailyLoss || 0;
          const dp = prev.riskSettings.maxDailyProfit || 0;

          if (isNowPct) {
            // Dollar to Percentage
            riskSettings.maxPositionSize = Number(((pos / balance) * 100).toFixed(2));
            riskSettings.maxDailyLoss = Number(((dl / balance) * 100).toFixed(2));
            riskSettings.maxDailyProfit = Number(((dp / balance) * 100).toFixed(2));
          } else {
            // Percentage to Dollar
            riskSettings.maxPositionSize = Number(((pos / 100) * balance).toFixed(2));
            riskSettings.maxDailyLoss = Number(((dl / 100) * balance).toFixed(2));
            riskSettings.maxDailyProfit = Number(((dp / 100) * balance).toFixed(2));
          }
        } else {
          // If no balance, set reasonable defaults when switching types to avoid 1000% position sizes
          if (value === 'percentage') {
            riskSettings.maxPositionSize = 10;
            riskSettings.maxDailyLoss = 1;
            riskSettings.maxDailyProfit = 2;
          } else {
            riskSettings.maxPositionSize = 1000;
            riskSettings.maxDailyLoss = 100;
            riskSettings.maxDailyProfit = 200;
          }
        }
      }

      const next = { ...prev, riskSettings };
      // Write through to storage so toggles like "Stop Auto-Trading" survive a
      // popup close/reopen instead of silently re-enabling auto-trading.
      if (typeof chrome !== 'undefined' && chrome.storage?.local) {
        chrome.storage.local.set({ userSettings: next });
      }
      return next;
    });
  };

  const updateNotifications = (key: keyof UserSettings['notifications'], value: number | boolean | string) => {
    setSettings(prev => ({
      ...prev,
      notifications: { ...prev.notifications, [key]: value },
    }));
  };

  const SectionHeader: React.FC<{ icon: React.ElementType; label: string }> = ({ icon: Icon, label }) => (
    <div className="flex items-center space-x-2 mb-4">
      <Icon className="w-4 h-4 text-muted" />
      <h3 className="text-sm font-semibold text-white">{label}</h3>
    </div>
  );

  return (
    <div className="space-y-4 pb-4">
      {/* Auto-Trading */}
      <div className="glass-card rounded-xl p-4">
        <SectionHeader icon={Key} label="Auto-Trading" />

        {statusMessage && (
          <div className={`mb-4 px-3 py-2 rounded-lg flex items-center space-x-2 border ${
            autoTradeStatus === 'active' ? 'bg-accent/8 border-accent/25' :
            autoTradeStatus === 'error' ? 'bg-danger/8 border-danger/25' :
            'bg-primary/8 border-primary/25'
          }`}>
            {autoTradeStatus === 'active' && <CheckCircle className="w-3.5 h-3.5 text-accent flex-shrink-0" />}
            {autoTradeStatus === 'error' && <AlertCircle className="w-3.5 h-3.5 text-danger flex-shrink-0" />}
            {autoTradeStatus === 'configuring' && (
              <div className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin flex-shrink-0"></div>
            )}
            <span className={`text-xs ${
              autoTradeStatus === 'active' ? 'text-accent' :
              autoTradeStatus === 'error' ? 'text-danger' :
              'text-primary'
            }`}>{statusMessage}</span>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className={labelCls}>Broker / Exchange</label>
            <Select
              value={brokerConfig.broker_type}
              onValueChange={(v) => { setBrokerConfig(prev => ({ ...prev, broker_type: (v as "alpaca" | "mt5" | "ccxt") })); if (autoTradeStatus === "error") { setAutoTradeStatus("idle"); setStatusMessage(""); } }}
              disabled={autoTradeStatus === 'active'}
            >
              <SelectTrigger>
                <SelectValue>
                  {brokerConfig.broker_type === 'alpaca' ? 'Alpaca (US Stocks)' :
                   brokerConfig.broker_type === 'mt5' ? 'MetaTrader 5 (Forex/Metals)' :
                   'Crypto Exchange (CCXT)'}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="alpaca">Alpaca (US Stocks)</SelectItem>
                <SelectItem value="mt5">MetaTrader 5 (Forex/Metals)</SelectItem>
                <SelectItem value="ccxt">Crypto Exchange (CCXT)</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted mt-1">
              {brokerConfig.broker_type === 'alpaca' ? 'Get free API keys at alpaca.markets' : 
               brokerConfig.broker_type === 'mt5' ? 'Connect to your MT5 terminal' : 
               'Connect to Binance, Bybit, Kraken, etc.'}
            </p>
          </div>

          <div>
            <label className={labelCls}>
              {brokerConfig.broker_type === 'alpaca' ? 'API Key' : 
               brokerConfig.broker_type === 'mt5' ? 'MT5 Login (Account ID)' : 
               'Exchange API Key'}
            </label>
            <input
              type="text"
              value={brokerConfig.api_key}
              onChange={(e) => { setBrokerConfig(prev => ({ ...prev, api_key: e.target.value })); if (autoTradeStatus === "error") { setAutoTradeStatus("idle"); setStatusMessage(""); } }}
              className={inputCls}
              placeholder={brokerConfig.broker_type === 'alpaca' ? 'Enter your API key' : 
                           brokerConfig.broker_type === 'mt5' ? 'Enter your MT5 Login ID' : 
                           'Enter Crypto API Key'}
              disabled={autoTradeStatus === 'active'}
            />
          </div>

          <div>
            <label className={labelCls}>
              {brokerConfig.broker_type === 'alpaca' ? 'API Secret' : 
               brokerConfig.broker_type === 'mt5' ? 'MT5 Password' : 
               'Exchange API Secret'}
            </label>
            <input
              type="password"
              value={brokerConfig.api_secret}
              onChange={(e) => { setBrokerConfig(prev => ({ ...prev, api_secret: e.target.value })); if (autoTradeStatus === "error") { setAutoTradeStatus("idle"); setStatusMessage(""); } }}
              className={inputCls}
              placeholder={brokerConfig.broker_type === 'alpaca' ? 'Enter your API secret' : 
                           brokerConfig.broker_type === 'mt5' ? 'Enter your MT5 Password' : 
                           'Enter Crypto API Secret'}
              disabled={autoTradeStatus === 'active'}
            />
          </div>

          {(brokerConfig.broker_type === 'mt5' || brokerConfig.broker_type === 'ccxt') && (
            <div>
              <label className={labelCls}>
                {brokerConfig.broker_type === 'mt5' ? 'MT5 Server Name' : 'Exchange Name'}
              </label>
              <input
                type="text"
                value={brokerConfig.api_server || ''}
                onChange={(e) => { setBrokerConfig(prev => ({ ...prev, api_server: e.target.value })); if (autoTradeStatus === "error") { setAutoTradeStatus("idle"); setStatusMessage(""); } }}
                className={inputCls}
                placeholder={brokerConfig.broker_type === 'mt5' ? 'e.g. Exness-MT5Real' : 'e.g. binance, bybit, kraken'}
                disabled={autoTradeStatus === 'active'}
              />
            </div>
          )}

          {brokerConfig.broker_type === 'mt5' && (
            <div>
              <label className={labelCls}>MT5 Terminal Path (Optional, fixes connection bugs)</label>
              <input
                type="text"
                value={brokerConfig.terminal_path || ''}
                onChange={(e) => { setBrokerConfig(prev => ({ ...prev, terminal_path: e.target.value })); if (autoTradeStatus === "error") { setAutoTradeStatus("idle"); setStatusMessage(""); } }}
                className={inputCls}
                placeholder="e.g. C:\Program Files\Exness - MetaTrader 5\terminal64.exe"
                disabled={autoTradeStatus === 'active'}
              />
            </div>
          )}

          <div className="flex items-center justify-between p-3 bg-background border border-border rounded-lg">
            <div>
              <p className="text-sm font-medium text-white">Paper trading</p>
              <p className="text-xs text-muted">Use simulated trading (recommended for testing)</p>
            </div>
            <Toggle
              checked={brokerConfig.paper_trading}
              onChange={(v) => setBrokerConfig(prev => ({ ...prev, paper_trading: v }))}
              disabled={autoTradeStatus === 'active'}
            />
          </div>

          <div>
            <label className={labelCls}>Minimum confidence: {minConfidence}%</label>
            <input
              type="range"
              min="50"
              max="90"
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseInt(e.target.value) || 0)}
              className="w-full accent-primary"
              disabled={autoTradeStatus === 'active'}
            />
            <p className="text-xs text-muted mt-1">Only trade when confidence exceeds {minConfidence}%</p>
          </div>

          {autoTradeStatus !== 'active' ? (
            <button
              onClick={setupAutoTrading}
              disabled={autoTradeStatus === 'configuring'}
              className="w-full px-4 py-2.5 bg-accent hover:bg-emerald-400 disabled:bg-zinc-700 disabled:text-muted rounded-xl text-sm font-semibold text-black transition-colors"
            >
              {autoTradeStatus === 'configuring' ? 'Setting up...' : 'Start Auto-Trading'}
            </button>
          ) : (
            <button
              onClick={stopAutoTrading}
              className="w-full px-4 py-2.5 bg-danger hover:bg-red-400 rounded-xl text-sm font-semibold text-white transition-colors"
            >
              Stop Auto-Trading
            </button>
          )}
        </div>
      </div>

      {/* Risk Management */}
      <div className="glass-card rounded-xl p-4">
        <SectionHeader icon={Shield} label="Risk Management" />

        <div className="p-3 bg-background border border-border rounded-lg mb-4 mt-2 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-white flex items-center gap-1.5">
              <Wallet size={14} className="text-primary shrink-0" />
              Account balance
            </p>
            <p className="text-[10px] text-muted truncate">
              {balanceSource === 'live'
                ? `Auto-detected from broker — $${(liveBalance ?? 0).toLocaleString()}`
                : 'Manual entry — used to size your trades'}
            </p>
          </div>
          <div className="w-32 shrink-0">
            <UnitInput
              value={balanceSource === 'live' ? (liveBalance ?? 0) : (settings.riskSettings.accountBalance ?? 0)}
              onChange={(v) => {
                setBalanceSource('manual');
                updateRiskSettings('accountBalance', v);
              }}
              unit="$"
              min={0}
            />
          </div>
        </div>

        {(() => {
          const balance = balanceSource === 'live' && liveBalance !== null ? liveBalance : (settings.riskSettings.accountBalance ?? 0);
          const stopLoss = settings.riskSettings.stopLossPercentage ?? 2;
          const isPct = settings.riskSettings.riskType === 'percentage';
          const suggestions = computeSuggestions(balance, stopLoss);
          const applySuggestions = () => {
            if (!suggestions) return;
            const rs = {
              ...settings.riskSettings,
              maxPositionSize: isPct ? suggestions.positionPct : suggestions.positionSize,
              maxDailyLoss: isPct ? 1 : suggestions.dailyLoss,
              maxDailyProfit: isPct ? 2 : suggestions.dailyProfit,
              takeProfitPercentage: suggestions.takeProfit,
            };
            setSettings((prev) => ({ ...prev, riskSettings: rs }));
            saveSettings({ ...settings, riskSettings: rs });
          };
          const saveBtnCls = 'px-3 py-1.5 text-xs rounded-md bg-primary/20 text-primary border border-primary/30 hover:bg-primary/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed';
          return (
            <>
              <div className="border-b border-border pb-4 mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <Wallet size={14} className="text-primary" />
                  <h4 className="text-sm font-medium text-white">Position Sizing</h4>
                  <p className="text-[10px] text-muted ml-auto text-right">{isPct ? 'Caps as % of balance' : 'Fixed dollar caps'}</p>
                </div>

                <div className="flex bg-background/50 p-1 rounded-lg mb-3">
                  <button
                    className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${settings.riskSettings.riskType !== 'percentage' ? 'bg-primary/20 text-primary font-medium' : 'text-muted-foreground hover:text-white'}`}
                    onClick={() => updateRiskSettings('riskType', 'dollar')}
                  >
                    Dollar ($)
                  </button>
                  <button
                    className={`flex-1 py-1.5 text-xs rounded-md transition-colors ${settings.riskSettings.riskType === 'percentage' ? 'bg-primary/20 text-primary font-medium' : 'text-muted-foreground hover:text-white'}`}
                    onClick={() => updateRiskSettings('riskType', 'percentage')}
                  >
                    Percentage (%)
                  </button>
                </div>

                <div>
                  <label className={labelCls}>Max position size ({isPct ? '%' : '$'})</label>
                  <UnitInput
                    value={settings.riskSettings.maxPositionSize ?? 0}
                    onChange={(v) => updateRiskSettings('maxPositionSize', v)}
                    unit={isPct ? '%' : '$'}
                    min={0}
                  />
                  {balance > 0 && (settings.riskSettings.maxPositionSize ?? 0) > 0 && (
                    <p className="text-[10px] text-muted mt-1">
                      {isPct
                        ? `≈ $${(((settings.riskSettings.maxPositionSize ?? 0) / 100) * balance).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : `${(((settings.riskSettings.maxPositionSize ?? 0) / balance) * 100).toFixed(2)}% of balance`}
                    </p>
                  )}
                </div>

                <div className="flex items-center justify-between gap-2 p-3 bg-primary/5 border border-primary/20 rounded-lg mt-3">
                  <div className="min-w-0">
                    <p className="text-[10px] text-muted mb-0.5">Suggestion</p>
                    {suggestions ? (
                      isPct ? (
                        <p className="text-xs text-white">
                          With <span className="text-primary font-medium">${balance.toLocaleString()}</span> and a {stopLoss}% stop, 1% risk of balance ={' '}
                          <span className="text-primary font-medium">{suggestions.positionPct}% position</span>
                        </p>
                      ) : (
                        <p className="text-xs text-white">
                          With <span className="text-primary font-medium">${balance.toLocaleString()}</span> and a {stopLoss}% stop, 1% risk of balance ={' '}
                          <span className="text-primary font-medium">${suggestions.positionSize.toLocaleString()}</span> position
                        </p>
                      )
                    ) : (
                      <p className="text-xs text-muted">Enter an account balance to get sizing suggestions</p>
                    )}
                  </div>
                  <button onClick={applySuggestions} disabled={!suggestions} className={`${saveBtnCls} shrink-0`}>
                    Apply all
                  </button>
                </div>
              </div>

              <div className="border-b border-border pb-4 mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <Target size={14} className="text-primary" />
                  <h4 className="text-sm font-medium text-white">Stops & Targets</h4>
                  <p className="text-[10px] text-muted ml-auto text-right">3:1 reward-to-risk</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Initial stop loss (%)</label>
                    <UnitInput
                      value={settings.riskSettings.stopLossPercentage ?? 2}
                      onChange={(v) => updateRiskSettings('stopLossPercentage', v)}
                      unit="%"
                      min={0}
                      max={100}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Take profit (%)</label>
                    <UnitInput
                      value={settings.riskSettings.takeProfitPercentage ?? 5}
                      onChange={(v) => updateRiskSettings('takeProfitPercentage', v)}
                      unit="%"
                      min={0}
                      max={100}
                    />
                  </div>
                </div>
                <p className="text-[10px] text-muted mt-1 mb-3">Breakeven & trailing activate after the stop-loss moves to entry</p>

                <div>
                  <label className={labelCls}>Breakeven trigger (%)</label>
                  <UnitInput
                    value={settings.riskSettings.breakevenTriggerPct ?? 2.0}
                    onChange={(v) => updateRiskSettings('breakevenTriggerPct', v)}
                    unit="%"
                    min={0}
                    max={100}
                  />
                  <p className="text-[10px] text-muted mt-1">Move stop loss to entry price if profit reaches this %</p>
                </div>

                <div className="mt-3 p-3 bg-background/50 border border-border rounded-lg space-y-3">
                  <p className="text-[10px] font-medium text-muted uppercase tracking-wide">Trailing stop</p>
                  <div>
                    <label className={labelCls}>Activation threshold (%)</label>
                    <UnitInput
                      value={settings.riskSettings.trailingActivationPct ?? 5.0}
                      onChange={(v) => updateRiskSettings('trailingActivationPct', v)}
                      unit="%"
                      min={0.1}
                      step={0.1}
                    />
                    <p className="text-[10px] text-muted mt-1">Profit % required to start trailing.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className={labelCls}>Distance (%)</label>
                      <UnitInput
                        value={settings.riskSettings.trailingDistancePct ?? 1.5}
                        onChange={(v) => updateRiskSettings('trailingDistancePct', v)}
                        unit="%"
                        min={0.1}
                        step={0.1}
                      />
                      <p className="text-[10px] text-muted mt-1">Pullback from the peak before closing</p>
                    </div>
                    <div>
                      <label className={labelCls}>Step (%)</label>
                      <UnitInput
                        value={settings.riskSettings.trailingStepPct ?? 0.5}
                        onChange={(v) => updateRiskSettings('trailingStepPct', v)}
                        unit="%"
                        min={0.1}
                        step={0.1}
                      />
                      <p className="text-[10px] text-muted mt-1">How often to raise the stop</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="border-b border-border pb-4 mb-4">
                <div className="flex items-center gap-2 mb-3">
                  <TrendingDown size={14} className="text-primary" />
                  <h4 className="text-sm font-medium text-white">Drawdown Limits</h4>
                  <p className="text-[10px] text-muted ml-auto text-right">1% loss · 2% profit</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Max daily loss ({isPct ? '%' : '$'})</label>
                    <UnitInput
                      value={settings.riskSettings.maxDailyLoss ?? (isPct ? 5 : 500)}
                      onChange={(v) => updateRiskSettings('maxDailyLoss', v)}
                      unit={isPct ? '%' : '$'}
                      min={0}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Max daily profit ({isPct ? '%' : '$'})</label>
                    <UnitInput
                      value={settings.riskSettings.maxDailyProfit ?? (isPct ? 5 : 1000)}
                      onChange={(v) => updateRiskSettings('maxDailyProfit', v)}
                      unit={isPct ? '%' : '$'}
                      min={0}
                    />
                  </div>
                </div>
                <p className="text-[10px] text-muted mt-1">
                  {suggestions
                    ? isPct
                      ? `Suggested: cap losses at 1% of balance ($${suggestions.dailyLoss.toLocaleString()}), bank 2% of balance ($${suggestions.dailyProfit.toLocaleString()})`
                      : `Suggested: stop at $${suggestions.dailyLoss.toLocaleString()} (1% of balance), bank $${suggestions.dailyProfit.toLocaleString()} (2% of balance)`
                    : 'Enter an account balance to get daily limit suggestions'}
                </p>
              </div>

              <div className="flex items-center justify-between p-3 bg-background border border-border rounded-lg mt-4">
                <div>
                  <p className="text-sm font-medium text-white flex items-center gap-1.5">
                    <Sparkles size={14} className="text-amber-400" />
                    Enable auto-trading
                  </p>
                  <p className="text-xs text-muted">Execute trades automatically — use with caution</p>
                </div>
                <Toggle
                  checked={settings.riskSettings.enableAutoTrade}
                  onChange={(v) => updateRiskSettings('enableAutoTrade', v)}
                />
              </div>
            </>
          );
        })()}
      </div>


      {/* Notifications */}
      <div className="glass-card rounded-xl p-4">
        <SectionHeader icon={Bell} label="Notifications" />

        <div className="space-y-2">
          {(['tradeAlerts', 'priceAlerts', 'newsAlerts'] as const).map((key) => (
            <div key={key} className="flex items-center justify-between p-3 bg-background border border-border rounded-lg">
              <span className="text-sm text-white capitalize">{key.replace(/([A-Z])/g, ' $1').trim()}</span>
              <Toggle
                checked={settings.notifications[key] as boolean}
                onChange={(v) => updateNotifications(key, v)}
              />
            </div>
          ))}
          
          <div className="mt-4 space-y-3 pt-3 border-t border-border">
            <div>
              <label className={labelCls}>Telegram Bot Token</label>
              <input
                type="text"
                value={settings.notifications.telegramBotToken || ''}
                onChange={(e) => updateNotifications('telegramBotToken', e.target.value)}
                className={inputCls}
                placeholder="123456789:ABCdefGHIjklmNOPqrSTuvw"
              />
            </div>
            <div>
              <label className={labelCls}>Telegram Chat ID</label>
              <input
                type="text"
                value={settings.notifications.telegramChatId || ''}
                onChange={(e) => updateNotifications('telegramChatId', e.target.value)}
                className={inputCls}
                placeholder="-100123456789"
              />
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <label className={labelCls}>Alert Confidence Threshold</label>
                <span className="text-white text-sm font-mono">{settings.notifications.telegramThreshold ?? 80}%</span>
              </div>
              <input
                type="range"
                min="50"
                max="95"
                step="5"
                value={settings.notifications.telegramThreshold ?? 80}
                onChange={(e) => updateNotifications('telegramThreshold', parseInt(e.target.value))}
                className="w-full accent-primary"
              />
              <p className="text-xs text-muted mt-1">Only send alerts for signals above this confidence level</p>
            </div>
            <button
              onClick={() => {
                const api = settings.apiEndpoint || 'http://127.0.0.1:8001';
                fetch(`${api}/api/test-telegram`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    token: settings.notifications.telegramBotToken,
                    chat_id: settings.notifications.telegramChatId
                  })
                }).then(r => r.json()).then(res => alert(res.message || 'Error')).catch(e => alert(e));
              }}
              className="w-full px-3 py-2 bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 border border-blue-500/30 rounded-lg text-xs font-semibold transition-colors"
            >
              Test Telegram Notification
            </button>
          </div>
        </div>
      </div>

      {/* Data Providers */}
      <div className="glass-card rounded-xl p-4">
        <SectionHeader icon={Key} label="Data Providers (API Keys)" />
        <div className="space-y-3">
          <div>
            <label className={labelCls}>Finnhub API Key (Primary Real-time)</label>
            <input
              type="text"
              value={settings.apiKeys?.finnhub || ''}
              onChange={(e) => setSettings(prev => ({ ...prev, apiKeys: { ...prev.apiKeys, finnhub: e.target.value } }))}
              className={inputCls}
              placeholder="Enter Finnhub API Key"
            />
          </div>
          <div>
            <label className={labelCls}>Twelve Data API Key (Primary Historical)</label>
            <input
              type="text"
              value={settings.apiKeys?.twelvedata || ''}
              onChange={(e) => setSettings(prev => ({ ...prev, apiKeys: { ...prev.apiKeys, twelvedata: e.target.value } }))}
              className={inputCls}
              placeholder="Enter Twelve Data API Key"
            />
          </div>
          <div>
            <label className={labelCls}>Alpha Vantage API Key (Fallback)</label>
            <input
              type="text"
              value={settings.apiKeys?.alphavantage || ''}
              onChange={(e) => setSettings(prev => ({ ...prev, apiKeys: { ...prev.apiKeys, alphavantage: e.target.value } }))}
              className={inputCls}
              placeholder="Enter Alpha Vantage API Key"
            />
          </div>
        </div>
      </div>

      {/* Backend */}
      <div className="glass-card rounded-xl p-4">
        <SectionHeader icon={Server} label="Backend" />
        <div>
          <label className={labelCls}>API endpoint</label>
          <input
            type="text"
            value={settings.apiEndpoint}
            onChange={(e) => setSettings(prev => ({ ...prev, apiEndpoint: e.target.value }))}
            className={inputCls}
            placeholder="http://127.0.0.1:8001"
          />
        </div>
      </div>

      {/* Save */}
      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={() => saveSettings()}
        className={`w-full px-4 py-2.5 rounded-xl text-sm font-semibold text-white transition-colors flex items-center justify-center gap-2 ${
          saved ? 'bg-accent' : 'bg-primary hover:bg-blue-400'
        }`}
      >
        <Save className="w-4 h-4" />
        {saved ? 'Saved!' : 'Save Settings'}
      </motion.button>
    </div>
  );
};

export default Settings;

