import os
import torch
import torch.nn as nn
import numpy as np
from typing import List, Tuple
import math

class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 5000):
        super().__init__()
        position = torch.arange(max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
        pe = torch.zeros(1, max_len, d_model)
        pe[0, :, 0::2] = torch.sin(position * div_term)
        pe[0, :, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: [batch_size, seq_len, embedding_dim]
        x = x + self.pe[:, :x.size(1), :]
        return x

class TimeAttentionTransformer(nn.Module):
    """
    Multi-Head Self-Attention Transformer for temporal market context.
    Replaces the legacy LSTM.
    """
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_heads: int = 4, num_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.pos_encoder = PositionalEncoding(hidden_dim)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim, 
            nhead=num_heads, 
            dim_feedforward=hidden_dim * 4,
            dropout=dropout,
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, 3) # Buy, Sell, Hold (Neutral)
        )
        
    def forward(self, x):
        # x shape: (batch, seq_len, input_dim)
        x = self.input_projection(x)
        x = self.pos_encoder(x)
        
        # Pass through transformer
        out = self.transformer_encoder(x)
        
        # Global Average Pooling across the sequence
        out = out.mean(dim=1)
        
        return self.fc(out)

class TemporalEngine:
    def __init__(self, feature_dim: int):
        self.model = TimeAttentionTransformer(input_dim=feature_dim)
        self.seq_len = 14 # Lookback window
        self.weights_path = os.path.join(os.path.dirname(__file__), 'models', 'temporal_transformer.pt')
        self.weights_loaded = False
        if os.path.exists(self.weights_path):
            try:
                self.model.load_state_dict(torch.load(self.weights_path, weights_only=True))
                self.weights_loaded = True
                print(f'[TemporalEngine] Loaded saved weights from {self.weights_path}')
            except Exception as e:
                print(f'[TemporalEngine] Could not load weights: {e}')
        
    def prepare_sequence(self, main_features: np.ndarray, correlation_features: List[np.ndarray] = None) -> torch.Tensor:
        """
        Converts 2D features into 3D sequence for Transformer.
        """
        if correlation_features:
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
            return 0  # No trained weights
        self.model.eval()
        with torch.no_grad():
            outputs = self.model(sequence)
            _, predicted = torch.max(outputs.data, 1)
            # Map index back: 0 -> -1, 1 -> 0, 2 -> 1
            return int(predicted.item()) - 1

    def train(self, X_sequences: np.ndarray, y_labels: np.ndarray, epochs: int = 10, lr: float = 0.001):
        """
        Train the Transformer on labeled sequences.
        """
        y_mapped = y_labels + 1
        
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
                print(f'[TemporalEngine] Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(loader):.4f}')
        
        os.makedirs(os.path.dirname(self.weights_path), exist_ok=True)
        torch.save(self.model.state_dict(), self.weights_path)
        print(f'[TemporalEngine] Weights saved to {self.weights_path}')
        self.model.eval()
