import { useEffect, useRef, useState, useCallback } from 'react';
import type { WSEvent } from '../types';

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<WSEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(() => {
        wsRef.current = new WebSocket(url);
      }, 2000);
    };
    ws.onmessage = (e) => {
      try {
        const event: WSEvent = JSON.parse(e.data);
        setEvents((prev) => [event, ...prev].slice(0, 100));
      } catch { /* ignore malformed */ }
    };

    return () => { ws.close(); };
  }, [url]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, clearEvents };
}
