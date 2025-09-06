import React, { useState } from 'react';
import { useFetch } from '../../lib/useFetch';
import { API } from '../../lib/api';

export default function SchedulePanel() {
  const { data, loading, error, setData } = useFetch(`${API}/schedule/tasks`, []);
  const [name, setName] = useState('');
  const [taskType, setTaskType] = useState('backup');
  const [serverName, setServerName] = useState('');
  const [cron, setCron] = useState('0 2 * * *');
  const [command, setCommand] = useState('');

  async function createTask() {
    const body = { name, task_type: taskType, server_name: serverName || null, cron_expression: cron, command: command || null };
    const r = await fetch(`${API}/schedule/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (r.ok) { const task = await r.json(); setData([...(data || []), task]); setName(''); setServerName(''); setCommand(''); }
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
        <select className="rounded bg-gray-800 border border-white/20 px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-brand-500" value={taskType} onChange={e => setTaskType(e.target.value)} style={{ backgroundColor: '#1f2937', color: '#ffffff' }}>
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
