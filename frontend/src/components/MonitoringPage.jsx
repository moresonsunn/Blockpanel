import React, { useEffect, useState } from 'react';
import { API } from '../lib/api';

function SmallStat({ label, value }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="text-xs text-white/60">{label}</div>
      <div className="text-2xl font-semibold mt-1">{value}</div>
    </div>
  );
}

export default function MonitoringPage() {
  const [data, setData] = useState(null);
  const [servers, setServers] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const r = await fetch(`${API}/monitoring/dashboard-data`, { headers: {} });
        if (!r.ok) return;
        const d = await r.json();
        if (!mounted) return;
        setData(d.system_overview || null);
        setServers(d.server_overview || []);
      } catch (e) {
        console.error('Failed to load dashboard data', e);
      }
    }
    load();
    const itv = setInterval(load, 5000);
    return () => { mounted = false; clearInterval(itv); };
  }, []);

  async function openServer(server) {
    setSelected({ loading: true });
    try {
      const r = await fetch(`${API}/monitoring/servers/${encodeURIComponent(server.name)}/current-stats`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      // Fetch a small logs preview as well
      let logs = '';
      try {
        const lid = d.id || d.id || d.container_id || d.id || server.id;
        const lr = await fetch(`${API}/servers/${encodeURIComponent(lid)}/logs?tail=200`);
        if (lr.ok) { const ld = await lr.json(); logs = ld.logs || ''; }
      } catch (e) { logs = ''; }
      setSelected({ loading: false, data: d, logs });
    } catch (e) {
      setSelected({ loading: false, error: String(e) });
    }
  }

  async function restartServer(server) {
    if (!server || !server.id) return alert('Missing server id');
    try {
      const r = await fetch(`${API}/servers/${encodeURIComponent(server.id)}/restart`, { method: 'POST' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      alert('Restart requested');
    } catch (e) {
      alert('Restart failed: ' + e);
    }
  }

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-start justify-between gap-6">
          <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SmallStat label="Total Servers" value={data?.total_servers ?? '--'} />
            <SmallStat label="Running" value={data?.running_servers ?? '--'} />
            <SmallStat label="Average CPU %" value={data?.avg_cpu_percent ?? '--'} />
          </div>
          <div className="w-80">
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="text-sm text-white/70">Recent Alerts</div>
              <div className="mt-2">
                {data?.alerts && data.alerts.length > 0 ? (
                  <div className="space-y-2">
                    {data.alerts.slice(0,6).map((a, idx) => (
                      <div key={idx} className={`p-2 rounded ${a.type === 'error' ? 'bg-red-500/10 text-red-300' : a.type === 'warning' ? 'bg-yellow-500/10 text-yellow-300' : 'bg-blue-500/10 text-blue-300'}`}>
                        <div className="text-xs">{a.message}</div>
                        <div className="text-[10px] text-white/60">{new Date(a.timestamp).toLocaleString()}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-white/50 mt-2">No recent alerts</div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm text-white/70">Servers</div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {servers.map(s => (
                  <div key={s.name} className="p-3 bg-black/20 rounded border border-white/10 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white">{s.name}</div>
                      <div className="text-xs text-white/60">Status: {s.status}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => openServer(s)} className="px-3 py-1 rounded bg-slate-600 text-sm">Open</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div>
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="text-sm text-white/70 mb-3">Server Details</div>
              {selected ? (
                selected.loading ? <div className="text-xs text-white/50">Loading…</div>
                : selected.error ? <div className="text-xs text-red-400">{selected.error}</div>
                : (
                  <div className="text-sm text-white/70 space-y-2">
                    <div>Type: {selected.data?.server_type || '—'}</div>
                    <div>Version: {selected.data?.server_version || '—'}</div>
                    <div>Java: {selected.data?.java_version || '—'}</div>
                    <div>CPU%: {selected.data?.cpu_percent ?? '--'}</div>
                    <div>Memory MB: {selected.data?.memory_usage_mb ?? '--'}</div>
                    <div>Players: {selected.data?.player_count ?? '--'}</div>
                    <div>Started: {selected.data?.started_at ? new Date(selected.data.started_at).toLocaleString() : '—'}</div>
                    <div>Uptime: {selected.data?.uptime_seconds ? `${Math.round(selected.data.uptime_seconds)}s` : (selected.data?.status === 'running' ? 'calculating…' : '—')}</div>
                    <div>Last exit code: {selected.data?.last_exit_code ?? '—'}</div>
                    <div className="mt-2">
                      <button onClick={() => restartServer(selected.data || server)} className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-sm">Restart</button>
                      <button onClick={() => { if (selected.logs) window.open('about:blank').document.write('<pre>' + selected.logs.replace(/</g,'&lt;') + '</pre>'); }} className="ml-2 px-3 py-1 rounded bg-slate-600 hover:bg-slate-500 text-sm">Logs Preview</button>
                    </div>
                    {selected.logs ? (
                      <details className="mt-2 text-xs text-white/60"><summary>Recent logs</summary><pre className="text-xs max-h-40 overflow-auto p-2 bg-black/10 rounded mt-2">{selected.logs}</pre></details>
                    ) : null}
                  </div>
                )
              ) : (
                <div className="text-xs text-white/50">Select a server to view details</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
