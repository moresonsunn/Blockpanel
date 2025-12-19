import LoginPage from './pages/LoginPage';
import MustChangePasswordPage from './pages/MustChangePasswordPage';
// --- New: Rename server button component ---
function RenameServerButton({ currentName, onRenamed }) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState(currentName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submitRename(e) {
    e.preventDefault();
    setError('');
    const trimmed = (newName || '').trim();
    if (!trimmed) {
      setError('Name cannot be empty');
      return;
    }
    if (trimmed === currentName) {
      setError('Name unchanged');
      return;
    }
    // Basic client-side validation: only allow alphanumerics, dashes, underscores
    if (!/^[-_a-zA-Z0-9]+$/.test(trimmed)) {
      setError('Invalid characters. Use letters, numbers, - or _.');
      return;
    }
    setBusy(true);
    try {
      const resp = await fetch(`/api/servers/${encodeURIComponent(currentName)}/rename-server`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: trimmed })
      });
      if (!resp.ok) {
        const txt = await resp.text();
        throw new Error(txt || `Rename failed (${resp.status})`);
      }
      const data = await resp.json();
      onRenamed?.(data.new_name || trimmed);
      setOpen(false);
    } catch (err) {
      setError(err.message || 'Rename failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => { setOpen(o => !o); setNewName(currentName); setError(''); }}
        className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-white"
      >Rename</button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-neutral-900 border border-white/10 rounded shadow-lg p-3 z-50">
          <form onSubmit={submitRename} className="flex flex-col gap-2">
            <div className="text-xs text-white/70">Rename Server</div>
            <input
              autoFocus
              value={newName}
              onChange={e => setNewName(e.target.value)}
              className="bg-neutral-800 text-sm p-2 rounded outline-none focus:ring-2 focus:ring-blue-500 text-white"
              placeholder="New server name"
            />
            {error && <div className="text-red-400 text-xs">{error}</div>}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { if (!busy) { setOpen(false); setError(''); } }}
                className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-white"
              >Cancel</button>
              <button
                type="submit"
                disabled={busy}
                className={"text-xs px-2 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"}
              >{busy && <span className="animate-spin inline-block w-3 h-3 border-2 border-white/30 border-t-white rounded-full"/>}Save</button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
import React, { useState, useEffect, useRef, useMemo, useCallback, createContext, useContext } from 'react';
import { normalizeRamInput } from './utils/ram';
import { APP_NAME, applyDocumentBranding } from './branding';
import {
  FaServer,
  FaPlay,
  FaStop,
  FaTrash,
  FaTerminal,
  FaFolder,
  FaCog,
  FaUsers,
  FaDownload,
  FaClock,
  FaSave,
  FaUpload,
  FaArrowLeft,
  FaMemory,
  FaMicrochip,
  FaNetworkWired,
  FaChevronRight,
  FaHome,
  FaUserCog,
  FaChartLine,
  FaDatabase,
  FaBell,
  FaShieldAlt,
  FaClipboardList,
  FaFileExport,
  FaHistory,
  FaRocket,
  FaCode,
  FaHeart,
  FaExclamationTriangle,
  FaCheckCircle,
  FaTimesCircle,
  FaInfoCircle,
  FaEdit,
  FaPlus,
  FaMinus,
  FaSearch,
  FaFilter,
  FaSort,
  FaSync,
  FaEye,
  FaEyeSlash,
  FaKey,
  FaCopy,
  FaGlobe,
  FaEnvelope,
  FaTasks,
  FaLayerGroup,
  FaProjectDiagram,
  FaTools,
  FaWrench,
  FaBug,
  FaLifeRing,
  FaQuestionCircle,
  FaBook,
  FaNewspaper,
  FaCalendarAlt,
  FaStopwatch,
  FaBackward,
  FaForward,
  FaPause,
  FaStepBackward,
  FaStepForward,
  FaFastBackward,
  FaFastForward,
  FaSun,
  FaMoon,
  // FaTable, // removed with Permission Matrix
  FaTimes,
  FaUserSlash,
  FaUserCheck,
  FaUniversalAccess,
} from 'react-icons/fa';
import TerminalPanel from './components/TerminalPanel';
import BackupsPanel from './components/server-details/BackupsPanel';
import ConfigPanel from './components/server-details/ConfigPanel';
import WorldsPanel from './components/server-details/WorldsPanel';
import SchedulePanel from './components/server-details/SchedulePanel';
import PlayersPanel from './components/server-details/PlayersPanel';
import GlobalSearchBar from './components/GlobalSearchBar';
const MonitoringPageLazy = React.lazy(() => import('./components/MonitoringPage'));
const TemplatesPageLazy = React.lazy(() => import('./pages/TemplatesPage'));
import FilesPanelWrapper from './components/server-details/FilesPanelWrapper';
import EditingPanel from './components/server-details/EditingPanel';
import { useFetch } from './lib/useFetch';

// Dynamic API base: prefer same-origin '/api' to avoid CORS; keep fallback to current origin if needed
const _defaultOrigin = (typeof window !== 'undefined' && window.location && window.location.origin)
  ? window.location.origin
  : 'http://localhost:8000';
// Primary (no prefix) and alias (/api) – /api helps bypass aggressive browser extensions blocking certain paths
const API_BASES = [_defaultOrigin + '/api', _defaultOrigin];
// Prefer /api base first to avoid cross-origin calls
let API = (typeof window !== 'undefined') ? '/api' : 'http://localhost:8000';

// Ensure document title reflects branding
if (typeof window !== 'undefined') {
  try { applyDocumentBranding(); } catch {}
}

// Defensive fallback: some production bundles / code-splits referenced `serverName`
// in contexts where it wasn't declared (causing ReferenceError). Provide a
// harmless global fallback to avoid runtime crashes. Local `const [serverName,...]`
// declarations will still shadow this global value.
if (typeof window !== 'undefined' && typeof serverName === 'undefined') {
  // eslint-disable-next-line no-var
  var serverName = '';
}

// Defensive fallback for hostPort to avoid runtime ReferenceError in prod bundles
if (typeof window !== 'undefined' && typeof hostPort === 'undefined') {
  // eslint-disable-next-line no-var
  var hostPort = '';
}

// Defensive fallback for minRam (and maxRam) to avoid ReferenceError in prod bundles
if (typeof window !== 'undefined' && typeof minRam === 'undefined') {
  // eslint-disable-next-line no-var
  var minRam = '';
}
if (typeof window !== 'undefined' && typeof maxRam === 'undefined') {
  // eslint-disable-next-line no-var
  var maxRam = '';
}

// Defensive fallback for javaOverride used in some UI flows
if (typeof window !== 'undefined' && typeof javaOverride === 'undefined') {
  // eslint-disable-next-line no-var
  var javaOverride = '';
}

// Defensive fallback for serverType used in several UI flows
if (typeof window !== 'undefined' && typeof serverType === 'undefined') {
  // eslint-disable-next-line no-var
  var serverType = '';
}

// Defensive fallback for serverVersion used in UI flows
if (typeof window !== 'undefined' && typeof serverVersion === 'undefined') {
  // eslint-disable-next-line no-var
  var serverVersion = '';
}

// Defensive fallback for busy flag used during many UI flows
if (typeof window !== 'undefined' && typeof busy === 'undefined') {
  // eslint-disable-next-line no-var
  var busy = false;
}

const THEME_MODE_KEY = 'theme-mode';
const COLORBLIND_KEY = 'theme-colorblind';

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  try {
    const storedTheme = window.localStorage.getItem(THEME_MODE_KEY);
    const mode = storedTheme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', mode);
    if (document.body) {
      document.body.setAttribute('data-theme', mode);
    }
    const storedPalette = window.localStorage.getItem(COLORBLIND_KEY);
    const palette = storedPalette === 'on' ? 'on' : 'off';
    document.documentElement.setAttribute('data-colorblind', palette);
    if (document.body) {
      document.body.setAttribute('data-colorblind', palette);
    }
  } catch (err) {
    console.warn('Theme initialization failed:', err);
  }
}

// Global Data Store Context for instant access to all data
const GlobalDataContext = createContext();

// Global data store that preloads everything
export function GlobalDataProvider({ children }) {
  // All application data - preloaded and always available
  const [globalData, setGlobalData] = useState({
    servers: [],
    serverStats: {},
    serverInfoById: {},
    dashboardData: null,
    systemHealth: null,
    alerts: [],
    users: [],
    roles: [],
    auditLogs: [],
    settings: {},
    serverTypes: [],
    serverVersions: {},
    isInitialized: false
  });

  // Keep latest servers in a ref for interval callbacks
  const serversRef = useRef(globalData.servers);
  useEffect(() => { serversRef.current = globalData.servers; }, [globalData.servers]);

  // Background timers/handles
  const refreshIntervals = useRef({});
  const abortControllers = useRef({});

  // Aggressive preloading function - loads EVERYTHING immediately (run once on mount)
  const preloadAllData = useCallback(async () => {
    const isAuth = !!getStoredToken();
    const endpoints = [
      { key: 'serverTypes', url: `${API}/server-types` },
      ...(isAuth ? [{ key: 'servers', url: `${API}/servers` }] : [])
    ];

    // Create abort controllers for all requests
    const localControllers = Object.fromEntries(
      endpoints.map(e => [e.key, new AbortController()])
    );
    abortControllers.current = localControllers;

    // Execute all requests in parallel
    const results = await Promise.all(endpoints.map(async endpoint => {
      try {
        const response = await fetch(endpoint.url, {
          signal: localControllers[endpoint.key]?.signal,
          headers: authHeaders()
        });
        if (response.ok) {
          const data = await response.json();
          return { key: endpoint.key, data };
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.warn(`Failed to preload ${endpoint.key}:`, error);
        }
      }
      return { key: endpoint.key, data: null };
    }));

    // Build a single update object and commit once
    const updates = {};
    results.forEach(result => {
      if (result.data) {
        switch (result.key) {
          case 'servers':
            updates.servers = Array.isArray(result.data) ? result.data : [];
            break;
          case 'serverTypes':
            updates.serverTypes = result.data.types || [];
            break;
          default:
            updates[result.key] = result.data;
        }
      }
    });

    // Schedule deferred background preloads once
    const t = setTimeout(() => {
      const isAuthNow = !!getStoredToken();
      if (!isAuthNow) return;
      refreshDataInBackground('dashboardData', `${API}/monitoring/dashboard-data`);
      refreshDataInBackground('systemHealth', `${API}/monitoring/system-health`);
      refreshDataInBackground('alerts', `${API}/monitoring/alerts`, (d) => d.alerts || []);
      refreshDataInBackground('users', `${API}/users`, (d) => d.users || []);
      refreshDataInBackground('roles', `${API}/users/roles`, (d) => d.roles || []);
      refreshDataInBackground('auditLogs', `${API}/users/audit-logs?page=1&page_size=50`, (d) => d.logs || []);
    }, 1500);
    refreshIntervals.current.deferredPreloads = t;

    setGlobalData(current => ({ ...current, ...updates, isInitialized: true }));
  }, []);

  // Helper: refresh servers list on demand
  const refreshServersNow = useCallback(async () => {
    try {
      const r = await fetch(`${API}/servers`, { headers: authHeaders() });
      if (!r.ok) return;
      const list = await r.json();
      setGlobalData(cur => ({ ...cur, servers: Array.isArray(list) ? list : [] }));
    } catch {}
  }, []);

  // Helper: optimistic update server status locally without reload
  const updateServerStatus = useCallback((id, status) => {
    setGlobalData(cur => ({
      ...cur,
      servers: (cur.servers || []).map(s => s.id === id ? { ...s, status } : s),
    }));
  }, []);

  // Background refresh function - updates data silently
  const refreshDataInBackground = useCallback(async (dataKey, url, processor = null) => {
    try {
      if (typeof window !== 'undefined' && window.HEAVY_PANEL_ACTIVE) return;
      const response = await fetch(url, { headers: authHeaders() });
      if (response.ok) {
        const data = await response.json();
        setGlobalData(current => ({
          ...current,
          [dataKey]: processor ? processor(data) : data
        }));
      }
    } catch (error) {
      // Silent fail for background updates
    }
  }, []);

// Start aggressive preloading on mount
  useEffect(() => {
    preloadAllData();

    // Set up optimized background refresh intervals for balanced performance
    // Keep a light fallback poll; primary real-time updates come via SSE below.
    refreshIntervals.current.servers = setInterval(() => {
      refreshDataInBackground('servers', `${API}/servers`, (data) => Array.isArray(data) ? data : []);
    }, 15000);

    refreshIntervals.current.dashboardData = setInterval(() => {
      refreshDataInBackground('dashboardData', `${API}/monitoring/dashboard-data`);
    }, 30000);

    refreshIntervals.current.alerts = setInterval(() => {
      refreshDataInBackground('alerts', `${API}/monitoring/alerts`, (data) => data.alerts || []);
    }, 60000);

    // Server stats refresh using bulk endpoint for performance
    refreshIntervals.current.serverStats = setInterval(async () => {
      try {
        if (typeof window !== 'undefined' && window.HEAVY_PANEL_ACTIVE) return;
        const r = await fetch(`${API}/servers/stats?ttl=2`, { headers: authHeaders() });
        if (!r.ok) return;
        const data = await r.json(); // { [id]: stats }
        setGlobalData(current => {
          const merged = { ...(current.serverStats || {}) };
          if (data && typeof data === 'object') {
            Object.entries(data).forEach(([id, s]) => {
              merged[id] = { ...(merged[id] || {}), ...(s || {}), players: merged[id]?.players };
            });
          }
          return { ...current, serverStats: merged };
        });
      } catch {}
    }, 6000);

    const handleVisibility = () => {
      if (typeof document !== 'undefined' && document.hidden) return;
      refreshDataInBackground('servers', `${API}/servers`, (data) => Array.isArray(data) ? data : []);
    };
    try {
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', handleVisibility);
      }
    } catch {}

    return () => {
      // Cleanup intervals and abort controllers
      Object.values(refreshIntervals.current).forEach((h) => { try { clearInterval(h); } catch {} });
      if (refreshIntervals.current.deferredPreloads) { try { clearTimeout(refreshIntervals.current.deferredPreloads); } catch {} }
      Object.values(abortControllers.current).forEach(controller => { try { controller.abort(); } catch {} });
      try {
        if (typeof document !== 'undefined') {
          document.removeEventListener('visibilitychange', handleVisibility);
        }
      } catch {}
    };
  }, []);

  // Real-time server list updates via SSE (falls back to polling above)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const token = getStoredToken();
    if (!token) return;

    const es = new EventSource(`${API}/servers/stream?token=${encodeURIComponent(token)}`);

    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.type === 'servers' && Array.isArray(payload.servers)) {
          setGlobalData(cur => ({ ...cur, servers: payload.servers }));
        }
      } catch {
        // ignore malformed payloads
      }
    };

    es.onerror = () => {
      try { es.close(); } catch {}
    };

    return () => {
      try { es.close(); } catch {}
    };
  }, [API]);

  // Preload server info (type/version + dir snapshots) for all servers after initial load
  useEffect(() => {
    const servers = serversRef.current || [];
    if (!servers.length) return;
    let cancelled = false;
    (async () => {
      const entries = await Promise.allSettled(
        servers.map(async (s) => {
          try {
            const r = await fetch(`${API}/servers/${s.id}/info`, { headers: authHeaders() });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const d = await r.json();
            return [s.id, d];
          } catch {
            return [s.id, null];
          }
        })
      );
      if (cancelled) return;
      const byId = {};
      entries.forEach(res => { if (res.status === 'fulfilled') { const [id, info] = res.value; if (info) byId[id] = info; } });
      if (Object.keys(byId).length) {
        setGlobalData(cur => ({ ...cur, serverInfoById: { ...(cur.serverInfoById || {}), ...byId } }));
      }
    })();
    return () => { cancelled = true; };
  }, [globalData.servers.length]);

  // Initial bulk fetch of server stats once servers are available
  useEffect(() => {
    if (globalData.servers.length > 0 && globalData.isInitialized) {
      (async () => {
        try {
          const r = await fetch(`${API}/servers/stats?ttl=0`, { headers: authHeaders() });
          if (!r.ok) return;
          const data = await r.json();
          setGlobalData(current => ({
            ...current,
            serverStats: { ...(current.serverStats || {}), ...(data || {}) }
          }));
        } catch {}
      })();
    }
  }, [globalData.servers, globalData.isInitialized]);

  return (
    <GlobalDataContext.Provider value={{
      ...globalData,
      __setGlobalData: setGlobalData,
      __refreshServers: refreshServersNow,
      __updateServerStatus: updateServerStatus,
      __refreshBG: refreshDataInBackground,
      __preloadAll: preloadAllData,
    }}>
      {children}
    </GlobalDataContext.Provider>
  );
}

// Hook to access global data instantly
function useGlobalData() {
  const data = useContext(GlobalDataContext);
  if (!data) {
    throw new Error('useGlobalData must be used within GlobalDataProvider');
  }
  return data;
}

const TOKEN_KEY = 'auth_token';
const getStoredToken = () => localStorage.getItem(TOKEN_KEY) || '';
const setStoredToken = (t) => localStorage.setItem(TOKEN_KEY, t);
const clearStoredToken = () => localStorage.removeItem(TOKEN_KEY);
const authHeaders = () => {
  const t = getStoredToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

// Attach Authorization header to all fetch calls
if (typeof window !== 'undefined' && typeof window.fetch === 'function') {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    try {
      const headers = { ...(init && init.headers ? init.headers : {}), ...authHeaders() };
      const urlStr = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
      const firstResp = await originalFetch(input, { ...(init || {}), headers });
      // If OK or not a candidate for retry, return immediately
      if (firstResp && firstResp.ok) return firstResp;
      const shouldRetry = (() => {
        // Network-level failures won't yield a Response (caught below), so only logic for non-ok
        if (!urlStr.startsWith(_defaultOrigin)) return false;
        if (urlStr.includes('/api/')) return false; // already using alias
        // Retry on common auth endpoints or if blocked by extension (ad blockers sometimes force 0/401 early)
        if (firstResp && (firstResp.status === 404 || firstResp.status === 0 || firstResp.status === 401)) return true;
        return false;
      })();
      if (!shouldRetry) return firstResp;
      const apiUrl = urlStr.replace(_defaultOrigin, _defaultOrigin + '/api');
      try {
        const secondResp = await originalFetch(apiUrl, { ...(init || {}), headers });
        if (!secondResp.ok) return secondResp; // propagate
        return secondResp;
      } catch (e2) {
        return firstResp; // fallback to original failure
      }
    } catch (e) {
      // Network error before Response – try /api if possible
      try {
        const urlStr = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
        if (urlStr.startsWith(_defaultOrigin) && !urlStr.includes('/api/')) {
          const apiUrl = urlStr.replace(_defaultOrigin, _defaultOrigin + '/api');
          const headers = { ...(init && init.headers ? init.headers : {}), ...authHeaders() };
          return await originalFetch(apiUrl, { ...(init || {}), headers });
        }
      } catch {
        // Swallow
      }
      throw e;
    }
  };
}

const BLOCKED_FILE_EXTENSIONS = [
  '.jar', '.exe', '.dll', '.zip', '.tar', '.gz', '.7z', '.rar', '.bin', '.img', '.iso', '.mp3', '.mp4', '.avi', '.mov', '.ogg', '.wav', '.class', '.so', '.o', '.a', '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.ttf', '.otf', '.woff', '.woff2'
];

function isBlockedFile(name) {
  const lower = name.toLowerCase();
  return BLOCKED_FILE_EXTENSIONS.some(ext => lower.endsWith(ext));
}

// Optimized server stats hook with debouncing and caching
function useServerStats(serverId) {
  const [stats, setStats] = useState(null);
  const [isVisible, setIsVisible] = useState(true);

  // Check if the tab/page is visible to pause polling when not needed
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsVisible(!document.hidden);
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (!serverId || !isVisible) return;
    
    let active = true;
    let interval = null;
    const abortController = new AbortController();
    let es = null;

    async function fetchStats() {
      if (!active || !isVisible) return;
      
      try {
        const r = await fetch(`${API}/servers/${serverId}/stats`, {
          signal: abortController.signal
        });
        if (!r.ok) {
          if (r.status === 404) {
            if (active) setStats(null);
            return;
          }
          throw new Error(`HTTP ${r.status}`);
        }
        const d = await r.json();
        if (active) setStats(d);
      } catch (e) {
        if (active && e.name !== 'AbortError' && e.message !== 'HTTP 404') {
          setStats(null);
        }
      }
    }

    // Try to establish SSE stream; fallback to polling if it fails
    try {
      const token = getStoredToken();
      const sseUrl = `${API}/monitoring/events?container_id=${encodeURIComponent(serverId)}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
      es = new EventSource(sseUrl);
      es.onmessage = (ev) => {
        if (!active) return;
        try {
          const payload = JSON.parse(ev.data);
          if (payload?.type === 'resources' && payload?.data) {
            setStats(payload.data);
          }
        } catch {}
      };
      es.onerror = () => {
        // Close and fallback to polling
        if (es) { try { es.close(); } catch(_) {} }
        if (!interval) {
          fetchStats();
          interval = setInterval(fetchStats, 5000);
        }
      };
    } catch (_) {
      // SSE not available; use polling
      fetchStats();
      interval = setInterval(fetchStats, 5000);
    }

    return () => {
      active = false;
      abortController.abort();
      if (interval) clearInterval(interval);
      if (es) { try { es.close(); } catch(_) {} }
    };
  }, [serverId, isVisible]);

  return stats;
}

function Stat({ label, value, icon }) {
  return (
    <div className="rounded-xl bg-white/5 border border-white/10 px-4 py-3 flex items-center gap-3">
      {icon && <span className="text-xl text-white/60">{icon}</span>}
      <div>
        <div className="text-sm text-white/70">{label}</div>
        <div className="text-2xl font-semibold mt-1">{value}</div>
      </div>
    </div>
  );
}



// List of server types that require loader version input
const SERVER_TYPES_WITH_LOADER = ['fabric', 'forge', 'neoforge'];

// ConfigPanel moved to components
// PluginsPanel moved to components
// WorldsPanel moved to components
// SchedulePanel moved to components
// PlayersPanel moved to components
function ServerDetailsPage({
  server,
  onBack,
  onStart,
  onStop,
  onDelete,
  onRestart,
  initialTab = 'overview',
  onTabChange,
  playerFocus = '',
  onPlayerFocusConsumed,
  configFocus = '',
  onConfigFocusConsumed,
}) {
  const globalData = useGlobalData();
  const [activeTab, setActiveTab] = useState('overview');
  const [filesEditing, setFilesEditing] = useState(false);
  const [editPath, setEditPath] = useState('');
  const [editContent, setEditContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [blockedFileError, setBlockedFileError] = useState('');
  const stats = useServerStats(server.id);
  const [logReset, setLogReset] = useState(0);
  const prettify = useCallback((value) => {
    if (!value) return '';
    return value
      .toString()
      .split(/[-_\s]+/)
      .filter(Boolean)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }, []);

  // Wrap power actions to bump log reset so TerminalPanel clears and refetches
  const onStartWrapped = useCallback(async (id) => {
    await onStart(id);
    setLogReset(x => x + 1);
  }, [onStart]);
  const onStopWrapped = useCallback(async (id) => {
    await onStop(id);
    setLogReset(x => x + 1);
  }, [onStop]);
  const onRestartWrapped = useCallback(async (id) => {
    await onRestart(id);
    setLogReset(x => x + 1);
  }, [onRestart]);

  const handleEditStart = useCallback((filePath, content) => {
    setEditPath(filePath);
    setEditContent(content);
    setIsEditing(true);
    setFilesEditing(true);
  }, []);

  // Prefer preloaded server info for instant render; fallback to fetch if missing
  const preloadedInfo = globalData.serverInfoById?.[server.id] || null;
  const { data: fetchedInfo, error: fetchedInfoError } = useFetch(
    !preloadedInfo && server?.id ? `${API}/servers/${server.id}/info` : null,
    [server?.id]
  );
  const typeVersionData = preloadedInfo || fetchedInfo || null;
  const infoError = fetchedInfoError ? (fetchedInfoError.message || String(fetchedInfoError)) : null;
  const runtimeKind = (typeVersionData?.server_kind || server?.server_kind || '').toLowerCase();
  const isSteam = runtimeKind === 'steam';
  const steamPorts = useMemo(() => {
    const raw = typeVersionData?.steam_ports ?? server?.steam_ports ?? [];
    return Array.isArray(raw) ? raw : [];
  }, [typeVersionData?.steam_ports, server?.steam_ports]);

  const primaryPort = useMemo(() => {
    if (isSteam) {
      if (!steamPorts.length) return 'Not mapped';
      const first = steamPorts[0] || {};
      const host = first.host_port ?? 'auto';
      const target = first.container_port ? `${first.container_port}${first.protocol ? `/${first.protocol}` : ''}` : 'container';
      const extras = steamPorts.length > 1 ? ` (+${steamPorts.length - 1} more)` : '';
      return `${host} → ${target}${extras}`;
    }
    // Prefer explicit port_mappings from server info
    const mapping = typeVersionData?.port_mappings?.["25565/tcp"];
    if (mapping && mapping.host_port) {
      return `${mapping.host_port} → 25565`;
    }
    // Fall back to host_port convenience field from the list endpoint
    if (server?.host_port) {
      return `${server.host_port} → 25565`;
    }
    // Legacy raw ports
    if (server?.ports) {
      const entries = Object.entries(server.ports)
        .filter(([containerPort, mappings]) =>
          containerPort.includes('25565') && mappings && mappings.length > 0
        )
        .map(([_, mappings]) => mappings[0]?.HostPort)
        .filter(Boolean);
      if (entries.length) {
        return `${entries[0]} → 25565`;
      }
    }
    return 'Not mapped';
  }, [isSteam, steamPorts, typeVersionData, server]);

  const createdDisplay = useMemo(() => {
    const created = typeVersionData?.created || typeVersionData?.state?.StartedAt || server?.created_at;
    if (!created) return 'N/A';
    const dt = new Date(created);
    return Number.isNaN(dt.getTime()) ? 'N/A' : dt.toLocaleString();
  }, [typeVersionData, server]);

  const tabs = useMemo(() => {
    const base = [
      { id: 'overview', label: 'Overview', icon: FaServer },
      { id: 'files', label: 'Files', icon: FaFolder },
      { id: 'config', label: 'Config', icon: FaCog },
      { id: 'players', label: 'Players', icon: FaUsers },
      { id: 'worlds', label: 'Worlds', icon: FaFolder },
      { id: 'backup', label: 'Backup', icon: FaDownload },
      { id: 'schedule', label: 'Schedule', icon: FaClock },
    ];
    if (!isSteam) {
      return base;
    }
    const allowed = new Set(['overview', 'files', 'backup', 'schedule']);
    return base.filter(tab => allowed.has(tab.id));
  }, [isSteam]);

  const displayType = useMemo(() => {
    if (isSteam) {
      const game = prettify(typeVersionData?.steam_game || server?.steam_game || server?.type || 'Steam');
      return game ? `Steam · ${game}` : 'Steam';
    }
    return typeVersionData?.server_type || typeVersionData?.labels?.['mc.type'] || server.type || 'Unknown';
  }, [isSteam, prettify, server, typeVersionData]);

  const displayVersion = useMemo(() => {
    if (isSteam) {
      return typeVersionData?.server_version || server?.version || 'latest';
    }
    return typeVersionData?.server_version || typeVersionData?.labels?.['mc.version'] || server.version || 'Unknown';
  }, [isSteam, server, typeVersionData]);

    useEffect(() => {
      const validTabs = new Set(tabs.map((tab) => tab.id));
      const desired = validTabs.has(initialTab) ? initialTab : 'overview';
      setActiveTab(desired);
    }, [initialTab, server?.id]);

    useEffect(() => {
      if (typeof onTabChange === 'function') {
        onTabChange(activeTab);
      }
    }, [activeTab, onTabChange]);

    useEffect(() => {
      if (!playerFocus) return;
      if (activeTab !== 'players') {
        setActiveTab('players');
      }
    }, [playerFocus, activeTab]);

    useEffect(() => {
      if (!configFocus) return;
      if (activeTab !== 'files') {
        setActiveTab('files');
      }
      if (!server?.name) {
        if (typeof onConfigFocusConsumed === 'function') {
          onConfigFocusConsumed();
        }
        return;
      }
      let cancelled = false;
      async function openConfigPath(path) {
        try {
          const response = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent(path)}`);
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          const payload = await response.json().catch(() => ({}));
          if (cancelled) return;
          setEditPath(path);
          setEditContent(payload.content || '');
          setIsEditing(true);
          setFilesEditing(true);
          setBlockedFileError('');
        } catch (err) {
          if (!cancelled) {
            setBlockedFileError(err.message || 'Unable to open file');
          }
        } finally {
          if (!cancelled && typeof onConfigFocusConsumed === 'function') {
            onConfigFocusConsumed();
          }
        }
      }
      openConfigPath(configFocus);
      return () => {
        cancelled = true;
      };
    }, [configFocus, server?.name, server?.id, activeTab, onConfigFocusConsumed]);

    useEffect(() => {
      setFilesEditing(false);
      setIsEditing(false);
      setEditPath('');
      setEditContent('');
      setBlockedFileError('');
    }, [server?.id]);

// FilesPanelWrapper moved to components/server-details/FilesPanelWrapper.jsx

  async function saveFile() {
    const body = new URLSearchParams({ content: editContent });
    await fetch(
      `${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent(
        editPath
      )}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      }
    );
    setIsEditing(false);
    setFilesEditing(false);
    setEditPath('');
    setEditContent('');
    setBlockedFileError('');
  }

  function cancelEdit() {
    setIsEditing(false);
    setFilesEditing(false);
    setEditPath('');
    setEditContent('');
    setBlockedFileError('');
  }

  useEffect(() => {
    if (activeTab === 'files' || activeTab === 'config') {
      if (typeof window !== 'undefined') window.HEAVY_PANEL_ACTIVE = true;
    } else {
      if (typeof window !== 'undefined') window.HEAVY_PANEL_ACTIVE = false;
    }
    return () => { if (typeof window !== 'undefined') window.HEAVY_PANEL_ACTIVE = false; };
  }, [activeTab]);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'files':
        return (
          <div className="flex flex-row gap-6 w-full">
            <FilesPanelWrapper 
              serverName={server.name} 
              initialItems={typeVersionData?.dir_snapshot}
              isBlockedFile={isBlockedFile}
              onEditStart={handleEditStart}
              onBlockedFileError={setBlockedFileError}
            />
            <div className="flex-1 min-w-[0]">
              {isEditing ? (
                <EditingPanel
                  editPath={editPath}
                  editContent={editContent}
                  setEditContent={setEditContent}
                  onSave={saveFile}
                  onCancel={cancelEdit}
                />
              ) : (
                <TerminalPanel containerId={server.id} resetToken={logReset} />
              )}
              {blockedFileError && (
                <div className="text-red-400 text-xs mt-2">{blockedFileError}</div>
              )}
            </div>
          </div>
        );
      case 'backup':
        return <BackupsPanel serverName={server.name} />;
      case 'worlds':
        return <WorldsPanel serverName={server.name} />;
      case 'config':
        return <ConfigPanel server={server} onRestart={onRestart} />;
      case 'players':
        return (
          <PlayersPanel
            serverId={server.id}
            serverName={server.name}
            focusPlayer={playerFocus}
            onFocusConsumed={onPlayerFocusConsumed}
          />
        );
      case 'schedule':
        return (
          <SchedulePanel />
        );
      default:
        return (
          <div className="p-4 bg-black/20 rounded-lg">
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm text-white/70">Server Information</div>
              {infoError ? (
                <div className="text-xs text-red-400">Details unavailable: {String(infoError)}</div>
              ) : null}
              <RenameServerButton currentName={server.name} onRenamed={(newName) => {
                // Update local server name and trigger a refresh
                server.name = newName;
                // Force a refetch if there's a loader or reload logic; simplest: update a key state
                setLogReset(Date.now());
              }} />
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-white/50">Status</div>
                <div
                  className={
                    server.status === 'running'
                      ? 'text-green-400'
                      : 'text-yellow-400'
                  }
                >
                  {server.status}
                </div>
              </div>
              <div>
                <div className="text-white/50">Port</div>
                <div>{primaryPort}</div>
              </div>
              <div>
                <div className="text-white/50">Type</div>
                <div>
                  {displayType || <span className="text-white/40">Unknown</span>}
                </div>
              </div>
              <div>
                <div className="text-white/50">Version</div>
                <div>
                  {displayVersion || <span className="text-white/40">Unknown</span>}
                </div>
              </div>
              <div>
                <div className="text-white/50">Created</div>
                <div>{createdDisplay}</div>
              </div>
              <div>
                <div className="text-white/50">ID</div>
                <div>{server.id}</div>
              </div>
              {isSteam ? (
                <div>
                  <div className="text-white/50">Steam Ports</div>
                  <div>
                    {steamPorts.length
                      ? steamPorts
                          .map(p => `${p.host_port ?? 'auto'} → ${p.container_port}${p.protocol ? `/${p.protocol}` : ''}`)
                          .join(', ')
                      : 'Not mapped'}
                  </div>
                </div>
              ) : null}
            </div>
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-6">
              <Stat
                label="CPU Usage"
                value={
                  stats && typeof stats.cpu_percent === 'number'
                    ? `${stats.cpu_percent.toFixed(1)}%`
                    : '...'
                }
                icon={<FaMicrochip />}
              />
              <Stat
                label="RAM Usage"
                value={
                  stats && typeof stats.memory_usage_mb === 'number'
                    ? `${Math.round(stats.memory_usage_mb)}MB / ${Math.round(stats.memory_limit_mb)}MB`
                    : '...'
                }
                icon={<FaMemory />}
              />
              <Stat
                label="Networking"
                value={
                  stats && typeof stats.network_rx_mb === 'number'
                    ? `In: ${stats.network_rx_mb.toFixed(2)} MB, Out: ${stats.network_tx_mb.toFixed(2)} MB`
                    : '...'
                }
                icon={<FaNetworkWired />}
              />
            </div>
          </div>
        );
    }
  };

  return (
    <div className="container max-w-4xl mx-auto mt-10 mb-16">
      <button
        onClick={onBack}
        className="mb-6 flex items-center gap-2 text-white/70 hover:text-white text-lg"
      >
        <FaArrowLeft /> Back to servers
      </button>
      <div className="rounded-2xl bg-white/5 border border-white/10 shadow-card p-4 min-h-[700px] md:min-h-[900px] flex flex-col">
        <div className="p-8 flex-1 flex flex-col">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-6">
              <div className="w-16 h-16 rounded-md bg-brand-500 inline-flex items-center justify-center text-3xl">
                <FaServer />
              </div>
              <div>
                <div className="font-bold text-2xl">{server.name}</div>
                <div className="text-sm text-white/60">
                  {server.id.slice(0, 12)}
                </div>
                <div className="text-xs text-white/50 mt-1">
                  Type: {displayType || <span className="text-white/40">Unknown</span>} | Version: {displayVersion || <span className="text-white/40">Unknown</span>}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div
                className={`text-sm px-3 py-1.5 rounded-full border ${
                  server.status === 'running'
                    ? 'bg-green-500/10 text-green-300 border-green-400/20'
                    : 'bg-gray-500/10 text-gray-300 border-gray-400/20'
                }`}
              >
                {server.status}
              </div>
              {server.status !== 'running' ? (
                <button
                  onClick={() => onStart(server.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-green-600 hover:bg-green-500 px-3 py-1.5 text-sm font-medium transition-colors"
                >
                  <FaPlay className="w-3 h-3" /> Start
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onStop(server.id)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-yellow-600 hover:bg-yellow-500 px-3 py-1.5 text-sm font-medium transition-colors"
                  >
                    <FaStop className="w-3 h-3" /> Stop
                  </button>
                  <button
                    onClick={() => onRestart(server.id)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 px-3 py-1.5 text-sm font-medium transition-colors"
                  >
                    <FaSync className="w-3 h-3" /> Restart
                  </button>
                </div>
              )}
            </div>
          </div>
          <div className="mt-8">
            <div className="flex gap-3 md:gap-4 border-b border-white/10 overflow-x-auto pb-2 md:pb-0">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 md:gap-3 px-4 py-3 md:px-6 md:py-4 text-base md:text-lg rounded-t-lg transition whitespace-nowrap ${
                    activeTab === tab.id
                      ? 'bg-brand-500 text-white'
                      : 'text-white/70 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <tab.icon />
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="mt-4 flex flex-col md:flex-row gap-6">
              {renderTabContent()}
            </div>
          </div>
          {activeTab !== 'files' && (
            <div className="mt-8">
              <TerminalPanel containerId={server.id} resetToken={logReset} />
            </div>
          )}
          {/* Minimal actions - only destructive action at bottom */}
          <div className="flex justify-end mt-8 pt-6 border-t border-white/10">
            <button
              onClick={() => onDelete(server.id)}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600/80 hover:bg-red-500 px-3 py-1.5 text-xs font-medium transition-colors text-red-100"
            >
              <FaTrash className="w-3 h-3" /> Delete Server
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Enhance ServerListCard with live stats - INSTANT with preloaded data
const ServerListCard = React.memo(function ServerListCard({ server, onClick }) {
  // Get preloaded server stats instantly
  const globalData = useGlobalData();
  const stats = globalData.serverStats[server.id] || null;
  
  // Still get type/version data since it's less frequently used
  const { data: typeVersionData } = useFetch(
    server?.id ? `${API}/servers/${server.id}/info` : null,
    [server?.id],
    { cacheDuration: 60000 } // Cache for 1 minute since this rarely changes
  );

  const normalizeLabel = useCallback((value) => {
    if (!value) return '';
    return value
      .toString()
      .split(/[-_\s]+/)
      .filter(Boolean)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }, []);

  const runtimeKind = (typeVersionData?.server_kind || server.server_kind || '').toLowerCase();
  const isSteam = runtimeKind === 'steam';
  const steamGame = typeVersionData?.steam_game || server.steam_game;
  const displayKind = isSteam
    ? `Steam · ${normalizeLabel(steamGame || server.type || 'Dedicated')}`
    : normalizeLabel(server.type || typeVersionData?.server_type || 'Minecraft');
  const primaryHostPort = typeVersionData?.primary_host_port
    ?? server.primary_host_port
    ?? server.host_port;
  const dataPath = typeVersionData?.data_path || server.data_path;
  
  // Predictive preloading on hover
  const handleMouseEnter = useCallback(() => {
    // Preload detailed server info when user hovers
    if (server?.id) {
      fetch(`${API}/servers/${server.id}/info`, { headers: authHeaders() })
        .catch(() => {}); // Silent fail for predictive loading
    }
  }, [server?.id]);

  return (
    <div
      className="rounded-xl bg-gradient-to-b from-white/10 to-white/5 border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)] p-5 md:p-6 transition-all duration-200 hover:from-white/15 hover:to-white/10"
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      tabIndex={0}
      role="button"
      style={{ minHeight: 100 }}
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4 md:gap-5">
          <div className="w-12 h-12 rounded-lg bg-brand-500/90 ring-4 ring-brand-500/20 inline-flex items-center justify-center text-2xl text-white shadow-md flex-shrink-0">
            <FaServer />
          </div>
          <div>
            <div className="font-bold text-lg md:text-xl leading-tight">{server.name}</div>
            <div className="text-xs md:text-sm text-white/60 break-all">{server.id.slice(0, 12)}</div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] md:text-xs text-white/60 mt-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/10 border border-white/15">
                {displayKind || <span className="text-white/40">Unknown</span>}
              </span>
              <span>
                Version: {typeVersionData?.server_version || server.version || <span className="text-white/40">Unknown</span>}
              </span>
              {primaryHostPort ? (
                <span>Port: {primaryHostPort}</span>
              ) : null}
            </div>
            {dataPath ? (
              <div className="text-[10px] text-white/40 mt-1 break-all">{dataPath}</div>
            ) : null}
            {stats && !stats.error && (
              <div className="flex flex-wrap items-center gap-2 mt-2 text-[11px] text-white/80">
                <span className="rounded-full bg-white/10 px-2 py-0.5 shadow-inner">CPU {stats.cpu_percent}%</span>
                <span className="rounded-full bg-white/10 px-2 py-0.5 shadow-inner">RAM {stats.memory_usage_mb}/{stats.memory_limit_mb} MB</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 md:self-start">
          <div
            className={`text-xs md:text-sm px-3 py-1.5 rounded-full border ${
              server.status === 'running'
                ? 'bg-green-500/15 text-green-300 border-green-400/20'
                : 'bg-yellow-500/15 text-yellow-300 border-yellow-400/20'
            }`}
          >
            {server.status}
          </div>
          <FaChevronRight className="text-white/40 text-lg md:text-xl" />
        </div>
      </div>
    </div>
  );
});

// Loading component for Suspense
function PageLoadingSpinner() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="text-white/70 flex items-center gap-2">
        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-brand-500"></div>
        Loading...
      </div>
    </div>
  );
}

// Compact Error Boundary: logs errors and shows a simple fallback message.
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error caught by ErrorBoundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6">
          <div className="text-red-300">An unexpected error occurred. The app captured the error and logged it to the console.</div>
        </div>
      );
    }
    return this.props.children;
  }
}

function AdvancedUserManagementPageImpl() {
  // Local/global data and UI state for Advanced User Management
  const globalData = useGlobalData();
  const safeUsers = Array.isArray(globalData.users) ? globalData.users : [];
  const safeRoles = Array.isArray(globalData.roles) ? globalData.roles : [];
  const safeAuditLogs = Array.isArray(globalData.auditLogs) ? globalData.auditLogs : [];

  const [searchTerm, setSearchTerm] = useState('');
  const [filterRole, setFilterRole] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [selectedUser, setSelectedUser] = useState(null);
  const [selectedRole, setSelectedRole] = useState(null);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [activeTab, setActiveTab] = useState('users');
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', confirmPassword: '', role: 'user', fullName: '', mustChangePassword: true, autoPassword: true });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Function to refresh user data
  const loadUsers = async () => {
    try {
      // Refresh global users, roles and audit logs without full reload
      const refresher = globalData.__refreshBG;
      if (refresher) {
        refresher('users', `${API}/users`, (d) => d.users || []);
        refresher('roles', `${API}/users/roles`, (d) => d.roles || []);
        refresher('auditLogs', `${API}/users/audit-logs?page=1&page_size=50`, (d) => d.logs || []);
      }
    } catch (error) {
      console.error('Failed to refresh users data:', error);
    }
  };
  
  // Permissions UI removed per request; roles remain view-only.

  function generatePassword(len = 16) {
    const upper = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const lower = 'abcdefghijklmnopqrstuvwxyz';
    const digits = '0123456789';
    const all = upper + lower + digits;
    let out = '';
    // Ensure at least one of each
    out += upper[Math.floor(Math.random() * upper.length)];
    out += lower[Math.floor(Math.random() * lower.length)];
    out += digits[Math.floor(Math.random() * digits.length)];
    for (let i = 3; i < len; i++) {
      out += all[Math.floor(Math.random() * all.length)];
    }
    return out.split('').sort(() => Math.random() - 0.5).join('');
  }

  async function createUser() {
    try {
      if (!newUser.username.trim() || !newUser.email.trim()) {
        setError('Username and email are required');
        return;
      }
      let tempPassword = newUser.password;
      if (newUser.autoPassword) {
        tempPassword = 'admin123';
      } else {
        if (!newUser.password) {
          setError('Password is required or enable auto-generate');
          return;
        }
        if (newUser.password !== newUser.confirmPassword) {
          setError('Passwords do not match');
          return;
        }
      }
      
      const resp = await fetch(`${API}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: newUser.username,
          email: newUser.email,
          password: tempPassword,
          role: newUser.role,
          full_name: newUser.fullName,
          must_change_password: newUser.mustChangePassword
        }),
      });
      if (!resp.ok) {
        const payload = await resp.json().catch(() => ({}));
        const detail = payload?.detail || payload?.message || `HTTP ${resp.status}`;
        throw new Error(detail);
      }
      setShowCreateUser(false);
      setNewUser({ 
        username: '', email: '', password: '', confirmPassword: '',
        role: 'user', fullName: '', mustChangePassword: true, autoPassword: true
      });
      setSuccess(`User created successfully. Temporary password: ${tempPassword}`);
      loadUsers();
    } catch (e) {
      setError('Failed to create user: ' + e.message);
      console.error('Failed to create user:', e);
    }
  }
  

  // Filtered users based on search and filters
  const filteredUsers = safeUsers.filter(user => {
    const matchesSearch = user.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         user.email?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRole = filterRole === 'all' || user.role === filterRole;
    const matchesStatus = filterStatus === 'all' || 
                         (filterStatus === 'active' && user.is_active) ||
                         (filterStatus === 'inactive' && !user.is_active);
    return matchesSearch && matchesRole && matchesStatus;
  });

  // Helper functions for user actions
  async function updateUserRole(userId, newRole) {
    try {
      await fetch(`${API}/users/${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      });
      setSuccess('User role updated successfully');
      loadUsers();
    } catch (e) {
      setError('Failed to update user role: ' + e.message);
    }
  }

  async function toggleUserActive(userId, isActive) {
    try {
      await fetch(`${API}/users/${userId}`, {
        method: 'PUT', 
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive }),
      });
      setSuccess(`User ${isActive ? 'activated' : 'deactivated'} successfully`);
      loadUsers();
    } catch (e) {
      setError('Failed to update user status: ' + e.message);
    }
  }

  async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) return;
    try {
      await fetch(`${API}/users/${userId}`, { method: 'DELETE' });
      setSuccess('User deleted successfully');
      loadUsers();
    } catch (e) {
      setError('Failed to delete user: ' + e.message);
    }
  }

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      {/* Header with tabs */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaShieldAlt className="text-brand-500" /> <span className="gradient-text-brand">Advanced User Management</span>
          </h1>
          <p className="text-white/70 mt-2">Comprehensive user, role, and permission management system</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowCreateUser(true)}
            className="bg-brand-500 hover:bg-brand-600 px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <FaPlus /> Create User
          </button>
        </div>
      </div>

      {/* Success/Error Messages */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-4 rounded-lg flex items-center gap-3">
          <FaExclamationTriangle />
          <span>{error}</span>
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-300">
            <FaTimes />
          </button>
        </div>
      )}
      
      {success && (
        <div className="bg-green-500/10 border border-green-500/20 text-green-300 p-4 rounded-lg flex items-center gap-3">
          <FaCheckCircle />
          <span>{success}</span>
          <button onClick={() => setSuccess('')} className="ml-auto text-green-400 hover:text-green-300">
            <FaTimes />
          </button>
        </div>
      )}

      {/* Create User Modal */}
      {showCreateUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur" onClick={() => setShowCreateUser(false)} />
          <div className="relative w-full max-w-2xl bg-ink border border-white/10 rounded-2xl shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm uppercase tracking-wide text-white/50">Create User</div>
                <div className="text-2xl font-semibold text-white">Invite a new teammate</div>
              </div>
              <button
                onClick={() => setShowCreateUser(false)}
                className="p-2 rounded-full bg-white/10 hover:bg-white/20 text-white/70"
                aria-label="Close create user modal"
              >
                <FaTimes />
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-white/60 block mb-1">Username</label>
                <input
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  placeholder="minecraft_admin"
                />
              </div>
              <div>
                <label className="text-xs text-white/60 block mb-1">Email</label>
                <input
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500"
                  type="email"
                  value={newUser.email}
                  onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                  placeholder="user@example.com"
                />
              </div>
              <div>
                <label className="text-xs text-white/60 block mb-1">Role</label>
                <select
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500"
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                >
                  {safeRoles.map((role) => (
                    <option key={role.name} value={role.name}>{role.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-white/60 block mb-1">Full Name (optional)</label>
                <input
                  className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500"
                  value={newUser.fullName}
                  onChange={(e) => setNewUser({ ...newUser, fullName: e.target.value })}
                  placeholder="Alex Smith"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs text-white/60 block">Password</label>
                <div className="flex items-center gap-2">
                  <input
                    className="flex-1 rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500 disabled:opacity-40"
                    type="password"
                    value={newUser.password}
                    onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                    placeholder={newUser.autoPassword ? 'Auto-generate secure password' : 'Enter a strong password'}
                    disabled={newUser.autoPassword}
                  />
                  <label className="flex items-center gap-2 text-sm text-white/80">
                    <input
                      type="checkbox"
                      checked={newUser.autoPassword}
                      onChange={(e) => setNewUser({ ...newUser, autoPassword: e.target.checked })}
                    />
                    Auto-generate
                  </label>
                </div>
                {!newUser.autoPassword && (
                  <input
                    className="w-full rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-white focus:ring-2 focus:ring-brand-500"
                    type="password"
                    value={newUser.confirmPassword}
                    onChange={(e) => setNewUser({ ...newUser, confirmPassword: e.target.value })}
                    placeholder="Confirm password"
                  />
                )}
              </div>
              <div className="space-y-2">
                <label className="text-xs text-white/60 block">Onboarding</label>
                <div className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2 text-sm text-white/80">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={newUser.mustChangePassword}
                      onChange={(e) => setNewUser({ ...newUser, mustChangePassword: e.target.checked })}
                    />
                    Require password change on first login
                  </label>
                  <p className="text-xs text-white/50">A one-time password is shown after creation.</p>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <div className="text-xs text-white/50">Passwords must include upper, lower, and a digit.</div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowCreateUser(false)}
                  className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white/80"
                  type="button"
                >
                  Cancel
                </button>
                <button
                  onClick={createUser}
                  className="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white shadow-lg"
                  type="button"
                >
                  Create User
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-1 flex">
        <button
          onClick={() => setActiveTab('users')}
          className={`flex-1 px-4 py-2 rounded-md flex items-center justify-center gap-2 transition-all ${
            activeTab === 'users' 
              ? 'bg-brand-500 text-white' 
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
        >
          <FaUsers /> Users ({safeUsers.length})
        </button>
        <button
          onClick={() => setActiveTab('roles')}
          className={`flex-1 px-4 py-2 rounded-md flex items-center justify-center gap-2 transition-all ${
            activeTab === 'roles' 
              ? 'bg-brand-500 text-white' 
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
        >
          <FaShieldAlt /> Roles ({safeRoles.length})
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`flex-1 px-4 py-2 rounded-md flex items-center justify-center gap-2 transition-all ${
            activeTab === 'audit' 
              ? 'bg-brand-500 text-white' 
              : 'text-white/70 hover:text-white hover:bg-white/10'
          }`}
        >
          <FaHistory /> Audit Logs ({safeAuditLogs.length})
        </button>
      </div>

      {/* Content based on active tab */}
      {activeTab === 'users' && (
        <UsersTab 
          users={filteredUsers}
          roles={safeRoles}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          filterRole={filterRole}
          setFilterRole={setFilterRole}
          filterStatus={filterStatus}
          setFilterStatus={setFilterStatus}
          updateUserRole={updateUserRole}
          toggleUserActive={toggleUserActive}
          deleteUser={deleteUser}
          setSelectedUser={setSelectedUser}
        />
      )}
      
      {activeTab === 'roles' && (
        <RolesTab 
          roles={safeRoles}
          setSelectedRole={setSelectedRole}
        />
      )}

      {selectedRole && (
        <RoleDetailsModal 
          role={selectedRole}
          onClose={() => setSelectedRole(null)}
        />
      )}
      
      {activeTab === 'audit' && (
        <AuditTab auditLogs={safeAuditLogs} />
      )}

      {/* Local server pack imports live on the Templates page. */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-4">
        <div className="text-sm text-white/70">Want to import a local server pack? Use the Templates & Modpacks page to upload ZIPs.</div>
        <div className="mt-3">
          <button onClick={() => window.location.hash = '#/templates'} className="px-3 py-1 rounded bg-brand-500">Go to Templates</button>
        </div>
      </div>

      {/* Monitoring-related UI (system health, alerts and server overview) moved to Server Status (Monitoring) to avoid duplication */}
    </div>
  );
}


// System Settings Page - renamed to avoid conflicts
function SettingsPageImpl() {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [curseforgeKey, setCurseforgeKey] = useState('');
  const [providersStatus, setProvidersStatus] = useState({ curseforge: { configured: false } });
  const [backupSettings, setBackupSettings] = useState({
    auto_backup: true,
    backup_interval: 24,
    keep_backups: 7,
    backup_location: '/data/backups'
  });
  const [notificationSettings, setNotificationSettings] = useState({
    email_enabled: false,
    email_smtp_host: '',
    email_smtp_port: 587,
    email_username: '',
    email_password: '',
    webhook_url: '',
    alert_on_server_crash: true,
    alert_on_high_cpu: true,
    alert_on_high_memory: true
  });
  // Sessions state
  const [sessions, setSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState('');

  useEffect(() => {
    loadSettings();
    loadIntegrations();
    loadSessions();
  }, []);

  async function loadSettings() {
    try {
      // This would load from backend settings API
      setLoading(false);
    } catch (e) {
      console.error('Failed to load settings:', e);
      setLoading(false);
    }
  }

  async function saveSettings() {
    setSaving(true);
    try {
      // This would save to backend settings API
      await new Promise(resolve => setTimeout(resolve, 1000)); // Simulate API call
      alert('Settings saved successfully!');
    } catch (e) {
      console.error('Failed to save settings:', e);
      alert('Failed to save settings');
    }
    setSaving(false);
  }

  async function loadIntegrations() {
    try {
      const r = await fetch(`${API}/integrations/status`);
      const d = await r.json();
      setProvidersStatus(d || { curseforge: { configured: false } });
    } catch {}
  }

  async function saveCurseforgeKey() {
    try {
      const r = await fetch(`${API}/integrations/curseforge-key`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ api_key: curseforgeKey }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) {
        const msg = d?.detail || `HTTP ${r.status}`;
        alert('Failed to save key: ' + msg);
        return;
      }
      // Refresh integration status
      await loadIntegrations();
      // Run a live test using the saved key and show diagnostic info
      try {
        const tr = await fetch(`${API}/integrations/curseforge-test`, { headers: authHeaders() });
        const td = await tr.json().catch(() => ({}));
        if (!tr.ok) {
          alert('Key saved but test failed: ' + (td?.detail || JSON.stringify(td)));
        } else {
          alert('CurseForge API key saved. Test result: ' + JSON.stringify(td));
        }
      } catch (e) {
        alert('CurseForge key saved but test request failed: ' + (e?.message || e));
      }
    } catch (e) {
      alert('Failed to save key: ' + (e?.message || e));
    }
  }

  async function loadSessions() {
    try {
      setSessionsLoading(true);
      setSessionsError('');
      const r = await fetch(`${API}/auth/sessions`);
      if (!r.ok) throw new Error(`Failed to load sessions (HTTP ${r.status})`);
      const data = await r.json();
      setSessions(Array.isArray(data) ? data : []);
    } catch (e) {
      setSessionsError(e.message || 'Failed to load sessions');
    } finally {
      setSessionsLoading(false);
    }
  }

  async function revokeSession(id) {
    try {
      const r = await fetch(`${API}/auth/sessions/${id}`, { method: 'DELETE' });
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}));
        throw new Error(payload.detail || `Failed to revoke session (HTTP ${r.status})`);
      }
      setSessions((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      alert(e.message || 'Failed to revoke session');
    }
  }

  if (loading) return <div className="p-6"><div className="text-white/70">Loading settings...</div></div>;

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaCog className="text-brand-500" /> <span className="gradient-text-brand">System Settings</span>
          </h1>
          <p className="text-white/70 mt-2">Configure system preferences and integrations</p>
        </div>
        <button
          onClick={saveSettings}
          disabled={saving}
          className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 rounded-lg flex items-center gap-2"
        >
          <FaSave /> {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      {/* Backup Settings */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaDatabase /> Backup Settings
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="auto_backup"
                checked={backupSettings.auto_backup}
                onChange={(e) => setBackupSettings({...backupSettings, auto_backup: e.target.checked})}
                className="w-4 h-4 text-brand-500 bg-white/10 border-white/20 rounded focus:ring-brand-500"
              />
              <label htmlFor="auto_backup" className="text-white/80">Enable automatic backups</label>
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Backup Interval (hours)</label>
              <input
                type="number"
                value={backupSettings.backup_interval}
                onChange={(e) => setBackupSettings({...backupSettings, backup_interval: parseInt(e.target.value)})}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              />
            </div>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Keep Backups (days)</label>
              <input
                type="number"
                value={backupSettings.keep_backups}
                onChange={(e) => setBackupSettings({...backupSettings, keep_backups: parseInt(e.target.value)})}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Backup Location</label>
              <input
                type="text"
                value={backupSettings.backup_location}
                onChange={(e) => setBackupSettings({...backupSettings, backup_location: e.target.value})}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Integrations */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Integrations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-white/70 mb-1">CurseForge API Key</div>
            <div className="flex gap-2">
              <input type="password" className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white" value={curseforgeKey} onChange={(e)=>setCurseforgeKey(e.target.value)} placeholder={providersStatus?.curseforge?.configured ? 'configured' : 'not configured'} />
              <button onClick={saveCurseforgeKey} className="bg-brand-500 hover:bg-brand-600 px-3 py-2 rounded">Save</button>
            </div>
            <div className="text-xs text-white/50 mt-1">Required to search/install from CurseForge catalog.</div>
          </div>
        </div>
      </div>

      {/* Notification Settings */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaBell /> Notification Settings
        </h3>
        <div className="space-y-6">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="email_enabled"
              checked={notificationSettings.email_enabled}
              onChange={(e) => setNotificationSettings({...notificationSettings, email_enabled: e.target.checked})}
              className="w-4 h-4 text-brand-500 bg-white/10 border-white/20 rounded focus:ring-brand-500"
            />
            <label htmlFor="email_enabled" className="text-white/80">Enable email notifications</label>
          </div>
          
          {notificationSettings.email_enabled && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 ml-7">
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">SMTP Host</label>
                <input
                  type="text"
                  value={notificationSettings.email_smtp_host}
                  onChange={(e) => setNotificationSettings({...notificationSettings, email_smtp_host: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  placeholder="smtp.gmail.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">SMTP Port</label>
                <input
                  type="number"
                  value={notificationSettings.email_smtp_port}
                  onChange={(e) => setNotificationSettings({...notificationSettings, email_smtp_port: parseInt(e.target.value)})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Email Username</label>
                <input
                  type="text"
                  value={notificationSettings.email_username}
                  onChange={(e) => setNotificationSettings({...notificationSettings, email_username: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Email Password</label>
                <input
                  type="password"
                  value={notificationSettings.email_password}
                  onChange={(e) => setNotificationSettings({...notificationSettings, email_password: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                />
              </div>
            </div>
          )}
          
          <div>
            <label className="block text-sm font-medium text-white/70 mb-2">Webhook URL</label>
            <input
              type="url"
              value={notificationSettings.webhook_url}
              onChange={(e) => setNotificationSettings({...notificationSettings, webhook_url: e.target.value})}
              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              placeholder="https://hooks.slack.com/services/..."
            />
          </div>
          
          <div className="space-y-3">
            <h4 className="font-medium text-white/80">Alert Types</h4>
            <div className="space-y-2">
              {[
                { key: 'alert_on_server_crash', label: 'Server crashes' },
                { key: 'alert_on_high_cpu', label: 'High CPU usage' },
                { key: 'alert_on_high_memory', label: 'High memory usage' }
              ].map(alert => (
                <div key={alert.key} className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id={alert.key}
                    checked={notificationSettings[alert.key]}
                    onChange={(e) => setNotificationSettings({...notificationSettings, [alert.key]: e.target.checked})}
                    className="w-4 h-4 text-brand-500 bg-white/10 border-white/20 rounded focus:ring-brand-500"
                  />
                  <label htmlFor={alert.key} className="text-white/70">{alert.label}</label>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Active Sessions */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2"><FaShieldAlt className="text-brand-500" /> Active Sessions</h3>
          <button
            onClick={loadSessions}
            className="bg-white/10 hover:bg-white/20 px-3 py-1.5 rounded border border-white/10 text-white/80 text-sm"
          >
            Refresh
          </button>
        </div>
        {sessionsLoading && <div className="text-white/60">Loading sessions...</div>}
        {sessionsError && <div className="text-red-300 text-sm mb-2">{sessionsError}</div>}
        {!sessionsLoading && !sessionsError && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-white/70">
                  <th className="px-3 py-2">IP Address</th>
                  <th className="px-3 py-2">User Agent</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Expires</th>
                  <th className="px-3 py-2">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {sessions.length === 0 && (
                  <tr>
                    <td className="px-3 py-3 text-white/60" colSpan={5}>No active sessions</td>
                  </tr>
                )}
                {sessions.map((s) => {
                  const created = s.created_at ? new Date(s.created_at) : null;
                  const expires = s.expires_at ? new Date(s.expires_at) : null;
                  return (
                    <tr key={s.id} className="text-white/80">
                      <td className="px-3 py-2">{s.ip_address || '—'}</td>
                      <td className="px-3 py-2 max-w-[32rem] truncate" title={s.user_agent || ''}>{s.user_agent || '—'}</td>
                      <td className="px-3 py-2">{created ? created.toLocaleString() : '—'}</td>
                      <td className="px-3 py-2">{expires ? expires.toLocaleString() : '—'}</td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => revokeSession(s.id)}
                          className="px-2 py-1 rounded bg-red-600/80 hover:bg-red-600 text-white text-xs border border-white/10"
                        >
                          Revoke
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// Modern Dashboard Page - ZERO LOADING with preloaded global data
const DashboardPage = React.memo(function DashboardPage({ onNavigate }) {
  // Get all data instantly from global store - NO LOADING!
  const globalData = useGlobalData();
  const gd = globalData;
  const { 
    servers, 
    serverStats,
    dashboardData, 
    systemHealth, 
    alerts, 
    isInitialized 
  } = globalData;

  // No loading states needed - data is always available!

  // Featured Modpacks (search)
  const [featured, setFeatured] = useState([]);
  const [featuredError, setFeaturedError] = useState('');

  // Lightweight install modal state (replaces removed Templates page flow)
  const [installOpen, setInstallOpen] = useState(false);
  const [installPack, setInstallPack] = useState(null);
  const [installProvider, setInstallProvider] = useState('modrinth');
  const [installVersions, setInstallVersions] = useState([]);
  const [installVersionId, setInstallVersionId] = useState('');
  const [installEvents, setInstallEvents] = useState([]);
  const [installWorking, setInstallWorking] = useState(false);
  const [serverName, setServerName] = useState('mp-' + Math.random().toString(36).slice(2,6));
  const [hostPort, setHostPort] = useState('');
  const [minRam, setMinRam] = useState('2048M');
  const [maxRam, setMaxRam] = useState('4096M');
  useEffect(() => {
    let cancelled = false;
    async function loadFeatured(){
      try {
  const r = await fetch(`${API}/catalog/search?provider=all&page_size=6`);
        const d = await r.json();
        if (!cancelled) setFeatured(Array.isArray(d?.results) ? d.results : []);
      } catch(e){ if (!cancelled) setFeaturedError(String(e.message||e)); }
    }
    loadFeatured();
    return () => { cancelled = true; };
  }, []);

  async function openInstallFromFeatured(pack) {
    setInstallPack(pack);
    setInstallOpen(true);
    setInstallEvents([]);
    setInstallWorking(false);
    try {
      const srcProvider = pack.provider || 'modrinth';
      setInstallProvider(srcProvider);
      const packId = encodeURIComponent(pack.id || pack.slug || '');
      const r = await fetch(`${API}/catalog/${srcProvider}/packs/${packId}/versions`, { headers: authHeaders() });
      const d = await r.json().catch(() => ({}));
      const vers = Array.isArray(d?.versions) ? d.versions : [];
      setInstallVersions(vers);
      setInstallVersionId(vers[0]?.id || '');
    } catch {
      setInstallVersions([]);
      setInstallVersionId('');
    }
  }

  async function submitInstall() {
    if (!installPack) return;
    if (!serverName || !String(serverName).trim()) {
      setInstallEvents((prev) => [...prev, { type: 'error', message: 'Server name is required' }]);
      return;
    }
    // Normalize RAM inputs to backend-expected format (e.g., 2048M)
    const normMin = normalizeRamInput(minRam);
    const normMax = normalizeRamInput(maxRam);
    if (!normMin || !normMax) {
      setInstallEvents((prev) => [...prev, { type: 'error', message: 'Please enter valid RAM values (examples: 2048M, 2G, or raw MB like 2048).' }]);
      return;
    }
    setInstallWorking(true);
    setInstallEvents([{ type: 'progress', message: 'Submitting install task...' }]);
    try {
      const body = {
        provider: installProvider,
        pack_id: String(installPack.id || installPack.slug || ''),
        version_id: installVersionId ? String(installVersionId) : null,
        name: String(serverName).trim(),
        host_port: hostPort ? Number(hostPort) : null,
        min_ram: normMin,
        max_ram: normMax,
      };
      const r = await fetch(`${API}/modpacks/install`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body)
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      const taskId = d?.task_id;
      if (!taskId) throw new Error('No task id');
      const es = new EventSource(`${API}/modpacks/install/events/${taskId}`);
      es.onmessage = (ev) => {
        try {
          const evd = JSON.parse(ev.data);
          setInstallEvents((prev) => {
            const next = [...prev, evd];
            return next.length > 500 ? next.slice(-500) : next;
          });
          if (evd.type === 'done' || evd.type === 'error') {
            try { es.close(); } catch {}
            setInstallWorking(false);
            // Ensure the servers list is refreshed when install finishes
            if (gd && gd.__refreshServers) {
              gd.__refreshServers();
              // schedule a couple of follow-up refreshes in case the backend finalizes after a short delay
              setTimeout(() => gd.__refreshServers && gd.__refreshServers(), 1000);
              setTimeout(() => gd.__refreshServers && gd.__refreshServers(), 3000);
            }
          }
        } catch {}
      };
      es.onerror = () => { try { es.close(); } catch {} setInstallWorking(false); };
    } catch (e) {
      setInstallEvents((prev) => [...prev, { type: 'error', message: String(e.message || e) }]);
      setInstallWorking(false);
    }
  }

  // Calculate real-time metrics - INSTANT calculation from preloaded data
  const { totalServers, runningServers, totalMemoryMB, avgCpuPercent, criticalAlerts, warningAlerts } = useMemo(() => {
    const total = servers?.length || 0;
    const runningList = Array.isArray(servers) ? servers.filter(s => s?.status === 'running') : [];
    const running = runningList.length || 0;

    // Backend monitoring endpoints provide health as { cpu_usage_percent, used_memory_gb, ... }
    const health = (systemHealth && typeof systemHealth === 'object')
      ? systemHealth
      : (dashboardData && typeof dashboardData === 'object' ? dashboardData.health : null);

    let cpuPercent = 0;
    let memoryMB = 0;

    if (health && typeof health.cpu_usage_percent === 'number') {
      cpuPercent = health.cpu_usage_percent;
    }
    if (health && typeof health.used_memory_gb === 'number') {
      memoryMB = health.used_memory_gb * 1024;
    }

    // Fallback: derive from per-server stats if health isn't available.
    if ((!cpuPercent || !memoryMB) && serverStats && typeof serverStats === 'object') {
      let cpuSum = 0;
      let cpuCount = 0;
      let memSumMB = 0;
      runningList.forEach((s) => {
        const id = s?.id;
        if (!id) return;
        const st = serverStats[id];
        if (st && typeof st.cpu_percent === 'number') {
          cpuSum += st.cpu_percent;
          cpuCount += 1;
        }
        if (st && typeof st.memory_usage_mb === 'number') {
          memSumMB += st.memory_usage_mb;
        }
      });
      if (!cpuPercent && cpuCount > 0) {
        cpuPercent = cpuSum / cpuCount;
      }
      if (!memoryMB && memSumMB > 0) {
        memoryMB = memSumMB;
      }
    }

    if (!Number.isFinite(cpuPercent)) cpuPercent = 0;
    if (!Number.isFinite(memoryMB)) memoryMB = 0;
    const critical = alerts?.filter(a => a.type === 'critical' && !a.acknowledged).length || 0;
    const warning = alerts?.filter(a => a.type === 'warning' && !a.acknowledged).length || 0;
    
    return {
      totalServers: total,
      runningServers: running,
      totalMemoryMB: memoryMB,
      avgCpuPercent: cpuPercent,
      criticalAlerts: critical,
      warningAlerts: warning
    };
  }, [servers, serverStats, dashboardData, systemHealth, alerts]);
  
  return (
    <div className="min-h-screen bg-transparent">
      {/* Clean Linear-inspired header */}
      <div className="border-b border-white/10 bg-ink/80 backdrop-blur supports-[backdrop-filter]:bg-ink/60">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-semibold gradient-text-brand mb-1">Overview</h1>
              <p className="text-sm text-white/60">Monitor your Minecraft infrastructure</p>
            </div>
            
            {(criticalAlerts > 0 || warningAlerts > 0) && (
              <div className="flex items-center gap-2">
                {criticalAlerts > 0 && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-red-900/20 text-red-300 rounded text-sm">
                    <div className="w-2 h-2 bg-red-400 rounded-full" />
                    {criticalAlerts}
                  </div>
                )}
                {warningAlerts > 0 && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-yellow-900/20 text-yellow-300 rounded text-sm">
                    <div className="w-2 h-2 bg-yellow-400 rounded-full" />
                    {warningAlerts}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8 animate-fade-in">

        {/* Simplified Stats */}
        <div className="grid grid-cols-4 gap-6">
          <div className="glassmorphism rounded-xl p-5">
            <div className="text-sm text-white/60 mb-1">Servers</div>
            <div className="flex items-baseline gap-2">
              <div className="text-2xl font-medium text-white">
                {runningServers}
              </div>
              <div className="text-sm text-white/40">/ {totalServers}</div>
            </div>
          </div>
          
          <div className="glassmorphism rounded-xl p-5">
            <div className="text-sm text-white/60 mb-1">CPU</div>
            <div className="text-2xl font-medium text-white">
              {`${avgCpuPercent.toFixed(0)}%`}
            </div>
          </div>
          
          <div className="glassmorphism rounded-xl p-5">
            <div className="text-sm text-white/60 mb-1">Memory</div>
            <div className="text-2xl font-medium text-white">
              {`${(totalMemoryMB / 1024).toFixed(1)}GB`}
            </div>
          </div>
          
          <div className="glassmorphism rounded-xl p-5">
            <div className="text-sm text-white/60 mb-1">Issues</div>
            <div className="text-2xl font-medium text-white">
              {criticalAlerts + warningAlerts}
            </div>
          </div>
        </div>

        {/* Featured Modpacks */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-white">Featured Modpacks</h2>
            {featuredError && <div className="text-sm text-red-400">{featuredError}</div>}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-3 gap-4">
            {featured.map((p, idx) => (
              <div key={p.id || p.slug || idx} className="glassmorphism rounded-xl p-4 hover:bg-white/10 transition-colors">
                <div className="flex items-center gap-3 mb-2">
                  {p.icon_url ? <img src={p.icon_url} alt="" className="w-8 h-8 rounded"/> : <div className="w-8 h-8 bg-white/10 rounded"/>}
                  <div>
                    <div className="text-white font-medium truncate max-w-[220px]" title={p.name}>{p.name}</div>
                    <div className="text-xs text-white/60">Modrinth • {typeof p.downloads==='number'?`⬇ ${Intl.NumberFormat().format(p.downloads)}`:''}</div>
                  </div>
                </div>
                <div className="text-sm text-white/60 line-clamp-2 min-h-[38px]">{p.description}</div>
                <div className="mt-3">
                  <button onClick={()=> openInstallFromFeatured(p)} className="text-sm text-brand-400 hover:text-brand-300">Install</button>
                </div>
              </div>
            ))}
            {featured.length === 0 && (
              <div className="text-white/60">No featured packs available.</div>
            )}
          </div>
        </div>

        {/* Install Wizard Modal */}
        {installOpen && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-ink border border-white/10 rounded-lg p-6 w-full max-w-2xl">
              <div className="flex items-center justify-between mb-4">
                <div className="text-lg font-semibold">Install Modpack{installPack?.name ? `: ${installPack.name}` : ''}</div>
                <button onClick={() => { setInstallOpen(false); setInstallPack(null); }} className="text-white/60 hover:text-white">Close</button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
                <div>
                  <label className="block text-xs text-white/60 mb-1">Version</label>
                  <select className="w-full rounded bg-white/10 border border-white/20 px-3 py-2 text-white" value={installVersionId} onChange={e=>setInstallVersionId(e.target.value)} style={{ backgroundColor: '#1f2937' }}>
                    {installVersions.map(v => <option key={v.id} value={v.id} style={{ backgroundColor: '#1f2937' }}>{v.name || v.version_number}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-white/60 mb-1">Server Name</label>
                  <input className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" value={serverName} onChange={e=>setServerName(e.target.value)} />
                </div>
                <div>
                  <label className="block text-xs text-white/60 mb-1">Host Port (optional)</label>
                  <input className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" value={hostPort} onChange={e=>setHostPort(e.target.value)} placeholder="25565" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-white/60 mb-1">Min RAM</label>
                    <input className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" value={minRam} onChange={e=>setMinRam(e.target.value)} onBlur={()=>{ const v = normalizeRamInput(minRam); if (v) setMinRam(v); }} />
                    <div className="text-[11px] text-white/50 mt-1">Accepts 2048M, 2G, or raw MB.</div>
                  </div>
                  <div>
                    <label className="block text-xs text-white/60 mb-1">Max RAM</label>
                    <input className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" value={maxRam} onChange={e=>setMaxRam(e.target.value)} onBlur={()=>{ const v = normalizeRamInput(maxRam); if (v) setMaxRam(v); }} />
                    <div className="text-[11px] text-white/50 mt-1">Accepts 4096M, 4G, or raw MB.</div>
                  </div>
                </div>
                <div className="md:col-span-2 flex items-center gap-2 mt-2">
                  <button disabled={installWorking} onClick={submitInstall} className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 rounded">{installWorking ? 'Installing…' : 'Start Install'}</button>
                  <div className="text-sm text-white/70">{installProvider}</div>
                </div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded p-3 h-40 overflow-auto text-sm">
                {installEvents.length === 0 ? (
                  <div className="text-white/50">No events yet…</div>
                ) : (
                  <ul className="space-y-1">
                    {installEvents.map((ev, i) => {
                      let text = '';
                      if (typeof ev?.message === 'string') {
                        text = ev.message;
                      } else if (ev?.message) {
                        try { text = JSON.stringify(ev.message); } catch { text = String(ev.message); }
                      } else if (ev?.step) {
                        const pct = typeof ev.progress === 'number' ? ` (${ev.progress}%)` : '';
                        text = `${ev.step}${pct}`;
                      } else {
                        try { text = JSON.stringify(ev); } catch { text = String(ev); }
                      }
                      return (
                        <li key={i} className="flex items-start gap-2">
                          <span className="w-2 h-2 rounded-full mt-2" style={{ background: ev.type === 'error' ? '#f87171' : ev.type === 'done' ? '#34d399' : '#a78bfa' }}></span>
                          <span>{text}</span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Clean Server List */}
        <div className="space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-white">Servers</h2>
              <button 
                onClick={() => onNavigate && onNavigate('servers')}
                className="text-sm text-white/60 hover:text-white transition-colors"
              >
                View all
              </button>
            </div>
            
            <div className="glassmorphism rounded-xl divide-y divide-white/10">
              {servers.length > 0 ? (
                servers.slice(0, 5).map((server) => {
                  const isRunning = server.status === 'running';
                  
                  return (
                    <div 
                      key={server.id}
                      className="flex items-center justify-between p-4 hover:bg-white/5 cursor-pointer transition-colors"
                      onClick={() => onNavigate && onNavigate('servers')}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${
                          isRunning ? 'bg-green-400' : 'bg-gray-500'
                        }`} />
                        <div>
                          <div className="text-white font-medium">{server.name}</div>
                          <div className="text-sm text-white/60">
                            {server.version} • {server.type || 'vanilla'}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <span className={`text-xs px-2 py-1 rounded ${
                          isRunning 
                            ? 'bg-green-500/15 text-green-200 border border-green-500/30'
                            : 'bg-white/5 text-white/60 border border-white/10'
                        }`}>
                          {isRunning ? 'Running' : 'Stopped'}
                        </span>
                        <FaChevronRight className="w-3 h-3 text-white/40" />
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="p-8 text-center">
                  <div className="text-white/60 mb-2">No servers yet</div>
                  <button 
                    onClick={() => onNavigate && onNavigate('servers')}
                    className="text-sm text-brand-400 hover:text-brand-300"
                  >
                    Create your first server
                  </button>
                </div>
              )}
            </div>
          </div>
          
          {/* Clean Alerts */}
          {alerts.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium text-white">Recent Issues</h2>
                <button 
                  onClick={() => onNavigate && onNavigate('monitoring')}
                  className="text-sm text-white/60 hover:text-white transition-colors"
                >
                  View all
                </button>
              </div>
              
              <div className="glassmorphism rounded-xl divide-y divide-white/10">
                {alerts.slice(0, 3).map((alert, index) => {
                  const isError = alert.type === 'critical' || alert.type === 'error';
                  
                  return (
                    <div key={alert.id || index} className="p-4">
                      <div className="flex items-start gap-3">
                        <div className={`w-2 h-2 rounded-full mt-2 ${
                          isError ? 'bg-red-400' : 'bg-yellow-400'
                        }`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-white text-sm">{alert.message}</div>
                          <div className="text-xs text-white/50 mt-1">
                            {new Date(alert.timestamp).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
});

// Servers Page with Global Data
function ServersPageWithGlobalData({
  servers: serversProp,
  onSelectServer,
  onNavigate,
}) {
  // Prefer servers passed from parent (kept in sync with details view); fallback to global data
  const globalData = useGlobalData();
  const servers = Array.isArray(serversProp) ? serversProp : (globalData?.servers || []);
  
  return (
    <ServersPage
      servers={servers}
      serversLoading={false} // Never loading with preloaded data!
      onSelectServer={onSelectServer}
      onNavigate={onNavigate}
    />
  );
}

// Original Servers Page
function ServersPage({
  servers,
  serversLoading,
  onSelectServer,
  onNavigate,
}) {
  const normalizedServers = useMemo(
    () => (Array.isArray(servers) ? servers : []),
    [servers]
  );

  const [statusFilter, setStatusFilter] = useState('all');
  const [runtimeFilter, setRuntimeFilter] = useState('all');
  const [modpackFilter, setModpackFilter] = useState('all');

  const deriveRuntime = useCallback((server) => {
    const image = typeof server?.image === 'string' ? server.image.toLowerCase() : '';
    if (image === 'local' || image.includes('local-runtime')) return 'local';
    return 'docker';
  }, []);

  const deriveModpackKey = useCallback((server) => {
    const labels = (server && server.labels) || {};
    const provider = labels['mc.modpack.provider'];
    const packId = labels['mc.modpack.id'];
    const versionId = labels['mc.modpack.version_id'];
    if (provider && packId) {
      const key = `${provider}:${packId}`;
      const suffix = versionId ? ` (${versionId})` : '';
      return { key, label: `${provider} · ${packId}${suffix}` };
    }
    return { key: 'none', label: 'No modpack' };
  }, []);

  const formatLabel = useCallback((value) => {
    if (!value) return 'Unknown';
    return value
      .toString()
      .split(/[-_\s]+/)
      .filter(Boolean)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' ');
  }, []);

  const filterSummary = useMemo(() => {
    const statusMap = new Map();
    const runtimeMap = new Map();
    const modpackMap = new Map();
    normalizedServers.forEach(server => {
      const status = (server?.status || 'unknown').toString().toLowerCase();
      statusMap.set(status, (statusMap.get(status) || 0) + 1);

      const runtime = deriveRuntime(server);
      runtimeMap.set(runtime, (runtimeMap.get(runtime) || 0) + 1);

      const modpack = deriveModpackKey(server);
      const existing = modpackMap.get(modpack.key) || { label: modpack.label, count: 0 };
      existing.label = modpack.label;
      existing.count += 1;
      modpackMap.set(modpack.key, existing);
    });
    if (!modpackMap.has('none')) {
      modpackMap.set('none', { label: 'No modpack', count: 0 });
    }
    return {
      statuses: Array.from(statusMap.entries()).map(([value, count]) => ({ value, count })),
      runtimes: Array.from(runtimeMap.entries()).map(([value, count]) => ({ value, count })),
      modpacks: Array.from(modpackMap.entries()).map(([value, info]) => ({ value, label: info.label, count: info.count })),
    };
  }, [normalizedServers, deriveRuntime, deriveModpackKey]);

  const statusOptions = useMemo(() => {
    const options = [{ value: 'all', label: 'All', count: normalizedServers.length }];
    filterSummary.statuses
      .slice()
      .sort((a, b) => b.count - a.count)
      .forEach(({ value, count }) => {
        options.push({ value, label: formatLabel(value), count });
      });
    return options;
  }, [filterSummary.statuses, normalizedServers.length, formatLabel]);

  const runtimeOptions = useMemo(() => {
    const options = [{ value: 'all', label: 'All', count: normalizedServers.length }];
    filterSummary.runtimes
      .slice()
      .sort((a, b) => b.count - a.count)
      .forEach(({ value, count }) => {
        options.push({ value, label: formatLabel(value), count });
      });
    return options;
  }, [filterSummary.runtimes, normalizedServers.length, formatLabel]);

  const modpackOptions = useMemo(() => {
    const options = [{ value: 'all', label: 'All', count: normalizedServers.length }];
    filterSummary.modpacks
      .slice()
      .sort((a, b) => b.count - a.count)
      .forEach(({ value, label, count }) => {
        if (value === 'none') {
          options.push({ value: 'none', label: 'No modpack', count });
        } else {
          options.push({ value, label, count });
        }
      });
    return options;
  }, [filterSummary.modpacks, normalizedServers.length]);

  const filteredServers = useMemo(() => {
    return normalizedServers.filter(server => {
      const status = (server?.status || 'unknown').toString().toLowerCase();
      if (statusFilter !== 'all' && status !== statusFilter) return false;
      const runtime = deriveRuntime(server);
      if (runtimeFilter !== 'all' && runtime !== runtimeFilter) return false;
      const modpack = deriveModpackKey(server);
      if (modpackFilter === 'none') {
        if (modpack.key !== 'none') return false;
      } else if (modpackFilter !== 'all' && modpack.key !== modpackFilter) {
        return false;
      }
      return true;
    });
  }, [normalizedServers, statusFilter, runtimeFilter, modpackFilter, deriveRuntime, deriveModpackKey]);

  const hasFilters = statusFilter !== 'all' || runtimeFilter !== 'all' || modpackFilter !== 'all';
  const totalServers = normalizedServers.length;

  const chipClass = useCallback((active) => (
    active
      ? 'px-3 py-1.5 rounded-full text-xs font-medium bg-brand-500 text-white border border-brand-500/70 shadow-sm transition-colors'
      : 'px-3 py-1.5 rounded-full text-xs font-medium bg-white/10 border border-white/10 text-white/80 hover:bg-white/15 transition-colors'
  ), []);

  const clearFilters = useCallback(() => {
    setStatusFilter('all');
    setRuntimeFilter('all');
    setModpackFilter('all');
  }, []);

  return (
    <div className="p-6 space-y-6 animate-fade-in">
      <nav className="flex items-center gap-2 text-xs text-white/60">
        <button
          type="button"
          onClick={() => onNavigate && onNavigate('dashboard')}
          className="inline-flex items-center gap-1 hover:text-white transition-colors"
        >
          <FaHome className="text-sm" /> Dashboard
        </button>
        <FaChevronRight className="text-white/40 text-[10px]" />
        <span className="text-white/80">Servers</span>
        {hasFilters ? (
          <span className="ml-2 text-white/50">{filteredServers.length} / {totalServers}</span>
        ) : null}
      </nav>

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaServer className="text-brand-500" /> <span className="gradient-text-brand">Server Management</span>
          </h1>
          <p className="text-white/70 mt-2">Create and manage your Minecraft servers</p>
        </div>
      </div>

      {/* Servers List */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">Your Servers</h3>
          <div className="flex items-center gap-3 text-xs text-white/60">
            <span>{filteredServers.length} / {totalServers}</span>
            {hasFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-xs text-white"
              >
                Clear filters
              </button>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div>
            <div className="text-[11px] text-white/50 uppercase tracking-wide flex items-center gap-2 mb-2">
              <FaFilter className="text-white/40" /> Status
            </div>
            <div className="flex flex-wrap gap-2">
              {statusOptions.map(({ value, label, count }) => (
                <button
                  key={`status-${value}`}
                  type="button"
                  onClick={() => setStatusFilter(value)}
                  className={chipClass(statusFilter === value)}
                >
                  {label}
                  <span className="ml-1 text-[10px] opacity-70">{count}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-white/50 uppercase tracking-wide flex items-center gap-2 mb-2">
              <FaFilter className="text-white/40" /> Runtime
            </div>
            <div className="flex flex-wrap gap-2">
              {runtimeOptions.map(({ value, label, count }) => (
                <button
                  key={`runtime-${value}`}
                  type="button"
                  onClick={() => setRuntimeFilter(value)}
                  className={chipClass(runtimeFilter === value)}
                >
                  {label}
                  <span className="ml-1 text-[10px] opacity-70">{count}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[11px] text-white/50 uppercase tracking-wide flex items-center gap-2 mb-2">
              <FaFilter className="text-white/40" /> Modpack
            </div>
            <div className="flex flex-wrap gap-2">
              {modpackOptions.map(({ value, label, count }) => (
                <button
                  key={`modpack-${value}`}
                  type="button"
                  onClick={() => setModpackFilter(value)}
                  className={chipClass(modpackFilter === value)}
                >
                  {label}
                  <span className="ml-1 text-[10px] opacity-70">{count}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {serversLoading ? (
          <div className="text-white/70">Loading servers...</div>
        ) : totalServers === 0 ? (
          <div className="text-white/60 text-center py-8 space-y-3">
            <div>No servers created yet. Use Templates to create your first server.</div>
            {onNavigate ? (
              <button
                type="button"
                onClick={() => onNavigate('templates')}
                className="inline-flex items-center gap-2 px-4 py-2 rounded bg-brand-500 hover:bg-brand-600 text-white text-sm"
              >
                Go to Templates
              </button>
            ) : null}
          </div>
        ) : filteredServers.length === 0 ? (
          <div className="text-white/60 text-center py-8">
            No servers match the current filters.
          </div>
        ) : (
          <div className="space-y-4">
            {filteredServers.map((server) => (
              <ServerListCard
                key={server.id}
                server={server}
                onClick={() => onSelectServer(server.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// Placeholder components for missing pages
function BackupManagementPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaDatabase className="text-brand-500" /> Backup Management
        </h1>
        <p className="text-white/70 mt-2">Manage automatic and manual backups</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 text-center">
        <FaDatabase className="text-6xl text-white/20 mx-auto mb-4" />
        <h3 className="text-xl font-semibold mb-2">Backup Management</h3>
        <p className="text-white/60">Advanced backup management features coming soon!</p>
      </div>
    </div>
  );
}

function SchedulerPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaClock className="text-brand-500" /> Task Scheduler
        </h1>
        <p className="text-white/70 mt-2">Schedule automated tasks and maintenance</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 text-center">
        <FaClock className="text-6xl text-white/20 mx-auto mb-4" />
        <h3 className="text-xl font-semibold mb-2">Task Scheduler</h3>
        <p className="text-white/60">Advanced scheduling features coming soon!</p>
      </div>
    </div>
  );
}

function PluginManagerPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaRocket className="text-brand-500" /> Plugin Manager
        </h1>
        <p className="text-white/70 mt-2">Browse and install plugins for your servers</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 text-center">
        <FaRocket className="text-6xl text-white/20 mx-auto mb-4" />
        <h3 className="text-xl font-semibold mb-2">Plugin Manager</h3>
        <p className="text-white/60">Plugin marketplace and management coming soon!</p>
      </div>
    </div>
  );
}

// Templates & Modpacks Page (curated templates removed)
function SecurityPage() {
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaShieldAlt className="text-brand-500" /> Security Center
        </h1>
        <p className="text-white/70 mt-2">Manage security settings and access controls</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 text-center">
        <FaShieldAlt className="text-6xl text-white/20 mx-auto mb-4" />
        <h3 className="text-xl font-semibold mb-2">Security Center</h3>
        <p className="text-white/60">Advanced security features coming soon!</p>
      </div>
    </div>
  );
}

function App() {
  // Auth state
  const [authToken, setAuthToken] = useState(getStoredToken());
  const isAuthenticated = !!authToken;
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);

  const [themeMode, setThemeMode] = useState('dark');

  const [colorblindMode, setColorblindMode] = useState(false);

  const toggleThemeMode = useCallback(() => {}, []); // disabled; keeping stub to avoid ref churn

  const toggleColorblindMode = useCallback(() => {}, []);
  
  // Main navigation state
  const [currentPage, setCurrentPage] = useState('dashboard');
  // Initialize sidebar open state based on screen width (closed on small screens)
  const initialSidebarOpen = (typeof window !== 'undefined') ? window.innerWidth >= 768 : true;
  const [sidebarOpen, setSidebarOpen] = useState(initialSidebarOpen);
  const [isMobile, setIsMobile] = useState((typeof window !== 'undefined') ? window.innerWidth < 768 : false);

  // Update isMobile on resize and auto-close sidebar on mobile
  useEffect(() => {
    function handleResize() {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarOpen(false);
    }
    try {
      window.addEventListener('resize', handleResize);
    } catch (e) {}
    return () => { try { window.removeEventListener('resize', handleResize); } catch {} };
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', themeMode);
      if (document.body) {
        document.body.setAttribute('data-theme', themeMode);
      }
    }
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_MODE_KEY, themeMode);
    }
  }, [themeMode]);

  useEffect(() => {
    const flag = colorblindMode ? 'on' : 'off';
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-colorblind', flag);
      if (document.body) {
        document.body.setAttribute('data-colorblind', flag);
      }
    }
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(COLORBLIND_KEY, flag);
    }
  }, [colorblindMode]);

  // Validate token and fetch current user
  useEffect(() => {
    let cancelled = false;
    async function validate() {
      if (!authToken) return;
      try {
        const r = await fetch(`${API}/auth/me`);
        if (!r.ok) throw new Error('invalid');
        const user = await r.json();
        if (!cancelled) setCurrentUser(user);
      } catch (_) {
        clearStoredToken();
        if (!cancelled) {
          setAuthToken('');
          setCurrentUser(null);
        }
      }
    }
    validate();
    return () => { cancelled = true; };
  }, [authToken]);

  async function handleLogin(e) {
    e.preventDefault();
    setLoginError('');
    setLoginLoading(true);
    try {
      const body = new URLSearchParams({ username: loginUsername, password: loginPassword });
      const r = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body
      });
      if (!r.ok) {
        const payload = await r.json().catch(() => null);
        throw new Error((payload && (payload.detail || payload.message)) || `HTTP ${r.status}`);
      }
      const data = await r.json();
      const token = data && data.access_token;
      if (!token) throw new Error('Invalid login response');
      setStoredToken(token);
      setAuthToken(token);
    } catch (err) {
      setLoginError(err.message || 'Login failed');
    } finally {
      setLoginLoading(false);
    }
  }

  const handleLogout = useCallback(async () => {
    try {
      await fetch(`${API}/auth/logout`, { method: 'POST' });
    } catch (_) {}
    clearStoredToken();
    setAuthToken('');
    // Reload to clear any in-memory state
    window.location.reload();
  }, []);

  // Auto-logout users after 5 minutes of inactivity
  useEffect(() => {
    if (!isAuthenticated || typeof window === 'undefined') return undefined;
    let timeoutId = null;
    const resetTimer = () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => {
        handleLogout();
      }, 5 * 60 * 1000);
    };

    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    events.forEach((evt) => window.addEventListener(evt, resetTimer, { passive: true }));
    resetTimer();

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      events.forEach((evt) => window.removeEventListener(evt, resetTimer));
    };
  }, [isAuthenticated, handleLogout]);

  // Fetch server types from backend
  const { data: typesData, error: typesError } = useFetch(
    `${API}/server-types`,
    []
  );
  // Default selected type is 'vanilla'
  const [selectedType, setSelectedType] = useState('vanilla');
  // Fetch versions for the selected type
  const { data: versionsData, error: versionsError } = useFetch(
    selectedType
      ? `${API}/server-types/${selectedType}/versions`
      : null,
    [selectedType]
  );

  // Loader version state for types that need it (as in backend/app.py)
  const [loaderVersion, setLoaderVersion] = useState('');
  const [loaderVersionsData, setLoaderVersionsData] = useState(null);
  const [loaderVersionsLoading, setLoaderVersionsLoading] = useState(false);
  const [loaderVersionsError, setLoaderVersionsError] = useState(null);
  const [installerVersion, setInstallerVersion] = useState('');

  // Fetch servers
  const {
    data: serversData,
    loading: serversLoading,
    error: serversError,
    setData: setServersData,
  } = useFetch(isAuthenticated ? `${API}/servers` : null, [isAuthenticated]);
  // Server creation form state
  const [name, setName] = useState(
    'mc-' + Math.random().toString(36).slice(2, 7)
  );
  const [version, setVersion] = useState('');
  const [hostPort, setHostPort] = useState('');

  // RAM state for min/max ram (in MB)
  const [minRam, setMinRam] = useState('1024');
  const [maxRam, setMaxRam] = useState('2048');

  // Selected server for details view
  const [selectedServer, setSelectedServer] = useState(null);
  const [serverDetailsTab, setServerDetailsTab] = useState('overview');
  const [pendingPlayerFocus, setPendingPlayerFocus] = useState('');
  const [pendingConfigFocus, setPendingConfigFocus] = useState('');

  // Only fetch loader versions for types that actually need it and only if a version is selected and valid
  useEffect(() => {
    // Only fetch loader versions if the selected type is in the loader list and a version is selected
    if (
      SERVER_TYPES_WITH_LOADER.includes(selectedType) &&
      version &&
      // Only fetch if the version string is not a snapshot or non-release (avoid 400s for invalid versions)
      !/^(\d{2}w\d{2}[a-z])$/i.test(version) // skip Minecraft snapshots like 25w32a
    ) {
      setLoaderVersionsLoading(true);
      setLoaderVersionsError(null);
      setLoaderVersionsData(null);
      fetch(`${API}/server-types/${selectedType}/loader-versions?version=${encodeURIComponent(version)}`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((d) => {
          setLoaderVersionsData(d);
          // Prefer first loader version returned (backend tends to sort newest first); UI keeps user choice open
          if (d?.loader_versions?.length) {
            setLoaderVersion(d.loader_versions[0]);
          } else {
            setLoaderVersion('');
          }
          // Set installer version default for Fabric when provided by backend
          if (selectedType === 'fabric') {
            if (d?.latest_installer_version) {
              setInstallerVersion(d.latest_installer_version);
            } else if (Array.isArray(d?.installer_versions) && d.installer_versions.length) {
              setInstallerVersion(d.installer_versions[0]);
            } else {
              setInstallerVersion('');
            }
          } else {
            setInstallerVersion('');
          }
        })
        .catch((e) => {
          setLoaderVersionsError(e);
          setLoaderVersion('');
          setInstallerVersion('');
        })
        .finally(() => setLoaderVersionsLoading(false));
    } else {
      setLoaderVersionsData(null);
      setLoaderVersion('');
      setInstallerVersion('');
    }
  }, [selectedType, version]);

  // Set default version when versionsData changes
  useEffect(() => {
    if (
      versionsData &&
      versionsData.versions &&
      versionsData.versions.length
    ) {
      setVersion(versionsData.versions[0]);
    }
  }, [versionsData]);

  // Memoized types and servers
  const types = useMemo(
    () => (typesData && typesData.types) || [],
    [typesData]
  );

  // Global data context (use once at top-level; reuse inside callbacks)
  const gd = useGlobalData();

  const servers = useMemo(() => {
    const globalServers = Array.isArray(gd?.servers) ? gd.servers : [];
    if (globalServers.length) {
      return globalServers;
    }
    return Array.isArray(serversData) ? serversData : [];
  }, [gd?.servers, serversData]);

  const handleGlobalNavigate = useCallback((item) => {
    if (!item) return;
    const candidateList = (gd?.servers && gd.servers.length) ? gd.servers : servers;
    let resolvedId = item.server_id || null;
    if (!resolvedId && item.server_name) {
      const byName = candidateList.find(entry => entry && entry.name === item.server_name);
      if (byName && byName.id) {
        resolvedId = byName.id;
      }
    }
    if (!resolvedId && item.server_name) {
      const byId = candidateList.find(entry => entry && entry.id === item.server_name);
      if (byId && byId.id) {
        resolvedId = byId.id;
      }
    }
    if (!resolvedId) {
      return;
    }

    if (item.type === 'server') {
      setServerDetailsTab('overview');
      setPendingPlayerFocus('');
      setPendingConfigFocus('');
    } else if (item.type === 'player') {
      setServerDetailsTab('players');
      setPendingPlayerFocus(item.name || item.player_name || '');
      setPendingConfigFocus('');
    } else if (item.type === 'config') {
      setServerDetailsTab('files');
      setPendingConfigFocus(item.path || '');
      setPendingPlayerFocus('');
    }

    setSelectedServer(resolvedId);
    setCurrentPage('servers');
    if (isMobile) setSidebarOpen(false);
  }, [gd, servers, isMobile]);

  // Create server handler, using loader_version as in backend/app.py - optimized with useCallback
  const createServer = useCallback(async function createServer(e) {
    e.preventDefault();
    const payload = {
      name,
      type: selectedType,
      version,
      loader_version: SERVER_TYPES_WITH_LOADER.includes(selectedType) ? loaderVersion : null,
      installer_version: selectedType === 'fabric' && installerVersion ? installerVersion : null,
      host_port: hostPort ? Number(hostPort) : null,
      min_ram: minRam ? Number(minRam) : null,
      max_ram: maxRam ? Number(maxRam) : null,
    };
    // Optimistic placeholder entry so the card appears immediately
    const optimistic = {
      id: `pending-${Date.now()}`,
      name,
      status: 'creating',
      type: selectedType,
      version,
    };
    setServersData && setServersData(prev => (Array.isArray(prev) ? [optimistic, ...prev] : [optimistic]));
    gd && gd.__setGlobalData && gd.__setGlobalData(cur => ({ ...cur, servers: [optimistic, ...(cur.servers || [])] }));

    // Fire create request
    await fetch(`${API}/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    // After creation, poll briefly until the new server appears, then update lists.
    // This avoids requiring a full page reload and handles async backend provisioning.
    const start = Date.now();
    const timeoutMs = 15000; // poll up to 15s
    const intervalMs = 800;  // gentle cadence
    let found = false;
    while (Date.now() - start < timeoutMs) {
      try {
        const r = await fetch(`${API}/servers`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const updated = await r.json();
        // consider it appeared if any entry matches by name
        if (Array.isArray(updated) && updated.some(s => s && s.name === name)) {
          found = true;
          if (gd && gd.__setGlobalData) {
            gd.__setGlobalData(cur => ({ ...cur, servers: updated }));
          }
          setServersData && setServersData(updated);
          break;
        } else {
          // still provisioning, keep optimistic but refresh list to show progress if available
          if (gd && gd.__setGlobalData) {
            gd.__setGlobalData(cur => ({ ...cur, servers: Array.isArray(updated) ? updated : cur.servers }));
          }
          setServersData && setServersData(Array.isArray(updated) ? updated : []);
        }
      } catch {}
      await new Promise(res => setTimeout(res, intervalMs));
    }
    // Final fallback refresh if not found in time (keeps optimistic card until background refresh swaps it)
    if (!found) {
      gd && gd.__refreshServers && gd.__refreshServers();
    }
  }, [name, selectedType, version, loaderVersion, installerVersion, hostPort, minRam, maxRam, gd]);

  // Start server handler - optimized
  const start = useCallback(async function start(id) {
    await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'start' }) });
    gd.__updateServerStatus && gd.__updateServerStatus(id, 'running');
    gd.__refreshServers && gd.__refreshServers();
  }, [gd]);
  
  // Stop server handler - optimized
  const stop = useCallback(async function stop(id) {
    await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'stop' }) });
    gd.__updateServerStatus && gd.__updateServerStatus(id, 'stopped');
    gd.__refreshServers && gd.__refreshServers();
  }, [gd]);
  
  // Delete server handler - optimized
  const del = useCallback(async function del(id) {
    await fetch(`${API}/servers/${id}`, { method: 'DELETE' });
    if (selectedServer === id) setSelectedServer(null);
    gd.__refreshServers && gd.__refreshServers();
  }, [gd, selectedServer]);

  // Restart server handler - optimized
  const restart = useCallback(async function restart(id) {
    try {
      await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'restart' }) });
      // Refresh servers data
      const response = await fetch(`${API}/servers`);
      if (response.ok) {
        const updatedServers = await response.json();
        if (gd && gd.__setGlobalData) {
          gd.__setGlobalData(cur => ({ ...cur, servers: Array.isArray(updatedServers) ? updatedServers : [] }));
        }
      }
    } catch (e) {
      console.error('Error restarting server:', e);
    }
  }, [gd]);

  // Find selected server object (prefer global servers so status reflects instantly)
  const serverListForDetails = (gd?.servers && gd.servers.length) ? gd.servers : servers;
  const selectedServerObj = selectedServer && serverListForDetails.find((s) => s.id === selectedServer);

  // Navigation with advanced user management like Crafty Controller
  const sidebarItems = [
    { id: 'dashboard', label: 'Dashboard', icon: FaHome },
    { id: 'servers', label: 'My Servers', icon: FaServer },
    { id: 'templates', label: 'Templates', icon: FaLayerGroup },
    { id: 'monitoring', label: 'Server Status', icon: FaChartLine },
    { id: 'users', label: 'User Management', icon: FaUsers, adminOnly: true },
    { id: 'settings', label: 'Settings', icon: FaCog },
  ];

  function renderCurrentPage() {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage onNavigate={setCurrentPage} />;
      case 'servers':
        return selectedServer && selectedServerObj ? (
          <ServerDetailsPage
            server={selectedServerObj}
            onBack={() => {
              setSelectedServer(null);
              setServerDetailsTab('overview');
              setPendingPlayerFocus('');
              setPendingConfigFocus('');
            }}
            onStart={start}
            onStop={stop}
            onDelete={del}
            onRestart={restart}
            initialTab={serverDetailsTab}
            onTabChange={setServerDetailsTab}
            playerFocus={pendingPlayerFocus}
            onPlayerFocusConsumed={() => setPendingPlayerFocus('')}
            configFocus={pendingConfigFocus}
            onConfigFocusConsumed={() => setPendingConfigFocus('')}
          />
        ) : (
          <ServersPageWithGlobalData
            servers={servers}
            onSelectServer={(id) => {
              setServerDetailsTab('overview');
              setPendingPlayerFocus('');
              setPendingConfigFocus('');
              setSelectedServer(id);
            }}
            onNavigate={(target) => {
              if (!target) return;
              setCurrentPage(target);
              if (target !== 'servers') {
                setSelectedServer(null);
                setServerDetailsTab('overview');
              }
            }}
          />
        );
      case 'monitoring':
        return (
          <React.Suspense fallback={<div className="p-6">Loading monitoring…</div>}>
            <MonitoringPageLazy />
          </React.Suspense>
        );
      case 'templates':
        return (
          <React.Suspense fallback={<div className="p-6">Loading templates…</div>}>
            <TemplatesPageLazy
              API={API}
              authHeaders={authHeaders}
              onCreateServer={createServer}
              types={types}
              versionsData={versionsData}
              selectedType={selectedType}
              setSelectedType={setSelectedType}
              name={name}
              setName={setName}
              version={version}
              setVersion={setVersion}
              hostPort={hostPort}
              setHostPort={setHostPort}
              minRam={minRam}
              setMinRam={setMinRam}
              maxRam={maxRam}
              setMaxRam={setMaxRam}
              loaderVersion={loaderVersion}
              setLoaderVersion={setLoaderVersion}
              loaderVersionsData={loaderVersionsData}
              installerVersion={installerVersion}
              setInstallerVersion={setInstallerVersion}
            />
          </React.Suspense>
        );
      case 'users':
        return (
          <ErrorBoundary>
            <AdvancedUserManagementPageImpl />
          </ErrorBoundary>
        );
      case 'settings':
        return <SettingsPageImpl />;
      default:
        return <DashboardPage servers={servers} />;
    }
  }

  if (!isAuthenticated) {
    return (
      <LoginPage
        appName={APP_NAME}
        username={loginUsername}
        password={loginPassword}
        onUsernameChange={setLoginUsername}
        onPasswordChange={setLoginPassword}
        onSubmit={handleLogin}
        error={loginError}
        loading={loginLoading}
      />
    );
  }

  if (isAuthenticated && !currentUser) {
    return (
      <div className="min-h-screen bg-ink bg-hero-gradient flex w-full items-center justify-center">
        <div className="text-white/70">Loading…</div>
      </div>
    );
  }

  if (isAuthenticated && currentUser && currentUser.must_change_password) {
    return (
      <MustChangePasswordPage
        appName={APP_NAME}
        apiBaseUrl={API}
        onComplete={async () => {
          try {
            const r = await fetch(`${API}/auth/me`);
            if (r.ok) {
              const user = await r.json();
              setCurrentUser(user);
            } else {
              setCurrentUser((prev) => (prev ? { ...prev, must_change_password: false } : prev));
            }
          } catch (_) {
            setCurrentUser((prev) => (prev ? { ...prev, must_change_password: false } : prev));
          }
        }}
        onLogout={handleLogout}
      />
    );
  }

  return (
      <div className="min-h-screen bg-ink bg-hero-gradient flex">
      {/* Sidebar */}
      {isAuthenticated && (() => {
        // Sidebar content reused for desktop and mobile overlay
        const sidebarContent = (
          <div className="flex flex-col h-full">
            <div className="p-4 border-b border-white/10">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-md bg-brand-500 inline-flex items-center justify-center shadow-card">
                  <FaServer className="text-white" />
                </div>
                {!isMobile && sidebarOpen && <div className="font-semibold">{APP_NAME}</div>}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              <nav className="p-4">
                <div className="space-y-2">
                  {sidebarItems.map(item => (
                    <button
                      key={item.id}
                      onClick={() => {
                        setCurrentPage(item.id);
                        setSelectedServer(null);
                        if (isMobile) setSidebarOpen(false);
                      }}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                        currentPage === item.id
                          ? 'bg-brand-500 text-white'
                          : 'text-white/70 hover:text-white hover:bg-white/10'
                      }`}
                    >
                      <item.icon className={`${(!isMobile && sidebarOpen) ? 'text-lg' : 'text-xl'}`} />
                      {(!isMobile && sidebarOpen) && (
                        <div className="flex items-center justify-between w-full">
                          <span>{item.label}</span>
                          {item.id === 'monitoring' && gd?.alerts && gd.alerts.length > 0 && (
                            <span className="ml-2 inline-flex items-center justify-center rounded-full bg-red-600 px-2 py-0.5 text-xs font-medium text-white">{gd.alerts.length}</span>
                          )}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </nav>
            </div>
            <div className="p-4 border-t border-white/10 bg-black/30 backdrop-blur supports-[backdrop-filter]:bg-black/20">
              <div
                className="flex items-center gap-3 mb-3 cursor-pointer hover:bg-white/10 rounded-lg p-2"
                onClick={() => { setCurrentPage('settings'); if (isMobile) setSidebarOpen(false); }}
                role="button"
                tabIndex={0}
              >
                {currentUser && (
                  <>
                    <div className="w-8 h-8 bg-brand-500 rounded-full flex items-center justify-center">
                      <FaUsers className="text-sm text-white" />
                    </div>
                    {(!isMobile && sidebarOpen) && (
                      <div className="text-sm">
                        <div className="text-white font-medium">{currentUser.username}</div>
                        <div className="text-white/60">{currentUser.role}</div>
                      </div>
                    )}
                  </>
                )}
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition-colors"
              >
                <FaArrowLeft />
                {(!isMobile && sidebarOpen) && <span>Logout</span>}
              </button>
            </div>
          </div>
        );

        if (isMobile) {
          return sidebarOpen ? (
            <div className="fixed inset-0 z-50 flex">
              <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
              <div className="relative w-64 bg-black/20 border-r border-white/10">{sidebarContent}</div>
            </div>
          ) : null;
        }

        return (
          <div className={`${sidebarOpen ? 'w-64' : 'w-16'} bg-black/20 border-r border-white/10 transition-all duration-300 flex flex-col sticky top-0 h-screen`}>
            {sidebarContent}
          </div>
        );
      })()}
      
      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Top Header */}
        {isAuthenticated && (
          <header className="border-b border-white/10 bg-ink/80 backdrop-blur supports-[backdrop-filter]:bg-ink/60">
            <div className="px-4 md:px-6 flex items-center justify-between h-14 gap-3">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="p-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                  aria-label={sidebarOpen ? 'Collapse navigation' : 'Expand navigation'}
                >
                  {sidebarOpen ? <FaBackward /> : <FaForward />}
                </button>
                <h1 className="text-lg font-semibold text-white">
                  {sidebarItems.find(item => item.id === currentPage)?.label || 'Dashboard'}
                </h1>
              </div>
              <div className="flex items-center gap-2 sm:gap-3">
                <GlobalSearchBar onNavigate={handleGlobalNavigate} className="w-40 sm:w-64 md:w-80" />
                <div className="hidden sm:block text-sm text-white/70">
                  Welcome back, {currentUser?.username || 'User'}
                </div>
              </div>
            </div>
          </header>
        )}

        {/* Main Content Area */}
        <main className="flex-1">
          {renderCurrentPage()}
        </main>
      </div>
      </div>
  );
}

// Advanced User Management Components

// Users Tab Component
function UsersTab({ 
  users, roles, searchTerm, setSearchTerm, filterRole, setFilterRole, 
  filterStatus, setFilterStatus, updateUserRole, toggleUserActive, 
  deleteUser, setSelectedUser 
}) {
  // Ensure users is always an array
  const safeUsers = Array.isArray(users) ? users : [];
  const safeRoles = Array.isArray(roles) ? roles : [];
  
  return (
    <div className="space-y-4">
      {/* Search and Filters */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="relative">
            <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-white/50" />
            <input
              type="text"
              placeholder="Search users by username or email..."
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/50 focus:ring-2 focus:ring-brand-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <select
            value={filterRole}
            onChange={(e) => setFilterRole(e.target.value)}
            className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white"
          >
            <option value="all">All Roles</option>
            {safeRoles.map(role => (
              <option key={role.name} value={role.name}>{role.name}</option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white"
          >
            <option value="all">All Status</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </div>
      </div>

      {/* Users Table */}
      <div className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-white/10">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-white/70 uppercase tracking-wider">User</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-white/70 uppercase tracking-wider">Role</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-white/70 uppercase tracking-wider">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-white/70 uppercase tracking-wider">Last Login</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-white/70 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {safeUsers.map((user) => {
                const userRole = safeRoles.find(r => r.name === user.role);
                return (
                  <tr key={user.id} className="hover:bg-white/5">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div 
                          className="w-10 h-10 rounded-full flex items-center justify-center text-white font-semibold"
                          style={{ backgroundColor: userRole?.color || '#6b7280' }}
                        >
                          {user.username?.charAt(0)?.toUpperCase() || '?'}
                        </div>
                        <div className="ml-3">
                          <div className="text-sm font-medium text-white">{user.username || 'Unknown'}</div>
                          <div className="text-sm text-white/60">{user.email || 'No email'}</div>
                          {user.fullName && <div className="text-xs text-white/50">{user.fullName}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <div 
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: userRole?.color || '#6b7280' }}
                        />
                        <span className="text-sm font-medium" style={{ color: userRole?.color || '#6b7280' }}>
                          {user.role}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                        user.is_active
                          ? 'bg-green-500/20 text-green-300 border border-green-500/30'
                          : 'bg-red-500/20 text-red-300 border border-red-500/30'
                      }`}>
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-white/70">
                      {user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setSelectedUser(user)}
                          className="p-2 text-blue-400 hover:text-blue-300 hover:bg-blue-500/10 rounded"
                          title="View Details"
                        >
                          <FaEye />
                        </button>
                        <button
                          onClick={() => toggleUserActive(user.id, !user.is_active)}
                          className={`p-2 rounded ${
                            user.is_active 
                              ? 'text-red-400 hover:text-red-300 hover:bg-red-500/10' 
                              : 'text-green-400 hover:text-green-300 hover:bg-green-500/10'
                          }`}
                          title={user.is_active ? 'Deactivate User' : 'Activate User'}
                        >
                          {user.is_active ? <FaUserSlash /> : <FaUserCheck />}
                        </button>
                        <button
                          onClick={() => deleteUser(user.id)}
                          className="p-2 text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded"
                          title="Delete User"
                        >
                          <FaTrash />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        
        {safeUsers.length === 0 && (
          <div className="text-center py-12 text-white/60">
            <FaUsers className="text-4xl mx-auto mb-3 text-white/30" />
            <p className="text-lg">No users found</p>
            <p className="text-sm text-white/40 mt-2">Create your first user or adjust your search filters</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Roles Tab Component
function RolesTab({ roles, permissionCategories, setSelectedRole }) {
  // Ensure roles is always an array
  const safeRoles = Array.isArray(roles) ? roles : [];
  
  return (
    <div className="space-y-4">
      {/* Role Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {safeRoles.map((role) => {
          const permissionCount = role.permissions?.length || 0;
          return (
            <div key={role.name} className="bg-white/5 border border-white/10 rounded-lg p-6 hover:bg-white/10 transition-colors">
              <div className="flex items-center gap-4 mb-4">
                <div 
                  className="w-12 h-12 rounded-lg flex items-center justify-center"
                  style={{ backgroundColor: role.color || '#6b7280' }}
                >
                  <FaShieldAlt className="text-xl text-white" />
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-lg" style={{ color: role.color || '#ffffff' }}>
                    {role.name}
                  </h3>
                  <p className="text-sm text-white/60">{role.description}</p>
                </div>
                {role.is_system && (
                  <div className="bg-blue-500/20 text-blue-300 px-2 py-1 rounded text-xs font-medium">
                    System
                  </div>
                )}
              </div>
              
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-white/70">Permissions</span>
                  <span className="text-sm font-medium text-white">{permissionCount}</span>
                </div>
                
                {role.level !== undefined && (
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-white/70">Access Level</span>
                    <div className="flex items-center gap-1">
                      {[...Array(5)].map((_, i) => (
                        <div
                          key={i}
                          className={`w-2 h-2 rounded-full ${
                            i < (role.level || 0) ? 'bg-brand-500' : 'bg-white/20'
                          }`}
                        />
                      ))}
                      <span className="ml-2 text-xs text-white/60">{role.level}/5</span>
                    </div>
                  </div>
                )}
              </div>
              
              <div className="mt-4 pt-4 border-t border-white/10">
                <button 
                  onClick={() => setSelectedRole(role)}
                  className="w-full py-2 px-4 bg-white/10 hover:bg-white/20 rounded-lg text-sm font-medium transition-colors"
                >
                  View Details
                </button>
              </div>
            </div>
          );
        })}
      </div>
      
      {safeRoles.length === 0 && (
        <div className="text-center py-12 text-white/60">
          <FaShieldAlt className="text-4xl mx-auto mb-3 text-white/30" />
          <p className="text-lg">No roles configured</p>
          <p className="text-sm text-white/40 mt-2">Create your first role to get started</p>
        </div>
      )}
    </div>
  );
}

// Audit Tab Component 
function AuditTab({ auditLogs }) {
  // Ensure auditLogs is always an array
  const safeLogs = Array.isArray(auditLogs) ? auditLogs : [];
  
  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-6">
      <div className="space-y-3 max-h-96 overflow-y-auto">
        {safeLogs.length > 0 ? (
          safeLogs.map((log, idx) => (
            <div key={idx} className="flex items-center gap-4 p-3 bg-white/5 rounded-lg">
              <div className="w-8 h-8 bg-brand-500/20 rounded-full flex items-center justify-center">
                <FaHistory className="text-xs text-brand-400" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium text-white">{log.action}</span>
                  <span className="text-white/60">by user {log.user_id}</span>
                  <span className="text-xs text-brand-400">
                    {new Date(log.timestamp).toLocaleString()}
                  </span>
                </div>
                {log.details && (
                  <div className="text-xs text-white/50 mt-1">
                    {typeof log.details === 'object' ? JSON.stringify(log.details) : log.details}
                  </div>
                )}
              </div>
              <div className="text-xs text-white/40">
                {log.resource_type && `${log.resource_type}:${log.resource_id}`}
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-8 text-white/60">
            <FaHistory className="text-3xl mx-auto mb-2 text-white/30" />
            <p className="text-sm">No audit logs available</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Create User Modal Component
function CreateUserModal({ show, onClose, newUser, setNewUser, roles, onSubmit }) {
  if (!show) return null;
  
  // Ensure roles is always an array
  const safeRoles = Array.isArray(roles) ? roles : [];
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white/10 border border-white/20 rounded-lg p-6 w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-6">
          <h3 className="text-xl font-semibold text-white">Create New User</h3>
          <button 
            onClick={onClose}
            className="text-white/60 hover:text-white"
          >
            <FaTimes />
          </button>
        </div>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-white/70 mb-2">Username *</label>
            <input
              type="text"
              value={newUser.username}
              onChange={(e) => setNewUser({...newUser, username: e.target.value})}
              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
              placeholder="Enter username"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-white/70 mb-2">Email *</label>
            <input
              type="email"
              value={newUser.email}
              onChange={(e) => setNewUser({...newUser, email: e.target.value})}
              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
              placeholder="Enter email"
              required
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-white/70 mb-2">Full Name</label>
            <input
              type="text"
              value={newUser.fullName}
              onChange={(e) => setNewUser({...newUser, fullName: e.target.value})}
              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
              placeholder="Enter full name (optional)"
            />
          </div>
          
          <div className="flex items-center gap-2">
            <input
              id="autoPassword"
              type="checkbox"
              checked={!!newUser.autoPassword}
              onChange={(e) => setNewUser({ ...newUser, autoPassword: e.target.checked })}
              className="w-4 h-4 text-brand-500 bg-white/10 border-white/20 rounded focus:ring-brand-500"
            />
            <label htmlFor="autoPassword" className="text-sm text-white/70">Generate a secure temporary password</label>
          </div>

          {!newUser.autoPassword && (
            <>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Password *</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({...newUser, password: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
                  placeholder="Enter password"
                  required
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Confirm Password *</label>
                <input
                  type="password"
                  value={newUser.confirmPassword}
                  onChange={(e) => setNewUser({...newUser, confirmPassword: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
                  placeholder="Confirm password"
                  required
                />
              </div>
            </>
          )}
          
          <div>
            <label className="block text-sm font-medium text-white/70 mb-2">Role</label>
            <select
              value={newUser.role}
              onChange={(e) => setNewUser({...newUser, role: e.target.value})}
              className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white focus:ring-2 focus:ring-brand-500"
            >
              {safeRoles.map(role => (
                <option key={role.name} value={role.name} style={{ backgroundColor: '#1f2937' }}>
                  {role.name} - {role.description}
                </option>
              ))}
            </select>
          </div>
          
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="mustChangePassword"
              checked={newUser.mustChangePassword}
              onChange={(e) => setNewUser({...newUser, mustChangePassword: e.target.checked})}
              className="w-4 h-4 text-brand-500 bg-white/10 border-white/20 rounded focus:ring-brand-500"
            />
            <label htmlFor="mustChangePassword" className="text-sm text-white/70">
              Require password change on first login
            </label>
          </div>
        </div>
        
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            className="px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded text-white transition-colors"
          >
            Create User
          </button>
        </div>
      </div>
    </div>
  );
}

// Role Details Modal
function RoleDetailsModal({ role, onClose }) {
  const gd = useGlobalData();
  const [permissions, setPermissions] = React.useState([]);
  const [localRole, setLocalRole] = React.useState(role || null);
  const [selectedPerms, setSelectedPerms] = React.useState(new Set(role?.permissions || []));
  const [editMode, setEditMode] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const [filter, setFilter] = React.useState('');

  React.useEffect(() => {
    setLocalRole(role || null);
    setSelectedPerms(new Set(role?.permissions || []));
    setEditMode(false);
    setError('');
  }, [role]);

  React.useEffect(() => {
    let cancelled = false;
    async function loadPermissions() {
      try {
        const r = await fetch(`${API}/users/permissions`, { headers: authHeaders() });
        if (!r.ok) return;
        const data = await r.json();
        if (!cancelled) setPermissions(Array.isArray(data.permissions) ? data.permissions : []);
      } catch {}
    }
    loadPermissions();
    return () => { cancelled = true; };
  }, [role?.name]);

  const permsByCategory = React.useMemo(() => {
    const grouped = {};
    const set = selectedPerms;
    permissions.forEach((p) => {
      const cat = p.category || 'uncategorized';
      if (!grouped[cat]) grouped[cat] = [];
      if (filter && !p.name.toLowerCase().includes(filter.toLowerCase())) return;
      grouped[cat].push({ ...p, checked: set.has(p.name) });
    });
    Object.keys(grouped).forEach(cat => grouped[cat].sort((a, b) => a.name.localeCompare(b.name)));
    return grouped;
  }, [permissions, selectedPerms, filter]);

  if (!localRole) return null;

  const togglePerm = (name) => {
    setSelectedPerms((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  };

  const selectAllCategory = (cat, value) => {
    setSelectedPerms((prev) => {
      const next = new Set(prev);
      (permsByCategory[cat] || []).forEach((p) => {
        if (value) next.add(p.name); else next.delete(p.name);
      });
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const body = { description: localRole.description, permissions: Array.from(selectedPerms) };
      const resp = await fetch(`${API}/users/roles/${encodeURIComponent(localRole.name)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(body)
      });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = payload?.detail || payload?.message || `HTTP ${resp.status}`;
        throw new Error(msg);
      }
      const updated = payload.role || { ...localRole, permissions: Array.from(selectedPerms) };
      setLocalRole(updated);
      setEditMode(false);
      // refresh global roles list
      gd?.__refreshBG && gd.__refreshBG('roles', `${API}/users/roles`, (d) => d.roles || []);
    } catch (e) {
      setError(e.message || 'Failed to update role');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
      <div className="bg-ink/95 backdrop-blur border border-white/10 rounded-xl p-6 w-full max-w-4xl max-h-[85vh] overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-xl font-semibold text-white">{localRole.name}</h3>
            <p className="text-white/70 text-sm">{localRole.description}</p>
          </div>
          <div className="flex items-center gap-2">
            {localRole.is_system && <span className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded">system</span>}
            {!editMode && (
              <button
                onClick={() => setEditMode(true)}
                className="px-3 py-1 rounded bg-white/10 hover:bg-white/20 text-white/80 text-sm"
              >Edit</button>
            )}
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 rounded mb-3 text-sm">{error}</div>
        )}

        {editMode && (
          <div className="mb-3 flex items-center gap-2">
            <input
              className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white"
              placeholder="Filter permissions"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <button
              onClick={() => setSelectedPerms(new Set(permissions.map(p => p.name)))}
              className="px-3 py-2 rounded bg-white/10 text-white/80 hover:bg-white/20 text-sm"
            >Select all</button>
            <button
              onClick={() => setSelectedPerms(new Set())}
              className="px-3 py-2 rounded bg-white/10 text-white/80 hover:bg-white/20 text-sm"
            >Clear</button>
          </div>
        )}

        <div className="space-y-4">
          {Object.entries(permsByCategory).length === 0 ? (
            <div className="text-white/60">No permissions available.</div>
          ) : (
            Object.entries(permsByCategory).map(([cat, perms]) => (
              <div key={cat} className="bg-gray-800/50 border border-white/10 rounded p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-white/80 font-medium">{cat.replace(/_/g,' ')}</div>
                  {editMode && (
                    <div className="flex items-center gap-2 text-xs text-white/70">
                      <button onClick={() => selectAllCategory(cat, true)} className="px-2 py-1 bg-white/10 rounded">All</button>
                      <button onClick={() => selectAllCategory(cat, false)} className="px-2 py-1 bg-white/10 rounded">None</button>
                    </div>
                  )}
                </div>
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-1">
                  {perms.map(p => (
                    <li key={p.name} className="text-sm text-white/80 flex items-center gap-2">
                      {editMode ? (
                        <label className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={p.checked}
                            onChange={() => togglePerm(p.name)}
                          />
                          <span>{p.name}</span>
                        </label>
                      ) : (
                        <span>{p.name}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>

        <div className="flex justify-end gap-3 mt-6">
          {editMode && (
            <>
              <button
                onClick={() => { setEditMode(false); setSelectedPerms(new Set(localRole.permissions || [])); setFilter(''); setError(''); }}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-white"
                disabled={saving}
              >Cancel</button>
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded text-white disabled:opacity-50"
                disabled={saving}
              >{saving ? 'Saving…' : 'Save'}</button>
            </>
          )}
          <button onClick={onClose} className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-white">Close</button>
        </div>
      </div>
    </div>
  );
}
export default App;
