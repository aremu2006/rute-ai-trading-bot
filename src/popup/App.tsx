import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Dashboard from './components/Dashboard';
import TradeHistory from './components/TradeHistory';
import Settings from './components/Settings';
import LiveMarket from './components/LiveMarket';
import Logic from './components/Logic';
import Portfolio from './components/Portfolio';
import Backtest from './components/Backtest';
import { TrendingUp, History, Settings as SettingsIcon, Activity, Briefcase, FlaskConical } from 'lucide-react';

type Tab = 'dashboard' | 'market' | 'strategies' | 'portfolio' | 'history' | 'settings';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard');
  const [account, setAccount] = useState<{ balance: number; currency: string } | null>(null);

  useEffect(() => {
    const fetchAccount = async () => {
      try {
        // Read apiEndpoint from chrome.storage (same source as Settings.tsx)
        const stored = await new Promise<any>((resolve) => {
          if (typeof chrome !== 'undefined' && chrome.storage?.local) {
            chrome.storage.local.get(['userSettings'], resolve);
          } else {
            resolve({});
          }
        });
        const apiEndpoint = stored.userSettings?.apiEndpoint || 'http://127.0.0.1:8001';
        
        const res = await fetch(`${apiEndpoint}/api/portfolio`);
        if (res.ok) {
          const data = await res.json();
          if (data.account) {
            setAccount(data.account);
          }
        }
      } catch (e) {
        // silently ignore for header
      }
    };
    
    fetchAccount();
    const interval = setInterval(fetchAccount, 10000);
    return () => clearInterval(interval);
  }, []);

  const tabs = [
    { id: 'dashboard' as Tab, label: 'Signals', icon: TrendingUp },
    { id: 'market'    as Tab, label: 'Market',  icon: Activity },
    { id: 'strategies' as Tab, label: 'Strategies', icon: FlaskConical },
    { id: 'portfolio' as Tab, label: 'Portfolio', icon: Briefcase },
    { id: 'history'   as Tab, label: 'History',  icon: History },
    { id: 'settings'  as Tab, label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <div className="w-[420px] h-[600px] text-gray-100 font-sans flex flex-col relative overflow-hidden bg-[#09090b]">
      
      {/* Background Layer */}
      <div className="absolute inset-0 pointer-events-none mesh-bg" />
      <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-72 h-72 rounded-full bg-primary/[0.12] blur-[80px] pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-56 h-56 rounded-full bg-secondary/[0.10] blur-[80px] pointer-events-none" />

      {/* Header */}
      <header className="relative z-10 flex-shrink-0 glass-panel border-x-0 border-t-0 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-7 h-7 rounded-lg overflow-hidden flex items-center justify-center bg-transparent ring-1 ring-white/10">
              <img src="Logo.png" alt="RUTE Logo" className="w-full h-full object-cover" />
            </div>
            <h1 className="text-base font-bold tracking-tight bg-gradient-to-r from-blue-400 via-violet-400 to-emerald-400 bg-clip-text text-transparent">
              RUTE
            </h1>
          </div>
          {account ? (
            <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/25 rounded-lg px-2.5 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-mono font-bold text-emerald-400 tabular-nums">
                ${account.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className="text-[9px] text-emerald-400/60 uppercase tracking-wide">{account.currency}</span>
            </div>
          ) : (
            <span className="text-[11px] text-muted tracking-wide">Trading Assistant</span>
          )}
        </div>
      </header>

      {/* Scrollable Content Area */}
      <main className="relative z-10 flex-1 overflow-y-auto px-3 pt-3 pb-3">
        <AnimatePresence mode="wait">
          {activeTab === 'dashboard' && (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <Dashboard />
            </motion.div>
          )}
          {activeTab === 'market' && (
            <motion.div
              key="market"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <LiveMarket />
            </motion.div>
          )}
          {activeTab === 'strategies' && (
            <motion.div
              key="strategies"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <Backtest />
            </motion.div>
          )}
          {activeTab === 'portfolio' && (
            <motion.div
              key="portfolio"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <Portfolio />
            </motion.div>
          )}
          {activeTab === 'history' && (
            <motion.div
              key="history"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <TradeHistory />
            </motion.div>
          )}
          {activeTab === 'settings' && (
            <motion.div
              key="settings"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <Settings />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Navigation */}
      <nav className="relative z-10 flex-shrink-0 glass-panel border-x-0 border-b-0 px-2 py-1.5">
        <div className="flex items-center justify-around">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex flex-col items-center justify-center gap-1 w-16 h-11 rounded-xl transition-colors ${
                  isActive ? 'text-white' : 'text-muted hover:text-zinc-300'
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeTabBg"
                    className="absolute inset-0 rounded-xl bg-gradient-to-b from-blue-500/25 to-violet-500/15 border border-primary/25 shadow-[0_0_16px_rgba(59,130,246,0.2)]"
                    transition={{ type: 'spring', bounce: 0.2, duration: 0.5 }}
                  />
                )}
                <Icon className="w-[17px] h-[17px] z-10" />
                <span className="text-[9px] tracking-wide z-10 leading-none font-medium">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

export default App;