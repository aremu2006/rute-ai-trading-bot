# backend/ml_engine/transformer_core.py
# BUG #2 FIX: Added train() method and weight persistence

import os
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple

class LSTMForecaster(nn.Module):
    """
    LSTM-based core for capturing temporal market context.
    Now supports Multi-Asset Tensors (Inter-market CNS).
    """
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2):
        super(LSTMForecaster, self).__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, 3) # Buy, Sell, Hold (Neutral)
        
    def forward(self, x):
        # x shape: (batch, seq_len, input_dim)
        out, _ = self.lstm(x)
        # Use final time point prediction
        out = self.fc(out[:, -1, :])
        return out

class TemporalEngine:
    def __init__(self, feature_dim: int):
        self.model = LSTMForecaster(input_dim=feature_dim)
        self.seq_len = 14 # Lookback window
        # BUG #2 FIX: Load saved weights if they exist
        self.weights_path = os.path.join(os.path.dirname(__file__), "models", "temporal_lstm.pt")
        self.weights_loaded = False
        if os.path.exists(self.weights_path):
            try:
                self.model.load_state_dict(torch.load(self.weights_path, weights_only=True))
                self.weights_loaded = True
                print(f"[TemporalEngine] Loaded saved weights from {self.weights_path}")
            except Exception as e:
                print(f"[TemporalEngine] Could not load weights: {e}")
        
    def prepare_sequence(self, main_features: np.ndarray, correlation_features: List[np.ndarray] = None) -> torch.Tensor:
        """
        Converts 2D features into 3D sequence for LSTM.
        Supports stacking of correlated assets (CNS).
        """
        if correlation_features:
            # Stack along feature dimension
            # Shape: (Samples, Features * Assets)
            combined = np.hstack([main_features] + correlation_features)
        else:
            combined = main_features
            
        if len(combined) < self.seq_len:
            pad_len = self.seq_len - len(combined)
            cols = combined.shape[1]
            padding = np.zeros((pad_len, cols))
            combined = np.vstack((padding, combined))
            
        seq = combined[-self.seq_len:]
        return torch.tensor(seq).unsqueeze(0).float()

    def predict(self, sequence: torch.Tensor) -> int:
        """
        Predict market direction: -1 (Sell), 0 (Hold), 1 (Buy)
        """
        if not self.weights_loaded:
            return 0  # No trained weights — neutral, do not influence confidence
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(sequence)
            _, predicted = torch.max(outputs.data, 1)
            # Map index back: 0 -> -1, 1 -> 0, 2 -> 1
            return int(predicted.item()) - 1

    def train(self, X_sequences: np.ndarray, y_labels: np.ndarray, epochs: int = 10, lr: float = 0.001):
        """
        BUG #2 FIX: Train the LSTM on labeled sequences.
        X_sequences: shape (N, seq_len, feature_dim)
        y_labels: shape (N,) with values in {-1, 0, 1} mapped to {0, 1, 2}
        """
        # Map labels: -1 -> 0, 0 -> 1, 1 -> 2
        y_mapped = y_labels + 1  # shift to 0-indexed
        
        X_t = torch.tensor(X_sequences, dtype=torch.float32)
        y_t = torch.tensor(y_mapped, dtype=torch.long)
        
        dataset = torch.utils.data.TensorDataset(X_t, y_t)
        loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)
        
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()
        
        self.model.train()
        for epoch in range(epochs):
            total_loss = 0
            for bx, by in loader:
                optimizer.zero_grad()
                out = self.model(bx)
                loss = criterion(out, by)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            
            if (epoch + 1) % 5 == 0:
                print(f"[TemporalEngine] Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(loader):.4f}")
        
        # Save weights
        os.makedirs(os.path.dirname(self.weights_path), exist_ok=True)
        torch.save(self.model.state_dict(), self.weights_path)
        print(f"[TemporalEngine] Weights saved to {self.weights_path}")
        self.model.eval()

