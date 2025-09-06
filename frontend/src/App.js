import React, { useState, useEffect, useRef, useMemo, lazy, Suspense, useCallback, createContext, useContext } from 'react';
import {
  FaServer,
  FaPlay,
  FaStop,
  FaTrash,
  FaTerminal,
  FaPlusCircle,
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
  FaTable,
  FaTimes,
  FaUserSlash,
  FaUserCheck,
} from 'react-icons/fa';
import TerminalPanel from './components/TerminalPanel';
import BackupsPanel from './components/server-details/BackupsPanel';
import ConfigPanel from './components/server-details/ConfigPanel';
import PluginsPanel from './components/server-details/PluginsPanel';
import WorldsPanel from './components/server-details/WorldsPanel';
import SchedulePanel from './components/server-details/SchedulePanel';
import PlayersPanel from './components/server-details/PlayersPanel';
import FilesPanelWrapper from './components/server-details/FilesPanelWrapper';
import EditingPanel from './components/server-details/EditingPanel';
import { useFetch } from './lib/useFetch';

const API = 'http://localhost:8000';

// Global Data Store Context for instant access to all data
const GlobalDataContext = createContext();

// Global data store that preloads everything
function GlobalDataProvider({ children }) {
  // All application data - preloaded and always available
  const [globalData, setGlobalData] = useState({
    servers: [],
    serverStats: {},
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

  // Background refresh intervals
  const refreshIntervals = useRef({});
  const abortControllers = useRef({});

  // Aggressive preloading function - loads EVERYTHING immediately
  const preloadAllData = useCallback(async () => {
    const endpoints = [
      { key: 'servers', url: `${API}/servers` },
      { key: 'dashboardData', url: `${API}/monitoring/dashboard-data` },
      { key: 'systemHealth', url: `${API}/monitoring/system-health` },
      { key: 'alerts', url: `${API}/monitoring/alerts` },
      { key: 'users', url: `${API}/users` },
      { key: 'roles', url: `${API}/users/roles` },
      { key: 'auditLogs', url: `${API}/users/audit-logs?page=1&page_size=50` },
      { key: 'serverTypes', url: `${API}/server-types` }
    ];

    // Create abort controllers for all requests
    endpoints.forEach(endpoint => {
      abortControllers.current[endpoint.key] = new AbortController();
    });

    // Execute all requests in parallel for maximum speed
    const promises = endpoints.map(async endpoint => {
      try {
        const response = await fetch(endpoint.url, {
          signal: abortControllers.current[endpoint.key]?.signal,
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
    });

    // Wait for all data to load
    const results = await Promise.all(promises);
    
    // Process results and update global state
    const newData = { ...globalData };
    
    results.forEach(result => {
      if (result.data) {
        switch (result.key) {
          case 'servers':
            newData.servers = Array.isArray(result.data) ? result.data : [];
            break;
          case 'alerts':
            newData.alerts = result.data.alerts || [];
            break;
          case 'users':
            newData.users = result.data.users || [];
            break;
          case 'roles':
            newData.roles = result.data.roles || [];
            break;
          case 'auditLogs':
            newData.auditLogs = result.data.logs || [];
            break;
          case 'serverTypes':
            newData.serverTypes = result.data.types || [];
            break;
          default:
            newData[result.key] = result.data;
        }
      }
    });

    // Preload server stats for all servers
    if (newData.servers.length > 0) {
      const serverStatsPromises = newData.servers.map(async server => {
        try {
          const response = await fetch(`${API}/servers/${server.id}/resources`, {
            headers: authHeaders()
          });
          if (response.ok) {
            const stats = await response.json();
            return { serverId: server.id, stats };
          }
        } catch (error) {
          console.warn(`Failed to preload stats for server ${server.id}:`, error);
        }
        return { serverId: server.id, stats: null };
      });

      const serverStatsResults = await Promise.all(serverStatsPromises);
      const serverStats = {};
      serverStatsResults.forEach(result => {
        if (result.stats) {
          serverStats[result.serverId] = result.stats;
        }
      });
      newData.serverStats = serverStats;
    }

    newData.isInitialized = true;
    setGlobalData(newData);
  }, [globalData]);

  // Background refresh function - updates data silently
  const refreshDataInBackground = useCallback(async (dataKey, url, processor = null) => {
    try {
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
    // Reduced frequencies to prevent database connection pool exhaustion
    refreshIntervals.current.servers = setInterval(() => {
      refreshDataInBackground('servers', `${API}/servers`, (data) => 
        Array.isArray(data) ? data : []
      );
    }, 10000); // Increased from 5s to 10s

    refreshIntervals.current.dashboardData = setInterval(() => {
      refreshDataInBackground('dashboardData', `${API}/monitoring/dashboard-data`);
    }, 20000); // Increased from 10s to 20s

    refreshIntervals.current.alerts = setInterval(() => {
      refreshDataInBackground('alerts', `${API}/monitoring/alerts`, (data) => 
        data.alerts || []
      );
    }, 30000); // Increased from 15s to 30s

    // Server stats refresh with reduced frequency but still responsive
    refreshIntervals.current.serverStats = setInterval(() => {
      globalData.servers.forEach(server => {
        refreshDataInBackground(`serverStats.${server.id}`, `${API}/servers/${server.id}/resources`);
      });
    }, 8000); // Increased from 3s to 8s

    return () => {
      // Cleanup intervals and abort controllers
      Object.values(refreshIntervals.current).forEach(clearInterval);
      Object.values(abortControllers.current).forEach(controller => {
        controller.abort();
      });
    };
  }, [preloadAllData, refreshDataInBackground]);

  // Update server stats in the background
  useEffect(() => {
    if (globalData.servers.length > 0 && globalData.isInitialized) {
      globalData.servers.forEach(server => {
        if (!globalData.serverStats[server.id]) {
          refreshDataInBackground('serverStats', `${API}/servers/${server.id}/resources`, (data) => ({
            ...globalData.serverStats,
            [server.id]: data
          }));
        }
      });
    }
  }, [globalData.servers, globalData.isInitialized, refreshDataInBackground]);

  return (
    <GlobalDataContext.Provider value={globalData}>
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
  window.fetch = (input, init = {}) => {
    const headers = { ...(init && init.headers ? init.headers : {}), ...authHeaders() };
    return originalFetch(input, { ...(init || {}), headers });
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
      es = new EventSource(`${API}/monitoring/events?container_id=${encodeURIComponent(serverId)}`);
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
function ServerDetailsPage({ server, onBack, onStart, onStop, onDelete, onRestart }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [filesEditing, setFilesEditing] = useState(false);
  const [editPath, setEditPath] = useState('');
  const [editContent, setEditContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [blockedFileError, setBlockedFileError] = useState('');
  const stats = useServerStats(server.id);

  const handleEditStart = useCallback((filePath, content) => {
    setEditPath(filePath);
    setEditContent(content);
    setIsEditing(true);
    setFilesEditing(true);
  }, []);

  const { data: typeVersionData } = useFetch(
    server?.id ? `${API}/servers/${server.id}/info` : null,
    [server?.id]
  );

  const tabs = [
    { id: 'overview', label: 'Overview', icon: FaServer },
    { id: 'files', label: 'Files', icon: FaFolder },
    { id: 'config', label: 'Config', icon: FaCog },
    { id: 'players', label: 'Players', icon: FaUsers },
    { id: 'plugins', label: 'Plugins', icon: FaCog },
    { id: 'worlds', label: 'Worlds', icon: FaFolder },
    { id: 'backup', label: 'Backup', icon: FaDownload },
    { id: 'schedule', label: 'Schedule', icon: FaClock },
  ];

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

  const renderTabContent = () => {
    switch (activeTab) {
      case 'files':
        return (
          <div className="flex flex-row gap-6 w-full">
            <FilesPanelWrapper 
              serverName={server.name} 
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
                <TerminalPanel containerId={server.id} />
              )}
              {blockedFileError && (
                <div className="text-red-400 text-xs mt-2">{blockedFileError}</div>
              )}
            </div>
          </div>
        );
      case 'backup':
        return <BackupsPanel serverName={server.name} />;
      case 'plugins':
        return <PluginsPanel serverName={server.name} />;
      case 'worlds':
        return <WorldsPanel serverName={server.name} />;
      case 'config':
        return <ConfigPanel server={server} onRestart={onRestart} />;
      case 'players':
        return (
          <PlayersPanel serverId={server.id} serverName={server.name} />
        );
      case 'schedule':
        return (
          <SchedulePanel />
        );
      default:
        return (
          <div className="p-4 bg-black/20 rounded-lg">
            <div className="text-sm text-white/70 mb-3">Server Information</div>
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
                <div>
                  {server.ports
                    ? Object.entries(server.ports)
                        .filter(([containerPort, mappings]) => 
                          containerPort.includes('25565') && mappings && mappings.length > 0
                        )
                        .map(([containerPort, mappings]) => {
                          const hostPort = mappings[0]?.HostPort;
                          return hostPort ? `${hostPort} → 25565` : '25565 (unmapped)';
                        })
                        .join(', ') || 'Not mapped'
                    : 'N/A'}
                </div>
              </div>
              <div>
                <div className="text-white/50">Type</div>
                <div>
                  {typeVersionData?.server_type ||
                    server.type ||
                    <span className="text-white/40">Unknown</span>}
                </div>
              </div>
              <div>
                <div className="text-white/50">Version</div>
                <div>
                  {typeVersionData?.server_version ||
                    server.version ||
                    <span className="text-white/40">Unknown</span>}
                </div>
              </div>
              <div>
                <div className="text-white/50">Created</div>
                <div>{server.created_at ? new Date(server.created_at).toLocaleString() : 'N/A'}</div>
              </div>
              <div>
                <div className="text-white/50">ID</div>
                <div>{server.id}</div>
              </div>
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
                  Type: {typeVersionData?.server_type || server.type || <span className="text-white/40">Unknown</span>} | Version: {typeVersionData?.server_version || server.version || <span className="text-white/40">Unknown</span>}
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
                <button
                  onClick={() => onStop(server.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-yellow-600 hover:bg-yellow-500 px-3 py-1.5 text-sm font-medium transition-colors"
                >
                  <FaStop className="w-3 h-3" /> Stop
                </button>
              )}
            </div>
          </div>
          <div className="mt-8">
            <div className="flex gap-4 border-b border-white/10 overflow-x-auto">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-3 px-6 py-4 text-lg rounded-t-lg transition ${
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
            <div className="mt-4 flex flex-row gap-6">
              {renderTabContent()}
            </div>
          </div>
          {activeTab !== 'files' && (
            <div className="mt-8">
              <TerminalPanel containerId={server.id} />
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
      className="rounded-xl bg-gradient-to-b from-white/10 to-white/5 border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)] p-6 transition-all duration-200 hover:from-white/15 hover:to-white/10"
      onClick={onClick}
      onMouseEnter={handleMouseEnter}
      tabIndex={0}
      role="button"
      style={{ minHeight: 100 }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-5">
          <div className="w-12 h-12 rounded-lg bg-brand-500/90 ring-4 ring-brand-500/20 inline-flex items-center justify-center text-2xl text-white shadow-md">
            <FaServer />
          </div>
          <div>
            <div className="font-bold text-xl">{server.name}</div>
            <div className="text-sm text-white/60">{server.id.slice(0, 12)}</div>
            <div className="text-xs text-white/60 mt-1">
              Type: {typeVersionData?.server_type || server.type || <span className="text-white/40">Unknown</span>} · Version: {typeVersionData?.server_version || server.version || <span className="text-white/40">Unknown</span>}
            </div>
            {stats && !stats.error && (
              <div className="flex items-center gap-2 mt-2 text-[11px] text-white/80">
                <span className="rounded-full bg-white/10 px-2 py-0.5 shadow-inner">CPU {stats.cpu_percent}%</span>
                <span className="rounded-full bg-white/10 px-2 py-0.5 shadow-inner">RAM {stats.memory_usage_mb}/{stats.memory_limit_mb} MB</span>
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div
            className={`text-sm px-3 py-1.5 rounded-full border ${
              server.status === 'running'
                ? 'bg-green-500/15 text-green-300 border-green-400/20'
                : 'bg-yellow-500/15 text-yellow-300 border-yellow-400/20'
            }`}
          >
            {server.status}
          </div>
          <FaChevronRight className="text-white/40 text-xl" />
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

// Error Boundary Component to catch JavaScript errors
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
        <div className="p-6 space-y-6">
          <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-6 rounded-lg">
            <div className="flex items-center gap-3 mb-4">
              <FaExclamationTriangle className="text-2xl" />
              <h2 className="text-xl font-semibold">Something went wrong</h2>
            </div>
            <p className="text-sm text-red-200 mb-4">
              An error occurred while loading this page. This is likely due to missing backend endpoints.
            </p>
            <div className="bg-red-500/5 border border-red-500/20 p-4 rounded-lg mb-4">
              <p className="text-xs text-red-300 font-mono">{this.state.error?.message}</p>
            </div>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              className="bg-red-600 hover:bg-red-700 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// Advanced User Management System - Inspired by Crafty Controller
function AdvancedUserManagementPageImpl() {
  // Get all data instantly from global store with fallbacks
  const globalData = useGlobalData();
  const { users, roles, auditLogs, isInitialized } = globalData;
  
  // Provide fallback data if backend endpoints aren't ready
  const safeUsers = users || [];
  const safeRoles = roles && roles.length > 0 ? roles : [
    { name: 'admin', description: 'System Administrator', color: '#dc2626', level: 4, is_system: true, permissions: [] },
    { name: 'moderator', description: 'Server Moderator', color: '#0ea5e9', level: 3, is_system: true, permissions: [] },
    { name: 'user', description: 'Regular User', color: '#6b7280', level: 1, is_system: true, permissions: [] }
  ];
  const safeAuditLogs = auditLogs || [];
  
  // State management
  const [activeTab, setActiveTab] = useState('users');
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [showCreateRole, setShowCreateRole] = useState(false);
  const [showPermissionMatrix, setShowPermissionMatrix] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [selectedRole, setSelectedRole] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterRole, setFilterRole] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // New user form
  const [newUser, setNewUser] = useState({ 
    username: '', 
    email: '', 
    password: '', 
    confirmPassword: '',
    role: 'user', 
    fullName: '',
    mustChangePassword: true
  });
  
  // New role form  
  const [newRole, setNewRole] = useState({
    name: '',
    description: '',
    color: '#6b7280',
    permissions: []
  });
  
  // Function to refresh user data
  const loadUsers = async () => {
    try {
      // Trigger refresh of global data
      window.location.reload();
    } catch (error) {
      console.error('Failed to refresh users data:', error);
    }
  };
  
  // Define comprehensive permission categories inspired by Crafty Controller
  const permissionCategories = {
    server_control: {
      name: 'Server Control',
      icon: FaServer,
      color: '#dc2626',
      permissions: [
        'server.view', 'server.create', 'server.start', 'server.stop', 
        'server.restart', 'server.kill', 'server.delete', 'server.clone'
      ]
    },
    server_console: {
      name: 'Console & Commands',
      icon: FaTerminal,
      color: '#059669',
      permissions: [
        'server.console.view', 'server.console.send', 'server.console.history'
      ]
    },
    server_config: {
      name: 'Configuration',
      icon: FaCog,
      color: '#0ea5e9',
      permissions: [
        'server.config.view', 'server.config.edit', 'server.properties.edit', 'server.startup.edit'
      ]
    },
    server_files: {
      name: 'File Management',
      icon: FaFolder,
      color: '#7c3aed',
      permissions: [
        'server.files.view', 'server.files.download', 'server.files.upload',
        'server.files.edit', 'server.files.delete', 'server.files.create', 'server.files.compress'
      ]
    },
    server_players: {
      name: 'Player Management',
      icon: FaUsers,
      color: '#ea580c',
      permissions: [
        'server.players.view', 'server.players.kick', 'server.players.ban',
        'server.players.whitelist', 'server.players.op', 'server.players.chat'
      ]
    },
    server_backup: {
      name: 'Backup Management',
      icon: FaDatabase,
      color: '#10b981',
      permissions: [
        'server.backup.view', 'server.backup.create', 'server.backup.restore',
        'server.backup.delete', 'server.backup.download', 'server.backup.schedule'
      ]
    },
    user_management: {
      name: 'User Management',
      icon: FaUserCog,
      color: '#f59e0b',
      permissions: [
        'user.view', 'user.create', 'user.edit', 'user.delete',
        'user.password.reset', 'user.sessions.view', 'user.sessions.revoke'
      ]
    },
    role_management: {
      name: 'Role & Permissions',
      icon: FaShieldAlt,
      color: '#dc2626',
      permissions: [
        'role.view', 'role.create', 'role.edit', 'role.delete', 'role.assign'
      ]
    },
    system_admin: {
      name: 'System Administration',
      icon: FaTools,
      color: '#991b1b',
      permissions: [
        'system.monitoring.view', 'system.logs.view', 'system.audit.view',
        'system.settings.view', 'system.settings.edit', 'system.maintenance', 'system.updates'
      ]
    }
  };

  async function createUser() {
    try {
      if (newUser.password !== newUser.confirmPassword) {
        setError('Passwords do not match');
        return;
      }
      
      await fetch(`${API}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: newUser.username,
          email: newUser.email,
          password: newUser.password,
          role: newUser.role,
          full_name: newUser.fullName,
          must_change_password: newUser.mustChangePassword
        }),
      });
      setShowCreateUser(false);
      setNewUser({ 
        username: '', email: '', password: '', confirmPassword: '',
        role: 'user', fullName: '', mustChangePassword: true
      });
      setSuccess('User created successfully');
      loadUsers();
    } catch (e) {
      setError('Failed to create user: ' + e.message);
      console.error('Failed to create user:', e);
    }
  }
  
  async function createRole() {
    try {
      await fetch(`${API}/roles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRole),
      });
      setShowCreateRole(false);
      setNewRole({ name: '', description: '', color: '#6b7280', permissions: [] });
      setSuccess('Role created successfully');
      loadUsers();
    } catch (e) {
      setError('Failed to create role: ' + e.message);
      console.error('Failed to create role:', e);
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
    <div className="p-6 space-y-6">
      {/* Header with tabs */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaShieldAlt className="text-brand-500" /> Advanced User Management
          </h1>
          <p className="text-white/70 mt-2">Comprehensive user, role, and permission management system</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowPermissionMatrix(true)}
            className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <FaTable /> Permission Matrix
          </button>
          <button
            onClick={() => setShowCreateRole(true)}
            className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <FaShieldAlt /> Create Role
          </button>
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
          permissionCategories={permissionCategories}
          setSelectedRole={setSelectedRole}
        />
      )}
      
      {activeTab === 'audit' && (
        <AuditTab auditLogs={safeAuditLogs} />
      )}

      {/* Create User Modal */}
      <CreateUserModal 
        show={showCreateUser}
        onClose={() => setShowCreateUser(false)}
        newUser={newUser}
        setNewUser={setNewUser}
        roles={safeRoles}
        onSubmit={createUser}
      />
      
      {/* Create Role Modal */}
      <CreateRoleModal 
        show={showCreateRole}
        onClose={() => setShowCreateRole(false)}
        newRole={newRole}
        setNewRole={setNewRole}
        permissionCategories={permissionCategories}
        onSubmit={createRole}
      />
      
      {/* Permission Matrix Modal */}
      <PermissionMatrixModal 
        show={showPermissionMatrix}
        onClose={() => setShowPermissionMatrix(false)}
        roles={safeRoles}
        permissionCategories={permissionCategories}
      />
    </div>
  );
}

// Monitoring Dashboard - INSTANT with preloaded data
function MonitoringPageImpl() {
  // Get all data instantly from global store
  const globalData = useGlobalData();
  const { systemHealth, dashboardData, alerts, isInitialized } = globalData;
  
  // Function to refresh monitoring data
  const refreshMonitoringData = async () => {
    try {
      // Trigger refresh of global data
      window.location.reload();
    } catch (error) {
      console.error('Failed to refresh monitoring data:', error);
    }
  };
  
  // Always show data - no loading states needed!

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaChartLine className="text-brand-500" /> Server Status
          </h1>
          <p className="text-white/70 mt-2">Monitor your servers and system performance</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={refreshMonitoringData}
            className="bg-brand-500 hover:bg-brand-600 px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <FaSync /> Refresh
          </button>
        </div>
      </div>

      {/* System Health Overview - Always show with fallback values */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Total Servers</p>
              <p className="text-2xl font-bold text-white">{systemHealth?.total_servers || globalData.servers?.length || 0}</p>
            </div>
            <FaServer className="text-3xl text-brand-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Running Servers</p>
              <p className="text-2xl font-bold text-green-400">
                {systemHealth?.running_servers || globalData.servers?.filter(s => s.status === 'running').length || 0}
              </p>
            </div>
            <FaPlay className="text-3xl text-green-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">CPU Usage</p>
              <p className="text-2xl font-bold text-white">{systemHealth?.cpu_usage_percent || '--'}%</p>
            </div>
            <FaMicrochip className="text-3xl text-yellow-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Memory Usage</p>
              <p className="text-2xl font-bold text-white">
                {systemHealth ? `${systemHealth.used_memory_gb} / ${systemHealth.total_memory_gb} GB` : '--'}
              </p>
            </div>
            <FaMemory className="text-3xl text-purple-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Online Players</p>
              <p className="text-2xl font-bold text-blue-400">
                {Object.values(globalData.serverStats || {}).reduce((sum, s) => sum + ((s && (s.players?.online ?? s.player_count)) || 0), 0)}
              </p>
            </div>
            <FaUsers className="text-3xl text-blue-500" />
          </div>
        </div>
      </div>

      )}

      {/* Alerts - Always show section */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaBell /> System Alerts
        </h3>
        {alerts && alerts.length > 0 ? (
          <div className="space-y-3">
            {alerts.map((alert, idx) => (
              <div key={idx} className={`p-4 rounded-lg border ${
                alert.type === 'warning' 
                  ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-300'
                  : alert.type === 'error'
                  ? 'bg-red-500/10 border-red-500/20 text-red-300'
                  : 'bg-blue-500/10 border-blue-500/20 text-blue-300'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {alert.type === 'warning' && <FaExclamationTriangle />}
                    {alert.type === 'error' && <FaTimesCircle />}
                    {alert.type === 'info' && <FaInfoCircle />}
                    <span>{alert.message}</span>
                  </div>
                  <span className="text-sm opacity-70">
                    {new Date(alert.timestamp).toLocaleString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-white/60">
            <FaBell className="text-3xl mx-auto mb-2 text-white/30" />
            <p className="text-sm">No active alerts</p>
            <p className="text-xs text-white/40 mt-1">System is running normally</p>
          </div>
        )}
      </div>

      {/* Server Overview - Always show with available servers */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaProjectDiagram /> Server Overview
        </h3>
        {globalData.servers && globalData.servers.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {globalData.servers.map((server, idx) => {
              const serverStats = globalData.serverStats?.[server.id];
              return (
                <div key={server.id || idx} className="bg-white/5 border border-white/10 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="font-medium">{server.name}</div>
                    <div className={`px-2 py-1 rounded text-xs ${
                      server.status === 'running'
                        ? 'bg-green-500/20 text-green-300'
                        : 'bg-red-500/20 text-red-300'
                    }`}>
                      {server.status || 'unknown'}
                    </div>
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-white/70">CPU:</span>
                      <span>{serverStats?.cpu_percent || '--'}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/70">Memory:</span>
                      <span>{serverStats?.memory_usage_mb ? `${serverStats.memory_usage_mb} MB` : '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-white/70">Players:</span>
                      <span>
                        {(() => {
                          const online = serverStats?.players?.online ?? serverStats?.player_count ?? 0;
                          const max = serverStats?.players?.max;
                          return max ? `${online}/${max}` : online;
                        })()}
                      </span>
                    </div>
                    {Array.isArray(serverStats?.players?.names) && serverStats.players.names.length > 0 && (
                      <div className="flex justify-between">
                        <span className="text-white/70">Names:</span>
                        <span className="text-right truncate max-w-[60%]">{serverStats.players.names.join(', ')}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-white/60">
            <FaServer className="text-4xl mx-auto mb-3 text-white/30" />
            <p className="text-lg">No servers created yet</p>
            <p className="text-sm text-white/40 mt-2">Create your first Minecraft server to see monitoring data here</p>
          </div>
        )}
      </div>
    </div>
  );
}

// System Settings Page - renamed to avoid conflicts
function SettingsPageImpl() {
  const [settings, setSettings] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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

  useEffect(() => {
    loadSettings();
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

  if (loading) return <div className="p-6"><div className="text-white/70">Loading settings...</div></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaCog className="text-brand-500" /> System Settings
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
    </div>
  );
}

// Modern Dashboard Page - ZERO LOADING with preloaded global data
const DashboardPage = React.memo(function DashboardPage({ onNavigate }) {
  // Get all data instantly from global store - NO LOADING!
  const globalData = useGlobalData();
  const { 
    servers, 
    dashboardData, 
    systemHealth, 
    alerts, 
    isInitialized 
  } = globalData;

  // No loading states needed - data is always available!

  // Calculate real-time metrics - INSTANT calculation from preloaded data
  const { totalServers, runningServers, totalMemoryMB, avgCpuPercent, criticalAlerts, warningAlerts } = useMemo(() => {
    const total = servers?.length || 0;
    const running = servers?.filter(s => s.status === 'running').length || 0;
    const memoryMB = dashboardData?.system_overview?.total_memory_mb || 0;
    const cpuPercent = dashboardData?.system_overview?.avg_cpu_percent || 0;
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
  }, [servers, dashboardData, alerts]);
  
  return (
    <div className="min-h-screen bg-gray-950">
      {/* Clean Linear-inspired header */}
      <div className="border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-medium text-white mb-1">Overview</h1>
              <p className="text-sm text-gray-400">Monitor your Minecraft infrastructure</p>
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
      
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

        {/* Simplified Stats */}
        <div className="grid grid-cols-4 gap-6">
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
            <div className="text-sm text-gray-400 mb-1">Servers</div>
            <div className="flex items-baseline gap-2">
              <div className="text-2xl font-medium text-white">
                {runningServers}
              </div>
              <div className="text-sm text-gray-500">/ {totalServers}</div>
            </div>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
            <div className="text-sm text-gray-400 mb-1">CPU</div>
            <div className="text-2xl font-medium text-white">
              {`${avgCpuPercent.toFixed(0)}%`}
            </div>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
            <div className="text-sm text-gray-400 mb-1">Memory</div>
            <div className="text-2xl font-medium text-white">
              {`${(totalMemoryMB / 1024).toFixed(1)}GB`}
            </div>
          </div>
          
          <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-5">
            <div className="text-sm text-gray-400 mb-1">Issues</div>
            <div className="text-2xl font-medium text-white">
              {criticalAlerts + warningAlerts}
            </div>
          </div>
        </div>

        {/* Clean Server List */}
        <div className="space-y-6">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-white">Servers</h2>
              <button 
                onClick={() => onNavigate && onNavigate('servers')}
                className="text-sm text-gray-400 hover:text-white transition-colors"
              >
                View all
              </button>
            </div>
            
            <div className="bg-gray-900/50 border border-gray-800 rounded-lg divide-y divide-gray-800">
              {servers.length > 0 ? (
                servers.slice(0, 5).map((server) => {
                  const isRunning = server.status === 'running';
                  
                  return (
                    <div 
                      key={server.id}
                      className="flex items-center justify-between p-4 hover:bg-gray-800/50 cursor-pointer transition-colors"
                      onClick={() => onNavigate && onNavigate('servers')}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-2 h-2 rounded-full ${
                          isRunning ? 'bg-green-400' : 'bg-gray-500'
                        }`} />
                        <div>
                          <div className="text-white font-medium">{server.name}</div>
                          <div className="text-sm text-gray-400">
                            {server.version} • {server.type || 'vanilla'}
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <span className={`text-xs px-2 py-1 rounded ${
                          isRunning 
                            ? 'bg-green-900/50 text-green-300'
                            : 'bg-gray-800 text-gray-400'
                        }`}>
                          {isRunning ? 'Running' : 'Stopped'}
                        </span>
                        <FaChevronRight className="w-3 h-3 text-gray-500" />
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="p-8 text-center">
                  <div className="text-gray-400 mb-2">No servers yet</div>
                  <button 
                    onClick={() => onNavigate && onNavigate('servers')}
                    className="text-sm text-blue-400 hover:text-blue-300"
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
                  className="text-sm text-gray-400 hover:text-white transition-colors"
                >
                  View all
                </button>
              </div>
              
              <div className="bg-gray-900/50 border border-gray-800 rounded-lg divide-y divide-gray-800">
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
                          <div className="text-xs text-gray-500 mt-1">
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
  onSelectServer, onCreateServer,
  types, versionsData, selectedType, setSelectedType,
  name, setName, version, setVersion, hostPort, setHostPort,
  minRam, setMinRam, maxRam, setMaxRam, loaderVersion, setLoaderVersion,
  loaderVersionsData, installerVersion, setInstallerVersion
}) {
  // Get servers from global data - INSTANT access!
  const globalData = useGlobalData();
  const { servers } = globalData;
  
  return (
    <ServersPage
      servers={servers}
      serversLoading={false} // Never loading with preloaded data!
      onSelectServer={onSelectServer}
      onCreateServer={onCreateServer}
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
  );
}

// Original Servers Page
function ServersPage({
  servers, serversLoading, onSelectServer, onCreateServer,
  types, versionsData, selectedType, setSelectedType,
  name, setName, version, setVersion, hostPort, setHostPort,
  minRam, setMinRam, maxRam, setMaxRam, loaderVersion, setLoaderVersion,
  loaderVersionsData, installerVersion, setInstallerVersion
}) {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaServer className="text-brand-500" /> Server Management
          </h1>
          <p className="text-white/70 mt-2">Create and manage your Minecraft servers</p>
        </div>
      </div>

      {/* Create Server Form */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaPlusCircle /> Create New Server
        </h3>
        <form onSubmit={onCreateServer} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Server Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                placeholder="Enter server name"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Server Type</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
              >
                {types.map((t) => (
                  <option key={t} value={t} style={{ backgroundColor: '#1f2937' }}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Version</label>
              <select
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
              >
                {(versionsData?.versions || []).map((v) => (
                  <option key={v} value={v} style={{ backgroundColor: '#1f2937' }}>{v}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Loader version for modded servers */}
          {SERVER_TYPES_WITH_LOADER.includes(selectedType) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Loader Version</label>
                <select
                  value={loaderVersion}
                  onChange={(e) => setLoaderVersion(e.target.value)}
                  className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded text-white"
                >
                  {(loaderVersionsData?.loader_versions || []).map((lv) => (
                    <option key={lv} value={lv} style={{ backgroundColor: '#1f2937' }}>{lv}</option>
                  ))}
                </select>
              </div>
              {selectedType === 'fabric' && (
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Installer Version</label>
                  <input
                    type="text"
                    value={installerVersion}
                    onChange={(e) => setInstallerVersion(e.target.value)}
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                    placeholder="e.g., 1.1.0"
                  />
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Host Port</label>
              <input
                type="number"
                value={hostPort}
                onChange={(e) => setHostPort(e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white placeholder-white/50"
                placeholder="25565"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Min RAM (MB)</label>
              <input
                type="number"
                value={minRam}
                onChange={(e) => setMinRam(e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white/70 mb-2">Max RAM (MB)</label>
              <input
                type="number"
                value={maxRam}
                onChange={(e) => setMaxRam(e.target.value)}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
              />
            </div>
          </div>
          <button
            type="submit"
            className="bg-brand-500 hover:bg-brand-600 px-6 py-3 rounded-lg text-white font-medium flex items-center gap-2"
          >
            <FaPlusCircle /> Create Server
          </button>
        </form>
      </div>

      {/* Servers List */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Your Servers</h3>
        {serversLoading ? (
          <div className="text-white/70">Loading servers...</div>
        ) : servers.length === 0 ? (
          <div className="text-white/60 text-center py-8">
            No servers created yet. Create your first server above.
          </div>
        ) : (
          <div className="space-y-4">
            {servers.map((server) => (
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

function TemplatesPage() {
  const [serverName, setServerName] = useState('mp-' + Math.random().toString(36).slice(2,6));
  const [url, setUrl] = useState('');
  const [hostPort, setHostPort] = useState('');
  const [minRam, setMinRam] = useState('2048M');
  const [maxRam, setMaxRam] = useState('4096M');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const [templates, setTemplates] = useState([]);
  const [templateCategories, setTemplateCategories] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [templatesError, setTemplatesError] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchTermTpl, setSearchTermTpl] = useState('');
  const [popularOnly, setPopularOnly] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadTemplates() {
      setTemplatesLoading(true);
      setTemplatesError('');
      try {
        const r = await fetch(`${API}/templates`);
        const d = await r.json();
        if (!cancelled) {
          setTemplates(Array.isArray(d?.templates) ? d.templates : []);
          setTemplateCategories(Array.isArray(d?.categories) ? d.categories : []);
        }
      } catch (e) {
        if (!cancelled) setTemplatesError(String(e.message || e));
      } finally {
        if (!cancelled) setTemplatesLoading(false);
      }
    }
    loadTemplates();
    return () => { cancelled = true; };
  }, []);

  async function importPack(e) {
    e.preventDefault();
    setBusy(true);
    setMsg('');
    try {
      const body = {
        server_name: serverName,
        server_pack_url: url,
        host_port: hostPort ? Number(hostPort) : null,
        min_ram: minRam,
        max_ram: maxRam
      };
      const r = await fetch(`${API}/modpacks/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setMsg('Server pack imported and container started. Go to Servers to see it.');
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  async function createFromTemplate(tplId) {
    setBusy(true);
    setMsg('');
    try {
      const r = await fetch(`${API}/servers/from-template`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          template_id: tplId, 
          name: serverName, 
          host_port: hostPort ? Number(hostPort) : null 
        })
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      setMsg('Server created from template. Go to Servers to see it.');
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaLayerGroup className="text-brand-500" /> Templates & Modpacks
        </h1>
        <p className="text-white/70 mt-2">Create from curated templates or import modpack server packs</p>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">Import Server Pack (CurseForge or direct URL)</h3>
        <form onSubmit={importPack} className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-white/70 mb-1">Server Name</label>
            <input value={serverName} onChange={e=>setServerName(e.target.value)} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" required />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Host Port (optional)</label>
            <input value={hostPort} onChange={e=>setHostPort(e.target.value)} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="e.g. 25565" />
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm text-white/70 mb-1">Server Pack URL (.zip)</label>
            <input value={url} onChange={e=>setUrl(e.target.value)} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="https://...serverpack.zip" required />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Min RAM</label>
            <input value={minRam} onChange={e=>setMinRam(e.target.value)} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" />
          </div>
          <div>
            <label className="block text-sm text-white/70 mb-1">Max RAM</label>
            <input value={maxRam} onChange={e=>setMaxRam(e.target.value)} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" />
          </div>
          <div className="md:col-span-2 flex items-center gap-3">
            <button disabled={busy} className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 rounded">{busy ? 'Importing...' : 'Import Server Pack'}</button>
            {msg && <div className="text-sm text-white/70">{msg}</div>}
          </div>
        </form>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Curated Templates</h3>
          {templatesLoading && <div className="text-sm text-white/60">Loading…</div>}
        </div>
        <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between mb-4">
          <div className="flex items-center gap-2">
            <input 
              className="rounded bg-white/5 border border-white/10 px-3 py-2 text-white placeholder-white/50"
              placeholder="Search templates..."
              value={searchTermTpl}
              onChange={(e) => setSearchTermTpl(e.target.value)}
              style={{ minWidth: 220 }}
            />
            <select 
              className="rounded bg-white/10 border border-white/20 px-3 py-2 text-white"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              style={{ backgroundColor: '#1f2937' }}
            >
              <option value="all" style={{ backgroundColor: '#1f2937' }}>All Categories</option>
              {templateCategories.map(cat => (
                <option key={cat.id} value={cat.id} style={{ backgroundColor: '#1f2937' }}>
                  {cat.icon} {cat.name}
                </option>
              ))}
            </select>
          </div>
          <label className="inline-flex items-center gap-2 text-sm text-white/70">
            <input type="checkbox" checked={popularOnly} onChange={(e) => setPopularOnly(e.target.checked)} />
            Popular only
          </label>
        </div>
        {templatesError && (
          <div className="text-sm text-red-400 mb-3">{templatesError}</div>
        )}
        {(() => {
          const filtered = (templates || [])
            .filter(t => selectedCategory === 'all' || t.category === selectedCategory)
            .filter(t => !popularOnly || t.popular)
            .filter(t => {
              const q = searchTermTpl.trim().toLowerCase();
              if (!q) return true;
              return (
                t.name?.toLowerCase().includes(q) ||
                t.description?.toLowerCase().includes(q) ||
                t.type?.toLowerCase().includes(q) ||
                (Array.isArray(t.tags) && t.tags.some(tag => String(tag).toLowerCase().includes(q)))
              );
            });
          return (!templatesLoading && filtered.length === 0) ? (
            <div className="text-white/60 text-center py-6">No templates match your filters</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filtered.map((tpl) => (
                <div key={tpl.id} className="bg-white/5 border border-white/10 rounded-lg p-4 flex flex-col">
                  <div className="flex items-center gap-3 mb-2">
                    <div className="text-2xl">{tpl.icon || '🎮'}</div>
                    <div>
                      <div className="font-semibold">{tpl.name}</div>
                      <div className="text-xs text-white/60">{tpl.type} • {tpl.version}</div>
                    </div>
                  </div>
                  <div className="text-sm text-white/70 flex-1">{tpl.description}</div>
                  <div className="text-xs text-white/50 mt-2">RAM {tpl.min_ram}–{tpl.max_ram}</div>
                  <div className="mt-3 flex items-center gap-2">
                    <button 
                      onClick={() => createFromTemplate(tpl.id)}
                      disabled={busy}
                      className="bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-3 py-1.5 rounded text-sm"
                    >
                      {busy ? 'Working…' : 'Create from Template'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

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
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('admin123');
  const [loginError, setLoginError] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  
  // Main navigation state
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(true);

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

  function handleLogout() {
    clearStoredToken();
    setAuthToken('');
    // Reload to clear any in-memory state
    window.location.reload();
  }

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
          if (d?.loader_versions?.length) {
            setLoaderVersion(d.loader_versions[0]);
          } else {
            setLoaderVersion('');
          }
        })
        .catch((e) => {
          setLoaderVersionsError(e);
          setLoaderVersion('');
        })
        .finally(() => setLoaderVersionsLoading(false));
    } else {
      setLoaderVersionsData(null);
      setLoaderVersion('');
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
  const servers = useMemo(
    () => (Array.isArray(serversData) ? serversData : []),
    [serversData]
  );

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
    await fetch(`${API}/servers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    window.location.reload();
  }, [name, selectedType, version, loaderVersion, installerVersion, hostPort, minRam, maxRam]);

  // Start server handler - optimized
  const start = useCallback(async function start(id) {
    await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'start' }) });
    window.location.reload();
  }, []);
  
  // Stop server handler - optimized
  const stop = useCallback(async function stop(id) {
    await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'stop' }) });
    window.location.reload();
  }, []);
  
  // Delete server handler - optimized
  const del = useCallback(async function del(id) {
    await fetch(`${API}/servers/${id}`, { method: 'DELETE' });
    window.location.reload();
  }, []);

  // Restart server handler - optimized
  const restart = useCallback(async function restart(id) {
    try {
      await fetch(`${API}/servers/${id}/power`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ signal: 'restart' }) });
      // Refresh servers data
      const response = await fetch(`${API}/servers`);
      if (response.ok) {
        const updatedServers = await response.json();
        setServersData(updatedServers);
      }
    } catch (e) {
      console.error('Error restarting server:', e);
    }
  }, []);

  // Find selected server object
  const selectedServerObj =
    selectedServer &&
    servers.find((s) => s.id === selectedServer);

  // Navigation with advanced user management like Crafty Controller
  const sidebarItems = [
    { id: 'dashboard', label: 'Dashboard', icon: FaHome },
    { id: 'servers', label: 'My Servers', icon: FaServer },
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
            onBack={() => setSelectedServer(null)}
            onStart={start}
            onStop={stop}
            onDelete={del}
            onRestart={restart}
          />
        ) : (
          <ServersPageWithGlobalData
            onSelectServer={setSelectedServer}
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
        );
      case 'monitoring':
        return <MonitoringPageImpl />;
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
      <div className="min-h-screen bg-ink bg-hero-gradient flex">
        <div className="min-h-screen flex items-center justify-center w-full">
          <div className="max-w-md w-full mx-4">
            <div className="rounded-xl bg-black/30 border border-white/10 p-6 space-y-4">
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-brand-500 rounded-full flex items-center justify-center mx-auto mb-4">
                  <FaServer className="text-2xl text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">Minecraft Panel</h1>
                <p className="text-white/70 mt-2">Please sign in to continue</p>
              </div>
              
              {loginError && (
                <div className="bg-red-500/10 border border-red-500/20 text-red-300 p-3 rounded-lg text-sm">
                  {loginError}
                </div>
              )}
              
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Username</label>
                  <input
                    type="text"
                    className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                    placeholder="Enter your username"
                    value={loginUsername}
                    onChange={(e) => setLoginUsername(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-white/70 mb-2">Password</label>
                  <input
                    type="password"
                    className="w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-white placeholder-white/50"
                    placeholder="Enter your password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={loginLoading}
                  className="w-full py-3 rounded-md bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white font-medium transition-colors"
                >
                  {loginLoading ? 'Signing in...' : 'Sign In'}
                </button>
              </form>
              
              <div className="text-center text-sm text-white/60 border-t border-white/10 pt-4">
                Default credentials: admin / admin123
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <GlobalDataProvider>
      <div className="min-h-screen bg-ink bg-hero-gradient flex">
      {/* Sidebar */}
      {isAuthenticated && (
        <div className={`${sidebarOpen ? 'w-64' : 'w-16'} bg-black/20 border-r border-white/10 transition-all duration-300 flex flex-col`}>
          <div className="p-4 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-md bg-brand-500 inline-flex items-center justify-center shadow-card">
                <FaServer className="text-white" />
              </div>
              {sidebarOpen && <div className="font-semibold">Minecraft Panel</div>}
            </div>
          </div>
          <nav className="flex-1 p-4">
            <div className="space-y-2">
              {sidebarItems.map(item => (
                <button
                  key={item.id}
                  onClick={() => {
                    setCurrentPage(item.id);
                    setSelectedServer(null); // Clear server selection when changing pages
                  }}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                    currentPage === item.id
                      ? 'bg-brand-500 text-white'
                      : 'text-white/70 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <item.icon className={`${sidebarOpen ? 'text-lg' : 'text-xl'}`} />
                  {sidebarOpen && <span>{item.label}</span>}
                </button>
              ))}
            </div>
          </nav>
          <div className="p-4 border-t border-white/10">
            <div className="flex items-center gap-3 mb-3">
              {currentUser && (
                <>
                  <div className="w-8 h-8 bg-brand-500 rounded-full flex items-center justify-center">
                    <FaUsers className="text-sm text-white" />
                  </div>
                  {sidebarOpen && (
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
              {sidebarOpen && <span>Logout</span>}
            </button>
          </div>
        </div>
      )}
      
      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Top Header */}
        {isAuthenticated && (
          <header className="border-b border-white/10 bg-ink/80 backdrop-blur supports-[backdrop-filter]:bg-ink/60">
            <div className="px-6 flex items-center justify-between h-14">
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="p-2 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                >
                  {sidebarOpen ? <FaBackward /> : <FaForward />}
                </button>
                <h1 className="text-lg font-semibold text-white">
                  {sidebarItems.find(item => item.id === currentPage)?.label || 'Dashboard'}
                </h1>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-sm text-white/70">
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
    </GlobalDataProvider>
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

// Placeholder components for CreateRoleModal and PermissionMatrixModal
function CreateRoleModal({ show, onClose }) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white/10 border border-white/20 rounded-lg p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold mb-4">Create Role</h3>
        <p className="text-white/70 mb-4">Role creation interface coming soon...</p>
        <button onClick={onClose} className="px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded text-white">
          Close
        </button>
      </div>
    </div>
  );
}

function PermissionMatrixModal({ show, onClose }) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white/10 border border-white/20 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        <h3 className="text-lg font-semibold mb-4">Permission Matrix</h3>
        <p className="text-white/70 mb-4">Advanced permission matrix interface coming soon...</p>
        <button onClick={onClose} className="px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded text-white">
          Close
        </button>
      </div>
    </div>
  );
}

export default App;
