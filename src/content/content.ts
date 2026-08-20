import { TradeRecommendation } from '../types';
import { humanClick } from './human_click';
import { findElementSafe, reportBreakage } from './resilience_engine';

console.log('RUTE Trading Assistant content script loaded');

const currentPlatform = detectPlatform();

function detectPlatform(): 'tradingview' | 'investing' | 'yahoo' | 'custom' | 'unknown' {
  const hostname = window.location.hostname;
  if (hostname.includes('tradingview.com')) return 'tradingview';
  if (hostname.includes('investing.com')) return 'investing';
  if (hostname.includes('yahoo.com')) return 'yahoo';
  return 'unknown';
}

async function isCustomTradingPlatform(): Promise<boolean> {
  return new Promise((resolve) => {
    chrome.storage.local.get(['userSettings'], (result) => {
      if (result.userSettings?.mt5Url) {
        try {
          const configuredDomain = new URL(result.userSettings.mt5Url).hostname;
          resolve(window.location.hostname === configuredDomain);
        } catch {
          resolve(false);
        }
      } else {
        resolve(false);
      }
    });
  });
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'EXECUTE_TRADE') {
    executeTrade(message.trade)
      .then(result => sendResponse({ success: true, result }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

async function executeTrade(trade: TradeRecommendation): Promise<any> {
  showTradeExecutionOverlay(trade);

  const isCustomPlatform = await isCustomTradingPlatform();
  if (currentPlatform === 'unknown' && !isCustomPlatform) {
    return executeSimulatedTrade(trade);
  }
  
  if (isCustomPlatform) return executeGenericTrade(trade);

  switch (currentPlatform) {
    case 'tradingview': return executeTradingViewTrade(trade);
    case 'investing':   return executeInvestingTrade(trade);
    case 'yahoo':       return executeSimulatedTrade(trade);
    default:            return executeSimulatedTrade(trade);
  }
}

async function executeGenericTrade(trade: TradeRecommendation): Promise<any> {
  try {
    await wait(1000);

    const tradeButton = findElementByText([
      'New Order', 'Trade', 'Buy/Sell', 'Open Trade', 'Place Order',
      'Create Order', 'Quick Trade', 'One Click Trading', 'Market Order',
      'Buy', 'Sell', 'Open Position',
    ]);

    if (tradeButton) {
      humanClick(tradeButton);
      await wait(500);

      const symbolInput = document.querySelector('input[name*="symbol" i]') as HTMLInputElement ||
                         document.querySelector('input[placeholder*="Symbol" i]') as HTMLInputElement ||
                         document.querySelector('input[name*="instrument" i]') as HTMLInputElement ||
                         document.querySelector('input[placeholder*="Instrument" i]') as HTMLInputElement ||
                         document.querySelector('input[id*="symbol" i]') as HTMLInputElement;

      if (symbolInput) {
        symbolInput.value = trade.symbol;
        symbolInput.dispatchEvent(new Event('input', { bubbles: true }));
        symbolInput.dispatchEvent(new Event('change', { bubbles: true }));
        symbolInput.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
      }

      await wait(300);

      const volumeInput = document.querySelector('input[name*="volume" i]') as HTMLInputElement ||
                         document.querySelector('input[placeholder*="Volume" i]') as HTMLInputElement ||
                         document.querySelector('input[name*="lot" i]') as HTMLInputElement ||
                         document.querySelector('input[placeholder*="Lot" i]') as HTMLInputElement ||
                         document.querySelector('input[name*="amount" i]') as HTMLInputElement ||
                         document.querySelector('input[placeholder*="Amount" i]') as HTMLInputElement;

      if (volumeInput) {
        volumeInput.value = '0.01';
        volumeInput.dispatchEvent(new Event('input', { bubbles: true }));
        volumeInput.dispatchEvent(new Event('change', { bubbles: true }));
      }

      await wait(300);

      const discoveryKey = trade.type === 'BUY' ? 'buy_button' : 'sell_button';
      const actionButton = findElementSafe(discoveryKey);

      if (actionButton) {
        const text = actionButton.innerText.toUpperCase();
        // Direction must match — a generic "ORDER"/"PLACE" button is not proof
        // the panel is set to the trade direction.
        if (text.includes(trade.type)) {
          humanClick(actionButton);
          return { platform: 'custom', status: 'executed', orderId: crypto.randomUUID(), executionPrice: trade.entryPrice, timestamp: Date.now() };
        } else {
          console.warn(`RUTE: Element text '${text}' does not match ${trade.type}. Vetoing.`);
          reportBreakage(discoveryKey);
        }
      } else {
        reportBreakage(discoveryKey);
      }
    }

    return executeSimulatedTrade(trade);
  } catch (error) {
    console.error('Trading platform execution error:', error);
    return executeSimulatedTrade(trade);
  }
}

function findElementByText(textArray: string[]): HTMLElement | null {
  for (const text of textArray) {
    const buttons = document.querySelectorAll('button, a, [role="button"]');
    for (const button of buttons) {
      if (button.textContent?.trim().toLowerCase().includes(text.toLowerCase())) {
        return button as HTMLElement;
      }
    }
    const byTitle = document.querySelector(`[title*="${text}" i]`);
    if (byTitle) return byTitle as HTMLElement;
    const byAria = document.querySelector(`[aria-label*="${text}" i]`);
    if (byAria) return byAria as HTMLElement;
  }
  return null;
}

async function executeTradingViewTrade(trade: TradeRecommendation): Promise<any> {
  try {
    // Only ever touch the button matching the trade direction — clicking the
    // buy button first on a SELL trade can place an opposite-direction order.
    const discoveryKey = trade.type === 'BUY' ? 'buy_button' : 'sell_button';
    const tradeButton = findElementSafe(discoveryKey);
    if (tradeButton) {
      humanClick(tradeButton);
      await wait(500);

      const symbolInput = document.querySelector('input[name="symbol"], [data-name="symbol-input"]') as HTMLInputElement;
      if (symbolInput) {
        symbolInput.value = trade.symbol;
        symbolInput.dispatchEvent(new Event('input', { bubbles: true }));
      }

      await wait(300);

      const actionButton = findElementSafe(discoveryKey);
      if (actionButton) {
        humanClick(actionButton);
        return { platform: 'tradingview', status: 'executed' };
      } else {
        reportBreakage(discoveryKey);
      }
    } else {
      reportBreakage(discoveryKey);
    }
    return executeSimulatedTrade(trade);
  } catch (error) {
    console.error('TradingView execution error:', error);
    return executeSimulatedTrade(trade);
  }
}

async function executeInvestingTrade(trade: TradeRecommendation): Promise<any> {
  try {
    const discoveryKey = trade.type === 'BUY' ? 'buy_button' : 'sell_button';
    const tradeButton = findElementSafe(discoveryKey);
    if (tradeButton) {
      humanClick(tradeButton);
      return { platform: 'investing', status: 'executed' };
    } else {
      reportBreakage(discoveryKey);
    }
    return executeSimulatedTrade(trade);
  } catch (error) {
    console.error('Investing.com execution error:', error);
    return executeSimulatedTrade(trade);
  }
}

async function executeSimulatedTrade(trade: TradeRecommendation): Promise<any> {
  await wait(1000);
  return {
    platform: 'simulated',
    status: 'executed',
    orderId: crypto.randomUUID(),
    executionPrice: trade.entryPrice,
    timestamp: Date.now(),
  };
}

// Escape HTML entities to prevent XSS when injecting trade data into the DOM
function escapeHtml(str: string): string {
  return str.replace(/[&<>"']/g, (c) => (
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' } as Record<string, string>)[c]
  ));
}

function showTradeExecutionOverlay(trade: TradeRecommendation) {
  const existing = document.getElementById('rute-trade-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'rute-trade-overlay';
  overlay.style.cssText = `
    position: fixed; top: 20px; right: 20px;
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #475569; border-radius: 12px; padding: 20px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5); z-index: 999999;
    min-width: 300px; color: white;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
    animation: ruteSlideIn 0.3s ease-out;
  `;

  const isBuy = trade.type === 'BUY';
  const color = isBuy ? '#10b981' : '#ef4444';

  // Use escapeHtml on symbol since it comes from external data.
  // Numeric fields (.toFixed) are safe but we cast to string for clarity.
  const safeSymbol = escapeHtml(trade.symbol);
  const safeType = escapeHtml(trade.type);
  const entryStr = (trade.entryPrice ?? 0).toFixed(2);
  const slStr = (trade.stopLoss ?? 0).toFixed(2);
  const tpStr = (trade.takeProfit ?? 0).toFixed(2);

  overlay.innerHTML = `
    <style>
      @keyframes ruteSlideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      @keyframes ruteFadeOut { from { opacity: 1; } to { opacity: 0; } }
      @keyframes ruteSpin { to { transform: rotate(360deg); } }
    </style>
    <div style="display:flex;align-items:center;margin-bottom:15px;">
      <div style="width:40px;height:40px;background:${color}20;border-radius:8px;display:flex;align-items:center;justify-content:center;margin-right:12px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2">
          <polyline points="${isBuy ? '23 6 13.5 15.5 8.5 10.5 1 18' : '23 18 13.5 8.5 8.5 13.5 1 6'}"></polyline>
          <polyline points="${isBuy ? '17 6 23 6 23 12' : '17 18 23 18 23 12'}"></polyline>
        </svg>
      </div>
      <div>
        <h3 style="margin:0;font-size:16px;font-weight:600;">Executing Trade</h3>
        <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">RUTE AI Trading Assistant</p>
      </div>
    </div>
    <div style="background:#0f172a;border-radius:8px;padding:12px;margin-bottom:12px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
        <span style="font-size:18px;font-weight:700;">${safeSymbol}</span>
        <span style="background:${color}20;color:${color};padding:4px 12px;border-radius:6px;font-size:12px;font-weight:600;">${safeType}</span>
      </div>
      <div style="font-size:12px;color:#94a3b8;">
        <div style="display:flex;justify-content:space-between;margin-top:8px;">
          <span>Entry Price:</span><span style="color:white;font-weight:600;">$${entryStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px;">
          <span>Stop Loss:</span><span style="color:#ef4444;font-weight:600;">$${slStr}</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px;">
          <span>Take Profit:</span><span style="color:#10b981;font-weight:600;">$${tpStr}</span>
        </div>
      </div>
    </div>
    <div style="display:flex;align-items:center;justify-content:center;padding:12px;background:#0ea5e920;border-radius:8px;">
      <div style="width:16px;height:16px;border:2px solid #0ea5e9;border-top-color:transparent;border-radius:50%;animation:ruteSpin 1s linear infinite;margin-right:8px;"></div>
      <span style="color:#0ea5e9;font-size:13px;font-weight:500;">Processing trade...</span>
    </div>
  `;

  document.body.appendChild(overlay);

  setTimeout(() => {
    overlay.style.animation = 'ruteFadeOut 0.3s ease-out';
    setTimeout(() => overlay.remove(), 300);
  }, 3000);
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
