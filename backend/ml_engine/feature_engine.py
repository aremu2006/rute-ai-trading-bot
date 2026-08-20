"""
Feature Engineering Pipeline
Generates 50+ technical indicators for ML model training
"""

import pandas as pd
import numpy as np
from ta.trend import (SMAIndicator, EMAIndicator, MACD, ADXIndicator,
                       AroonIndicator, CCIIndicator, IchimokuIndicator)
from ta.momentum import (RSIIndicator, StochasticOscillator, WilliamsRIndicator,
                          ROCIndicator, TSIIndicator, KAMAIndicator)
from ta.volatility import (BollingerBands, AverageTrueRange, KeltnerChannel,
                            DonchianChannel)
from ta.volume import (OnBalanceVolumeIndicator, ChaikinMoneyFlowIndicator,
                        ForceIndexIndicator, VolumePriceTrendIndicator)


class FeatureEngineer:
    def __init__(self):
        self.feature_names = []

    def add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features"""
        # Price changes
        df['price_change_1d'] = df['Close'].pct_change(1)
        df['price_change_3d'] = df['Close'].pct_change(3)
        df['price_change_5d'] = df['Close'].pct_change(5)
        df['price_change_10d'] = df['Close'].pct_change(10)

        # Price position
        df['high_low_diff'] = (df['High'] - df['Low']) / df['Close']
        df['close_high_diff'] = (df['High'] - df['Close']) / df['Close']
        df['close_low_diff'] = (df['Close'] - df['Low']) / df['Close']

        return df

    def add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend indicators (20+ features)"""
        close = df['Close']

        # Moving Averages
        for period in [5, 10, 20, 50, 100, 200]:
            sma = SMAIndicator(close=close, window=period)
            df[f'sma_{period}'] = sma.sma_indicator()
            df[f'price_to_sma_{period}'] = (close - df[f'sma_{period}']) / df[f'sma_{period}']

        # Exponential Moving Averages
        for period in [12, 26, 50]:
            ema = EMAIndicator(close=close, window=period)
            df[f'ema_{period}'] = ema.ema_indicator()

        # MACD
        macd = MACD(close=close)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()

        # ADX (Trend Strength)
        adx = ADXIndicator(high=df['High'], low=df['Low'], close=close)
        df['adx'] = adx.adx()
        df['adx_pos'] = adx.adx_pos()
        df['adx_neg'] = adx.adx_neg()

        # Aroon
        aroon = AroonIndicator(high=df['High'], low=df['Low'])
        df['aroon_up'] = aroon.aroon_up()
        df['aroon_down'] = aroon.aroon_down()
        df['aroon_indicator'] = aroon.aroon_indicator()

        # CCI (Commodity Channel Index)
        cci = CCIIndicator(high=df['High'], low=df['Low'], close=close)
        df['cci'] = cci.cci()

        return df

    def add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum indicators (15+ features)"""
        close = df['Close']

        # RSI (multiple periods)
        for period in [7, 14, 21]:
            rsi = RSIIndicator(close=close, window=period)
            df[f'rsi_{period}'] = rsi.rsi()

        # Stochastic Oscillator
        stoch = StochasticOscillator(high=df['High'], low=df['Low'], close=close)
        df['stoch_k'] = stoch.stoch()
        df['stoch_d'] = stoch.stoch_signal()

        # Williams %R
        williams = WilliamsRIndicator(high=df['High'], low=df['Low'], close=close)
        df['williams_r'] = williams.williams_r()

        # Rate of Change
        for period in [10, 20]:
            roc = ROCIndicator(close=close, window=period)
            df[f'roc_{period}'] = roc.roc()

        # TSI (True Strength Index)
        tsi = TSIIndicator(close=close)
        df['tsi'] = tsi.tsi()

        # KAMA (Kaufman Adaptive Moving Average)
        kama = KAMAIndicator(close=close)
        df['kama'] = kama.kama()

        return df

    def add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility indicators (10+ features)"""
        close = df['Close']

        # Bollinger Bands
        bb = BollingerBands(close=close)
        df['bb_upper'] = bb.bollinger_hband()
        df['bb_middle'] = bb.bollinger_mavg()
        df['bb_lower'] = bb.bollinger_lband()
        df['bb_width'] = bb.bollinger_wband()
        df['bb_percentage'] = bb.bollinger_pband()

        # ATR (Average True Range)
        atr = AverageTrueRange(high=df['High'], low=df['Low'], close=close)
        df['atr'] = atr.average_true_range()

        # Keltner Channel
        kc = KeltnerChannel(high=df['High'], low=df['Low'], close=close)
        df['kc_upper'] = kc.keltner_channel_hband()
        df['kc_lower'] = kc.keltner_channel_lband()
        df['kc_width'] = kc.keltner_channel_wband()

        # Donchian Channel
        dc = DonchianChannel(high=df['High'], low=df['Low'], close=close)
        df['dc_upper'] = dc.donchian_channel_hband()
        df['dc_lower'] = dc.donchian_channel_lband()
        df['dc_width'] = dc.donchian_channel_wband()

        return df

    def add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume indicators (10+ features)"""
        close = df['Close']
        volume = df['Volume']

        # OBV (On Balance Volume)
        obv = OnBalanceVolumeIndicator(close=close, volume=volume)
        df['obv'] = obv.on_balance_volume()

        # Chaikin Money Flow
        cmf = ChaikinMoneyFlowIndicator(high=df['High'], low=df['Low'], close=close, volume=volume)
        df['cmf'] = cmf.chaikin_money_flow()

        # Force Index
        fi = ForceIndexIndicator(close=close, volume=volume)
        df['force_index'] = fi.force_index()

        # Volume Price Trend
        vpt = VolumePriceTrendIndicator(close=close, volume=volume)
        df['vpt'] = vpt.volume_price_trend()

        # Volume ratios
        df['volume_sma_20'] = volume.rolling(window=20).mean()
        df['volume_ratio'] = volume / df['volume_sma_20']

        # Volume momentum
        df['volume_change'] = volume.pct_change()

        return df

    def add_higher_timeframe_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Weekly/monthly trend alignment — high-value edge features"""
        close = df['Close']

        # Multi-period returns (proxy for weekly/monthly trend)
        for days in [5, 10, 21, 63]:
            df[f'return_{days}d'] = close.pct_change(days)

        # 52-week high/low proximity
        roll_max = close.rolling(252).max()
        roll_min = close.rolling(252).min()
        df['pct_from_52w_high'] = (close - roll_max) / roll_max
        safe_min = roll_min.replace(0, np.nan)
        df['pct_from_52w_low']  = (close - safe_min) / safe_min

        # Trend alignment: daily and monthly pointing same direction
        df['trend_aligned_up']   = ((df['return_5d'] > 0) & (df['return_21d'] > 0)).astype(int)
        df['trend_aligned_down'] = ((df['return_5d'] < 0) & (df['return_21d'] < 0)).astype(int)

        # Gap features (overnight gap — often signals institutional activity)
        df['gap_up']   = ((df['Open'] > df['Close'].shift(1)) & (df['Open'] > df['Open'].shift(1))).astype(int)
        df['gap_down']  = ((df['Open'] < df['Close'].shift(1)) & (df['Open'] < df['Open'].shift(1))).astype(int)
        df['gap_size']  = (df['Open'] - df['Close'].shift(1)) / df['Close'].shift(1)

        return df

    def add_candle_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Candle pattern features — each one a proven edge in price action.
        Encoded as signed integers: +1 bullish, -1 bearish, 0 none.
        """
        o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
        body = (c - o).abs()
        candle_range = h - l
        # Avoid div-by-zero
        candle_range_safe = candle_range.replace(0, np.nan)

        # Hammer / Shooting Star — long wick, small body at top/bottom
        lower_wick = np.minimum(o, c) - l
        upper_wick = h - np.maximum(o, c)
        is_hammer       = (lower_wick > body * 2) & (upper_wick < body * 0.5) & (body / candle_range_safe > 0.15)
        is_shooting_star = (upper_wick > body * 2) & (lower_wick < body * 0.5) & (body / candle_range_safe > 0.15)
        df['candle_hammer']       = is_hammer.astype(int)
        df['candle_shooting_star'] = (-is_shooting_star.astype(int))

        # Doji — body is tiny relative to range (indecision)
        is_doji = body / candle_range_safe < 0.1
        df['candle_doji'] = is_doji.astype(int)

        # Bullish / Bearish Engulfing
        prev_body = (df['Close'].shift(1) - df['Open'].shift(1))
        curr_body = c - o
        bullish_engulf = (prev_body < 0) & (curr_body > 0) & (c > df['Open'].shift(1)) & (o < df['Close'].shift(1))
        bearish_engulf = (prev_body > 0) & (curr_body < 0) & (o > df['Close'].shift(1)) & (c < df['Open'].shift(1))
        df['candle_engulfing'] = bullish_engulf.astype(int) - bearish_engulf.astype(int)

        # Inside bar (consolidation before breakout)
        df['candle_inside_bar'] = ((h < df['High'].shift(1)) & (l > df['Low'].shift(1))).astype(int)

        # Pin bar — rejection candle with tail >= 2/3 of total range
        pin_tail = np.maximum(lower_wick, upper_wick)
        df['candle_pin_bar'] = (pin_tail / candle_range_safe > 0.66).astype(int) * np.where(lower_wick > upper_wick, 1, -1)

        return df.fillna(0)

    def add_target(self, df: pd.DataFrame, forward_days: int = 5,
                   top_pct: float = 0.20, bottom_pct: float = 0.20) -> pd.DataFrame:
        """
        Rolling-percentile target: guaranteed ~20% BUY / 20% SELL / 60% HOLD regardless
        of the stock's volatility regime.  The threshold adapts to whatever the
        last 252 days' distribution of returns looked like, so early AAPL data
        (tiny nominal prices, high % swings) and recent data are treated the same way.

        Target = 1  (BUY)  if future_return is in top    top_pct  of the past year
        Target = -1 (SELL) if future_return is in bottom bottom_pct of the past year
        Target = 0  (HOLD) otherwise
        """
        df['future_return'] = df['Close'].pct_change(forward_days).shift(-forward_days)

        roll = df['future_return'].rolling(252, min_periods=50)
        upper_thresh = roll.quantile(1 - top_pct)
        lower_thresh = roll.quantile(bottom_pct)

        df['target'] = 0
        df.loc[df['future_return'] > upper_thresh, 'target'] =  1
        df.loc[df['future_return'] < lower_thresh, 'target'] = -1

        return df

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all feature engineering"""
        print("Engineering features...")

        # Add all indicators
        df = self.add_price_features(df)
        df = self.add_trend_indicators(df)
        df = self.add_momentum_indicators(df)
        df = self.add_volatility_indicators(df)
        df = self.add_volume_indicators(df)
        df = self.add_higher_timeframe_features(df)
        df = self.add_candle_patterns(df)

        # Add target
        df = self.add_target(df)

        # Replace inf/-inf (can arise from division in ratio features) then drop NaN
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        initial_size = len(df)
        df = df.dropna()
        final_size = len(df)

        print(f"  Generated {len(df.columns)} features")
        print(f"  Rows after dropna: {final_size} (dropped {initial_size - final_size})")

        # Store feature names (exclude OHLCV and target)
        exclude_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits', 'target', 'future_return']
        self.feature_names = [col for col in df.columns if col not in exclude_cols]

        print(f"  Feature count for ML: {len(self.feature_names)}")

        return df


if __name__ == "__main__":
    # Test feature engineering
    from data_collector import HistoricalDataCollector

    collector = HistoricalDataCollector()
    df = collector.load_data("AAPL")

    if df is not None:
        print(f"\nOriginal data shape: {df.shape}")
        print(f"Date range: {df.index[0]} to {df.index[-1]}\n")

        engineer = FeatureEngineer()
        df_features = engineer.engineer_features(df.copy())

        print(f"\nFeature-engineered data shape: {df_features.shape}")
        print(f"\nFeature names ({len(engineer.feature_names)} total):")
        print(engineer.feature_names)

        print(f"\nTarget distribution:")
        print(df_features['target'].value_counts())
        print(f"\nBUY signals: {(df_features['target'] == 1).sum()}")
        print(f"SELL signals: {(df_features['target'] == -1).sum()}")
        print(f"HOLD signals: {(df_features['target'] == 0).sum()}")
    else:
        print("No data found. Run data_collector.py first.")
