import { useState, useEffect, useRef, useMemo } from 'react';
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
} from 'react-icons/fa';

const API = 'http://localhost:8000';

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

function useFetch(url, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!url) return;
    let active = true;
    setLoading(true);
    fetch(url)
      .then(async (r) => {
        const payload = await r.json().catch(() => null);
        if (!r.ok)
          throw new Error(
            (payload && (payload.detail || payload.message)) ||
              `HTTP ${r.status}`
          );
        return payload;
      })
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, deps);

  return { data, loading, error, setData };
}

function useServerStats(serverId) {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (!serverId) return;
    let active = true;
    let interval = null;

    async function fetchStats() {
      try {
        const r = await fetch(`${API}/servers/${serverId}/stats`);
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
        if (active && e.message !== 'HTTP 404') {
          setStats(null);
        }
      }
    }

    fetchStats();
    interval = setInterval(fetchStats, 2000);

    return () => {
      active = false;
      if (interval) clearInterval(interval);
    };
  }, [serverId]);

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

function TerminalPanel({ containerId }) {
  const [cmd, setCmd] = useState('');
  const [logs, setLogs] = useState('');
  const scrollRef = useRef(null);

  useEffect(() => {
    if (!containerId) return;
    let active = true;
    setLogs('');
    fetch(`${API}/servers/${containerId}/logs?tail=200`)
      .then((r) => r.json())
      .then((d) => {
        if (active && d && typeof d.logs === 'string') setLogs(d.logs);
      })
      .catch(() => {
        if (active) setLogs('');
      });
    return () => {
      active = false;
    };
  }, [containerId]);

  useEffect(() => {
    if (!containerId) return;
    let active = true;
    let interval = null;

    async function pollLogs() {
      try {
        const r = await fetch(`${API}/servers/${containerId}/logs?tail=200`);
        const d = await r.json();
        if (active && d && typeof d.logs === 'string') setLogs(d.logs);
      } catch (e) {
        if (active) setLogs('');
      }
    }

    interval = setInterval(pollLogs, 2000);
    return () => {
      active = false;
      if (interval) clearInterval(interval);
    };
  }, [containerId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  function send() {
    if (!cmd.trim()) return;
    fetch(`${API}/servers/${containerId}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd }),
    });
    setCmd('');
  }

  return (
    <div className="p-6 bg-black/20 rounded-lg space-y-4" style={{ minHeight: 600 }}>
      <div className="text-base text-white/70 mb-2">Server Console & Logs (live)</div>
      <div
        ref={scrollRef}
        className="text-sm text-white/70 whitespace-pre-wrap bg-black/30 p-4 rounded max-h-[800px] min-h-[500px] overflow-auto font-mono"
        style={{ fontSize: '1.15rem', lineHeight: '1.5', height: 500 }}
      >
        {logs || <span className="text-white/40">No output yet.</span>}
      </div>
      <div className="flex gap-3 mt-2">
        <input
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          className="flex-1 rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
          placeholder="Type a command (e.g. say hello or op Username)"
        />
        <button
          onClick={send}
          className="inline-flex items-center gap-2 rounded-md bg-brand-500 hover:bg-brand-400 px-4 py-3 font-semibold text-base"
        >
          <FaTerminal /> Send
        </button>
      </div>
    </div>
  );
}

function FilesPanel({ serverName, onEditStateChange }) {
  // This component is now unused, see FilesPanelWrapper in ServerDetailsPage
  return null;
}

function EditingPanel({ editPath, editContent, setEditContent, onSave, onCancel }) {
  return (
    <div className="mt-4">
      <div className="text-xs text-white/70 mb-1">Editing: {editPath}</div>
      <textarea
        className="w-full h-40 rounded bg-black/40 border border-white/10 p-2 text-xs"
        value={editContent}
        onChange={(e) => setEditContent(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <button
          onClick={onSave}
          className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 inline-flex items-center gap-2 text-xs"
        >
          <FaSave /> Save
        </button>
        <button
          onClick={onCancel}
          className="rounded bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function BackupsPanel({ serverName }) {
  const [list, setList] = useState([]);
  async function refresh() {
    const r = await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/backups`
    );
    const d = await r.json();
    setList(d.items || []);
  }
  useEffect(() => {
    refresh();  
  }, [serverName]);
  async function createBackup() {
    await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/backups`,
      { method: 'POST' }
    );
    refresh();
  }
  async function restore(file) {
    await fetch(
      `${API}/servers/${encodeURIComponent(serverName)}/restore?file=${encodeURIComponent(
        file
      )}`,
      { method: 'POST' }
    );
    alert('Restore triggered. Stop the server before restoring for safety.');
  }
  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm text-white/70">Backups</div>
        <button
          onClick={createBackup}
          className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 inline-flex items-center gap-2"
        >
          <FaDownload /> Create backup
        </button>
      </div>
      <div className="space-y-1">
        {list.map((b) => (
          <div
            key={b.file}
            className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-3 py-2 text-sm"
          >
            <div>
              {b.file}{' '}
              <span className="text-white/50">
                ({Math.ceil((b.size || 0) / 1024 / 1024)} MB)
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => restore(b.file)}
                className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
              >
                Restore
              </button>
            </div>
          </div>
        ))}
        {list.length === 0 && (
          <div className="text-white/60 text-sm">No backups yet.</div>
        )}
      </div>
    </div>
  );
}

// List of server types that require loader version input
const SERVER_TYPES_WITH_LOADER = ['fabric', 'forge', 'neoforge'];

function ConfigPanel({ server, onRestart }) {
  const [javaVersions, setJavaVersions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentVersion, setCurrentVersion] = useState(null);
  const [updating, setUpdating] = useState(false);

  // Fetch available Java versions
  useEffect(() => {
    async function fetchJavaVersions() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API}/servers/${server.id}/java-versions`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        setJavaVersions(data.available_versions);
        setCurrentVersion(data.current_version);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }

    fetchJavaVersions();
  }, [server.id]);

  // Update Java version
  async function updateJavaVersion(version) {
    setUpdating(true);
    setError(null);
    try {
      const response = await fetch(`${API}/servers/${server.id}/java-version`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ java_version: version }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }
      
      const data = await response.json();
      setCurrentVersion(data.java_version);
      
      // Show success message
      alert(`Java version updated to ${data.java_version}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setUpdating(false);
    }
  }

  if (loading) {
    return (
      <div className="p-4 bg-black/20 rounded-lg">
        <div className="text-sm text-white/70">Loading Java version information...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-black/20 rounded-lg">
        <div className="text-sm text-red-400">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="text-lg font-semibold text-white mb-4">Server Configuration</div>
      
      {/* Java Version Selection */}
      <div className="mb-6">
        <div className="text-sm text-white/70 mb-2">Java Version</div>
        <div className="text-xs text-white/50 mb-3">
          Current version: <span className="text-green-400">{currentVersion}</span>
        </div>
        
        <div className="grid grid-cols-2 gap-3">
          {javaVersions?.map((javaInfo) => (
            <button
              key={javaInfo.version}
              onClick={() => updateJavaVersion(javaInfo.version)}
              disabled={updating || currentVersion === javaInfo.version}
              className={`p-3 rounded-lg border transition ${
                currentVersion === javaInfo.version
                  ? 'bg-brand-500 border-brand-400 text-white'
                  : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10 hover:text-white'
              } ${updating ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="font-semibold">{javaInfo.name}</div>
              <div className="text-xs opacity-70">{javaInfo.description}</div>
            </button>
          ))}
        </div>
        
        {updating && (
          <div className="text-sm text-yellow-400 mt-2">Updating Java version...</div>
        )}
        
        {currentVersion && (
          <div className="mt-3 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
            <div className="text-sm text-blue-300 mb-2">💡 Tip</div>
            <div className="text-xs text-blue-200">
              After changing the Java version, restart the server for the changes to take effect.
            </div>
            {onRestart && (
              <button
                onClick={() => onRestart(server.id)}
                className="mt-2 px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition"
              >
                Restart Server
              </button>
            )}
          </div>
        )}
      </div>

      {/* Additional Configuration Options */}
      <div className="border-t border-white/10 pt-4">
        <div className="text-sm text-white/70 mb-2">Additional Settings</div>
        <div className="text-xs text-white/50">
          Use the Files tab to edit server.properties, spigot.yml, and other configuration files.
        </div>
      </div>
    </div>
  );
}

function PluginsPanel({ serverName }) {
  const [plugins, setPlugins] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${API}/plugins/${encodeURIComponent(serverName)}`);
      const d = await r.json();
      setPlugins(d.plugins || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line
  }, [serverName]);

  async function upload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    await fetch(`${API}/plugins/${encodeURIComponent(serverName)}/upload`, { method: 'POST', body: fd });
    await refresh();
  }

  async function reloadPlugins() {
    await fetch(`${API}/plugins/${encodeURIComponent(serverName)}/reload`, { method: 'POST' });
  }

  async function remove(name) {
    await fetch(`${API}/plugins/${encodeURIComponent(serverName)}/${encodeURIComponent(name)}`, { method: 'DELETE' });
    await refresh();
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-white/70">Plugins</div>
        <div className="flex items-center gap-2">
          <label className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 cursor-pointer inline-flex items-center gap-2">
            <FaUpload /> Upload
            <input type="file" className="hidden" accept=".jar" onChange={upload} />
          </label>
          <button onClick={reloadPlugins} className="rounded bg-slate-600 hover:bg-slate-500 px-3 py-1.5">Reload</button>
        </div>
      </div>
      {loading ? (
        <div className="text-white/60 text-sm">Loading…</div>
      ) : error ? (
        <div className="text-red-400 text-sm">{error}</div>
      ) : (
        <div className="space-y-2">
          {plugins.map(p => (
            <div key={p.name} className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-3 py-2">
              <div className="text-sm">{p.name}</div>
              <button onClick={() => remove(p.name)} className="text-red-300 hover:text-red-200 text-sm">Delete</button>
            </div>
          ))}
          {!plugins.length && <div className="text-white/50 text-sm">No plugins found.</div>}
        </div>
      )}
    </div>
  );
}

function WorldsPanel({ serverName }) {
  const [worlds, setWorlds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    setLoading(true);
    setError('');
    try {
      const r = await fetch(`${API}/worlds/${encodeURIComponent(serverName)}`);
      const d = await r.json();
      setWorlds(d.worlds || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line
  }, [serverName]);

  async function upload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await fetch(`${API}/worlds/${encodeURIComponent(serverName)}/upload?world_name=world`, { method: 'POST', body: fd });
      await refresh();
    } finally {
      setUploading(false);
    }
  }

  function download(worldName) {
    window.location.href = `${API}/worlds/${encodeURIComponent(serverName)}/download?world=${encodeURIComponent(worldName)}`;
  }

  async function backup(worldName) {
    await fetch(`${API}/worlds/${encodeURIComponent(serverName)}/backup?world=${encodeURIComponent(worldName)}&compression=zip`, { method: 'POST' });
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-white/70">Worlds</div>
        <label className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 cursor-pointer inline-flex items-center gap-2">
          <FaUpload /> Upload World (.zip)
          <input type="file" className="hidden" accept=".zip,.tar,.gz" onChange={upload} />
        </label>
      </div>
      {loading ? (
        <div className="text-white/60 text-sm">Loading…</div>
      ) : error ? (
        <div className="text-red-400 text-sm">{error}</div>
      ) : (
        <div className="space-y-2">
          {worlds.map(w => (
            <div key={w.name} className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-3 py-2">
              <div>
                <div className="text-sm">{w.name}</div>
                <div className="text-xs text-white/50">{(w.size / (1024*1024)).toFixed(1)} MB</div>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => download(w.name)} className="rounded bg-slate-600 hover:bg-slate-500 px-3 py-1.5 text-sm">Download</button>
                <button onClick={() => backup(w.name)} className="rounded bg-slate-600 hover:bg-slate-500 px-3 py-1.5 text-sm">Backup</button>
              </div>
            </div>
          ))}
          {!worlds.length && <div className="text-white/50 text-sm">No worlds detected.</div>}
        </div>
      )}
      {uploading && <div className="text-white/60 text-sm mt-2">Uploading…</div>}
    </div>
  );
}

function SchedulePanel() {
  const { data, loading, error, setData } = useFetch(`${API}/schedule/tasks`, []);
  const [name, setName] = useState('');
  const [taskType, setTaskType] = useState('backup');
  const [serverName, setServerName] = useState('');
  const [cron, setCron] = useState('0 2 * * *');
  const [command, setCommand] = useState('');

  async function createTask() {
    const body = { name, task_type: taskType, server_name: serverName || null, cron_expression: cron, command: command || null };
    const r = await fetch(`${API}/schedule/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.ok) {
      const task = await r.json();
      setData([...(data || []), task]);
      setName(''); setServerName(''); setCommand('');
    }
  }

  async function removeTask(id) {
    await fetch(`${API}/schedule/tasks/${id}`, { method: 'DELETE' });
    setData((data || []).filter(t => t.id !== id));
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="text-sm text-white/70 mb-3">Scheduled Tasks</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Task name" value={name} onChange={e => setName(e.target.value)} />
        <select 
          className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-500" 
          value={taskType} 
          onChange={e => setTaskType(e.target.value)}
          style={{ backgroundColor: '#1f2937', color: '#ffffff' }}
        >
          <option value="backup" style={{ backgroundColor: '#1f2937', color: '#ffffff' }}>Backup</option>
          <option value="restart" style={{ backgroundColor: '#1f2937', color: '#ffffff' }}>Restart</option>
          <option value="command" style={{ backgroundColor: '#1f2937', color: '#ffffff' }}>Command</option>
          <option value="cleanup" style={{ backgroundColor: '#1f2937', color: '#ffffff' }}>Cleanup</option>
        </select>
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Server name (backup/restart/command)" value={serverName} onChange={e => setServerName(e.target.value)} />
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Cron (e.g., 0 2 * * *)" value={cron} onChange={e => setCron(e.target.value)} />
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 md:col-span-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Command (for command tasks)" value={command} onChange={e => setCommand(e.target.value)} />
        <button onClick={createTask} className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-2">Create Task</button>
      </div>
      {loading ? <div className="text-white/60 text-sm">Loading…</div> : error ? <div className="text-red-400 text-sm">{String(error)}</div> : (
        <div className="space-y-2">
          {(data || []).map(t => (
            <div key={t.id} className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-3 py-2">
              <div className="text-sm">
                <div className="font-medium">{t.name} <span className="text-white/50">({t.task_type})</span></div>
                <div className="text-xs text-white/50">cron: {t.cron_expression} {t.server_name ? `| server: ${t.server_name}` : ''}</div>
              </div>
              <button onClick={() => removeTask(t.id)} className="text-red-300 hover:text-red-200 text-sm">Delete</button>
            </div>
          ))}
          {!data?.length && <div className="text-white/50 text-sm">No scheduled tasks yet.</div>}
        </div>
      )}
    </div>
  );
}

function PlayersPanel({ serverName }) {
  const [playerName, setPlayerName] = useState('');
  const [reason, setReason] = useState('');

  async function call(endpoint, method = 'POST', body = null) {
    await fetch(`${API}/players/${encodeURIComponent(serverName)}/${endpoint}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg space-y-3">
      <div className="text-sm text-white/70">Player Management</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Player name" value={playerName} onChange={e => setPlayerName(e.target.value)} />
        <input className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500" placeholder="Reason (optional)" value={reason} onChange={e => setReason(e.target.value)} />
        <div className="flex items-center gap-2">
          <button onClick={() => call('whitelist', 'POST', { player_name: playerName, reason })} className="rounded bg-slate-600 hover:bg-slate-500 px-3 py-2 text-sm">Whitelist</button>
          <button onClick={() => call('ban', 'POST', { player_name: playerName, reason })} className="rounded bg-red-600 hover:bg-red-500 px-3 py-2 text-sm">Ban</button>
          <button onClick={() => call('kick', 'POST', { player_name: playerName, reason })} className="rounded bg-yellow-600 hover:bg-yellow-500 px-3 py-2 text-sm">Kick</button>
          <button onClick={() => call('op', 'POST', { player_name: playerName, reason })} className="rounded bg-green-600 hover:bg-green-500 px-3 py-2 text-sm">OP</button>
        </div>
      </div>
    </div>
  );
}

function ServerDetailsPage({ server, onBack, onStart, onStop, onDelete, onRestart }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [filesEditing, setFilesEditing] = useState(false);
  const [editPath, setEditPath] = useState('');
  const [editContent, setEditContent] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [blockedFileError, setBlockedFileError] = useState('');
  const stats = useServerStats(server.id);

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

  // FilesPanelWrapper implements the new/changed file methods
  function FilesPanelWrapper({ serverName }) {
    const [path, setPath] = useState('.');
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [err, setErr] = useState('');
    const [blockedFileErrorLocal, setBlockedFileErrorLocal] = useState('');

    useEffect(() => {
      loadDir('.');
      // eslint-disable-next-line
    }, [serverName]);

    async function loadDir(p = path) {
      setLoading(true);
      setErr('');
      try {
        const r = await fetch(
          `${API}/servers/${encodeURIComponent(serverName)}/files?path=${encodeURIComponent(
            p
          )}`
        );
        const d = await r.json();
        setItems(d.items || []);
        setPath(p);
      } catch (e) {
        setErr(String(e));
      } finally {
        setLoading(false);
      }
    }

    async function openFile(name) {
      setBlockedFileErrorLocal('');
      setBlockedFileError('');
      if (isBlockedFile(name)) {
        setBlockedFileErrorLocal('Cannot open this file type in the editor.');
        setBlockedFileError('Cannot open this file type in the editor.');
        return;
      }
      const filePath = path === '.' ? name : `${path}/${name}`;
      // Backend should check file size and type, and only return content for text files
      const r = await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/file?path=${encodeURIComponent(
          filePath
        )}`
      );
      const d = await r.json();
      if (d && d.error) {
        setBlockedFileErrorLocal(d.error);
        setBlockedFileError(d.error);
        return;
      }
      setEditPath(filePath);
      setEditContent(d.content || '');
      setIsEditing(true);
      setFilesEditing(true);
    }
    async function openDir(name) {
      await loadDir(path === '.' ? name : `${path}/${name}`);
    }
    function goUp() {
      if (path === '.' || !path) return;
      const parts = path.split('/');
      parts.pop();
      const p = parts.length ? parts.join('/') : '.';
      loadDir(p);
    }
    async function del(name, isDir) {
      const p = path === '.' ? name : `${path}/${name}`;
      await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/file?path=${encodeURIComponent(
          p
        )}`,
        { method: 'DELETE' }
      );
      loadDir(path);
    }
    async function upload(ev) {
      const file = ev.target.files?.[0];
      if (!file) return;
      const fd = new window.FormData();
      fd.append('path', path);
      fd.append('file', file);
      await fetch(
        `${API}/servers/${encodeURIComponent(serverName)}/upload`,
        { method: 'POST', body: fd }
      );
      loadDir(path);
    }

    const sortedItems = useMemo(() => {
      return [...items].sort((a, b) => {
        if (a.is_dir && !b.is_dir) return -1;
        if (!a.is_dir && b.is_dir) return 1;
        return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      });
    }, [items]);

    return (
      <div className="p-2 bg-black/20 rounded-lg" style={{ maxWidth: 520, minWidth: 320 }}>
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs text-white/70">
            Path: <span className="text-white">{path}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={goUp}
              className="text-xs rounded bg-white/10 hover:bg-white/20 px-2 py-1"
            >
              Up
            </button>
            <label className="text-xs rounded bg-brand-500 hover:bg-brand-400 px-2 py-1 cursor-pointer inline-flex items-center gap-2">
              <FaUpload /> Upload
              <input type="file" className="hidden" onChange={upload} />
            </label>
          </div>
        </div>
        {loading && <div className="text-white/70 text-xs">Loading…</div>}
        {err && <div className="text-red-400 text-xs">{err}</div>}
        {blockedFileErrorLocal && <div className="text-red-400 text-xs">{blockedFileErrorLocal}</div>}
        {!loading && (
          <div className="space-y-1">
            {sortedItems.map((it) => (
              <div
                key={it.name}
                className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-2 py-1"
                style={{ minHeight: 32 }}
              >
                <div className="flex items-center gap-2">
                  <span className="text-yellow-400 text-base">
                    {it.is_dir ? <FaFolder /> : '📄'}
                  </span>
                  <span className="text-xs">{it.name}</span>
                </div>
                <div className="flex items-center gap-1 text-xs">
                  {it.is_dir ? (
                    <button
                      onClick={() => openDir(it.name)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1"
                    >
                      Open
                    </button>
                  ) : (
                    <button
                      onClick={() => openFile(it.name)}
                      className="rounded bg-white/10 hover:bg-white/20 px-2 py-1 inline-flex items-center gap-1"
                      disabled={isBlockedFile(it.name)}
                      style={isBlockedFile(it.name) ? { opacity: 0.5, pointerEvents: 'none' } : {}}
                      title={isBlockedFile(it.name) ? "Cannot open this file type in the editor" : "Edit"}
                    >
                      <FaSave /> Edit
                    </button>
                  )}
                  <button
                    onClick={() => del(it.name, it.is_dir)}
                    className="rounded bg-red-600 hover:bg-red-500 px-2 py-1"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

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
            <FilesPanelWrapper serverName={server.name} />
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
          <PlayersPanel serverName={server.name} />
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
            <div className="flex items-center gap-4">
              <div
                className={`text-base px-4 py-2 rounded-full ${
                  server.status === 'running'
                    ? 'bg-green-500/20 text-green-300'
                    : 'bg-yellow-500/20 text-yellow-300'
                }`}
              >
                {server.status}
              </div>
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
          <div className="flex gap-4 mt-8 pt-8 border-t border-white/10">
            <button
              onClick={() => onStart(server.id)}
              className="inline-flex items-center gap-2 rounded-md bg-green-600 hover:bg-green-500 px-6 py-3 text-lg font-semibold"
            >
              <FaPlay /> Start
            </button>
            <button
              onClick={() => onStop(server.id)}
              className="inline-flex items-center gap-2 rounded-md bg-yellow-600 hover:bg-yellow-500 px-6 py-3 text-lg font-semibold"
            >
              <FaStop /> Stop
            </button>
            <button
              className="inline-flex items-center gap-2 rounded-md bg-slate-700 hover:bg-slate-600 px-6 py-3 text-lg font-semibold"
              style={{ pointerEvents: 'none', opacity: 0.5 }}
              tabIndex={-1}
              aria-disabled="true"
            >
              <FaTerminal /> Console/Logs
            </button>
            <button
              onClick={() => onDelete(server.id)}
              className="inline-flex items-center gap-2 rounded-md bg-red-600 hover:bg-red-500 px-6 py-3 text-lg font-semibold ml-auto"
            >
              <FaTrash /> Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Enhance ServerListCard with live stats
function ServerListCard({ server, onClick }) {
  const { data: typeVersionData } = useFetch(
    server?.id ? `${API}/servers/${server.id}/info` : null,
    [server?.id]
  );
  const stats = useServerStats(server.id);

  return (
    <div
      className="rounded-xl bg-gradient-to-b from-white/10 to-white/5 border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)] p-6"
      onClick={onClick}
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
}

// User Management Components
function UserManagementPage() {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', email: '', role: 'user', password: '' });
  const [selectedUser, setSelectedUser] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    loadUsers();
    loadRoles();
    loadAuditLogs();
  }, []);

  async function loadUsers() {
    try {
      const r = await fetch(`${API}/users`);
      const data = await r.json();
      setUsers(data.users || []);
    } catch (e) {
      console.error('Failed to load users:', e);
    }
  }

  async function loadRoles() {
    try {
      const r = await fetch(`${API}/users/roles`);
      const data = await r.json();
      setRoles(data.roles || []);
    } catch (e) {
      console.error('Failed to load roles:', e);
    }
  }

  async function loadAuditLogs() {
    try {
      const r = await fetch(`${API}/users/audit-logs?limit=50`);
      const data = await r.json();
      setAuditLogs(data.logs || []);
    } catch (e) {
      console.error('Failed to load audit logs:', e);
    }
    setLoading(false);
  }

  async function createUser() {
    try {
      await fetch(`${API}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUser),
      });
      setShowCreateUser(false);
      setNewUser({ username: '', email: '', role: 'user', password: '' });
      loadUsers();
    } catch (e) {
      console.error('Failed to create user:', e);
    }
  }

  async function updateUserRole(userId, newRole) {
    try {
      await fetch(`${API}/users/${userId}/role`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: newRole }),
      });
      loadUsers();
    } catch (e) {
      console.error('Failed to update user role:', e);
    }
  }

  async function toggleUserActive(userId, isActive) {
    try {
      await fetch(`${API}/users/${userId}/${isActive ? 'activate' : 'deactivate'}`, {
        method: 'PUT',
      });
      loadUsers();
    } catch (e) {
      console.error('Failed to toggle user status:', e);
    }
  }

  async function deleteUser(userId) {
    if (!confirm('Are you sure you want to delete this user?')) return;
    try {
      await fetch(`${API}/users/${userId}`, { method: 'DELETE' });
      loadUsers();
    } catch (e) {
      console.error('Failed to delete user:', e);
    }
  }

  const filteredUsers = users.filter(user => 
    user.username?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    user.email?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  if (loading) return <div className="p-6"><div className="text-white/70">Loading users...</div></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaUsers className="text-brand-500" /> User Management
          </h1>
          <p className="text-white/70 mt-2">Manage users, roles, and permissions</p>
        </div>
        <button
          onClick={() => setShowCreateUser(true)}
          className="bg-brand-500 hover:bg-brand-600 px-4 py-2 rounded-lg flex items-center gap-2"
        >
          <FaPlus /> Create User
        </button>
      </div>

      {/* Search and filters */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-4">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <FaSearch className="absolute left-3 top-1/2 transform -translate-y-1/2 text-white/50" />
            <input
              type="text"
              placeholder="Search users by username or email..."
              className="w-full pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/50 focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <button className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg flex items-center gap-2">
            <FaFilter /> Filter
          </button>
        </div>
      </div>

      {/* Users table */}
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
              {filteredUsers.map((user) => (
                <tr key={user.id} className="hover:bg-white/5">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="w-8 h-8 bg-brand-500 rounded-full flex items-center justify-center">
                        <FaUsers className="text-sm text-white" />
                      </div>
                      <div className="ml-3">
                        <div className="text-sm font-medium text-white">{user.username}</div>
                        <div className="text-sm text-white/60">{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <select
                      value={user.role}
                      onChange={(e) => updateUserRole(user.id, e.target.value)}
                      className="bg-white/10 border border-white/20 rounded px-2 py-1 text-white text-sm"
                    >
                      {roles.map(role => (
                        <option key={role.name} value={role.name} style={{ backgroundColor: '#1f2937' }}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                      user.is_active
                        ? 'bg-green-500/20 text-green-300'
                        : 'bg-red-500/20 text-red-300'
                    }`}>
                      {user.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-white/70">
                    {user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium space-x-2">
                    <button
                      onClick={() => setSelectedUser(user)}
                      className="text-blue-400 hover:text-blue-300"
                    >
                      <FaEye />
                    </button>
                    <button
                      onClick={() => toggleUserActive(user.id, !user.is_active)}
                      className={`${user.is_active ? 'text-red-400 hover:text-red-300' : 'text-green-400 hover:text-green-300'}`}
                    >
                      {user.is_active ? <FaEyeSlash /> : <FaEye />}
                    </button>
                    <button
                      onClick={() => deleteUser(user.id)}
                      className="text-red-400 hover:text-red-300"
                    >
                      <FaTrash />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit Logs */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaHistory /> Recent Audit Logs
        </h3>
        <div className="space-y-2 max-h-64 overflow-y-auto">
          {auditLogs.map((log, idx) => (
            <div key={idx} className="flex items-center gap-3 text-sm p-2 bg-white/5 rounded">
              <div className="text-brand-400 text-xs">
                {new Date(log.timestamp).toLocaleString()}
              </div>
              <div className="text-white/80">{log.action}</div>
              <div className="text-white/60">{log.user_id}</div>
              {log.details && <div className="text-white/50 text-xs">{JSON.stringify(log.details)}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Create User Modal */}
      {showCreateUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white/10 border border-white/20 rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-4">Create New User</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Username</label>
                <input
                  type="text"
                  value={newUser.username}
                  onChange={(e) => setNewUser({...newUser, username: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  placeholder="Enter username"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Email</label>
                <input
                  type="email"
                  value={newUser.email}
                  onChange={(e) => setNewUser({...newUser, email: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  placeholder="Enter email"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Password</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({...newUser, password: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                  placeholder="Enter password"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-white/70 mb-2">Role</label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({...newUser, role: e.target.value})}
                  className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white"
                >
                  {roles.map(role => (
                    <option key={role.name} value={role.name} style={{ backgroundColor: '#1f2937' }}>
                      {role.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreateUser(false)}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 rounded text-white"
              >
                Cancel
              </button>
              <button
                onClick={createUser}
                className="px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded text-white"
              >
                Create User
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Monitoring Dashboard
function MonitoringPage() {
  const [systemHealth, setSystemHealth] = useState(null);
  const [serverMetrics, setServerMetrics] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadMonitoringData();
    const interval = setInterval(loadMonitoringData, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);

  async function loadMonitoringData() {
    try {
      const [healthRes, dashboardRes, alertsRes] = await Promise.all([
        fetch(`${API}/monitoring/system-health`),
        fetch(`${API}/monitoring/dashboard-data`),
        fetch(`${API}/monitoring/alerts`)
      ]);
      
      if (healthRes.ok) setSystemHealth(await healthRes.json());
      if (dashboardRes.ok) setDashboardData(await dashboardRes.json());
      if (alertsRes.ok) setAlerts((await alertsRes.json()).alerts || []);
    } catch (e) {
      console.error('Failed to load monitoring data:', e);
    }
    setLoading(false);
  }

  if (loading) return <div className="p-6"><div className="text-white/70">Loading monitoring data...</div></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaChartLine className="text-brand-500" /> System Monitoring
          </h1>
          <p className="text-white/70 mt-2">Real-time system and server performance monitoring</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadMonitoringData}
            className="bg-brand-500 hover:bg-brand-600 px-4 py-2 rounded-lg flex items-center gap-2"
          >
            <FaSync /> Refresh
          </button>
        </div>
      </div>

      {/* System Health Overview */}
      {systemHealth && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white/5 border border-white/10 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white/70 text-sm">Total Servers</p>
                <p className="text-2xl font-bold text-white">{systemHealth.total_servers}</p>
              </div>
              <FaServer className="text-3xl text-brand-500" />
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white/70 text-sm">Running Servers</p>
                <p className="text-2xl font-bold text-green-400">{systemHealth.running_servers}</p>
              </div>
              <FaPlay className="text-3xl text-green-500" />
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white/70 text-sm">CPU Usage</p>
                <p className="text-2xl font-bold text-white">{systemHealth.cpu_usage_percent}%</p>
              </div>
              <FaMicrochip className="text-3xl text-yellow-500" />
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-white/70 text-sm">Memory Usage</p>
                <p className="text-2xl font-bold text-white">
                  {systemHealth.used_memory_gb} / {systemHealth.total_memory_gb} GB
                </p>
              </div>
              <FaMemory className="text-3xl text-purple-500" />
            </div>
          </div>
        </div>
      )}

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <FaBell /> System Alerts
          </h3>
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
        </div>
      )}

      {/* Server Overview */}
      {dashboardData && (
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <FaProjectDiagram /> Server Overview
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {dashboardData.server_overview.map((server, idx) => (
              <div key={idx} className="bg-white/5 border border-white/10 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="font-medium">{server.name}</div>
                  <div className={`px-2 py-1 rounded text-xs ${
                    server.status === 'running'
                      ? 'bg-green-500/20 text-green-300'
                      : 'bg-red-500/20 text-red-300'
                  }`}>
                    {server.status}
                  </div>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-white/70">CPU:</span>
                    <span>{server.cpu_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">Memory:</span>
                    <span>{server.memory_percent}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/70">Players:</span>
                    <span>{server.player_count}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// System Settings Page
function SettingsPage() {
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

// Dashboard Page
function DashboardPage({ servers = [] }) {
  const [systemStats, setSystemStats] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [quickStats, setQuickStats] = useState({
    totalServers: 0,
    runningServers: 0,
    totalPlayers: 0,
    totalMemoryUsage: 0
  });

  useEffect(() => {
    // Calculate quick stats
    const running = servers.filter(s => s.status === 'running').length;
    setQuickStats({
      totalServers: servers.length,
      runningServers: running,
      totalPlayers: 0, // This would be calculated from server stats
      totalMemoryUsage: 0 // This would be calculated from server stats
    });
  }, [servers]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <FaHome className="text-brand-500" /> Dashboard
          </h1>
          <p className="text-white/70 mt-2">Overview of your Minecraft server infrastructure</p>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Total Servers</p>
              <p className="text-3xl font-bold text-white">{quickStats.totalServers}</p>
            </div>
            <FaServer className="text-4xl text-brand-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Running Servers</p>
              <p className="text-3xl font-bold text-green-400">{quickStats.runningServers}</p>
            </div>
            <FaPlay className="text-4xl text-green-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">Total Players</p>
              <p className="text-3xl font-bold text-blue-400">{quickStats.totalPlayers}</p>
            </div>
            <FaUsers className="text-4xl text-blue-500" />
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-white/70 text-sm">System Health</p>
              <p className="text-3xl font-bold text-yellow-400">Good</p>
            </div>
            <FaHeart className="text-4xl text-red-500" />
          </div>
        </div>
      </div>

      {/* Server Status Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <FaServer /> Server Status
          </h3>
          <div className="space-y-3">
            {servers.slice(0, 5).map(server => (
              <div key={server.id} className="flex items-center justify-between p-3 bg-white/5 rounded">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${
                    server.status === 'running' ? 'bg-green-500' : 'bg-red-500'
                  }`} />
                  <span className="font-medium">{server.name}</span>
                </div>
                <span className={`text-sm px-2 py-1 rounded ${
                  server.status === 'running'
                    ? 'bg-green-500/20 text-green-300'
                    : 'bg-red-500/20 text-red-300'
                }`}>
                  {server.status}
                </span>
              </div>
            ))}
            {servers.length === 0 && (
              <div className="text-white/60 text-center py-8">
                No servers created yet
              </div>
            )}
          </div>
        </div>
        
        <div className="bg-white/5 border border-white/10 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <FaBell /> Recent Activity
          </h3>
          <div className="space-y-3">
            {recentActivity.length > 0 ? (
              recentActivity.map((activity, idx) => (
                <div key={idx} className="flex items-center gap-3 p-3 bg-white/5 rounded">
                  <FaInfoCircle className="text-blue-400" />
                  <div>
                    <div className="text-sm">{activity.message}</div>
                    <div className="text-xs text-white/60">{activity.timestamp}</div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-white/60 text-center py-8">
                No recent activity
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white/5 border border-white/10 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <FaRocket /> Quick Actions
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <button className="flex items-center gap-3 p-4 bg-brand-500/20 hover:bg-brand-500/30 border border-brand-500/30 rounded-lg transition-colors">
            <FaPlusCircle className="text-brand-400" />
            <span>Create Server</span>
          </button>
          <button className="flex items-center gap-3 p-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors">
            <FaDownload className="text-white/60" />
            <span>Backup All</span>
          </button>
          <button className="flex items-center gap-3 p-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors">
            <FaChartLine className="text-white/60" />
            <span>View Metrics</span>
          </button>
          <button className="flex items-center gap-3 p-4 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg transition-colors">
            <FaCog className="text-white/60" />
            <span>Settings</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// Servers Page
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
  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FaLayerGroup className="text-brand-500" /> Server Templates
        </h1>
        <p className="text-white/70 mt-2">Create and manage server templates</p>
      </div>
      <div className="bg-white/5 border border-white/10 rounded-lg p-6 text-center">
        <FaLayerGroup className="text-6xl text-white/20 mx-auto mb-4" />
        <h3 className="text-xl font-semibold mb-2">Server Templates</h3>
        <p className="text-white/60">Template system coming soon!</p>
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

  // Create server handler, using loader_version as in backend/app.py
  async function createServer(e) {
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
  }

  // Start server handler
  async function start(id) {
    await fetch(`${API}/servers/${id}/start`, { method: 'POST' });
    window.location.reload();
  }
  // Stop server handler
  async function stop(id) {
    await fetch(`${API}/servers/${id}/stop`, { method: 'POST' });
    window.location.reload();
  }
  // Delete server handler
  async function del(id) {
    await fetch(`${API}/servers/${id}`, { method: 'DELETE' });
    window.location.reload();
  }

  // Restart server handler
  async function restart(id) {
    try {
      await fetch(`${API}/servers/${id}/stop`, { method: 'POST' });
      // Wait a moment for the server to stop
      await new Promise(resolve => setTimeout(resolve, 2000));
      await fetch(`${API}/servers/${id}/start`, { method: 'POST' });
      // Refresh servers data
      const response = await fetch(`${API}/servers`);
      if (response.ok) {
        const updatedServers = await response.json();
        setServersData(updatedServers);
      }
    } catch (e) {
      console.error('Error restarting server:', e);
    }
  }

  // Find selected server object
  const selectedServerObj =
    selectedServer &&
    servers.find((s) => s.id === selectedServer);

  const sidebarItems = [
    { id: 'dashboard', label: 'Dashboard', icon: FaHome },
    { id: 'servers', label: 'Servers', icon: FaServer },
    { id: 'monitoring', label: 'Monitoring', icon: FaChartLine },
    { id: 'users', label: 'User Management', icon: FaUsers },
    { id: 'backups', label: 'Backups', icon: FaDatabase },
    { id: 'schedule', label: 'Scheduler', icon: FaClock },
    { id: 'plugins', label: 'Plugin Manager', icon: FaRocket },
    { id: 'templates', label: 'Templates', icon: FaLayerGroup },
    { id: 'security', label: 'Security', icon: FaShieldAlt },
    { id: 'settings', label: 'Settings', icon: FaCog },
  ];

  function renderCurrentPage() {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage servers={servers} />;
      case 'servers':
        return selectedServer ? (
          selectedServerObj && (
            <ServerDetailsPage
              server={selectedServerObj}
              onBack={() => setSelectedServer(null)}
              onStart={start}
              onStop={stop}
              onDelete={del}
              onRestart={restart}
            />
          )
        ) : (
          <ServersPage
            servers={servers}
            serversLoading={serversLoading}
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
        return <MonitoringPage />;
      case 'users':
        return <UserManagementPage />;
      case 'backups':
        return <BackupManagementPage />;
      case 'schedule':
        return <SchedulerPage />;
      case 'plugins':
        return <PluginManagerPage />;
      case 'templates':
        return <TemplatesPage />;
      case 'security':
        return <SecurityPage />;
      case 'settings':
        return <SettingsPage />;
      default:
        return <DashboardPage servers={servers} />;
    }
  }

  return (
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
          {!isAuthenticated ? (
            <div className="min-h-screen flex items-center justify-center">
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
          ) : (
            renderCurrentPage()
          )}
        </main>
      </div>
    </div>
  );
}

export default App;
