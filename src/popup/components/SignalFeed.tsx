import React, { useState, useEffect, useRef } from 'react';
import { RefreshCw, Wifi, WifiOff } from 'lucide-react';

interface ScanEvent {
  ts: string;
  type: 'scan_start' | 'signal' | 'skip' | 'error';
  status: string;
  symbol?: string;
  message: string;
  action?: 'BUY' | 'SELL';
  confidence?: number;
}

const SignalFeed: React.FC = () => {
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);
  const [apiEndpoint, setApiEndpoint] = useState('http://127.0.0.1:8001');
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (typeof chrome !== 'undefined' && chrome.storage?.local) {
      chrome.storage.local.get(['userSettings'], (res) => {
        if (res.userSettings?.apiEndpoint) {
          setApiEndpoint(res.userSettings.apiEndpoint);
        }
      });
    }
  }, []);

  const fetchLog = async () => {
    try {
      const r = await fetch(`${apiEndpoint}/api/scan-log?limit=100`);
      if (r.ok) {
        const data = await r.json();
        setEvents(data.events || []);
      }
    } catch {
      // Backend not reachable yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLog();
    if (live) {
      intervalRef.current = window.setInterval(fetchLog, 4000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, apiEndpoint]);

  const toggleLive = () => setLive(prev => !prev);

  // Format time to look like MT5: YYYY.MM.DD HH:MM:SS.mmm
  const fmtTime = (ts: string) => {
    if (!ts || isNaN(new Date(ts).getTime())) return ts || '';
    try {
      const d = new Date(ts);
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const HH = String(d.getHours()).padStart(2, '0');
      const MM = String(d.getMinutes()).padStart(2, '0');
      const SS = String(d.getSeconds()).padStart(2, '0');
      const mmm = String(d.getMilliseconds()).padStart(3, '0');
      return `${yyyy}.${mm}.${dd} ${HH}:${MM}:${SS}.${mmm}`;
    } catch { return ts; }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 pb-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-white">Experts / Journal</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchLog}
            className="p-1.5 glass-card hover:border-zinc-600 rounded transition-colors"
            title="Refresh now"
          >
            <RefreshCw className="w-3.5 h-3.5 text-muted" />
          </button>
          <button
            onClick={toggleLive}
            className={`flex items-center gap-1 px-2 py-1 rounded border text-[10px] font-medium transition-colors ${
              live
                ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-400'
                : 'bg-surface border-border text-zinc-400'
            }`}
          >
            {live ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {live ? 'Auto-scroll' : 'Paused'}
          </button>
        </div>
      </div>

      {/* Terminal View */}
      <div className="flex-1 bg-[#1e1e1e] border border-[#333] rounded overflow-hidden flex flex-col shadow-inner font-mono">
        {/* Table Header */}
        <div className="flex text-[#cccccc] text-[10px] bg-[#2d2d2d] border-b border-[#333] px-2 py-1 select-none">
          <div className="w-[140px] flex-shrink-0">Time</div>
          <div className="w-[120px] flex-shrink-0">Source</div>
          <div className="flex-1">Message</div>
        </div>
        
        {/* Table Body */}
        <div className="flex-1 overflow-y-auto px-2 py-1 text-[10px]">
          {loading ? (
            <div className="text-[#808080] py-2">Loading journal...</div>
          ) : events.length === 0 ? (
            <div className="text-[#808080] py-2">No journal entries.</div>
          ) : (
            <div className="space-y-0.5">
              {events.map((e, idx) => {
                const sourceText = e.symbol ? `Everything (${e.symbol},D1)` : 'System';
                let messageText = e.message || '';
                
                // If the message starts with "Skipped: ", we strip it because the backend now formats it perfectly
                if (messageText.startsWith("Skipped: ")) {
                  messageText = messageText.replace("Skipped: ", "");
                }

                // Determine text color based on the message content (like MT5)
                let msgColor = 'text-[#cccccc]'; // default text
                if (messageText.includes('Signal: BUY')) msgColor = 'text-[#4ec9b0]'; // green-ish
                if (messageText.includes('Signal: SELL')) msgColor = 'text-[#ce9178]'; // red/orange-ish
                if (messageText.includes('Signal: SKIP')) msgColor = 'text-[#dcdcaa]'; // yellow-ish
                if (e.type === 'error') msgColor = 'text-[#f44747]'; // red

                return (
                  <div key={`${e.ts}-${idx}`} className="flex hover:bg-[#2a2d2e] cursor-default whitespace-nowrap">
                    <div className="w-[140px] flex-shrink-0 text-[#808080] overflow-hidden text-ellipsis">
                      {fmtTime(e.ts)}
                    </div>
                    <div className="w-[120px] flex-shrink-0 text-[#cccccc] overflow-hidden text-ellipsis px-2">
                      {sourceText}
                    </div>
                    <div className={`flex-1 overflow-hidden text-ellipsis ${msgColor}`}>
                      {messageText}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SignalFeed;
