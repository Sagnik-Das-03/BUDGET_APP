import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { useConfirmDialog } from '../lib/useConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

// Reachable at /admin regardless of which profile is active - the actual
// gate is the admin account's password (see backend _require_admin), which
// this page asks for once and reuses for every create/delete in the same
// visit, rather than re-prompting per action.
export function Admin() {
  const queryClient = useQueryClient();
  const { confirm, dialog } = useConfirmDialog();
  const stats = useQuery({ queryKey: ['userStats'], queryFn: () => api.getUserStats() });
  const [adminPassword, setAdminPassword] = useState('');

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [seedDemo, setSeedDemo] = useState(false);

  function invalidateUserQueries() {
    queryClient.invalidateQueries({ queryKey: ['userStats'] });
    queryClient.invalidateQueries({ queryKey: ['users'] });
  }

  const create = useMutation({
    mutationFn: () => api.createUser({
      username: newUsername.trim(), password: newPassword,
      seedDemoData: seedDemo, adminPassword: adminPassword || undefined,
    }),
    onSuccess: () => {
      invalidateUserQueries();
      setNewUsername('');
      setNewPassword('');
      setSeedDemo(false);
    },
  });

  const del = useMutation({
    mutationFn: (username: string) => api.deleteUser(username, adminPassword || undefined),
    onSuccess: invalidateUserQueries,
  });

  async function handleDelete(username: string) {
    const ok = await confirm(
      `Permanently delete "${username}" and all of its data? This can't be undone.`,
      { title: 'Delete user', confirmLabel: 'Delete' },
    );
    if (ok) del.mutate(username);
  }

  const users = stats.data?.users ?? [];

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Admin</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        Manage user profiles - each one is a fully separate database. Creating or deleting a
        user is gated by the admin account's own password (set it from Settings while signed
        in as admin); until one is set, these actions stay open.
      </p>

      <div className="mb-5 max-w-xs">
        <Input
          type="password"
          placeholder="Admin password (only if one is set)"
          value={adminPassword}
          onChange={(e) => setAdminPassword(e.target.value)}
        />
      </div>

      {stats.data && (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:max-w-md">
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Total users</div>
            <div className="mt-1 text-2xl font-bold">{stats.data.total_users}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Total disk usage</div>
            <div className="mt-1 text-2xl font-bold">{fmtBytes(stats.data.total_size_bytes)}</div>
          </Card>
        </div>
      )}

      <Card className="mb-6 p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Transactions</TableHead>
              <TableHead>Disk usage</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.username}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-1.5">
                    {u.username}
                    {u.is_active && <Badge variant="secondary">active</Badge>}
                  </div>
                </TableCell>
                <TableCell>{u.transaction_count}</TableCell>
                <TableCell>{fmtBytes(u.db_size_bytes)}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost" size="icon" className="text-muted-foreground hover:text-destructive"
                    disabled={u.is_active || users.length <= 1 || del.isPending}
                    title={u.is_active ? "Can't delete the currently active user" : 'Delete user'}
                    onClick={() => handleDelete(u.username)}
                    aria-label={`Delete ${u.username}`}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {del.isError && <p className="mb-4 text-sm text-destructive">{(del.error as Error).message}</p>}

      <Card className="max-w-sm p-4">
        <h2 className="mb-3 text-sm font-semibold">Create a new user</h2>
        <div className="flex flex-col gap-2.5">
          <Input placeholder="Username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
          <Input
            type="password" placeholder="Password (min 4 characters)"
            value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
          />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Checkbox checked={seedDemo} onCheckedChange={(c) => setSeedDemo(c === true)} />
            Fill with demo data (so dashboard charts have something to show)
          </label>
          <Button
            disabled={!newUsername.trim() || newPassword.length < 4 || create.isPending}
            onClick={() => create.mutate()}
          >
            Create user
          </Button>
          {create.isError && <p className="text-xs text-destructive">{(create.error as Error).message}</p>}
        </div>
      </Card>

      {dialog}
    </>
  );
}
