export interface TradeRecommendation {
  id: string;
  symbol: string;
  type: 'BUY' | 'SELL';
  assetType: 'FOREX' | 'STOCK';
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  reasoning: {
    technicalIndicators: string[];
    marketTrend: string;
    sentiment: string;
    summary: string;
    cnsContext?: {
      dxy_trend: string;
      hurst: number;
      entropy: number;
      institutional_wall: boolean;
    };
  };
  timestamp: number;
  status: 'pending' | 'confirmed' | 'rejected' | 'executed';
  // Attached by the background worker during live scans
  strategyAgreement?: number;
  strategiesActive?: number;
  details?: {
    model_disagreement?: number;
    models_agreeing?: number;
    models_total?: number;
    [key: string]: any;
  };
}

export interface MarketData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  timestamp: number;
}

export interface WatchlistItem {
  symbol: string;
  assetType: 'FOREX' | 'STOCK';
  addedAt: number;
}

export interface TradeLog {
  id: string;
  recommendation: TradeRecommendation;
  executedAt: number;
  executionPrice: number;
  result?: {
    exitPrice: number;
    profit: number;
    exitedAt: number;
    exitReason?: string;
    exitContext?: {
      vol_expansion: boolean;
      hit_target: boolean;
    };
  };
}

export interface RiskSettings {
  riskType?: 'dollar' | 'percentage';
  maxPositionSize: number;
  maxDailyLoss: number;
  maxDailyProfit?: number;
  stopLossPercentage: number;
  takeProfitPercentage: number;
  breakevenTriggerPct?: number;
  enableAutoTrade: boolean;
  trailingEnabled?: boolean;
  accountBalance?: number;
  trailingActivationPct?: number;
  trailingDistancePct?: number;
  trailingStepPct?: number;
}

export interface UserSettings {
  riskSettings: RiskSettings;
  notifications: {
    tradeAlerts: boolean;
    priceAlerts: boolean;
    newsAlerts: boolean;
    telegramBotToken?: string;
    telegramChatId?: string;
    telegramThreshold?: number;
  };
  apiEndpoint: string;
  mt5Url?: string;
  marketDataSources?: string[];
  apiKeys?: {
    finnhub?: string;
    twelvedata?: string;
    alphavantage?: string;
  };
}

export interface AIResponse {
  recommendations: TradeRecommendation[];
  marketAnalysis: {
    overall: string;
    sentiment: 'bullish' | 'bearish' | 'neutral';
    volatility: 'low' | 'medium' | 'high';
  };
}
