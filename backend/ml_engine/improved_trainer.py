"""
Improved ML Model for 80%+ Win Rate
Strategy: Conservative predictions with high confidence only
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os

from ml_engine.data_collector import HistoricalDataCollector
from ml_engine.feature_engine import FeatureEngineer


class ImprovedTrainer:
    """
    Key improvements for 80%+ win rate:
    1. Lower profit threshold (1% instead of 2%)
    2. Shorter prediction window (3 days instead of 5)
    3. Only trade when model is >70% confident
    4. Ensemble of multiple models
    5. Add volatility filter - only trade in stable markets
    """

    def __init__(self):
        self.models = []
        self.feature_names = None

    def prepare_conservative_data(self, symbol: str):
        """Prepare data with conservative targets"""
        print(f"\nPreparing conservative data for {symbol}...")

        collector = HistoricalDataCollector()
        df = collector.load_data(symbol)

        if df is None or df.empty:
            return None, None, None

        # Add features
        engineer = FeatureEngineer()
        df = engineer.add_price_features(df)
        df = engineer.add_trend_indicators(df)
        df = engineer.add_momentum_indicators(df)
        df = engineer.add_volatility_indicators(df)
        df = engineer.add_volume_indicators(df)

        # Conservative target: 1% profit in 3 days
        df['future_return_3d'] = df['Close'].pct_change(3).shift(-3)

        # Only trade when:
        # 1. Clear signal (>1% move)
        # 2. Low volatility (ATR < average)
        atr_mean = df['atr'].mean()

        df['target'] = 0  # HOLD by default

        # BUY: 1%+ gain in 3 days, low volatility
        buy_condition = (df['future_return_3d'] > 0.01) & (df['atr'] < atr_mean * 1.2)
        df.loc[buy_condition, 'target'] = 1

        # SELL: 1%+ loss in 3 days, low volatility
        sell_condition = (df['future_return_3d'] < -0.01) & (df['atr'] < atr_mean * 1.2)
        df.loc[sell_condition, 'target'] = -1

        df = df.dropna()

        self.feature_names = engineer.feature_names
        X = df[self.feature_names]
        y = df['target']

        print(f"  Data: {X.shape[0]} rows")
        print(f"  BUY: {sum(y==1)}, SELL: {sum(y==-1)}, HOLD: {sum(y==0)}")

        return X, y, df

    def train_ensemble(self, X, y):
        """Train ensemble of models for better accuracy"""
        print("\nTraining ensemble models...")

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # Encode targets
        y_train_enc = y_train.map({-1: 0, 0: 1, 1: 2})
        y_test_enc = y_test.map({-1: 0, 0: 1, 1: 2})

        # Train 3 models with different hyperparameters
        model_configs = [
            {'max_depth': 6, 'learning_rate': 0.03, 'n_estimators': 400},  # Conservative
            {'max_depth': 8, 'learning_rate': 0.05, 'n_estimators': 300},  # Balanced
            {'max_depth': 10, 'learning_rate': 0.07, 'n_estimators': 200}  # Aggressive
        ]

        self.models = []
        predictions = []

        for i, config in enumerate(model_configs):
            print(f"  Training model {i+1}/3...")

            model = xgb.XGBClassifier(
                objective='multi:softprob',  # Get probabilities
                num_class=3,
                **config,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42 + i
            )

            model.fit(X_train, y_train_enc, verbose=False)
            self.models.append(model)

            # Get predictions
            pred_proba = model.predict_proba(X_test)
            predictions.append(pred_proba)

        # Ensemble prediction: average probabilities
        ensemble_proba = np.mean(predictions, axis=0)
        ensemble_pred_enc = np.argmax(ensemble_proba, axis=1)

        # Only predict BUY/SELL if confidence > 70%
        max_proba = np.max(ensemble_proba, axis=1)
        conservative_pred_enc = ensemble_pred_enc.copy()
        conservative_pred_enc[max_proba < 0.7] = 1  # Low confidence -> HOLD

        # Decode
        ensemble_pred = pd.Series(conservative_pred_enc).map({0: -1, 1: 0, 2: 1})

        accuracy = accuracy_score(y_test, ensemble_pred)
        print(f"\n  Ensemble Accuracy: {accuracy:.2%}")

        return X_test, y_test, ensemble_pred, ensemble_proba

    def backtest_conservative(self, X_test, y_test, y_pred, df):
        """Backtest with conservative strategy"""
        print("\n" + "="*60)
        print("CONSERVATIVE BACKTEST RESULTS")
        print("="*60)

        test_df = df.iloc[-len(X_test):].copy()
        test_df['predicted'] = y_pred.values
        test_df['actual'] = y_test.values

        # Only execute BUY/SELL trades
        trades = test_df[test_df['predicted'].isin([-1, 1])].copy()

        if len(trades) == 0:
            print("No trades (model too conservative)")
            return 0

        profitable = sum(trades['predicted'] == trades['actual'])
        total = len(trades)
        win_rate = (profitable / total) * 100

        # Calculate returns
        returns = []
        for idx, row in trades.iterrows():
            if row['predicted'] == row['actual']:
                returns.append(abs(row['future_return_3d']))
            else:
                returns.append(-abs(row['future_return_3d']))

        cumulative_return = sum(returns) * 100

        print(f"\nWin Rate: {win_rate:.2f}%")
        print(f"Total Trades: {total}")
        print(f"  Profitable: {profitable}")
        print(f"  Losing: {total - profitable}")
        print(f"  Cumulative Return: {cumulative_return:.2f}%")

        buy_trades = trades[trades['predicted'] == 1]
        sell_trades = trades[trades['predicted'] == -1]

        if len(buy_trades) > 0:
            buy_wins = sum(buy_trades['predicted'] == buy_trades['actual'])
            print(f"\nBUY: {len(buy_trades)} trades, {buy_wins/len(buy_trades)*100:.1f}% win rate")

        if len(sell_trades) > 0:
            sell_wins = sum(sell_trades['predicted'] == sell_trades['actual'])
            print(f"SELL: {len(sell_trades)} trades, {sell_wins/len(sell_trades)*100:.1f}% win rate")

        if win_rate >= 80:
            print(f"\n[SUCCESS] {win_rate:.2f}% >= 80% target!")
        else:
            print(f"\n[BELOW TARGET] {win_rate:.2f}% < 80%")

        print("="*60)

        return win_rate

    def save_ensemble(self, symbol, win_rate):
        """Save ensemble models"""
        model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        os.makedirs(model_dir, exist_ok=True)

        filename = f"{symbol}_ensemble_{win_rate:.1f}pct.joblib"
        filepath = os.path.join(model_dir, filename)

        data = {
            'models': self.models,
            'feature_names': self.feature_names,
            'symbol': symbol,
            'win_rate': win_rate
        }

        joblib.dump(data, filepath)
        print(f"\nSaved ensemble to: {filepath}")


def train_conservative_models():
    """Train conservative models for all symbols"""
    symbols = ["AAPL", "TSLA", "GOOGL", "MSFT", "NVDA"]

    print("\n" + "="*60)
    print("TRAINING CONSERVATIVE MODELS FOR 80%+ WIN RATE")
    print("="*60)

    results = []

    for symbol in symbols:
        try:
            trainer = ImprovedTrainer()

            X, y, df = trainer.prepare_conservative_data(symbol)
            if X is None:
                continue

            X_test, y_test, y_pred, proba = trainer.train_ensemble(X, y)
            win_rate = trainer.backtest_conservative(X_test, y_test, y_pred, df)

            if win_rate >= 70:
                trainer.save_ensemble(symbol, win_rate)

            results.append({'symbol': symbol, 'win_rate': win_rate})

        except Exception as e:
            print(f"\nError with {symbol}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)

    for r in results:
        status = "[OK]" if r['win_rate'] >= 80 else "[LOW]"
        print(f"{status} {r['symbol']:6} - Win Rate: {r['win_rate']:.2f}%")

    if results:
        avg = np.mean([r['win_rate'] for r in results])
        print(f"\nAverage Win Rate: {avg:.2f}%")

        if avg >= 80:
            print("[SUCCESS] System ready for deployment!")
        else:
            print("[INFO] Models saved. Consider further tuning for 80%+ target.")


if __name__ == "__main__":
    train_conservative_models()
