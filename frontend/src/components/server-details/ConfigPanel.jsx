import React, { useEffect, useState } from 'react';
import { FaMemory, FaMicrochip, FaNetworkWired, FaSave } from 'react-icons/fa';
import { API } from '../../lib/api';

export default function ConfigPanel({ server, onRestart }) {
  const [javaVersions, setJavaVersions] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentVersion, setCurrentVersion] = useState(null);
  const [updating, setUpdating] = useState(false);

  const [propsLoading, setPropsLoading] = useState(false);
  const [propsError, setPropsError] = useState('');
  const [propsData, setPropsData] = useState({ max_players: '', motd: '', difficulty: '', online_mode: '' });

  useEffect(() => {
    async function fetchJavaVersions() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API}/servers/${server.id}/java-versions`);
        if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
        const data = await response.json();
        setJavaVersions(data.available_versions);
        setCurrentVersion(data.current_version);
      } catch (e) { setError(e.message); } finally { setLoading(false); }
    }
    fetchJavaVersions();
  }, [server.id]);

  useEffect(() => {
    async function loadProps() {
      setPropsLoading(true);
      setPropsError('');
      try {
        const r = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        const text = d.content || '';
        const lines = text.split(/\r?\n/);
        const map = {};
        for (const line of lines) {
          if (!line || line.trim().startsWith('#')) continue;
          const idx = line.indexOf('=');
          if (idx > -1) { const k = line.substring(0, idx).trim(); const v = line.substring(idx + 1).trim(); map[k] = v; }
        }
        setPropsData({
          max_players: map['max-players'] || '',
          motd: map['motd'] || '',
          difficulty: map['difficulty'] || '',
          online_mode: map['online-mode'] || '',
        });
      } catch (e) { setPropsError(String(e)); } finally { setPropsLoading(false); }
    }
    loadProps();
  }, [server.name]);

  async function saveProps() {
    try {
      setPropsLoading(true);
      setPropsError('');
      const r = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`);
      const d = await r.json();
      let lines = (d.content || '').split(/\r?\n/);
      const setOrAdd = (k, val) => { let found = false; lines = lines.map(line => { if (line.startsWith(k + '=')) { found = true; return `${k}=${val}`; } return line; }); if (!found) lines.push(`${k}=${val}`); };
      setOrAdd('max-players', propsData.max_players || '20');
      setOrAdd('motd', propsData.motd || 'A Minecraft Server');
      setOrAdd('difficulty', propsData.difficulty || 'easy');
      setOrAdd('online-mode', propsData.online_mode || 'true');
      const newContent = lines.join('\n');
      const body = new URLSearchParams({ content: newContent });
      const wr = await fetch(`${API}/servers/${encodeURIComponent(server.name)}/file?path=${encodeURIComponent('server.properties')}`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body });
      if (!wr.ok) throw new Error(`HTTP ${wr.status}`);
      alert('server.properties saved. Restart the server to apply changes.');
    } catch (e) { setPropsError(String(e)); } finally { setPropsLoading(false); }
  }

  async function updateJavaVersion(version) {
    setUpdating(true);
    setError(null);
    try {
      const response = await fetch(`${API}/servers/${server.id}/java-version`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ java_version: version }) });
      if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || `HTTP ${response.status}`); }
      const data = await response.json();
      setCurrentVersion(data.java_version);
      alert(`Java version updated to ${data.java_version}`);
    } catch (e) { setError(e.message); } finally { setUpdating(false); }
  }

  if (loading) return (<div className="p-4 bg-black/20 rounded-lg"><div className="text-sm text-white/70">Loading Java version information...</div></div>);
  if (error) return (<div className="p-4 bg-black/20 rounded-lg"><div className="text-sm text-red-400">Error: {error}</div></div>);

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="text-lg font-semibold text-white mb-4">Server Configuration</div>
      <div className="mb-6">
        <div className="text-sm text-white/70 mb-2">Java Version</div>
        <div className="text-xs text-white/50 mb-3">Current version: <span className="text-green-400">{currentVersion}</span></div>
        <div className="grid grid-cols-2 gap-3">
          {javaVersions?.map((javaInfo) => (
            <button key={javaInfo.version} onClick={() => updateJavaVersion(javaInfo.version)} disabled={updating || currentVersion === javaInfo.version}
              className={`p-3 rounded-lg border transition ${currentVersion === javaInfo.version ? 'bg-brand-500 border-brand-400 text-white' : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10 hover:text-white'} ${updating ? 'opacity-50 cursor-not-allowed' : ''}`}>
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

      <div className="border-t border-white/10 pt-4 mt-6">
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
        </div>
        <div className="mt-3 flex items-center gap-2">
          <button onClick={saveProps} disabled={propsLoading} className="px-3 py-1.5 bg-brand-500 hover:bg-brand-400 rounded text-sm disabled:opacity-50">{propsLoading ? 'Saving…' : 'Save server.properties'}</button>
          {onRestart && <button onClick={() => onRestart(server.id)} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm">Restart Server</button>}
        </div>
      </div>
    </div>
  );
}
