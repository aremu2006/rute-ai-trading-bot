"""
ML Model Training System with XGBoost
Trains model and validates with backtesting to achieve 80%+ win rate
"""

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.feature_selection import RFE
from sklearn.utils.class_weight import compute_sample_weight
import joblib
import optuna
import os
from datetime import datetime

from ml_engine.data_collector import HistoricalDataCollector
from ml_engine.feature_engine import FeatureEngineer


class ModelTrainer:
    def __init__(self, model_dir=None):
        self.model_dir = model_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        os.makedirs(self.model_dir, exist_ok=True)
        self.model = None
        self.feature_names = None
        self.scaler = None

    def prepare_data(self, symbol: str):
        """Load and prepare data for training"""
        print(f"\nPreparing data for {symbol}...")

        collector = HistoricalDataCollector()
        df = collector.load_data(symbol)

        if df is None or df.empty:
            print(f"  No data found for {symbol}")
            return None, None, None, None

        engineer = FeatureEngineer()
        df = engineer.engineer_features(df)

        # Split features and target
        X = df[engineer.feature_names]
        y = df['target']

        self.feature_names = engineer.feature_names

        print(f"  Data shape: {X.shape}")
        print(f"  Target distribution: BUY={sum(y==1)}, SELL={sum(y==-1)}, HOLD={sum(y==0)}")

        return X, y, df

    def _xgb_params(self) -> dict:
        """Base XGBoost params optimised for precision on BUY/SELL signals."""
        return {
            'objective': 'multi:softprob',
            'num_class': 3,
            'max_depth': 5,
            'learning_rate': 0.05,
            'n_estimators': 300,
            'subsample': 0.8,
            'colsample_bytree': 0.7,
            'min_child_weight': 10,  # Higher → fewer, higher-confidence leaves
            'gamma': 0.5,            # Require meaningful split gain
            'reg_alpha': 0.5,
            'reg_lambda': 2.0,
            'random_state': 42,
            'tree_method': 'hist',
            'eval_metric': 'mlogloss',
        }

    def train_model(self, X, y):
        """Train XGBoost model with walk-forward cross-validation."""
        print("\nTraining XGBoost model...")

        # ── Walk-forward validation (5 folds) ──────────────────────────────
        print("\n  Walk-forward validation (5 folds):")
        tscv = TimeSeriesSplit(n_splits=5)
        fold_win_rates = []

        for fold, (train_idx, test_idx) in enumerate(tscv.split(X), 1):
            Xf_train, Xf_test = X.iloc[train_idx], X.iloc[test_idx]
            yf_train, yf_test = y.iloc[train_idx], y.iloc[test_idx]

            yf_train_enc = yf_train.map({-1: 0, 0: 1, 1: 2})
            yf_test_enc  = yf_test.map({-1: 0, 0: 1, 1: 2})

            # Auto-balanced weights so all three classes contribute equally.
            sample_weights = compute_sample_weight('balanced', yf_train_enc)

            m = xgb.XGBClassifier(**self._xgb_params())
            m.fit(Xf_train, yf_train_enc, sample_weight=sample_weights, verbose=False)

            preds_enc = m.predict(Xf_test)
            preds = pd.Series(preds_enc, index=yf_test.index).map({0: -1, 1: 0, 2: 1})

            # Win rate = precision on BUY+SELL signals only
            active = preds[preds != 0]
            if len(active) > 0:
                wins = (active == yf_test.loc[active.index]).sum()
                wr = wins / len(active) * 100
                fold_win_rates.append(wr)
                print(f"    Fold {fold}: {len(active):3d} signals, {wr:.1f}% precision")
            else:
                print(f"    Fold {fold}: no signals (market too choppy in this window)")

        if fold_win_rates:
            print(f"\n  Walk-forward win rate: {np.mean(fold_win_rates):.1f}% "
                  f"(±{np.std(fold_win_rates):.1f}%)")
        self.fold_win_rates = fold_win_rates
        # ───────────────────────────────────────────────────────────────────

        # ── Honest holdout evaluation ─────────────────────────────────────
        # The holdout report must come from a model that never saw those
        # rows. We fit on the first 80% ONLY for the evaluation; the
        # production model below is trained on 100% and is never scored.
        y_all_enc = y.map({-1: 0, 0: 1, 1: 2})
        sample_weights = compute_sample_weight('balanced', y_all_enc)

        split_idx = int(len(X) * 0.8)
        X_test = y_test = y_pred = None
        if 50 <= split_idx < len(X):
            X_test = X.iloc[split_idx:]
            y_test = y.iloc[split_idx:]
            y_test_enc = y_test.map({-1: 0, 0: 1, 1: 2})
            holdout_model = xgb.XGBClassifier(**self._xgb_params())
            holdout_model.fit(
                X.iloc[:split_idx], y_all_enc.iloc[:split_idx],
                sample_weight=sample_weights[:split_idx], verbose=False,
            )
            y_pred_enc = holdout_model.predict(X_test)
            y_pred = pd.Series(y_pred_enc, index=y_test.index).map({0: -1, 1: 0, 2: 1})

        if y_test is not None and len(y_test) > 0:
            print("\n  Holdout Classification Report (out-of-sample):")
            for label, name in [(-1, "SELL"), (0, "HOLD"), (1, "BUY")]:
                if (y_test == label).sum() > 0:
                    prec = precision_score(y_test == label, y_pred == label, zero_division=0)
                    rec  = recall_score(y_test == label, y_pred == label, zero_division=0)
                    f1   = f1_score(y_test == label, y_pred == label, zero_division=0)
                    print(f"    {name:6} — Precision: {prec:.2%}  Recall: {rec:.2%}  F1: {f1:.2%}")

        # ── Final production model trained on 100% of data ────────────
        print("\n  Training final production model on 100% of data...")
        self.model = xgb.XGBClassifier(**self._xgb_params())
        self.model.fit(X, y_all_enc, sample_weight=sample_weights, verbose=False)

        return self.model, X_test, y_test, y_pred

    def backtest(self, X_test, y_test, y_pred, df):
        """
        Backtest the model to calculate actual win rate

        Win rate = (profitable trades) / (total trades executed)
        """
        print("\n" + "="*60)
        print("BACKTESTING RESULTS")
        print("="*60)

        # Get test period prices
        test_df = df.iloc[-len(X_test):].copy()
        test_df['predicted'] = y_pred.values
        test_df['actual'] = y_test.values

        # Only trade on BUY/SELL signals (ignore HOLD)
        trades = test_df[test_df['predicted'].isin([-1, 1])].copy()

        if len(trades) == 0:
            print("No trades executed")
            return 0, {}

        # Calculate trade outcomes
        profitable_trades = 0
        losing_trades = 0
        total_profit = 0

        for idx, row in trades.iterrows():
            predicted_direction = row['predicted']  # 1=BUY, -1=SELL
            actual_direction = row['actual']  # 1=price went up, -1=price went down

            # Trade is profitable if prediction matches reality
            if predicted_direction == actual_direction:
                profitable_trades += 1
                total_profit += abs(row['future_return'])  # Simplified profit calculation
            else:
                losing_trades += 1
                total_profit -= abs(row['future_return'])

        total_trades = len(trades)
        win_rate = (profitable_trades / total_trades) * 100 if total_trades > 0 else 0

        # Statistics
        buy_trades = trades[trades['predicted'] == 1]
        sell_trades = trades[trades['predicted'] == -1]

        buy_wins = sum((buy_trades['predicted'] == buy_trades['actual']).values)
        sell_wins = sum((sell_trades['predicted'] == sell_trades['actual']).values)

        buy_win_rate = (buy_wins / len(buy_trades) * 100) if len(buy_trades) > 0 else 0
        sell_win_rate = (sell_wins / len(sell_trades) * 100) if len(sell_trades) > 0 else 0

        results = {
            'win_rate': win_rate,
            'total_trades': total_trades,
            'profitable_trades': profitable_trades,
            'losing_trades': losing_trades,
            'total_profit_pct': total_profit * 100,
            'buy_trades': len(buy_trades),
            'buy_win_rate': buy_win_rate,
            'sell_trades': len(sell_trades),
            'sell_win_rate': sell_win_rate
        }

        print(f"\nOverall Win Rate: {win_rate:.2f}%")
        print(f"Total Trades: {total_trades}")
        print(f"  Profitable: {profitable_trades}")
        print(f"  Losing: {losing_trades}")
        print(f"  Cumulative Return: {total_profit*100:.2f}%")
        print(f"\nBUY Trades: {len(buy_trades)} (Win Rate: {buy_win_rate:.2f}%)")
        print(f"SELL Trades: {len(sell_trades)} (Win Rate: {sell_win_rate:.2f}%)")

        if win_rate >= 80:
            print(f"\n[SUCCESS] TARGET ACHIEVED: {win_rate:.2f}% win rate >= 80%")
        else:
            print(f"\n[BELOW TARGET] {win_rate:.2f}% win rate < 80%")
            print("  Model needs improvement or more data")

        print("="*60)

        return win_rate, results

    def save_model(self, symbol: str, win_rate: float):
        """Save trained model"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol}_{win_rate:.1f}pct_{timestamp}.joblib"
        filepath = os.path.join(self.model_dir, filename)

        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'symbol': symbol,
            'win_rate': win_rate,
            'fold_win_rates': getattr(self, 'fold_win_rates', []),
            'trained_at': timestamp
        }

        joblib.dump(model_data, filepath)
        print(f"\nModel saved to: {filepath}")
        return filepath

    def prune_features(self, X, y, target_n: int = 20):
        """Use Recursive Feature Elimination to drop noisy features"""
        print(f"\nPruning features from {X.shape[1]} down to {target_n}...")
        
        # Use a simpler XGBoost for RFE speed
        estimator = xgb.XGBClassifier(n_estimators=100, max_depth=5, random_state=42)
        
        # Convert target: -1 -> 0, 0 -> 1, 1 -> 2
        y_encoded = y.map({-1: 0, 0: 1, 1: 2})
        
        selector = RFE(estimator, n_features_to_select=target_n, step=5)
        selector = selector.fit(X, y_encoded)
        
        selected_mask = selector.support_
        self.feature_names = [name for i, name in enumerate(self.feature_names) if selected_mask[i]]
        
        print(f"  Selected Top {target_n} Features: {self.feature_names}")
        return X[self.feature_names]

    def optimize_hyperparameters(self, X, y, n_trials=50):
        """Use Optuna for Bayesian hyperparameter tuning"""
        print(f"\nOptimizing hyperparameters with Optuna ({n_trials} trials)...")
        
        # Split data
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        y_train_encoded = y_train.map({-1: 0, 0: 1, 1: 2})
        y_test_encoded = y_test.map({-1: 0, 0: 1, 1: 2})

        def objective(trial):
            params = {
                'objective': 'multi:softmax',
                'num_class': 3,
                'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
                'max_depth': trial.suggest_int('max_depth', 3, 15),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                'subsample': trial.suggest_float('subsample', 0.5, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
                'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
                'gamma': trial.suggest_float('gamma', 1e-8, 1.0, log=True),
                'tree_method': 'hist',
                'random_state': 42
            }
            
            model = xgb.XGBClassifier(**params)
            model.fit(X_train, y_train_encoded)
            
            y_pred = model.predict(X_test)
            return accuracy_score(y_test_encoded, y_pred)

        study = optuna.create_study(direction='maximize')
        study.optimize(objective, n_trials=n_trials)
        
        print("\n  Optimization complete.")
        print(f"  Best accuracy: {study.best_value:.2%}")
        print(f"  Best params: {study.best_params}")
        
        return study.best_params

    def load_model(self, filepath: str):
        """Load trained model"""
        model_data = joblib.load(filepath)
        self.model = model_data['model']
        self.feature_names = model_data['feature_names']
        print(f"Loaded model: {model_data['symbol']} (Win Rate: {model_data['win_rate']:.2f}%)")
        return model_data


def train_all_symbols():
    """Train models for all symbols and report results"""
    symbols = ["AAPL", "TSLA", "GOOGL", "MSFT", "AMZN", "NVDA"]

    print("\n" + "="*60)
    print("TRAINING ML MODELS FOR ALL SYMBOLS")
    print("="*60)

    all_results = []

    for symbol in symbols:
        try:
            trainer = ModelTrainer()

            # Prepare data
            X, y, df = trainer.prepare_data(symbol)
            if X is None:
                continue

            # Train model
            model, X_test, y_test, y_pred = trainer.train_model(X, y)

            # Backtest
            win_rate, results = trainer.backtest(X_test, y_test, y_pred, df)

            # Save if good
            if win_rate >= 50:  # Save models with >50% win rate
                trainer.save_model(symbol, win_rate)

            all_results.append({
                'symbol': symbol,
                'win_rate': win_rate,
                **results
            })

        except Exception as e:
            print(f"\nError training {symbol}: {e}")
            continue

    # Summary
    print("\n" + "="*60)
    print("TRAINING SUMMARY")
    print("="*60)
    for result in all_results:
        status = "[OK]" if result['win_rate'] >= 80 else "[LOW]"
        trades = result.get('total_trades', 0)
        print(f"{status} {result['symbol']:6} - Win Rate: {result['win_rate']:.2f}% ({trades} trades)")

    avg_win_rate = np.mean([r['win_rate'] for r in all_results]) if all_results else 0
    print(f"\nAverage Win Rate: {avg_win_rate:.2f}%")

    if avg_win_rate >= 80:
        print("[SYSTEM READY] Average win rate meets 80% target!")
    else:
        print("[NEEDS IMPROVEMENT] Consider collecting more data or tuning hyperparameters")

    return all_results


if __name__ == "__main__":
    # Train all symbols
    results = train_all_symbols()
