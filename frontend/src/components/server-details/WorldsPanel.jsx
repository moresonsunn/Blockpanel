import React, { useEffect, useState } from 'react';
import { FaUpload } from 'react-icons/fa';
import { API } from '../../lib/api';

export default function WorldsPanel({ serverName }) {
  const [worlds, setWorlds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);

  async function refresh() {
    setLoading(true); setError('');
    try {
      const r = await fetch(`${API}/worlds/${encodeURIComponent(serverName)}`);
      const d = await r.json();
      setWorlds(d.worlds || []);
    } catch (e) { setError(String(e)); } finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, [serverName]);

  async function upload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await fetch(`${API}/worlds/${encodeURIComponent(serverName)}/upload?world_name=world`, { method: 'POST', body: fd });
      await refresh();
    } finally { setUploading(false); }
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
