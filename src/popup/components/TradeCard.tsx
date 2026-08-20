import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Target, Shield, DollarSign, BarChart2 } from 'lucide-react';
import { TradeRecommendation } from '../../types';

interface TradeCardProps {
  trade: TradeRecommendation;
  onConfirm: () => void;
  onReject: () => void;
}

const TradeCard: React.FC<TradeCardProps> = ({ trade, onConfirm, onReject }) => {
  const isBuy = trade.type === 'BUY';

  // Math.abs handles both BUY (TP > entry) and SELL (TP < entry) correctly
  const entry = trade.entryPrice || 1;
  const profitPotential = Math.abs((trade.takeProfit - trade.entryPrice) / entry) * 100;
  const riskPotential = Math.abs((trade.entryPrice - trade.stopLoss) / entry) * 100;
  const riskRewardRatio = riskPotential > 0 ? profitPotential / riskPotential : 0;

  const directionColor = isBuy ? 'text-accent' : 'text-danger';
  const directionBg = isBuy ? 'bg-accent/10 border-accent/20' : 'bg-danger/10 border-danger/20';

  return (
    <div className="glass-card rounded-xl p-4 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center border ${directionBg}`}>
            {isBuy ? (
              <TrendingUp className={`w-5 h-5 ${directionColor}`} />
            ) : (
              <TrendingDown className={`w-5 h-5 ${directionColor}`} />
            )}
          </div>
          <div>
            <h3 className="text-base font-bold text-white">{trade.symbol}</h3>
            <p className="text-xs text-muted">{trade.assetType}</p>
          </div>
        </div>
        <div className="text-right space-y-1">
          <div className={`inline-flex px-2.5 py-0.5 rounded border text-xs font-semibold ${directionBg} ${directionColor}`}>
            {trade.type}
          </div>
          <p className="text-xs text-muted">{trade.confidence}% confidence</p>
          {trade.strategyAgreement !== undefined && trade.strategiesActive !== undefined && (
            <p className={`text-[10px] font-semibold ${trade.strategyAgreement >= 1 ? 'text-emerald-400' : 'text-zinc-500'}`}>
              {trade.strategyAgreement}/{trade.strategiesActive} strategies agree
            </p>
          )}
          {trade.details?.models_agreeing !== undefined && trade.details?.models_total !== undefined && (
            <p className="text-[10px] text-zinc-500">
              Models: {trade.details.models_agreeing}/{trade.details.models_total} agree
              {trade.details.model_disagreement !== undefined && ` (±${trade.details.model_disagreement})`}
            </p>
          )}
        </div>
      </div>

      {/* Price Info */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-background border border-border rounded-lg p-2.5">
          <div className="flex items-center space-x-1 mb-1">
            <DollarSign className="w-3 h-3 text-muted" />
            <span className="text-[10px] text-muted">Entry</span>
          </div>
          <p className="text-sm font-semibold text-white font-mono">${(trade.entryPrice ?? 0).toFixed(2)}</p>
        </div>
        <div className="bg-background border border-border rounded-lg p-2.5">
          <div className="flex items-center space-x-1 mb-1">
            <Shield className="w-3 h-3 text-danger" />
            <span className="text-[10px] text-muted">Stop</span>
          </div>
          <p className="text-sm font-semibold text-white font-mono">${(trade.stopLoss ?? 0).toFixed(2)}</p>
        </div>
        <div className="bg-background border border-border rounded-lg p-2.5">
          <div className="flex items-center space-x-1 mb-1">
            <Target className="w-3 h-3 text-accent" />
            <span className="text-[10px] text-muted">Target</span>
          </div>
          <p className="text-sm font-semibold text-white font-mono">${(trade.takeProfit ?? 0).toFixed(2)}</p>
        </div>
      </div>

      {/* Risk/Reward */}
      <div className="flex items-center justify-between bg-background border border-border rounded-lg p-3">
        <div className="flex items-center space-x-2">
          <div className="w-7 h-7 bg-surface rounded-lg flex items-center justify-center">
            <BarChart2 className="w-4 h-4 text-muted" />
          </div>
          <div>
            <p className="text-xs text-muted">R:R Ratio</p>
            <p className="text-sm font-semibold text-white font-mono">1:{riskRewardRatio.toFixed(2)}</p>
          </div>
        </div>
        <div className="text-right font-mono">
          <p className="text-xs text-accent">+{profitPotential.toFixed(2)}%</p>
          <p className="text-xs text-danger">-{riskPotential.toFixed(2)}%</p>
        </div>
      </div>

      {/* Analysis */}
      <div className="bg-background border border-border rounded-lg p-3 space-y-2">
        <p className="text-xs font-medium text-gray-300">Analysis</p>
        <p className="text-xs text-gray-400 leading-relaxed">{trade.reasoning.summary}</p>

        <div className="flex flex-wrap gap-1 pt-1">
          {trade.reasoning.technicalIndicators.map((indicator, i) => (
            <span
              key={i}
              className="px-1.5 py-0.5 glass-card rounded text-[10px] text-gray-400"
            >
              {indicator}
            </span>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
          <div>
            <p className="text-[10px] text-muted mb-0.5">Trend</p>
            <p className="text-xs font-medium text-white">{trade.reasoning.marketTrend}</p>
          </div>
          <div>
            <p className="text-[10px] text-muted mb-0.5">Sentiment</p>
            <p className="text-xs font-medium text-white">{trade.reasoning.sentiment}</p>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex space-x-3 pt-1">
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={onReject}
          className="flex-1 px-4 py-2.5 bg-background hover:bg-zinc-800 border border-border rounded-lg text-xs font-medium text-gray-300 transition-colors"
        >
          Dismiss
        </motion.button>
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={onConfirm}
          className={`flex-1 px-4 py-2.5 rounded-lg text-xs font-semibold transition-colors ${
            isBuy
              ? 'bg-accent hover:bg-emerald-400 text-black'
              : 'bg-danger hover:bg-red-400 text-white'
          }`}
        >
          Execute
        </motion.button>
      </div>
    </div>
  );
};

export default TradeCard;
