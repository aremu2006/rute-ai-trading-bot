import React from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, TrendingUp, TrendingDown, X } from 'lucide-react';
import { TradeRecommendation } from '../../types';

interface ConfirmationModalProps {
  trade: TradeRecommendation;
  onConfirm: () => void;
  onCancel: () => void;
}

const ConfirmationModal: React.FC<ConfirmationModalProps> = ({ trade, onConfirm, onCancel }) => {
  const isBuy = trade.type === 'BUY';

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
        className="glass-card rounded-2xl p-6 max-w-sm w-full space-y-4"
      >
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-yellow-500/15 border border-yellow-500/30 rounded-xl flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-yellow-400" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Confirm Trade</h3>
              <p className="text-xs text-muted">Review before executing</p>
            </div>
          </div>
          <button onClick={onCancel} className="text-muted hover:text-white transition-colors p-1">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Trade Details */}
        <div className="bg-background border border-border rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {isBuy ? (
                <TrendingUp className="w-4 h-4 text-accent" />
              ) : (
                <TrendingDown className="w-4 h-4 text-danger" />
              )}
              <span className="text-base font-bold text-white">{trade.symbol}</span>
            </div>
            <div className={`px-2.5 py-0.5 rounded-lg text-xs font-semibold ${
              isBuy ? 'bg-accent/15 text-accent' : 'bg-danger/15 text-danger'
            }`}>
              {trade.type}
            </div>
          </div>

          <div className="space-y-2 pt-1">
            <div className="flex justify-between text-sm">
              <span className="text-muted">Entry Price</span>
              <span className="font-mono font-medium text-white">${(trade.entryPrice ?? 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Stop Loss</span>
              <span className="font-mono font-medium text-danger">${(trade.stopLoss ?? 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Take Profit</span>
              <span className="font-mono font-medium text-accent">${(trade.takeProfit ?? 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted">Confidence</span>
              <span className="font-mono font-medium text-yellow-400">{trade.confidence}%</span>
            </div>
          </div>
        </div>

        {/* Warning */}
        <div className="bg-yellow-500/8 border border-yellow-500/25 rounded-lg p-3">
          <p className="text-xs text-yellow-200/80">
            This will execute the trade on your trading platform. Review all details carefully before confirming.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex space-x-3">
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onCancel}
            className="flex-1 px-4 py-2.5 bg-background hover:bg-zinc-800 border border-border rounded-xl text-sm font-medium text-gray-300 transition-colors"
          >
            Cancel
          </motion.button>
          <motion.button
            whileTap={{ scale: 0.97 }}
            onClick={onConfirm}
            className={`flex-1 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
              isBuy
                ? 'bg-accent hover:bg-emerald-400 text-black'
                : 'bg-danger hover:bg-red-400 text-white'
            }`}
          >
            Confirm & Execute
          </motion.button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default ConfirmationModal;
