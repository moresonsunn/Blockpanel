import React, { useCallback, useEffect, useRef, useState } from 'react';
import { API, authHeaders } from '../lib/api';

const STATUS_STYLES = {
  ok: 'bg-emerald-500/15 text-emerald-200 border border-emerald-500/30',
  warning: 'bg-yellow-500/15 text-yellow-200 border border-yellow-500/40',
  error: 'bg-red-500/15 text-red-200 border border-red-500/40',
  critical: 'bg-red-500/15 text-red-200 border border-red-500/40',
  info: 'bg-blue-500/15 text-blue-200 border border-blue-500/30',
  success: 'bg-emerald-500/15 text-emerald-200 border border-emerald-500/30',
  unknown: 'bg-white/5 text-white/70 border border-white/10',
};

const STATUS_LABELS = {
  ok: 'OK',
  warning: 'Warning',
  error: 'Error',
  critical: 'Critical',
  info: 'Info',
  success: 'Success',
  unknown: 'Unknown',
};

function SmallStat({ label, value, loading }) {
  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="text-xs text-white/60">{label}</div>
      <div className="text-2xl font-semibold mt-1">{loading ? '…' : value ?? '—'}</div>
    </div>
  );
}

function StatusBadge({ status, count }) {
  const key = (status || 'unknown').toLowerCase();
  const cls = STATUS_STYLES[key] || STATUS_STYLES.unknown;
  const label = STATUS_LABELS[key] || STATUS_LABELS.unknown;
  const suffix = typeof count === 'number' ? ` · ${count}` : '';
  return (
    <span className={`px-2 py-1 rounded-full text-[10px] font-semibold tracking-wide uppercase ${cls}`}>
      {label}{suffix}
    </span>
  );
}

function IntegrityPanel({ reports, summary, onRefresh, loading }) {
  const hasReports = reports && reports.length > 0;
  const serverStatusEntries = summary?.server_status ? Object.entries(summary.server_status) : [];

  return (
    <div className="rounded-lg bg-white/5 border border-white/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <div className="text-sm text-white/80">Integrity Checks</div>
          <div className="text-xs text-white/50">{summary?.total ? `${summary.total} historical reports` : 'Waiting for first report…'}</div>
        </div>
        <div className="flex items-center gap-2">
          {['ok', 'warning', 'error'].map((key) => (
            summary?.by_status?.[key] ? <StatusBadge key={key} status={key} count={summary.by_status[key]} /> : null
          ))}
          <button
            type="button"
            onClick={() => onRefresh?.({ showSpinner: true })}
            className="px-2 py-1 text-xs rounded bg-white/10 hover:bg-white/20 text-white disabled:opacity-40"
            disabled={loading}
          >Refresh</button>
        </div>
      </div>

      {serverStatusEntries.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2 text-[11px] text-white/60">
          {serverStatusEntries.slice(0, 6).map(([name, status]) => (
            <span key={name} className="flex items-center gap-1">
              <span className="text-white/70">{name}</span>
              <StatusBadge status={status} />
            </span>
          ))}
        </div>
      )}

      {loading && !hasReports ? (
        <div className="text-xs text-white/50">Loading latest reports…</div>
      ) : hasReports ? (
        <div className="space-y-3">
          {reports.map((report) => {
            const issues = Array.isArray(report.issues) ? report.issues : [];
            const preview = issues.slice(0, 3);
            const latestBackup = report.metadata?.latest_backup;
            return (
              <div key={report.id} className="p-3 rounded border border-white/10 bg-black/20">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-white">{report.server_name || 'All Servers'}</div>
                    <div className="text-[11px] text-white/50">
                      Task: {report.task_name || '—'}
                    </div>
                  </div>
                  <StatusBadge status={report.status} />
                </div>
                <div className="text-[11px] text-white/40 mt-1">
                  Checked {new Date(report.checked_at).toLocaleString()}
                </div>
                {issues.length > 0 ? (
                  <div className="mt-2 space-y-1 text-xs text-white/70">
                    {preview.map((issue, idx) => (
                      <div key={idx} className="flex gap-2">
                        <span className="text-white/40">•</span>
                        <span>
                          <span className="text-white/80">{issue.code || 'Issue'}</span>
                          {issue.message ? ` – ${issue.message}` : ''}
                        </span>
                      </div>
                    ))}
                    {issues.length > preview.length && (
                      <div className="text-[11px] text-white/40">+{issues.length - preview.length} more</div>
                    )}
                  </div>
                ) : (
                  <div className="mt-2 text-xs text-white/50">No issues detected.</div>
                )}
                {latestBackup && latestBackup.created_at && (
                  <div className="mt-2 text-[11px] text-white/50">
                    Latest backup: {new Date(latestBackup.created_at).toLocaleString()} {latestBackup.auto ? '(auto)' : ''}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-xs text-white/50">No integrity reports available yet.</div>
      )}
    </div>
  );
}

export default function MonitoringPage() {
  const [health, setHealth] = useState(null);
  const [servers, setServers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [alertsSummary, setAlertsSummary] = useState(null);
  const [integrity, setIntegrity] = useState({ reports: [], summary: null });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const isMounted = useRef(true);

  useEffect(() => () => { isMounted.current = false; }, []);

  const loadData = useCallback(async (options = {}) => {
    const { showSpinner = false } = options;
    if (showSpinner && isMounted.current) {
      setLoading(true);
    }

    try {
      const headers = authHeaders();
      const [dashboardRes, integrityRes, alertsRes] = await Promise.all([
        fetch(`${API}/monitoring/dashboard-data`, { headers }),
        fetch(`${API}/monitoring/integrity-reports?limit=8`, { headers }),
        fetch(`${API}/monitoring/alerts`, { headers }),
      ]);

      if (!isMounted.current) {
        return;
      }

      if (dashboardRes.ok) {
        const dashPayload = await dashboardRes.json();
        setHealth(dashPayload.health || null);
        setServers(Array.isArray(dashPayload.servers) ? dashPayload.servers : []);
        setAlertsSummary(dashPayload.alerts_summary || null);
      }

      if (integrityRes.ok) {
        const integrityPayload = await integrityRes.json();
        setIntegrity({
          reports: Array.isArray(integrityPayload.reports) ? integrityPayload.reports : [],
          summary: integrityPayload.summary || null,
        });
      }

      if (alertsRes.ok) {
        const alertsPayload = await alertsRes.json();
        setAlerts(Array.isArray(alertsPayload.alerts) ? alertsPayload.alerts : []);
        setAlertsSummary(alertsPayload.summary || null);
      }

      setError('');
    } catch (err) {
      if (isMounted.current) {
        setError('Failed to refresh monitoring data');
      }
    } finally {
      if (showSpinner && isMounted.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMounted.current = true;
    loadData({ showSpinner: true });
    const interval = setInterval(() => loadData({ showSpinner: false }), 15000);
    return () => {
      clearInterval(interval);
      isMounted.current = false;
    };
  }, [loadData]);

  const openServer = useCallback(async (server) => {
    if (!server) return;
    setSelected({ loading: true, server });
    try {
      const headers = authHeaders();
      const res = await fetch(`${API}/monitoring/servers/${encodeURIComponent(server.name)}/current-stats`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      let logs = '';
      const logsId = data?.id || server.id || data?.container_id || server.name;
      if (logsId) {
        try {
          const logsRes = await fetch(`${API}/servers/${encodeURIComponent(logsId)}/logs?tail=200`, { headers });
          if (logsRes.ok) {
            const logsJson = await logsRes.json();
            logs = typeof logsJson === 'string' ? logsJson : logsJson.logs || '';
          }
        } catch (logErr) {
          console.warn('Failed to fetch logs preview', logErr);
        }
      }

      if (!isMounted.current) return;
      setSelected({ loading: false, server, data, logs });
    } catch (err) {
      if (!isMounted.current) return;
      setSelected({ loading: false, server, error: err instanceof Error ? err.message : String(err) });
    }
  }, []);

  const restartServer = useCallback(async (server) => {
    if (!server || !server.id) {
      alert('Missing server id');
      return;
    }

    try {
      const headers = { 'Content-Type': 'application/json', ...authHeaders() };
      const response = await fetch(`${API}/servers/${encodeURIComponent(server.id)}/power`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ signal: 'restart' })
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      alert('Restart requested');
    } catch (err) {
      alert(`Restart failed: ${err instanceof Error ? err.message : err}`);
    }
  }, []);

  const totalServersDisplay = health?.total_servers ?? '—';
  const runningServersDisplay = health?.running_servers ?? '—';
  const cpuDisplay = typeof health?.cpu_usage_percent === 'number'
    ? `${health.cpu_usage_percent.toFixed(1)}%`
    : '—';

  return (
    <div className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {error && (
          <div className="rounded bg-red-500/10 border border-red-500/40 text-red-200 text-sm px-4 py-3">
            {error}
          </div>
        )}

        <div className="flex flex-col lg:flex-row items-start justify-between gap-6">
          <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-4 w-full">
            <SmallStat label="Total Servers" value={totalServersDisplay} loading={loading} />
            <SmallStat label="Running" value={runningServersDisplay} loading={loading} />
            <SmallStat label="Average CPU %" value={cpuDisplay} loading={loading} />
          </div>
          <div className="w-full lg:w-80">
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="text-sm text-white/70">Recent Alerts</div>
              <div className="mt-2 space-y-2">
                {alerts.length ? alerts.slice(0, 6).map((a) => (
                  <div key={a.id} className="p-2 rounded border border-white/10 bg-black/20">
                    <div className="flex items-start justify-between gap-3">
                      <div className="text-xs text-white/80">{a.message}</div>
                      <StatusBadge status={a.type} />
                    </div>
                    <div className="text-[11px] text-white/50 mt-1">{new Date(a.timestamp).toLocaleString()}</div>
                  </div>
                )) : (
                  <div className="text-xs text-white/50">No recent alerts</div>
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
                {servers.map((s) => (
                  <div key={s.id || s.name} className="p-3 bg-black/20 rounded border border-white/10 flex items-center justify-between">
                    <div>
                      <div className="font-semibold text-white">{s.name}</div>
                      <div className="text-xs text-white/60">Status: {s.status}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => openServer(s)} className="px-3 py-1 rounded bg-slate-600 hover:bg-slate-500 text-sm">Open</button>
                    </div>
                  </div>
                ))}
                {!servers.length && (
                  <div className="col-span-full text-xs text-white/50">No servers discovered.</div>
                )}
              </div>
            </div>

            <IntegrityPanel
              reports={integrity.reports}
              summary={integrity.summary}
              onRefresh={loadData}
              loading={loading}
            />
          </div>

          <div>
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <div className="text-sm text-white/70 mb-3">Server Details</div>
              {selected ? (
                selected.loading ? <div className="text-xs text-white/50">Loading…</div>
                : selected.error ? <div className="text-xs text-red-400">{selected.error}</div>
                : (
                  <div className="text-sm text-white/70 space-y-2">
                    <div>Name: {selected.server?.name || '—'}</div>
                    <div>Status: {selected.data?.status || '—'}</div>
                    <div>Type: {selected.data?.server_type || '—'}</div>
                    <div>Version: {selected.data?.server_version || '—'}</div>
                    <div>Java: {selected.data?.java_version || '—'}</div>
                    <div>CPU%: {selected.data?.cpu_percent ?? '—'}</div>
                    <div>Memory MB: {selected.data?.memory_usage_mb ?? '—'}</div>
                    <div>Players: {selected.data?.player_count ?? '—'}</div>
                    <div>Started: {selected.data?.started_at ? new Date(selected.data.started_at).toLocaleString() : '—'}</div>
                    <div>Uptime: {selected.data?.uptime_seconds ? `${Math.round(selected.data.uptime_seconds)}s` : '—'}</div>
                    <div>Last exit code: {selected.data?.last_exit_code ?? '—'}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button onClick={() => restartServer(selected.server)} className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-sm">Restart</button>
                      <button
                        onClick={() => {
                          if (!selected.logs) return;
                          const w = window.open('about:blank');
                          if (w) {
                            w.document.write(`<pre style="white-space:pre-wrap;font-family:monospace;padding:16px;">${selected.logs.replace(/</g, '&lt;')}</pre>`);
                          }
                        }}
                        className="px-3 py-1 rounded bg-slate-600 hover:bg-slate-500 text-sm"
                      >Logs Preview</button>
                    </div>
                    {selected.logs ? (
                      <details className="mt-2 text-xs text-white/60">
                        <summary>Recent logs</summary>
                        <pre className="text-xs max-h-48 overflow-auto p-2 bg-black/10 rounded mt-2">{selected.logs}</pre>
                      </details>
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
