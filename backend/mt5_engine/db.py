"""MT5 Database Initialization"""
import sqlite3
import logging

from .config import DB_FILE

log = logging.getLogger("mt5_engine.db")


def init_db():
    """Create SQLite tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trade_type TEXT,
            entry_price REAL,
            exit_price REAL,
            outcome TEXT,
            pnl REAL,
            features BLOB,
            prediction_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_predictions (
            prediction_id INTEGER PRIMARY KEY,
            features_blob BLOB,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    log.info(f"[DB] Initialized at {DB_FILE}")
