import { useEffect, useState } from 'react';

// Simple cache for API responses
const apiCache = new Map();
const etagCache = new Map(); // url -> etag
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

    const headers = {};
    const prevEtag = etagCache.get(url);
    if (prevEtag) headers['If-None-Match'] = prevEtag;

    fetch(url, { signal: abortController.signal, headers })
      .then(async (r) => {
        if (r.status === 304) {
          // Not modified; use cached data if present
          const cached = apiCache.get(url);
          if (cached) {
            return cached.data;
          }
          // Fallback: parse anyway if server sent a body (unlikely with 304)
          const payload = await r.json().catch(() => null);
          return payload;
        }
        const et = r.headers.get('etag');
        if (et) etagCache.set(url, et);
        const payload = await r.json().catch(() => null);
        if (!r.ok)
          throw new Error(
            (payload && (payload.detail || payload.message)) || `HTTP ${r.status}`
          );
        return payload;
      })
      .then((d) => {
        if (active && d != null) {
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
