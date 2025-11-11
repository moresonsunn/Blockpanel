import React, { useEffect, useRef, useState } from 'react';
import { FaMemory, FaMicrochip, FaNetworkWired, FaSave } from 'react-icons/fa';
import { API } from '../../lib/api';

// Simple in-memory cache for Config per server
const CONFIG_CACHE = {}; // { [serverName]: { ts, propsData, eulaAccepted, javaVersions, currentVersion, propsText } }
const CACHE_TTL_MS = 60_000;

export default function ConfigPanel({ server, onRestart }) {
  const [javaVersions, setJavaVersions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentVersion, setCurrentVersion] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [selectedJava, setSelectedJava] = useState(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const [propsLoading, setPropsLoading] = useState(false);
  const [propsError, setPropsError] = useState('');
  const [propsData, setPropsData] = useState({
    max_players: '',
    motd: '',
    difficulty: '',
    online_mode: '',
    white_list: '',
    pvp: '',
    allow_nether: '',
    enable_command_block: '',
    view_distance: '',
    simulation_distance: ''
  });
  const baselinePropsRef = useRef('');
  const [javaArgs, setJavaArgs] = useState('');
  const [javaArgsSaving, setJavaArgsSaving] = useState(false);
  const [javaArgsError, setJavaArgsError] = useState('');
  const javaArgsBaselineRef = useRef('');

  // EULA state
  const [eulaLoading, setEulaLoading] = useState(false);
  const [eulaError, setEulaError] = useState('');
  const [eulaAccepted, setEulaAccepted] = useState(false);

  // Server icon upload
  const [iconUploading, setIconUploading] = useState(false);
  const [iconMessage, setIconMessage] = useState('');

  useEffect(() => {
    async function fetchJavaVersions() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API}/servers/${server.id}/java-versions`);
        if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
        const data = await response.json();
        const raw = Array.isArray(data.available_versions) ? data.available_versions : [];
        const normalized = raw.map(v => (
          typeof v === 'string'
            ? { version: v, name: `Java ${v}`, description: v === '21' ? 'Latest LTS' : (v === '17' ? 'LTS' : '') }
            : v
        ));
        setJavaVersions(normalized);
        setCurrentVersion(data.current_version || data.java_version || null);
      } catch (e) { setError(e.message); } finally { setLoading(false); }
    }
    fetchJavaVersions();
  }, [server.id]);

  useEffect(() => {
    const abort = new AbortController();
    let timeoutIds = [];

    function withTimeout(promise, ms, controller) {
      return new Promise((resolve, reject) => {
        const id = setTimeout(() => {
          try { controller.abort(); } catch {}
          reject(new DOMException('Timeout', 'AbortError'));
        }, ms);
        timeoutIds.push(id);
        promise.then((v) => { clearTimeout(id); resolve(v); }).catch((e) => { clearTimeout(id); reject(e); });
      });
    }

    async function loadAll(staleOnly = false) {
      const cached = CONFIG_CACHE[server.name];
      const now = Date.now();
      if (cached && now - cached.ts < CACHE_TTL_MS) {
        // hydrate from cache first
        setPropsData(cached.propsData || { max_players: '', motd: '', difficulty: '', online_mode: '', white_list: '' });
        setEulaAccepted(!!cached.eulaAccepted);
        baselinePropsRef.current = cached.propsText || '';
        if (cached.javaVersions) setJavaVersions(cached.javaVersions);
        if (cached.currentVersion) setCurrentVersion(cached.currentVersion);
        if (typeof cached.javaArgs === 'string') {
          setJavaArgs(cached.javaArgs);
          javaArgsBaselineRef.current = cached.javaArgs;
        }
        if (staleOnly) return; // no network fetch
      }

      // Fetch in parallel with timeouts
      setPropsLoading(true); setEulaLoading(true); setError(null);
      setPropsError(''); setEulaError('');
      try {
        // Try bundled endpoint first (properties + eula + java info)
        const bundle = await withTimeout(fetch(`${API}/servers/${encodeURIComponent(server.name)}/config-bundle?container_id=${encodeURIComponent(server.id)}`, { signal: abort.signal }), 8000, abort)
          .then(async (r) => {
            if (!r.ok) return null;
            const d = await r.json();
            if (d && d.properties) {
              const map = d.properties || {};
              const pd = {
                max_players: map['max-players'] || '',
                motd: map['motd'] || '',
                difficulty: map['difficulty'] || '',
                online_mode: map['online-mode'] || '',
                white_list: map['white-list'] || '',
                pvp: map['pvp'] || '',
                allow_nether: map['allow-nether'] || '',
                enable_command_block: map['enable-command-block'] || '',
                view_distance: map['view-distance'] || '',
                simulation_distance: map['simulation-distance'] || ''
              };
              setPropsData(pd);
              setEulaAccepted(!!d.eula_accepted);
              // Java info from bundle when available
              if (d.java) {
                const rawJ = Array.isArray(d.java.available_versions) ? d.java.available_versions : [];
                const normalizedJ = rawJ.map(v => (
                  typeof v === 'string'
                    ? { version: v, name: `Java ${v}`, description: v === '21' ? 'Latest LTS' : (v === '17' ? 'LTS' : '') }
                    : v
                ));
                setJavaVersions(normalizedJ);
                setCurrentVersion(d.java.current_version || null);
                if (typeof d.java.custom_args === 'string') {
                  setJavaArgs(d.java.custom_args);
                  javaArgsBaselineRef.current = d.java.custom_args;
                }
              }
              // Rebuild baseline text from map minimally (best-effort)
              const text = Object.entries(map).map(([k, v]) => `${k}=${v}`).join('\n');
              baselinePropsRef.current = text;
              return {
                propsData: pd,
                propsText: text,
                eulaAccepted: !!d.eula_accepted,
                javaArgs: typeof d?.java?.custom_args === 'string' ? d.java.custom_args : undefined,
              };
            }
            return null;
          })
          .catch(() => null);

        const propsP = withTimeout(fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`, { signal: abort.signal }), 10000, abort)
          .then(async (r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const d = await r.json();
            const text = d.content || '';
            baselinePropsRef.current = text;
            const lines = text.split(/\r?\n/);
            const map = {};
            for (const line of lines) {
              if (!line || line.trim().startsWith('#')) continue;
              const idx = line.indexOf('=');
              if (idx > -1) { const k = line.substring(0, idx).trim(); const v = line.substring(idx + 1).trim(); map[k] = v; }
            }
            const pd = {
              max_players: map['max-players'] || '',
              motd: map['motd'] || '',
              difficulty: map['difficulty'] || '',
              online_mode: map['online-mode'] || '',
              white_list: map['white-list'] || '',
              pvp: map['pvp'] || '',
              allow_nether: map['allow-nether'] || '',
              enable_command_block: map['enable-command-block'] || '',
              view_distance: map['view-distance'] || '',
              simulation_distance: map['simulation-distance'] || ''
            };
            setPropsData(pd);
            return { propsData: pd, propsText: text };
          })
          .catch((e) => { if (e?.name !== 'AbortError') setPropsError(String(e)); return null; });

        const eulaP = withTimeout(fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('eula.txt')}`, { signal: abort.signal }), 10000, abort)
          .then(async (r) => {
            if (!r.ok) return { eulaAccepted: false };
            const d = await r.json();
            const text = (d.content || '').toLowerCase();
            const acc = /eula\s*=\s*true/.test(text);
            setEulaAccepted(acc);
            return { eulaAccepted: acc };
          })
          .catch((e) => { if (e?.name !== 'AbortError') setEulaError(String(e)); return null; });

        const javaP = withTimeout(fetch(`${API}/servers/${server.id}/java-versions`, { signal: abort.signal }), 10000, abort)
          .then(async (r) => {
            if (!r.ok) return null;
            const data = await r.json();
            const raw = Array.isArray(data.available_versions) ? data.available_versions : [];
            const normalized = raw.map(v => (
              typeof v === 'string'
                ? { version: v, name: `Java ${v}`, description: v === '21' ? 'Latest LTS' : (v === '17' ? 'LTS' : '') }
                : v
            ));
            setJavaVersions(normalized);
            const cur = data.current_version || data.java_version || null;
            setCurrentVersion(cur);
            return { javaVersions: normalized, currentVersion: cur };
          })
          .catch((e) => { /* ignore abort/other here */ return null; });

        const javaArgsP = withTimeout(fetch(`${API}/servers/${server.id}/java-args`, { signal: abort.signal }), 8000, abort)
          .then(async (r) => {
            if (!r.ok) return null;
            const data = await r.json();
            const val = typeof data?.java_args === 'string' ? data.java_args : '';
            setJavaArgs(val);
            javaArgsBaselineRef.current = val;
            return { javaArgs: val };
          })
          .catch(() => null);

        const results = await Promise.all([propsP, eulaP, javaP, javaArgsP]);
        const merged = Object.assign({}, ...results.filter(Boolean));
        CONFIG_CACHE[server.name] = { ts: Date.now(), ...(CONFIG_CACHE[server.name] || {}), ...merged };
      } finally {
        setPropsLoading(false); setEulaLoading(false);
      }
    }

    // try cache-first; then revalidate
    loadAll(false);

    return () => {
      try { abort.abort(); } catch {}
      timeoutIds.forEach((id) => clearTimeout(id));
    };
  }, [server.name, server.id, refreshNonce]);

  async function saveProps() {
    try {
      setPropsLoading(true);
      setPropsError('');
      let baseText = baselinePropsRef.current;
      if (!baseText) {
        const r = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`);
        const d = await r.json();
        baseText = d.content || '';
      }
      let lines = (baseText || '').split(/\r?\n/);
      const setOrAdd = (k, val) => { let found = false; lines = lines.map(line => { if (line.startsWith(k + '=')) { found = true; return `${k}=${val}`; } return line; }); if (!found) lines.push(`${k}=${val}`); };
      setOrAdd('max-players', propsData.max_players || '20');
      setOrAdd('motd', propsData.motd || 'A Minecraft Server');
      setOrAdd('difficulty', propsData.difficulty || 'easy');
      setOrAdd('online-mode', propsData.online_mode || 'true');
      if (propsData.white_list) setOrAdd('white-list', propsData.white_list);
      if (propsData.pvp) setOrAdd('pvp', propsData.pvp);
      if (propsData.allow_nether) setOrAdd('allow-nether', propsData.allow_nether);
      if (propsData.enable_command_block) setOrAdd('enable-command-block', propsData.enable_command_block);
      if (propsData.view_distance) setOrAdd('view-distance', propsData.view_distance);
      if (propsData.simulation_distance) setOrAdd('simulation-distance', propsData.simulation_distance);
      const newContent = lines.join('\n');
      baselinePropsRef.current = newContent;
      const body = new URLSearchParams({ content: newContent });
      const wr = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
      if (!wr.ok) throw new Error(`HTTP ${wr.status}`);
      alert('server.properties saved. Restart the server to apply changes.');
    } catch (e) { setPropsError(String(e)); } finally { setPropsLoading(false); }
  }

  async function saveEula(accepted) {
    try {
      setEulaLoading(true);
      setEulaError('');
      const content = `# EULA accepted via panel\neula=${accepted ? 'true' : 'false'}\n`;
      const body = new URLSearchParams({ content });
      const wr = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('eula.txt')}`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
      if (!wr.ok) throw new Error(`HTTP ${wr.status}`);
      setEulaAccepted(accepted);
    } catch (e) { setEulaError(String(e)); } finally { setEulaLoading(false); }
  }

  async function handleIconUpload(ev) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    setIconMessage(''); setIconUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await fetch(`${API}/servers/${encodeURIComponent(server.name)}/upload?path=.`, { method: 'POST', body: fd });
      setIconMessage('server-icon uploaded. Restart server to apply.');
    } catch (e) { setIconMessage('Upload failed: ' + String(e)); } finally { setIconUploading(false); }
  }

  async function updateJavaVersion(version) {
    setUpdating(true);
    setError(null);
    try {
      const response = await fetch(`${API}/servers/${server.id}/java-version`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ java_version: version }) });
      if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || `HTTP ${response.status}`); }
      const data = await response.json();
      // Re-query server info to confirm persisted value (handles recreate flows)
      try {
        const infoResp = await fetch(`${API}/servers/${server.id}/info`);
        if (infoResp.ok) {
          const info = await infoResp.json();
          if (info && info.java_version) setCurrentVersion(info.java_version);
        } else {
          // fallback to returned value
          if (data && data.java_version) setCurrentVersion(data.java_version);
        }
      } catch (e) {
        if (data && data.java_version) setCurrentVersion(data.java_version);
      }
      alert(`Java version updated to ${data.java_version}`);
    } catch (e) { setError(e.message); } finally { setUpdating(false); }
  }

  // Helper used by the small 'Change Java' control below
  async function applySelectedJava() {
    if (!selectedJava) return alert('Select a Java version first');
    await updateJavaVersion(selectedJava);
  }

  async function saveJavaArgs() {
    setJavaArgsSaving(true);
    setJavaArgsError('');
    try {
      const response = await fetch(`${API}/servers/${server.id}/java-args`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ java_args: javaArgs })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || `HTTP ${response.status}`);
      }
      const saved = typeof data?.java_args === 'string' ? data.java_args : '';
      setJavaArgs(saved);
      javaArgsBaselineRef.current = saved;
      CONFIG_CACHE[server.name] = { ts: Date.now(), ...(CONFIG_CACHE[server.name] || {}), javaArgs: saved };
      alert('Custom Java arguments updated. Restart the server to apply changes.');
    } catch (e) {
      setJavaArgsError(String(e));
    } finally {
      setJavaArgsSaving(false);
    }
  }

  function resetJavaArgs() {
    setJavaArgs(javaArgsBaselineRef.current || '');
    setJavaArgsError('');
  }

  if (loading) return (<div className="p-4 bg-black/20 rounded-lg"><div className="text-sm text-white/70">Loading Java version information...</div></div>);
  if (error) return (<div className="p-4 bg-black/20 rounded-lg"><div className="text-sm text-red-400">Error: {error}</div></div>);

  return (
    <div className="p-4 bg-black/20 rounded-lg" style={{ minHeight: 500, minWidth: 1043.02 }}>
      <div className="flex items-center justify-between mb-4">
        <div className="text-lg font-semibold text-white">Server Configuration</div>
        <div className="flex items-center gap-2">
          <button onClick={() => setRefreshNonce(n => n + 1)} className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm">Refresh</button>
        </div>
      </div>

      {/* EULA Section */}
      <div className="mb-6 p-3 bg-white/5 border border-white/10 rounded-lg">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-white/70">EULA Acceptance</div>
            <div className="text-xs text-white/50">You must accept the Minecraft EULA to run the server</div>
          </div>
          <label className="inline-flex items-center gap-2 text-sm text-white/80">
            <input type="checkbox" checked={!!eulaAccepted} disabled={eulaLoading} onChange={(e) => saveEula(e.target.checked)} />
            Accept EULA
          </label>
        </div>
        {eulaError && <div className="text-xs text-red-400 mt-2">{eulaError}</div>}
      </div>

      {/* Two-column layout: left = Java/EULA/Icon, right = Quick Settings */}
      <div className="mb-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          {/* Java Section (compact) */}
          <div className="mb-4">
            <div className="text-sm text-white/70 mb-2">Java Version</div>
            <div className="text-xs text-white/50 mb-2">Current version: <span className="text-green-400">{currentVersion}</span></div>
            <div className="grid grid-cols-2 gap-3">
              {javaVersions?.map((javaInfo) => (
                <button key={javaInfo.version} onClick={() => updateJavaVersion(javaInfo.version)} disabled={updating || currentVersion === javaInfo.version}
                  className={`p-3 rounded-lg border transition text-left ${currentVersion === javaInfo.version ? 'bg-brand-500 border-brand-400 text-white' : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10 hover:text-white'} ${updating ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <div className="font-semibold">{javaInfo.name}</div>
                  <div className="text-xs opacity-70">{javaInfo.description}</div>
                </button>
              ))}
            </div>
            {updating && (<div className="text-sm text-yellow-400 mt-2">Updating Java version...</div>)}
            {currentVersion && (
              <div className="mt-3 p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                <div className="text-sm text-blue-300 mb-2">💡 Tip</div>
                <div className="text-xs text-blue-200">After changing the Java version, restart the server for the changes to take effect.</div>
                {onRestart && (
                  <button onClick={() => onRestart(server.id)} className="mt-2 px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded transition">Restart Server</button>
                )}
              </div>
            )}
          </div>

          <div className="mb-4 p-3 bg-white/5 border border-white/10 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-sm text-white/70">Custom Java Arguments (JAVA_OPTS)</div>
                <div className="text-xs text-white/50">Advanced JVM flags applied when the server starts.</div>
              </div>
              <button
                type="button"
                onClick={resetJavaArgs}
                disabled={javaArgsSaving || javaArgs === (javaArgsBaselineRef.current || '')}
                className={`px-3 py-1 text-xs rounded ${javaArgsSaving || javaArgs === (javaArgsBaselineRef.current || '') ? 'bg-white/5 text-white/40 cursor-not-allowed' : 'bg-white/10 hover:bg-white/20 text-white/80'}`}
              >Reset</button>
            </div>
            <textarea
              value={javaArgs}
              onChange={(e) => { setJavaArgs(e.target.value); setJavaArgsError(''); }}
              className="w-full rounded bg-black/40 border border-white/10 px-3 py-2 text-white text-sm font-mono min-h-[88px]"
              placeholder="Example: -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC"
            />
            {javaArgsError && <div className="text-xs text-red-400 mt-2">{javaArgsError}</div>}
            <div className="flex items-center justify-between mt-3">
              <div className="text-xs text-white/40">Leave empty to use BlockPanel defaults. Arguments are normalized to a single line.</div>
              <button
                type="button"
                onClick={saveJavaArgs}
                disabled={javaArgsSaving || javaArgs === (javaArgsBaselineRef.current || '')}
                className={`px-3 py-1.5 text-xs rounded ${javaArgsSaving || javaArgs === (javaArgsBaselineRef.current || '') ? 'bg-brand-500/30 text-white/40 cursor-not-allowed' : 'bg-brand-500 hover:bg-brand-400 text-white'} flex items-center gap-2`}
              >
                {javaArgsSaving && <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                Save Arguments
              </button>
            </div>
          </div>

          {/* EULA Section (left) */}
          <div className="mb-4 p-3 bg-white/5 border border-white/10 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-white/70">EULA Acceptance</div>
                <div className="text-xs text-white/50">You must accept the Minecraft EULA to run the server</div>
              </div>
              <label className="inline-flex items-center gap-2 text-sm text-white/80">
                <input type="checkbox" checked={!!eulaAccepted} disabled={eulaLoading} onChange={(e) => saveEula(e.target.checked)} />
                Accept EULA
              </label>
            </div>
            {eulaError && <div className="text-xs text-red-400 mt-2">{eulaError}</div>}
          </div>

          {/* Server Icon Upload (left) */}
          <div className="mb-4">
            <div className="text-sm text-white/70 mb-2">Server Icon</div>
            <div className="flex items-center gap-3">
              <label className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 cursor-pointer inline-flex items-center gap-2 text-sm">
                Upload server-icon.png
                <input type="file" className="hidden" accept="image/png" onChange={handleIconUpload} />
              </label>
              {iconUploading && <span className="text-white/60 text-sm">Uploading…</span>}
              {iconMessage && <span className="text-white/60 text-sm">{iconMessage}</span>}
            </div>
          </div>
        </div>

        <div>
          {/* Quick Settings (right) */}
          <div className="border-t border-white/10 pt-4 mt-0">
            <div className="text-sm text-white/70 mb-3">Quick Settings (server.properties)</div>
            {propsError && <div className="text-xs text-red-400 mb-2">{propsError}</div>}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-white/60 mb-1">Max Players</label>
                <input value={propsData.max_players} onChange={e=>setPropsData({...propsData, max_players: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="20" />
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Online Mode</label>
                <select value={propsData.online_mode} onChange={e=>setPropsData({...propsData, online_mode: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="true" style={{ backgroundColor: '#1f2937' }}>true</option>
                  <option value="false" style={{ backgroundColor: '#1f2937' }}>false</option>
                </select>
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs text-white/60 mb-1">MOTD</label>
                <input value={propsData.motd} onChange={e=>setPropsData({...propsData, motd: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="A Minecraft Server" />
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Difficulty</label>
                <select value={propsData.difficulty} onChange={e=>setPropsData({...propsData, difficulty: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="peaceful" style={{ backgroundColor: '#1f2937' }}>peaceful</option>
                  <option value="easy" style={{ backgroundColor: '#1f2937' }}>easy</option>
                  <option value="normal" style={{ backgroundColor: '#1f2937' }}>normal</option>
                  <option value="hard" style={{ backgroundColor: '#1f2937' }}>hard</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Whitelist Enabled</label>
                <select value={propsData.white_list} onChange={e=>setPropsData({...propsData, white_list: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="true" style={{ backgroundColor: '#1f2937' }}>true</option>
                  <option value="false" style={{ backgroundColor: '#1f2937' }}>false</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">PVP Enabled</label>
                <select value={propsData.pvp} onChange={e=>setPropsData({...propsData, pvp: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="true" style={{ backgroundColor: '#1f2937' }}>true</option>
                  <option value="false" style={{ backgroundColor: '#1f2937' }}>false</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Allow Nether</label>
                <select value={propsData.allow_nether} onChange={e=>setPropsData({...propsData, allow_nether: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="true" style={{ backgroundColor: '#1f2937' }}>true</option>
                  <option value="false" style={{ backgroundColor: '#1f2937' }}>false</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Enable Command Blocks</label>
                <select value={propsData.enable_command_block} onChange={e=>setPropsData({...propsData, enable_command_block: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" style={{ backgroundColor: '#1f2937' }}>
                  <option value="true" style={{ backgroundColor: '#1f2937' }}>true</option>
                  <option value="false" style={{ backgroundColor: '#1f2937' }}>false</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">View Distance</label>
                <input type="number" min={2} max={32} value={propsData.view_distance} onChange={e=>setPropsData({...propsData, view_distance: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="10" />
              </div>
              <div>
                <label className="block text-xs text-white/60 mb-1">Simulation Distance</label>
                <input type="number" min={2} max={32} value={propsData.simulation_distance} onChange={e=>setPropsData({...propsData, simulation_distance: e.target.value})} className="w-full rounded bg-white/5 border border-white/10 px-3 py-2 text-white" placeholder="10" />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <button onClick={saveProps} disabled={propsLoading} className="px-3 py-1.5 bg-brand-500 hover:bg-brand-400 rounded text-sm disabled:opacity-50">{propsLoading ? 'Saving…' : 'Save server.properties'}</button>
              {onRestart && <button onClick={() => onRestart(server.id)} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm">Restart Server</button>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
