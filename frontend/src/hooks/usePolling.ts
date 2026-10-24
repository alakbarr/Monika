import { useEffect, useRef } from 'react';
import { useDashboardStore } from '../store/dashboardStore';

export const usePolling = (
  quickInterval = 5_000,   // 5s for live data
  fullInterval = 60_000,   // 60s for all data
) => {
  const { fetchQuick, fetchAll, wsConnected } = useDashboardStore();
  const mounted = useRef(false);
  const isFetchingQuick = useRef(false);
  const isFetchingFull = useRef(false);

  // Initial load
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      fetchAll();
    }
  }, [fetchAll]);

  // Full refresh (every fullInterval, e.g. 60s)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let active = true;

    const runFull = async () => {
      if (typeof document !== 'undefined' && document.hidden) {
        timer = setTimeout(runFull, 10_000);
        return;
      }
      if (!isFetchingFull.current) {
        isFetchingFull.current = true;
        try {
          await fetchAll();
        } finally {
          isFetchingFull.current = false;
        }
      }
      if (active) {
        timer = setTimeout(runFull, fullInterval);
      }
    };

    timer = setTimeout(runFull, fullInterval);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [fetchAll, fullInterval]);

  // Quick refresh (drops to 30s heartbeat when WS connected, 5s when disconnected)
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let active = true;

    const runQuick = async () => {
      if (typeof document !== 'undefined' && document.hidden) {
        timer = setTimeout(runQuick, 10_000);
        return;
      }
      const delay = wsConnected ? 30_000 : quickInterval;
      if (!isFetchingQuick.current) {
        isFetchingQuick.current = true;
        try {
          await fetchQuick();
        } finally {
          isFetchingQuick.current = false;
        }
      }
      if (active) {
        timer = setTimeout(runQuick, delay);
      }
    };

    const initialDelay = wsConnected ? 30_000 : quickInterval;
    timer = setTimeout(runQuick, initialDelay);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [fetchQuick, quickInterval, wsConnected]);
};
