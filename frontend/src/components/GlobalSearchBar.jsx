import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  FaSearch,
  FaServer,
  FaUsers,
  FaFileAlt,
  FaTimes,
  FaKeyboard,
} from 'react-icons/fa';
import { API, getStoredToken } from '../lib/api';

const ICON_BY_TYPE = {
  server: FaServer,
  player: FaUsers,
  config: FaFileAlt,
};

const LABEL_BY_TYPE = {
  server: 'Servers',
  player: 'Players',
  config: 'Config Files',
};

function friendlyShortcut() {
  if (typeof navigator !== 'undefined' && /mac os x/i.test(navigator.userAgent)) {
    return '⌘K';
  }
  return 'Ctrl+K';
}

export default function GlobalSearchBar({ onNavigate, className = '' }) {
  const containerRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [highlightIndex, setHighlightIndex] = useState(-1);

  const trimmedQuery = query.trim();

  const showDropdown = open && (loading || error || results.length > 0 || trimmedQuery.length >= 2);

  const runSearch = useCallback((term, signal) => {
    const token = getStoredToken();
    const headers = { Accept: 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const url = `${API}/search?q=${encodeURIComponent(term)}&limit=15`;
    return fetch(url, { headers, signal })
      .then(async (response) => {
        const payload = await response.json().catch(() => null);
        if (!response.ok) {
          const detail = payload && (payload.detail || payload.message);
          throw new Error(detail || `HTTP ${response.status}`);
        }
        return payload && Array.isArray(payload.results) ? payload.results : [];
      });
  }, []);

  useEffect(() => {
    if (abortRef.current) {
      try { abortRef.current.abort(); } catch (_) {}
      abortRef.current = null;
    }
    if (trimmedQuery.length < 2) {
      setResults([]);
      setError('');
      setLoading(false);
      setHighlightIndex(-1);
      if (!trimmedQuery.length) setOpen(false);
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError('');
    setOpen(true);
    const timeoutId = setTimeout(() => {
      runSearch(trimmedQuery, controller.signal)
        .then((items) => {
          setResults(items);
          setHighlightIndex(-1);
        })
        .catch((err) => {
          if (err.name === 'AbortError') return;
          setError(err.message || 'Search failed');
        })
        .finally(() => {
          setLoading(false);
        });
    }, 160);

    return () => {
      clearTimeout(timeoutId);
      try { controller.abort(); } catch (_) {}
      abortRef.current = null;
    };
  }, [trimmedQuery, runSearch]);

  useEffect(() => {
    function handleOutside(event) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(event.target)) {
        setOpen(false);
        setHighlightIndex(-1);
      }
    }
    document.addEventListener('pointerdown', handleOutside);
    return () => document.removeEventListener('pointerdown', handleOutside);
  }, []);

  useEffect(() => {
    function handleShortcut(event) {
      const key = event.key && event.key.toLowerCase();
      if (!key || key !== 'k') return;
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      if (inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
        setOpen(true);
      }
    }
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  const groupedResults = useMemo(() => {
    const groups = new Map();
    results.forEach((item) => {
      const key = item.type || 'unknown';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    });
    return Array.from(groups.entries());
  }, [results]);

  const flatResults = useMemo(() => {
    const out = [];
    groupedResults.forEach(([type, items]) => {
      out.push({ _kind: 'header', type });
      items.forEach((item) => out.push({ _kind: 'item', item }));
    });
    return out;
  }, [groupedResults]);

  useEffect(() => {
    if (!flatResults.length) {
      setHighlightIndex(-1);
      return;
    }
    if (highlightIndex === -1) {
      const firstItemIndex = flatResults.findIndex((entry) => entry._kind === 'item');
      setHighlightIndex(firstItemIndex);
    }
  }, [flatResults, highlightIndex]);

  const ensureVisible = useCallback((index) => {
    const listNode = containerRef.current?.querySelector('[data-role="result-list"]');
    if (!listNode) return;
    const item = listNode.querySelector(`[data-index="${index}"]`);
    if (!item) return;
    const parentRect = listNode.getBoundingClientRect();
    const itemRect = item.getBoundingClientRect();
    if (itemRect.top < parentRect.top) {
      listNode.scrollTop -= (parentRect.top - itemRect.top);
    } else if (itemRect.bottom > parentRect.bottom) {
      listNode.scrollTop += (itemRect.bottom - parentRect.bottom);
    }
  }, []);

  const moveHighlight = useCallback((direction) => {
    if (!flatResults.length) return;
    let idx = highlightIndex;
    for (let i = 0; i < flatResults.length; i++) {
      idx = (idx + direction + flatResults.length) % flatResults.length;
      if (flatResults[idx]._kind === 'item') {
        setHighlightIndex(idx);
        ensureVisible(idx);
        break;
      }
    }
  }, [highlightIndex, flatResults, ensureVisible]);

  const handleSelect = useCallback((item) => {
    if (!item) return;
    if (typeof onNavigate === 'function') {
      onNavigate(item);
    }
    setOpen(false);
    setQuery('');
    setResults([]);
    setHighlightIndex(-1);
    setError('');
    if (inputRef.current) inputRef.current.blur();
  }, [onNavigate]);

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      moveHighlight(1);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      moveHighlight(-1);
    } else if (event.key === 'Enter') {
      if (highlightIndex >= 0 && flatResults[highlightIndex] && flatResults[highlightIndex]._kind === 'item') {
        event.preventDefault();
        handleSelect(flatResults[highlightIndex].item);
      }
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
      setHighlightIndex(-1);
    }
  }, [moveHighlight, flatResults, highlightIndex, handleSelect]);

  const shortcutLabel = friendlyShortcut();

  return (
    <div ref={containerRef} className={`relative text-white ${className}`}>
      <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm backdrop-blur supports-[backdrop-filter]:bg-white/10 focus-within:ring-2 focus-within:ring-brand-500/20 transition-shadow">
        <FaSearch className="text-white/50" />
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { if (results.length || trimmedQuery.length >= 2) setOpen(true); }}
          placeholder="Search servers, players, files"
          className="bg-transparent flex-1 outline-none text-white placeholder-white/50"
        />
        {query ? (
          <button
            type="button"
            onClick={() => { setQuery(''); setResults([]); setError(''); setHighlightIndex(-1); setOpen(false); }}
            className="text-white/50 hover:text-white"
            aria-label="Clear search"
          >
            <FaTimes />
          </button>
        ) : (
          <div className="hidden sm:flex items-center gap-1 text-[11px] text-white/40">
            <FaKeyboard className="text-[10px]" />
            <span>{shortcutLabel}</span>
          </div>
        )}
      </div>
      {showDropdown && (
        <div className="absolute left-0 right-0 mt-2 bg-black/80 border border-white/10 rounded-lg shadow-xl backdrop-blur supports-[backdrop-filter]:bg-black/70 z-50 max-h-80 overflow-hidden">
          {loading ? (
            <div className="px-4 py-3 text-sm text-white/70">Searching…</div>
          ) : null}
          {error ? (
            <div className="px-4 py-3 text-sm text-red-400">{error}</div>
          ) : null}
          {!loading && !error && trimmedQuery.length >= 2 && results.length === 0 ? (
            <div className="px-4 py-3 text-sm text-white/60">No matches found.</div>
          ) : null}
          {!loading && !error && results.length > 0 && (
            <div data-role="result-list" className="max-h-64 overflow-y-auto py-1">
              {flatResults.map((entry, index) => {
                if (entry._kind === 'header') {
                  return (
                    <div
                      key={`header-${entry.type}`}
                      className="px-4 pt-2 pb-1 text-[11px] uppercase tracking-wide text-white/40"
                    >
                      {LABEL_BY_TYPE[entry.type] || entry.type}
                    </div>
                  );
                }
                const { item } = entry;
                const Icon = ICON_BY_TYPE[item.type] || FaSearch;
                const active = index === highlightIndex;
                return (
                  <button
                    key={item.id || `${item.type}-${item.name}`}
                    type="button"
                    data-index={index}
                    className={`w-full px-4 py-2 text-left text-sm flex items-start gap-3 transition-colors ${
                      active ? 'bg-brand-500/20 text-white' : 'hover:bg-white/10'
                    }`}
                    onMouseEnter={() => setHighlightIndex(index)}
                    onMouseDown={(event) => { event.preventDefault(); handleSelect(item); }}
                  >
                    <span className="mt-0.5 text-white/60">
                      <Icon />
                    </span>
                    <span className="flex-1">
                      <span className="block text-sm font-medium text-white">{item.name}</span>
                      {item.description ? (
                        <span className="block text-xs text-white/60">{item.description}</span>
                      ) : null}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide text-white/40">{item.type}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
