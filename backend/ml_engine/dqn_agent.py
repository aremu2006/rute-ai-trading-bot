# backend/ml_engine/dqn_agent.py
# FIX #10: Added Target Network, Vectorized Replay, Save/Load

import os
import torch
import torch.nn as nn
import torch.optim as optim
import random
import numpy as np
from collections import deque

class DQNAgent:
    """
    Deep Q-Learning Agent with Target Network (Fix #10).
    Learns from trading 'Rewards' (Profit) and 'Penalties' (Loss/Slippage).
    """
    def __init__(self, state_dim: int, action_dim: int = 3):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.memory = deque(maxlen=2000)
        self.gamma = 0.95    # Discount rate
        self.epsilon = 1.0   # Exploration rate
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.learning_rate = 0.001
        self.step_count = 0  # FIX #10: Track steps for target sync
        self.target_sync_interval = 100  # FIX #10: Sync every 100 steps

        self.model = self._build_model()
        # FIX #10: Target network (frozen copy for stable Q-targets)
        self.target_model = self._build_model()
        self.target_model.load_state_dict(self.model.state_dict())
        self.target_model.eval()

        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self.criterion = nn.MSELoss()

    def _build_model(self):
        # Neural Network for Deep Q-learning
        model = nn.Sequential(
            nn.Linear(self.state_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, self.action_dim)
        )
        return model

    def remember(self, state, action, reward, next_state, done=False):
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state):
        if np.random.rand() <= self.epsilon:
            return random.randrange(self.action_dim)

        state_tensor = torch.tensor(state).float().unsqueeze(0)
        act_values = self.model(state_tensor)
        return torch.argmax(act_values[0]).item()

    def replay(self, batch_size: int = 32):
        """FIX #10: Vectorized batch replay with target network."""
        if len(self.memory) < batch_size:
            return

        minibatch = random.sample(self.memory, batch_size)

        # Vectorize into tensors
        states = torch.tensor(np.array([m[0] for m in minibatch])).float()
        actions = torch.tensor([m[1] for m in minibatch]).long()
        rewards = torch.tensor([m[2] for m in minibatch]).float()
        next_states = torch.tensor(np.array([m[3] for m in minibatch])).float()
        dones = torch.tensor([float(m[4]) for m in minibatch]).float()

        # Current Q-values for chosen actions
        q_values = self.model(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        # Target Q-values from frozen target network
        with torch.no_grad():
            next_q = self.target_model(next_states).max(1)[0]
        expected_q = rewards + self.gamma * next_q * (1 - dones)

        # Update
        loss = self.criterion(q_values, expected_q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        # FIX #10: Sync target network periodically
        self.step_count += 1
        if self.step_count % self.target_sync_interval == 0:
            self.target_model.load_state_dict(self.model.state_dict())

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def save(self, path: str = "ml_engine/models/dqn_agent.pt"):
        """FIX #10: Save model weights."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save({
            'model_state': self.model.state_dict(),
            'target_state': self.target_model.state_dict(),
            'optimizer_state': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'step_count': self.step_count,
        }, path)

    def load(self, path: str = "ml_engine/models/dqn_agent.pt"):
        """FIX #10: Load model weights."""
        if os.path.exists(path):
            checkpoint = torch.load(path, weights_only=True)
            self.model.load_state_dict(checkpoint['model_state'])
            self.target_model.load_state_dict(checkpoint['target_state'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state'])
            self.epsilon = checkpoint.get('epsilon', self.epsilon)
            self.step_count = checkpoint.get('step_count', 0)
