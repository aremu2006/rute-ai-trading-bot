import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Clock, TrendingUp, AlertCircle, Lightbulb, CheckCircle, XCircle, ChevronDown, ChevronUp, FileText, Search } from 'lucide-react';

interface ThoughtItem {
  timestamp: string;
  thought: any;
}

interface SymbolThoughts {
  symbol: string;
  analysis: ThoughtItem[];
  decisions: ThoughtItem[];
  executions: ThoughtItem[];
  outcomes: ThoughtItem[];
}

interface LearningSummary {
  timeframe: string;
  performance_metrics: {
    total_trades: number;
    wins: number;
    losses: number;
    win_rate: number;
    profit_factor: number;
  };
  successful_patterns: Array<{
    pattern: string;
    count: number;
    win_rate: number;
  }>;
  mistakes_learned: Array<{
    mistake: string;
    corrective_action: string;
  }>;
}

const Logic: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('AAPL');
  const [thoughts, setThoughts] = useState<SymbolThoughts | null>(null);
  const [learningSummary, setLearningSummary] = useState<LearningSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    analysis: true,
    decisions: true,
    executions: true,
    outcomes: true,
    learning: false,
  });

  const symbols = ['AAPL', 'TSLA', 'GOOGL', 'MSFT', 'AMZN', 'BTC-USD', 'ETH-USD', 'EURUSD=X'];

  useEffect(() => {
    fetchThoughts();
    fetchLearningSummary();
  }, [selectedSymbol]);

  const fetchThoughts = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://127.0.0.1:8001/api/thoughts/${selectedSymbol}`);
      const data = await response.json();
      setThoughts(data);
    } catch (error) {
      console.error('Error fetching thoughts:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchLearningSummary = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8001/api/learning/summary?days=7');
      const data = await response.json();
      setLearningSummary(data);
    } catch (error) {
      console.error('Error fetching learning summary:', error);
    }
  };

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const renderAnalysisThoughts = () => {
    if (!thoughts?.analysis || thoughts.analysis.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-10 space-y-4">
          <div className="relative">
            <motion.div animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.7, 0.3] }} transition={{ duration: 2, repeat: Infinity }} className="absolute inset-0 bg-primary/20 rounded-full blur-xl" />
            <Search className="w-8 h-8 text-primary relative z-10" />
          </div>
          <p className="text-muted text-sm animate-pulse">Scanning market patterns...</p>
        </div>
      );
    }

    return thoughts.analysis.map((item, idx) => (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.1 }}
        className="bg-background border border-border rounded-lg p-3 mb-2"
      >
        <span className="text-xs text-muted block mb-2">{new Date(item.timestamp).toLocaleString()}</span>
        <div className="space-y-2 text-sm">
          <p className="text-gray-300"><span className="text-primary font-medium">Observation: </span>{item.thought.observation}</p>
          {item.thought.technical_analysis && (
            <div>
              <p className="text-gray-300 font-medium mb-1 text-xs">Technical signals</p>
              <ul className="text-muted text-xs space-y-1 ml-3">
                {item.thought.technical_analysis.indicators?.map((ind: string, i: number) => (
                  <li key={i}>• {ind}</li>
                ))}
              </ul>
            </div>
          )}
          {item.thought.ml_analysis && (
            <div>
              <p className="text-gray-300 text-xs">Prediction: <span className="text-accent">{item.thought.ml_analysis.prediction}</span></p>
              <p className="text-muted text-xs">Confidence: {item.thought.ml_analysis.confidence}%</p>
            </div>
          )}
        </div>
      </motion.div>
    ));
  };

  const renderDecisionThoughts = () => {
    if (!thoughts?.decisions || thoughts.decisions.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-10 space-y-4">
          <div className="relative">
            <motion.div animate={{ rotate: 360 }} transition={{ duration: 8, repeat: Infinity, ease: "linear" }} className="w-12 h-12 border-2 border-dashed border-accent/50 rounded-full flex items-center justify-center">
              <Lightbulb className="w-5 h-5 text-accent" />
            </motion.div>
          </div>
          <p className="text-muted text-sm animate-pulse">Awaiting ML signal confidence...</p>
        </div>
      );
    }

    return thoughts.decisions.map((item, idx) => (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.1 }}
        className="bg-background border border-border rounded-lg p-3 mb-2"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted">{new Date(item.timestamp).toLocaleString()}</span>
          <span className={`text-xs px-2 py-0.5 rounded ${
            item.thought.decision?.includes('EXECUTE') ? 'bg-accent/15 text-accent' : 'bg-yellow-500/15 text-yellow-400'
          }`}>
            {item.thought.decision}
          </span>
        </div>
        {item.thought.reasoning_chain && (
          <div className="mt-2">
            <p className="text-gray-300 text-xs font-medium mb-1">Reasoning</p>
            <div className="space-y-1">
              {item.thought.reasoning_chain.slice(0, 5).map((step: string, i: number) => (
                <p key={i} className="text-xs text-muted ml-2">→ {step}</p>
              ))}
              {item.thought.reasoning_chain.length > 5 && (
                <p className="text-xs text-muted/60 ml-2">+{item.thought.reasoning_chain.length - 5} more steps</p>
              )}
            </div>
          </div>
        )}
        {item.thought.alternatives_considered && item.thought.alternatives_considered.length > 0 && (
          <div className="mt-2">
            <p className="text-gray-300 text-xs font-medium mb-1">Alternatives considered</p>
            {item.thought.alternatives_considered.map((alt: any, i: number) => (
              <p key={i} className="text-xs text-muted ml-2">• {alt.option} — {alt.rejected_because}</p>
            ))}
          </div>
        )}
      </motion.div>
    ));
  };

  const renderExecutionThoughts = () => {
    if (!thoughts?.executions || thoughts.executions.length === 0) {
      return <p className="text-muted text-sm py-2">No executions logged yet</p>;
    }

    return thoughts.executions.map((item, idx) => (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.1 }}
        className="bg-background border border-border rounded-lg p-3 mb-2"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted">{new Date(item.timestamp).toLocaleString()}</span>
          <span className="text-xs px-2 py-0.5 rounded bg-primary/15 text-primary">
            {item.thought.action}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div>
            <p className="text-muted text-xs">Quantity</p>
            <p className="text-gray-200 text-xs font-mono">{item.thought.quantity} shares</p>
          </div>
          <div>
            <p className="text-muted text-xs">Entry</p>
            <p className="text-gray-200 text-xs font-mono">${(item.thought.entry_price ?? 0).toFixed(2)}</p>
          </div>
          <div>
            <p className="text-muted text-xs">Stop Loss</p>
            <p className="text-danger text-xs font-mono">${(item.thought.stop_loss ?? 0).toFixed(2)}</p>
          </div>
          <div>
            <p className="text-muted text-xs">Take Profit</p>
            <p className="text-accent text-xs font-mono">${(item.thought.take_profit ?? 0).toFixed(2)}</p>
          </div>
        </div>
        {item.thought.execution_thoughts && (
          <p className="mt-2 text-xs text-muted">• {item.thought.execution_thoughts.why_market_order}</p>
        )}
      </motion.div>
    ));
  };

  const renderOutcomeThoughts = () => {
    if (!thoughts?.outcomes || thoughts.outcomes.length === 0) {
      return <p className="text-muted text-sm py-2">No outcomes logged yet</p>;
    }

    return thoughts.outcomes.map((item, idx) => (
      <motion.div
        key={idx}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: idx * 0.1 }}
        className={`rounded-lg p-3 mb-2 border ${
          item.thought.outcome === 'WIN'
            ? 'bg-accent/8 border-accent/25'
            : 'bg-danger/8 border-danger/25'
        }`}
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted">{new Date(item.timestamp).toLocaleString()}</span>
          <div className="flex items-center space-x-1.5">
            {item.thought.outcome === 'WIN' ? (
              <CheckCircle className="w-3.5 h-3.5 text-accent" />
            ) : (
              <XCircle className="w-3.5 h-3.5 text-danger" />
            )}
            <span className={`text-xs font-medium ${item.thought.outcome === 'WIN' ? 'text-accent' : 'text-danger'}`}>
              {item.thought.outcome}
            </span>
          </div>
        </div>

        {item.thought.outcome === 'WIN' && item.thought.what_worked && (
          <div className="mt-2">
            <p className="text-gray-300 text-xs font-medium mb-1">What worked</p>
            <ul className="space-y-0.5">
              {item.thought.what_worked.slice(0, 3).map((point: string, i: number) => (
                <li key={i} className="text-xs text-muted ml-2">✓ {point}</li>
              ))}
            </ul>
          </div>
        )}

        {item.thought.outcome === 'LOSS' && item.thought.what_went_wrong && (
          <div className="mt-2">
            <p className="text-gray-300 text-xs font-medium mb-1">What went wrong</p>
            <ul className="space-y-0.5">
              {item.thought.what_went_wrong.slice(0, 3).map((point: string, i: number) => (
                <li key={i} className="text-xs text-muted ml-2">✗ {point}</li>
              ))}
            </ul>
          </div>
        )}

        {item.thought.learning_points && (
          <div className="mt-2">
            <p className="text-gray-300 text-xs font-medium mb-1 flex items-center">
              <Lightbulb className="w-3 h-3 mr-1" /> Learnings
            </p>
            <ul className="space-y-0.5">
              {item.thought.learning_points.slice(0, 3).map((point: string, i: number) => (
                <li key={i} className="text-xs text-muted ml-2">• {point}</li>
              ))}
            </ul>
          </div>
        )}
      </motion.div>
    ));
  };

  const renderLearning = () => {
    if (!learningSummary || 'error' in learningSummary) {
      return (
        <div className="bg-background border border-border rounded-lg p-4 text-center">
          <AlertCircle className="w-6 h-6 text-muted mx-auto mb-2" />
          <p className="text-muted text-xs">Learning data appears after auto-trading is enabled</p>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        <div className="bg-background border border-border rounded-lg p-3">
          <p className="text-xs font-medium text-gray-300 mb-3">Performance (7 days)</p>
          {(() => {
            const pm = learningSummary?.performance_metrics;
            if (!pm) return <p className="text-xs text-muted">No performance data yet</p>;
            return (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-muted text-xs">Total Trades</p>
                  <p className="text-white text-lg font-bold font-mono">{pm.total_trades ?? 0}</p>
                </div>
                <div>
                  <p className="text-muted text-xs">Win Rate</p>
                  <p className={`text-lg font-bold font-mono ${(pm.win_rate ?? 0) >= 50 ? 'text-accent' : 'text-danger'}`}>
                    {(pm.win_rate ?? 0).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-muted text-xs">Wins</p>
                  <p className="text-accent text-lg font-bold font-mono">{pm.wins ?? 0}</p>
                </div>
                <div>
                  <p className="text-muted text-xs">Losses</p>
                  <p className="text-danger text-lg font-bold font-mono">{pm.losses ?? 0}</p>
                </div>
              </div>
            );
          })()}
        </div>

        {learningSummary.successful_patterns && learningSummary.successful_patterns.length > 0 && (
          <div className="bg-accent/8 border border-accent/25 rounded-lg p-3">
            <h4 className="text-accent text-xs font-medium mb-2 flex items-center">
              <CheckCircle className="w-3.5 h-3.5 mr-1.5" /> Successful patterns
            </h4>
            <div className="space-y-2">
              {learningSummary.successful_patterns.slice(0, 3).map((pattern, idx) => (
                <div key={idx} className="text-xs">
                  <p className="text-gray-300">{pattern.pattern}</p>
                  <p className="text-muted">{pattern.win_rate.toFixed(1)}% win rate · {pattern.count} trades</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {learningSummary.mistakes_learned && learningSummary.mistakes_learned.length > 0 && (
          <div className="bg-danger/8 border border-danger/25 rounded-lg p-3">
            <h4 className="text-danger text-xs font-medium mb-2 flex items-center">
              <AlertCircle className="w-3.5 h-3.5 mr-1.5" /> Mistakes to avoid
            </h4>
            <div className="space-y-2">
              {learningSummary.mistakes_learned.slice(0, 3).map((mistake, idx) => (
                <div key={idx} className="text-xs">
                  <p className="text-gray-300">✗ {mistake.mistake}</p>
                  <p className="text-muted">→ {mistake.corrective_action}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const Section = ({
    id,
    label,
    icon: Icon,
    iconColor,
    count,
    children,
  }: {
    id: keyof typeof expandedSections;
    label: string;
    icon: React.ElementType;
    iconColor: string;
    count?: number;
    children: React.ReactNode;
  }) => (
    <div className="glass-card rounded-xl overflow-hidden">
      <button
        onClick={() => toggleSection(id)}
        className="w-full flex items-center justify-between p-3 hover:bg-white/4 transition-colors"
      >
        <div className="flex items-center space-x-2">
          <Icon className={`w-4 h-4 ${iconColor}`} />
          <span className="text-sm font-medium text-gray-200">{label}</span>
          {count !== undefined && (
            <span className="text-xs text-muted">({count})</span>
          )}
        </div>
        {expandedSections[id] ? (
          <ChevronUp className="w-4 h-4 text-muted" />
        ) : (
          <ChevronDown className="w-4 h-4 text-muted" />
        )}
      </button>
      {expandedSections[id] && (
        <div className="px-3 pb-3">{children}</div>
      )}
    </div>
  );

  return (
    <div className="space-y-3 pb-20">
      {/* Header */}
      <div className="flex items-center space-x-2">
        <FileText className="w-4 h-4 text-muted" />
        <h2 className="text-base font-semibold text-white">Decision Log</h2>
      </div>

      {/* Symbol Selector */}
      <div className="flex space-x-2">
        {symbols.map(symbol => (
          <button
            key={symbol}
            onClick={() => setSelectedSymbol(symbol)}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              selectedSymbol === symbol
                ? 'bg-primary text-white'
                : 'glass-card text-muted hover:text-gray-200'
            }`}
          >
            {symbol}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : (
        <>
          <Section id="analysis" label="Analysis" icon={TrendingUp} iconColor="text-primary" count={thoughts?.analysis?.length}>
            {renderAnalysisThoughts()}
          </Section>

          <Section id="decisions" label="Decisions" icon={FileText} iconColor="text-secondary" count={thoughts?.decisions?.length}>
            {renderDecisionThoughts()}
          </Section>

          <Section id="executions" label="Executions" icon={Clock} iconColor="text-accent" count={thoughts?.executions?.length}>
            {renderExecutionThoughts()}
          </Section>

          <Section id="outcomes" label="Outcomes" icon={Lightbulb} iconColor="text-yellow-400" count={thoughts?.outcomes?.length}>
            {renderOutcomeThoughts()}
          </Section>

          <Section id="learning" label="Learning (7 days)" icon={CheckCircle} iconColor="text-accent">
            {renderLearning()}
          </Section>

          {(!thoughts || 'error' in thoughts || (
            !thoughts.analysis?.length &&
            !thoughts.decisions?.length &&
            !thoughts.executions?.length &&
            !thoughts.outcomes?.length
          )) && (
            <div className="bg-primary/8 border border-primary/25 rounded-xl p-4">
              <div className="flex items-start space-x-2.5">
                <AlertCircle className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-primary text-xs font-medium mb-1">No decisions logged yet</p>
                  <p className="text-gray-400 text-xs leading-relaxed">
                    Enable auto-trading in Settings to see the full decision log — every analysis, trade decision, and outcome will appear here.
                  </p>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Logic;
