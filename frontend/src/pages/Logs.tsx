import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

const LEVEL_COLORS: Record<string, string> = { info: '#898781', warn: '#fab219', error: '#e34948' };

export function Logs() {
  const logs = useQuery({ queryKey: ['syncLogs'], queryFn: api.syncLogs, refetchInterval: 15000 });

  return (
    <>
      <h1>Sync Logs</h1>
      <p className="subtitle">Recent sync activity, most recent first.</p>
      <table>
        <thead><tr><th>Time</th><th>Level</th><th>Message</th></tr></thead>
        <tbody>
          {!logs.data?.length ? (
            <tr><td colSpan={3}><div className="empty-state">No sync activity yet.</div></td></tr>
          ) : logs.data.map((r, i) => (
            <tr key={i}>
              <td>{new Date(r.timestamp).toLocaleString()}</td>
              <td><span className="pill" style={{ background: LEVEL_COLORS[r.level] || '#898781' }}>{r.level}</span></td>
              <td>{r.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
