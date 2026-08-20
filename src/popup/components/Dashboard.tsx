import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, Link, RefreshCw } from 'lucide-react';
import { TradeRecommendation } from '../../types';
import TradeCard from './TradeCard';
import ConfirmationModal from './ConfirmationModal';

const Dashboard: React.FC = () => {
  const [recommendations, setRecommendations] = useState<TradeRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTrade, setSelectedTrade] = useState<TradeRecommendation | null>(null);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [tradingPlatformUrl, setTradingPlatformUrl] = useState('');

  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['userSettings'], (result) => {
        if (result.userSettings?.mt5Url) {
          setTradingPlatformUrl(result.userSettings.mt5Url);
        }
      });
    }
  }, []);

  useEffect(() => {
    loadRecommendations();

    // If nothing is cached (fresh worker / alarms lost), ask the background to
    // run a scan NOW instead of waiting up to 5 minutes for the alarm.
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['rute_recommendations'], (result) => {
        if (!Array.isArray(result.rute_recommendations) || result.rute_recommendations.length === 0) {
          chrome.runtime.sendMessage({ type: 'REFRESH_RECOMMENDATIONS' });
        }
      });
    }

    if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
      const listener = (message: any) => {
        if (message.type === 'NEW_RECOMMENDATIONS') {
          setRecommendations(message?.recommendations || []);
        }
      };
      chrome.runtime.onMessage.addListener(listener);
      return () => chrome.runtime.onMessage.removeListener(listener);
    }
  }, []);

  const loadRecommendations = async () => {
    try {
      setLoading(true);

      if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
        setLoading(false);
        return;
      }

      chrome.runtime.sendMessage({ type: 'GET_RECOMMENDATIONS' }, (response) => {
        if (chrome.runtime.lastError) {
          setLoading(false);
          return;
        }
        if (response?.recommendations) {
          setRecommendations(response?.recommendations || []);
        }
        setLoading(false);
      });
    } catch (error) {
      console.error('Error loading recommendations:', error);
      setLoading(false);
    }
  };

  const handleTradeAction = (trade: TradeRecommendation, action: 'confirm' | 'reject') => {
    if (action === 'confirm') {
      setSelectedTrade(trade);
      setShowConfirmation(true);
    } else {
      if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
        chrome.runtime.sendMessage({ type: 'UPDATE_TRADE_STATUS', tradeId: trade.id, status: 'rejected' });
      }
      setRecommendations(prev => prev.filter(r => r.id !== trade.id));
    }
  };

  const handleConfirmTrade = async () => {
    if (!selectedTrade) return;

    try {
      if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
        chrome.runtime.sendMessage({ type: 'EXECUTE_TRADE', trade: selectedTrade }, (response) => {
          if (chrome.runtime.lastError) {
            console.error('Trade execution failed:', chrome.runtime.lastError);
            return;
          }
          if (response?.success) {
            setRecommendations(prev => prev.filter(r => r.id !== selectedTrade!.id));
            setShowConfirmation(false);
            setSelectedTrade(null);
          }
        });
      } else {
        setRecommendations(prev => prev.filter(r => r.id !== selectedTrade.id));
        setShowConfirmation(false);
        setSelectedTrade(null);
      }
    } catch (error) {
      console.error('Error executing trade:', error);
    }
  };

  const handleRefresh = () => {
    if (typeof chrome !== 'undefined' && chrome.runtime?.sendMessage) {
      chrome.runtime.sendMessage({ type: 'REFRESH_RECOMMENDATIONS' });
    }
    loadRecommendations();
  };

  const saveTradingPlatformUrl = () => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['userSettings'], (result) => {
        const settings = { ...(result.userSettings || {}), mt5Url: tradingPlatformUrl };
        chrome.storage.local.set({ userSettings: settings });
      });
    }
  };

  const handleBrokerUrlKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      saveTradingPlatformUrl();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-80">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-muted text-sm">Loading recommendations...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-4">


      {/* Section header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-gray-200">
          Signals
          {recommendations.length > 0 && (
            <span className="ml-2 text-xs text-muted font-normal">{recommendations.length} active</span>
          )}
        </h2>
        <button
          onClick={handleRefresh}
          className="flex items-center space-x-1.5 px-3 py-1.5 glass-card hover:border-zinc-600 rounded-lg text-xs text-muted hover:text-gray-200 transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          <span>Refresh</span>
        </button>
      </div>

      {/* Recommendations List */}
      <div className="space-y-3">
        {recommendations.length === 0 ? (
          <div className="glass-card rounded-xl p-8 text-center">
            <div className="w-10 h-10 bg-background rounded-full flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-5 h-5 text-muted" />
            </div>
            <p className="text-gray-300 text-sm font-medium">No signals found</p>
            <p className="text-muted text-xs mt-1">Hit refresh to scan for new setups</p>
          </div>
        ) : (
          recommendations.map((trade, index) => (
            <motion.div
              key={trade.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.08 }}
            >
              <TradeCard
                trade={trade}
                onConfirm={() => handleTradeAction(trade, 'confirm')}
                onReject={() => handleTradeAction(trade, 'reject')}
              />
            </motion.div>
          ))
        )}
      </div>

      {/* Confirmation Modal */}
      {showConfirmation && selectedTrade && (
        <ConfirmationModal
          trade={selectedTrade}
          onConfirm={handleConfirmTrade}
          onCancel={() => {
            setShowConfirmation(false);
            setSelectedTrade(null);
          }}
        />
      )}
    </div>
  );
};

export default Dashboard;
