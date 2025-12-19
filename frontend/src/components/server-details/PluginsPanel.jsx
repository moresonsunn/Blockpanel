import React, { useEffect, useState } from 'react';
import { FaUpload } from 'react-icons/fa';
import { API, getStoredToken } from '../../lib/api';

export default function PluginsPanel({ serverName }) {
  const sName = serverName || '';
  const [plugins, setPlugins] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploadPct, setUploadPct] = useState(0);
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    setLoading(true); setError('');
    try {
  if (!sName) { setPlugins([]); return; }
  const r = await fetch(`${API}/plugins/${encodeURIComponent(sName)}`);
      const d = await r.json();
      setPlugins(d.plugins || []);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }

  useEffect(() => { refresh(); }, [serverName]);

  async function upload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    setUploading(true); setUploadPct(0);
    try {
      const token = getStoredToken();
  if (!sName) return;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', `${API}/plugins/${encodeURIComponent(sName)}/upload`, true);
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) setUploadPct(Math.round((ev.loaded/ev.total)*100));
      };
      xhr.onload = async () => { await refresh(); };
      xhr.onerror = () => setError('Upload failed');
      const fd = new FormData();
      fd.append('file', file);
      xhr.send(fd);
    } finally {
      // Allow a short delay so the UI can show 100%
      setTimeout(() => { setUploading(false); setUploadPct(0); }, 400);
    }
  }

  async function reloadPlugins() { if (!sName) return; await fetch(`${API}/plugins/${encodeURIComponent(sName)}/reload`, { method: 'POST' }); }

  async function remove(name) {
    if (!sName) return;
    await fetch(`${API}/plugins/${encodeURIComponent(sName)}/${encodeURIComponent(name)}`, { method: 'DELETE' });
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
          <button onClick={reloadPlugins} className="rounded bg-white/10 hover:bg-white/20 border border-white/10 px-3 py-1.5 text-white/80">Reload</button>
        </div>
      </div>
      {uploading && (
        <div className="mb-2">
          <div className="text-xs text-white/70">Uploading… {uploadPct}%</div>
          <div className="w-full h-1.5 bg-white/10 rounded overflow-hidden"><div className="h-full bg-brand-500" style={{ width: `${uploadPct}%` }} /></div>
        </div>
      )}
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
