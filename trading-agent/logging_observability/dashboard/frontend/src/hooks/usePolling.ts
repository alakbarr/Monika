import { useEffect, useRef } from 'react';
import { useDashboardStore } from '../store/dashboardStore';

export const usePolling = (
  quickInterval = 5_000,   // 5s for live data
  fullInterval = 60_000,   // 60s for all data
) => {
  const { fetchQuick, fetchAll, wsConnected } = useDashboardStore();
  const quickTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const fullTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const mounted = useRef(false);

  // Initial load
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      fetchAll();
    }
  }, [fetchAll]);

  // Full refresh (every fullInterval, e.g. 60s)
  useEffect(() => {
    fullTimer.current = setInterval(fetchAll, fullInterval);
    return () => {
      if (fullTimer.current) clearInterval(fullTimer.current);
    };
  }, [fetchAll, fullInterval]);

  // Quick refresh (drops to 30s heartbeat when WS connected, 5s when disconnected)
  useEffect(() => {
    const effectiveQuick = wsConnected ? 30_000 : quickInterval;
    quickTimer.current = setInterval(fetchQuick, effectiveQuick);

    return () => {
      if (quickTimer.current) clearInterval(quickTimer.current);
    };
  }, [fetchQuick, quickInterval, wsConnected]);
};

