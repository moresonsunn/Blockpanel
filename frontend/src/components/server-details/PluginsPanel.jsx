import React, { useEffect, useState } from 'react';
import { FaUpload } from 'react-icons/fa';
import { API } from '../../lib/api';

export default function PluginsPanel({ serverName }) {
  const [plugins, setPlugins] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function refresh() {
    setLoading(true); setError('');
    try {
      const r = await fetch(`${API}/plugins/${encodeURIComponent(serverName)}`);
      const d = await r.json();
      setPlugins(d.plugins || []);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, [serverName]);

  async function upload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    await fetch(`${API}/plugins/${encodeURIComponent(serverName)}/upload`, { method: 'POST', body: fd });
    await refresh();
  }

  async function reloadPlugins() { await fetch(`${API}/plugins/${encodeURIComponent(serverName)}/reload`, { method: 'POST' }); }

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
