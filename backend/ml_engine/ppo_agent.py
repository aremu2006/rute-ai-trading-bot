"""
PPO Reinforcement Learning Agent (Upgrade 5)
Learns to optimize lot size, trailing ATR, and scale-out percentage.
"""
import os
import logging
from typing import Dict, Optional

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Normal

log = logging.getLogger("ml_engine.ppo_agent")


class PPOBuffer:
    """Trajectory storage for PPO training."""

    def __init__(self):
        self.states = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.values = []

    def store(self, state, action, log_prob, reward, value):
        self.states.append(state)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.values.append(value)

    def __len__(self):
        return len(self.states)

    def clear(self):
        self.states.clear()
        self.actions.clear()
        self.log_probs.clear()
        self.rewards.clear()
        self.values.clear()

    def get_tensors(self):
        return (
            torch.tensor(np.array(self.states), dtype=torch.float32),
            torch.tensor(np.array(self.actions), dtype=torch.float32),
            torch.tensor(np.array(self.log_probs), dtype=torch.float32),
            torch.tensor(np.array(self.rewards), dtype=torch.float32),
            torch.tensor(np.array(self.values), dtype=torch.float32),
        )


class ActorCritic(nn.Module):
    """
    Shared backbone with actor (continuous actions) and critic (value) heads.
    Actions: [lot_multiplier, trail_atr, scale_out_pct]
    """

    def __init__(self, state_dim: int = 61, action_dim: int = 3):
        super(ActorCritic, self).__init__()

        # Shared feature extractor
        self.shared = nn.Sequential(
            nn.Linear(state_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
        )

        # Actor: outputs mean and log_std for each action
        self.actor_mean = nn.Linear(128, action_dim)
        self.actor_log_std = nn.Parameter(torch.zeros(action_dim))

        # Critic: outputs single value
        self.critic = nn.Linear(128, 1)

    def forward(self, x):
        features = self.shared(x)
        action_mean = self.actor_mean(features)
        value = self.critic(features)
        return action_mean, value

    def get_dist(self, x):
        action_mean, value = self.forward(x)
        std = self.actor_log_std.exp()
        dist = Normal(action_mean, std)
        return dist, value


class PPOAgent:
    """
    Proximal Policy Optimization agent for trade parameter optimization.

    Actions (continuous):
        - lot_multiplier: [0.5, 2.0] — scales the position size
        - trail_atr: [0.5, 3.0] — trailing stop ATR multiplier
        - scale_out_pct: [10, 50] — percentage to scale out at TP1
    """

    # Action ranges for denormalization
    ACTION_RANGES = {
        "lot_multiplier": (0.5, 2.0),
        "trail_atr": (0.5, 3.0),
        "scale_out_pct": (10.0, 50.0),
    }

    def __init__(self, state_dim: int = 61, action_dim: int = 3,
                 lr: float = 3e-4, gamma: float = 0.99,
                 eps_clip: float = 0.2, K_epochs: int = 10):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.eps_clip = eps_clip
        self.K_epochs = K_epochs
        self.min_buffer_size = 32

        self.policy = ActorCritic(state_dim, action_dim)
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=lr)
        self.buffer = PPOBuffer()
        self.trained = False  # True only when weights were actually loaded

        # Track pending actions (pre-outcome)
        self._pending_actions = {}

    def select_action(self, state: np.ndarray) -> Dict:
        """
        Select trade parameters given a market state.
        Returns denormalized action values + internal metadata.
        """
        state_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
        self.policy.eval()

        with torch.no_grad():
            dist, value = self.policy.get_dist(state_t)
            action_raw = dist.sample()
            log_prob = dist.log_prob(action_raw).sum(dim=-1)

        # Denormalize actions to trading ranges
        action_np = action_raw.squeeze(0).numpy()
        actions_scaled = {}
        action_names = list(self.ACTION_RANGES.keys())

        for i, name in enumerate(action_names):
            lo, hi = self.ACTION_RANGES[name]
            # Sigmoid-like clamping: map raw action to range
            scaled = lo + (hi - lo) * (1 / (1 + np.exp(-action_np[i])))
            actions_scaled[name] = round(float(scaled), 3)

        # Store for later reward assignment
        action_id = id(state)
        self._pending_actions[action_id] = {
            "state": state,
            "action_raw": action_np,
            "log_prob": log_prob.item(),
            "value": value.item(),
        }

        return {
            **actions_scaled,
            "_action_id": action_id,
        }

    def store_outcome(self, action_data: Dict, reward: float):
        """Record the outcome of a trade for the action that was taken."""
        action_id = action_data.get("_action_id")
        pending = self._pending_actions.pop(action_id, None)

        if pending is None:
            log.warning("[PPO] No pending action found for this outcome")
            return

        self.buffer.store(
            state=pending["state"],
            action=pending["action_raw"],
            log_prob=pending["log_prob"],
            reward=reward,
            value=pending["value"],
        )

        # Auto-train when buffer is full enough
        if len(self.buffer) >= self.min_buffer_size:
            self.train()

    def _compute_returns(self, rewards: torch.Tensor, values: torch.Tensor) -> torch.Tensor:
        """Return rewards as-is: every stored experience is an independent
        1-step episode (one trade → one outcome). Discounting across them
        chained unrelated trades' outcomes into each other's returns, which
        contaminated critic targets and advantages."""
        return rewards.clone()

    def train(self):
        """Run PPO update on collected experience."""
        if len(self.buffer) < self.min_buffer_size:
            return

        states, actions, old_log_probs, rewards, old_values = self.buffer.get_tensors()

        # Normalize rewards
        if rewards.std() > 1e-8:
            rewards = (rewards - rewards.mean()) / rewards.std()

        returns = self._compute_returns(rewards, old_values)
        advantages = returns - old_values

        # Normalize advantages
        if advantages.std() > 1e-8:
            advantages = (advantages - advantages.mean()) / advantages.std()

        self.policy.train()

        for _ in range(self.K_epochs):
            dist, values = self.policy.get_dist(states)
            new_log_probs = dist.log_prob(actions).sum(dim=-1)

            # Ratio
            ratios = torch.exp(new_log_probs - old_log_probs)

            # Clipped surrogate objective
            surr1 = ratios * advantages
            surr2 = torch.clamp(ratios, 1 - self.eps_clip, 1 + self.eps_clip) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()

            # Value loss
            critic_loss = nn.MSELoss()(values.squeeze(), returns)

            # Entropy bonus
            entropy = dist.entropy().mean()

            loss = actor_loss + 0.5 * critic_loss - 0.01 * entropy

            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=0.5)
            self.optimizer.step()

        log.info(f"[PPO] Trained on {len(self.buffer)} experiences. "
                 f"Loss={loss.item():.4f} Entropy={entropy.item():.4f}")
        self.buffer.clear()

    def save(self, path: str):
        """Save model weights to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save(self.policy.state_dict(), path)
        log.info(f"[PPO] Model saved to {path}")

    def load(self, path: str):
        """Load model weights from disk."""
        if os.path.exists(path):
            self.policy.load_state_dict(torch.load(path, weights_only=True))
            self.policy.eval()
            self.trained = True
            log.info(f"[PPO] Model loaded from {path}")
        else:
            log.warning(f"[PPO] No saved model at {path} — serving default parameters only")


# Global instance
ppo_agent = PPOAgent(state_dim=61, action_dim=3)

# Try to load saved weights
_default_path = os.path.join(os.path.dirname(__file__), "models", "ppo_agent.pt")
ppo_agent.load(_default_path)
