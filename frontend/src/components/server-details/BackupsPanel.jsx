import React, { useEffect, useState } from 'react';
import { FaDownload } from 'react-icons/fa';
import { API } from '../../lib/api';

export default function BackupsPanel({ serverName }) {
  const [list, setList] = useState([]);
  async function refresh() {
    const r = await fetch(`${API}/servers/${encodeURIComponent(serverName)}/backups`);
    const d = await r.json();
    setList(d.items || []);
  }
  useEffect(() => { refresh(); }, [serverName]);

  async function createBackup() {
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/backups`, { method: 'POST' });
    refresh();
  }
  async function restore(file) {
    await fetch(`${API}/servers/${encodeURIComponent(serverName)}/restore?file=${encodeURIComponent(file)}`, { method: 'POST' });
    alert('Restore triggered. Stop the server before restoring for safety.');
  }

  return (
    <div className="p-4 bg-black/20 rounded-lg">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm text-white/70">Backups</div>
        <button onClick={createBackup} className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 inline-flex items-center gap-2">
          <FaDownload /> Create backup
        </button>
      </div>
      <div className="space-y-1">
        {list.map((b) => (
          <div key={b.file} className="flex items-center justify-between bg-white/5 border border-white/10 rounded px-3 py-2 text-sm">
            <div>
              {b.file} <span className="text-white/50">({Math.ceil((b.size || 0) / 1024 / 1024)} MB)</span>
            </div>
            <div className="flex gap-2">
              <button onClick={() => restore(b.file)} className="rounded bg-white/10 hover:bg-white/20 px-2 py-1">Restore</button>
            </div>
          </div>
        ))}
        {list.length === 0 && <div className="text-white/60 text-sm">No backups yet.</div>}
      </div>
    </div>
  );
}
