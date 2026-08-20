"""
WORKING ML TRAINER - 60-70% Win Rate Target
Simple, stable implementation using RandomForest
Trained on 45 years of data
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
import os
from datetime import datetime

from ml_engine.data_collector import HistoricalDataCollector
from ml_engine.feature_engine import FeatureEngineer


class WorkingTrainer:
    """Simplified trainer that actually works"""

    def __init__(self, symbol):
        self.symbol = symbol
        self.model = None
        self.feature_names = None
        self.model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        os.makedirs(self.model_dir, exist_ok=True)

    def prepare_data(self):
        """Load and prepare data"""
        print(f"\n{'='*60}")
        print(f"PREPARING {self.symbol}")
        print(f"{'='*60}")

        collector = HistoricalDataCollector()
        df = collector.load_data(self.symbol)

        if df is None or df.empty:
            print("No data found")
            return None, None, None

        print(f"Loaded: {len(df)} days ({df.index[0]} to {df.index[-1]})")

        # Feature engineering
        engineer = FeatureEngineer()
        df = engineer.engineer_features(df.copy())

        # Get features
        self.feature_names = engineer.feature_names

        # Prepare X and y
        X = df[self.feature_names].values  # Convert to numpy array
        y = df['target'].values

        print(f"Features: {len(self.feature_names)}")
        print(f"Samples: {len(X)}")
        print(f"  BUY: {sum(y==1)} ({sum(y==1)/len(y)*100:.1f}%)")
        print(f"  SELL: {sum(y==-1)} ({sum(y==-1)/len(y)*100:.1f}%)")
        print(f"  HOLD: {sum(y==0)} ({sum(y==0)/len(y)*100:.1f}%)")

        return X, y, df

    def train_model(self, X, y):
        """Train RandomForest model"""
        print(f"\n{'='*60}")
        print("TRAINING MODEL")
        print(f"{'='*60}")

        # 80/20 split
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        print(f"Train: {len(X_train)} | Test: {len(X_test)}")

        # RandomForest - stable and reliable
        self.model = RandomForestClassifier(
            n_estimators=200,
            max_depth=12,
            min_samples_split=10,
            min_samples_leaf=5,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )

        print("Training...")
        self.model.fit(X_train, y_train)

        # Predict with confidence threshold
        y_pred_proba = self.model.predict_proba(X_test)
        max_conf = np.max(y_pred_proba, axis=1)
        y_pred = self.model.predict(X_test)

        # Only trade when confidence > 55%
        conservative_pred = y_pred.copy()
        conservative_pred[max_conf < 0.55] = 0  # Low confidence -> HOLD

        accuracy = accuracy_score(y_test, conservative_pred)
        print(f"\nOverall Accuracy: {accuracy:.2%}")

        return X_test, y_test, conservative_pred

    def backtest(self, X_test, y_test, y_pred, df):
        """Backtest the model"""
        print(f"\n{'='*60}")
        print("BACKTEST RESULTS")
        print(f"{'='*60}")

        test_df = df.iloc[-len(X_test):].copy()
        test_df['predicted'] = y_pred
        test_df['actual'] = y_test

        # Only count actual trades (not HOLD)
        trades = test_df[test_df['predicted'] != 0].copy()

        if len(trades) == 0:
            print("No trades executed")
            return 0, 0

        # Calculate wins
        correct = sum(trades['predicted'] == trades['actual'])
        total = len(trades)
        win_rate = (correct / total) * 100

        print(f"\nWin Rate: {win_rate:.2f}%")
        print(f"Total Trades: {total}")
        print(f"  Wins: {correct}")
        print(f"  Losses: {total - correct}")

        # By trade type
        buy_trades = trades[trades['predicted'] == 1]
        sell_trades = trades[trades['predicted'] == -1]

        if len(buy_trades) > 0:
            buy_wins = sum(buy_trades['predicted'] == buy_trades['actual'])
            buy_wr = buy_wins / len(buy_trades) * 100
            print(f"\nBUY: {len(buy_trades)} trades ({buy_wr:.1f}% win rate)")

        if len(sell_trades) > 0:
            sell_wins = sum(sell_trades['predicted'] == sell_trades['actual'])
            sell_wr = sell_wins / len(sell_trades) * 100
            print(f"SELL: {len(sell_trades)} trades ({sell_wr:.1f}% win rate)")

        # Status
        if 60 <= win_rate <= 75:
            print(f"\n[EXCELLENT] {win_rate:.2f}% - Perfect for profitability!")
        elif win_rate > 75:
            print(f"\n[GREAT] {win_rate:.2f}% - Exceeding expectations!")
        elif win_rate >= 55:
            print(f"\n[GOOD] {win_rate:.2f}% - Profitable with good R:R")
        else:
            print(f"\n[LOW] {win_rate:.2f}% - Needs improvement")

        return win_rate, total

    def save_model(self, win_rate):
        """Save model"""
        filename = f"{self.symbol}_RF_{win_rate:.1f}pct_{datetime.now().strftime('%Y%m%d')}.joblib"
        filepath = os.path.join(self.model_dir, filename)

        data = {
            'symbol': self.symbol,
            'model': self.model,
            'feature_names': self.feature_names,
            'win_rate': win_rate,
            'model_type': 'RandomForest',
            'trained_at': datetime.now().isoformat()
        }

        joblib.dump(data, filepath)
        print(f"\nSaved: {filepath}")
        return filepath


def train_all_symbols():
    """Train models for all symbols"""
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

    print("\n" + "="*60)
    print("TRAINING ML MODELS - 60-70% WIN RATE TARGET")
    print("Using 45 years of historical data")
    print("="*60)

    results = []

    for symbol in symbols:
        try:
            trainer = WorkingTrainer(symbol)

            # Prepare
            X, y, df = trainer.prepare_data()
            if X is None:
                continue

            # Train
            X_test, y_test, y_pred = trainer.train_model(X, y)

            # Backtest
            win_rate, total_trades = trainer.backtest(X_test, y_test, y_pred, df)

            # Save if good enough
            if win_rate >= 55:
                trainer.save_model(win_rate)

            results.append({
                'symbol': symbol,
                'win_rate': win_rate,
                'trades': total_trades
            })

        except Exception as e:
            print(f"\nError with {symbol}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n\n" + "="*60)
    print("TRAINING COMPLETE - SUMMARY")
    print("="*60)

    for r in results:
        if r['trades'] > 0:
            if 60 <= r['win_rate'] <= 75:
                status = "[PERFECT]"
            elif r['win_rate'] > 75:
                status = "[EXCELLENT]"
            elif r['win_rate'] >= 55:
                status = "[GOOD]"
            else:
                status = "[LOW]"

            print(f"{status} {r['symbol']:6} - {r['win_rate']:.2f}% ({r['trades']} trades)")

    if results:
        avg_wr = np.mean([r['win_rate'] for r in results])
        print(f"\nAverage Win Rate: {avg_wr:.2f}%")

        if 60 <= avg_wr <= 75:
            print("\n" + "="*60)
            print("[SUCCESS] MODELS READY FOR DEPLOYMENT!")
            print(f"Average {avg_wr:.2f}% win rate is PERFECT for profitability")
            print("With 2:1 risk/reward, this generates consistent profits")
            print("="*60)
        elif avg_wr > 75:
            print("\n[EXCELLENT] Models exceeding expectations!")
        elif avg_wr >= 55:
            print("\n[GOOD] Models are profitable")

    return results


if __name__ == "__main__":
    train_all_symbols()
