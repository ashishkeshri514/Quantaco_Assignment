import { useCallback, useEffect, useRef, useState } from "react";
import { streamUrl } from "./api";

/**
 * Subscribe to SSE events. Refreshes on transaction + alert_ack.
 * Token is in the query string because EventSource cannot set headers.
 */
export function useTransactionStream(enabled: boolean, onEvent: () => void) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const [connected, setConnected] = useState(false);

  const connect = useCallback(() => {
    if (!enabled) return () => undefined;

    const es = new EventSource(streamUrl());
    const bump = () => onEventRef.current();
    es.addEventListener("connected", () => setConnected(true));
    es.addEventListener("transaction", bump);
    es.addEventListener("alert_ack", bump);
    es.onerror = () => {
      setConnected(false);
    };
    return () => {
      es.close();
      setConnected(false);
    };
  }, [enabled]);

  useEffect(() => connect(), [connect]);

  return { connected };
}
