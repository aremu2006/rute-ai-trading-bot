"""MT5 Correlation Guard — prevents overexposure in correlated assets."""
import time
import logging

from .config import CORRELATION_GROUPS, CORRELATION_MAX_SAME_DIR, CORRELATION_SIGNAL_TTL

log = logging.getLogger("mt5_engine.guards")

_active_signals: dict = {}


def get_correlation_group(symbol: str):
    """Return the correlation group for a symbol, or None."""
    for group in CORRELATION_GROUPS:
        if symbol in group:
            return group
    return None


def check_correlation_block(symbol: str, direction: str) -> bool:
    """Returns True if this trade should be BLOCKED due to correlation."""
    group = get_correlation_group(symbol)
    if group is None:
        return False

    now = time.time()
    same_dir_count = 0
    for sym in group:
        if sym == symbol:
            continue
        sig = _active_signals.get(sym)
        if sig and (now - sig["timestamp"]) < CORRELATION_SIGNAL_TTL:
            if sig["direction"] == direction:
                same_dir_count += 1

    return same_dir_count >= CORRELATION_MAX_SAME_DIR


def register_signal(symbol: str, direction: str):
    """Register an approved signal for correlation tracking."""
    _active_signals[symbol] = {"direction": direction, "timestamp": time.time()}


def cleanup_expired_signals():
    """Remove signals older than TTL."""
    now = time.time()
    expired = [s for s, v in _active_signals.items() if (now - v["timestamp"]) >= CORRELATION_SIGNAL_TTL]
    for s in expired:
        del _active_signals[s]
