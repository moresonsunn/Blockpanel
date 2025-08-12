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
} from 'react-icons/fa';

const API = 'http://localhost:8000';

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
      case 'config':
        return <ConfigPanel server={server} onRestart={onRestart} />;
      case 'players':
        return (
          <div className="p-4 bg-black/20 rounded-lg text-sm text-white/70">
            Player listing and management coming soon.
          </div>
        );
      case 'schedule':
        return (
          <div className="p-4 bg-black/20 rounded-lg text-sm text-white/70">
            Scheduling UI coming soon.
          </div>
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
                        .map(
                          ([, v]) => v?.[0]?.HostPort || 'N/A'
                        )
                        .join(', ')
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

function ServerListCard({ server, onClick }) {
  const { data: typeVersionData } = useFetch(
    server?.id ? `${API}/servers/${server.id}/info` : null,
    [server?.id]
  );

  return (
    <div
      className="rounded-xl bg-white/5 border border-white/10 shadow-card p-6 flex items-center justify-between cursor-pointer hover:bg-brand-500/10 transition"
      onClick={onClick}
      tabIndex={0}
      role="button"
      style={{ minHeight: 100 }}
    >
      <div className="flex items-center gap-5">
        <div className="w-12 h-12 rounded-md bg-brand-500 inline-flex items-center justify-center text-2xl">
          <FaServer />
        </div>
        <div>
          <div className="font-bold text-xl">{server.name}</div>
          <div className="text-sm text-white/60">{server.id.slice(0, 12)}</div>
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
        <FaChevronRight className="text-white/40 text-xl" />
      </div>
    </div>
  );
}

function App() {
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

  // Fetch servers
  const {
    data: serversData,
    loading: serversLoading,
    error: serversError,
  } = useFetch(`${API}/servers`, []);
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

  return (
    <div className="min-h-full bg-ink bg-hero-gradient">
      <header className="border-b border-white/10 bg-ink/80 backdrop-blur supports-[backdrop-filter]:bg-ink/60">
        <div className="container flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-brand-500 inline-flex items-center justify-center shadow-card">
              <FaServer className="text-white" />
            </div>
            <div className="font-semibold">Minecraft Panel</div>
          </div>
        </div>
      </header>

      {!selectedServer && (
        <section className="container mt-8">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-8 shadow-card">
            <div className="grid md:grid-cols-2 gap-10 items-center">
              <div>
                <h1 className="text-4xl md:text-5xl font-bold leading-tight">
                  Minecraft Panel
                </h1>
                <p className="text-white/70 mt-4 text-lg">
                  Supports sometimes vanilla, paper, purpur, fabric, forge, and neoforge.
                </p>
                <div className="grid grid-cols-3 gap-6 mt-8">
                  <Stat label="Server Types" value={types.length || 0} />
                  <Stat label="Active Servers" value={servers.length || 0} />
                  <Stat
                    label="Docker"
                    value={!serversError ? 'Connected' : 'Unavailable'}
                  />
                </div>
              </div>
              <form
                onSubmit={createServer}
                className="rounded-xl bg-black/30 border border-white/10 p-6 space-y-4"
              >
                <div className="flex items-center gap-3 text-white/80 text-lg">
                  <FaPlusCircle />{' '}
                  <span className="font-medium">Create new server</span>
                </div>
                <div>
                  <label className="text-base text-white/70">Server name</label>
                  <input
                    className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-brand-500 text-base"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-base text-white/70">Type</label>
                    <select
                      className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                      value={selectedType}
                      onChange={(e) => setSelectedType(e.target.value)}
                    >
                      {types.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-base text-white/70">Version</label>
                    <select
                      className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                      value={version}
                      onChange={(e) => setVersion(e.target.value)}
                    >
                      {(versionsData?.versions || [])
                        .slice(0, 50)
                        .map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                    </select>
                  </div>
                </div>
                {/* Loader version select for types that need it */}
                {SERVER_TYPES_WITH_LOADER.includes(selectedType) && (
                  <div>
                    <label className="text-base text-white/70">
                      Loader version
                    </label>
                    {/* Only show loader version select if loaderVersionsData is available and not loading/error */}
                    {loaderVersionsLoading ? (
                      <div className="mt-2 text-white/70 text-sm">Loading loader versions…</div>
                    ) : loaderVersionsError ? (
                      <div className="mt-2 text-red-400 text-sm">
                        Error loading loader versions: {loaderVersionsError.message}
                      </div>
                    ) : loaderVersionsData && loaderVersionsData.loader_versions && loaderVersionsData.loader_versions.length > 0 ? (
                      <select
                        className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                        value={loaderVersion}
                        onChange={(e) => setLoaderVersion(e.target.value)}
                        required
                      >
                        {(loaderVersionsData?.loader_versions || []).map((lv) => (
                          <option key={lv} value={lv}>
                            {lv}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <div className="mt-2 text-white/50 text-sm">
                        No loader versions available for this Minecraft version.
                      </div>
                    )}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-base text-white/70">
                      Min RAM (MB)
                    </label>
                    <input
                      className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                      type="number"
                      min="256"
                      step="1"
                      value={minRam}
                      onChange={e => setMinRam(e.target.value)}
                      placeholder="1024"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-base text-white/70">
                      Max RAM (MB)
                    </label>
                    <input
                      className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                      type="number"
                      min={minRam || 256}
                      step="1"
                      value={maxRam}
                      onChange={e => setMaxRam(e.target.value)}
                      placeholder="2048"
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="text-base text-white/70">
                    Host port (optional)
                  </label>
                  <input
                    className="mt-2 w-full rounded-md bg-white/5 border border-white/10 px-4 py-3 text-base"
                    value={hostPort}
                    onChange={(e) => setHostPort(e.target.value)}
                    placeholder="25565"
                  />
                </div>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-md bg-brand-500 hover:bg-brand-400 transition px-6 py-3 font-semibold shadow-card text-lg"
                >
                  <FaPlusCircle /> Create server
                </button>
                {(serversError || typesError || versionsError) && (
                  <div className="text-base text-red-400">
                    {(serversError &&
                      `Servers error: ${serversError.message}`) ||
                      (typesError &&
                        `Types error: ${typesError.message}`) ||
                      (versionsError &&
                        `Versions error: ${versionsError.message}`)}
                  </div>
                )}
              </form>
            </div>
          </div>
        </section>
      )}
      {!selectedServer ? (
        <section className="container mt-16 mb-16">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-semibold">Your servers</h2>
          </div>
          {serversLoading && (
            <div className="text-white/70 text-lg">Loading servers…</div>
          )}
          {!serversLoading && servers.length === 0 && (
            <div className="text-white/70 text-lg">
              No servers yet. Create your first one above.
            </div>
          )}
          <div className="grid md:grid-cols-1 lg:grid-cols-1 xl:grid-cols-1 gap-6">
            {servers.map((s) => (
              <ServerListCard
                key={s.id}
                server={s}
                onClick={() => setSelectedServer(s.id)}
              />
            ))}
          </div>
        </section>
      ) : (
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
      )}
    </div>
  );
}

export default App;