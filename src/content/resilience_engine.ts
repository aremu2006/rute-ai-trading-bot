// src/content/resilience_engine.ts

const SELECTOR_MAP = {
  buy_button: [
    "[data-name='buy-button']",         // Strategic data attributes
    "button[aria-label*='Buy']",        // Accessibility labels (very stable)
    ".layout__area--right button",       // Positional context
    "//button[contains(text(), 'Buy')]"  // XPath fallback for text content
  ],
  sell_button: [
    "[data-name='sell-button']",
    "button[aria-label*='Sell']",
    ".layout__area--left button",
    "//button[contains(text(), 'Sell')]"
  ],
  price_label: [
    "[data-name='current-price']",
    ".symbol-header__price",
    "//div[contains(@class, 'price')]"
  ]
};

export const findElementSafe = (key: keyof typeof SELECTOR_MAP): HTMLElement | null => {
  const candidates = SELECTOR_MAP[key];
  
  for (const selector of candidates) {
    let element: HTMLElement | null = null;
    
    try {
        if (selector.startsWith("//")) {
            // XPath evaluation
            element = document.evaluate(
                selector, 
                document, 
                null, 
                XPathResult.FIRST_ORDERED_NODE_TYPE, 
                null
            ).singleNodeValue as HTMLElement;
        } else {
            element = document.querySelector(selector);
        }
    } catch (e) {
        console.warn(`RUTE: Selector failed: ${selector}`, e);
    }
    
    if (element && element.offsetParent !== null) { // Ensure it's visible
      console.log(`RUTE: Resilience Engine found ${key} using: ${selector}`);
      return element;
    }
  }
  
  return null;
};

/**
 * Report a broken selector to the backend
 */
export const reportBreakage = (key: string) => {
    console.error(`RUTE: DOM Breakage detected for ${key}! Reporting to Brain...`);
    chrome.runtime.sendMessage({
        type: 'DOM_BREAKAGE_REPORT',
        element: key,
        url: window.location.href,
        timestamp: Date.now()
    });
};
