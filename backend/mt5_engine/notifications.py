"""MT5 Telegram Notification Sender"""
import urllib.request
import urllib.parse
import logging

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger("mt5_engine.notifications")


def send_telegram(message: str):
    """Send a Telegram message. Fails silently."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        encoded_msg = urllib.parse.quote_plus(message)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={encoded_msg}"
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=10)
        log.info("[Telegram] Notification sent.")
    except Exception as e:
        log.warning(f"[Telegram] Failed to send: {e}")
