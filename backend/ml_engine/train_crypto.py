import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_engine.data_collector import HistoricalDataCollector
from ml_engine.working_trainer import WorkingTrainer

def run():
    print("Starting ML Training for core pairs...")
    
    # Map frontend symbols to yfinance symbols
    symbol_map = {
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "AAPL": "AAPL",
        "TSLA": "TSLA"
    }
    
    collector = HistoricalDataCollector(data_dir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    
    for frontend_sym, yf_sym in symbol_map.items():
        print(f"\n--- Processing {frontend_sym} (Yahoo: {yf_sym}) ---")
        
        # 1. Collect data using Yahoo symbol
        df = collector.collect_symbol_data(yf_sym, period="10y")
        if df is None or df.empty:
            print(f"Failed to collect data for {yf_sym}")
            continue
            
        # 2. Save data using FRONTEND symbol so the trainer finds it
        collector.save_data(frontend_sym, df)
        
        # 3. Train using FRONTEND symbol
        trainer = WorkingTrainer(frontend_sym)
        X, y, df_trained = trainer.prepare_data()
        
        if X is not None and len(X) > 0:
            X_test, y_test, y_pred = trainer.train_model(X, y)
            win_rate, total_trades = trainer.backtest(X_test, y_test, y_pred, df_trained)
            
            # Save the model
            trainer.save_model(win_rate)
            print(f"Successfully trained and saved model for {frontend_sym} with win rate {win_rate:.1f}%")
        else:
            print(f"Failed to prepare data for {frontend_sym}")

if __name__ == "__main__":
    run()
