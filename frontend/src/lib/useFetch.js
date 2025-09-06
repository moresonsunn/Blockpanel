import { useEffect, useState } from 'react';

// Simple cache for API responses
const apiCache = new Map();
const DEFAULT_CACHE_DURATION = 30000; // 30s

export function useFetch(url, deps = [], options = {}) {
  const { cacheEnabled = true, cacheDuration = DEFAULT_CACHE_DURATION } = options;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!url) return;

    let active = true;
    const abortController = new AbortController();

    // Check cache first
    if (cacheEnabled) {
      const cached = apiCache.get(url);
      if (cached && Date.now() - cached.timestamp < cacheDuration) {
        if (active) {
          setData(cached.data);
          setLoading(false);
          setError(null);
        }
        return () => { active = false; abortController.abort(); };
      }
    }

    setLoading(true);
    setError(null);

    fetch(url, { signal: abortController.signal })
      .then(async (r) => {
        const payload = await r.json().catch(() => null);
        if (!r.ok)
          throw new Error(
            (payload && (payload.detail || payload.message)) || `HTTP ${r.status}`
          );
        return payload;
      })
      .then((d) => {
        if (active) {
          setData(d);
          if (cacheEnabled) apiCache.set(url, { data: d, timestamp: Date.now() });
        }
      })
      .catch((e) => {
        if (active && e.name !== 'AbortError') setError(e);
      })
      .finally(() => { if (active) setLoading(false); });

    return () => {
      active = false;
      abortController.abort();
    };
  }, deps);

  return { data, loading, error, setData };
}
