import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Trash2 } from 'lucide-react';
import { api } from '../lib/api';
import { useConfirmDialog } from '../lib/useConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
// visit, rather than re-prompting per action. admin has no Settings link of
// its own (it's not a financial profile), so its own password control lives
// here instead.
export function Admin() {
  const queryClient = useQueryClient();
  const { confirm, dialog } = useConfirmDialog();
  const stats = useQuery({ queryKey: ['userStats'], queryFn: () => api.getUserStats() });
  const [adminPassword, setAdminPassword] = useState('');

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [seedDemo, setSeedDemo] = useState(false);

  const [currentAdminPw, setCurrentAdminPw] = useState('');
  const [nextAdminPw, setNextAdminPw] = useState('');

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

  const admin = stats.data?.users.find((u) => u.username.toLowerCase() === 'admin');
  const changeAdminPw = useMutation({
    mutationFn: () => api.setUserPassword(admin!.username, nextAdminPw, currentAdminPw || undefined),
    onSuccess: () => {
      invalidateUserQueries();
      // The freshly-set password immediately becomes correct for the
      // "authorize" field below too, so changing/setting it here doesn't
      // force retyping it a second time to create or delete a user next.
      setAdminPassword(nextAdminPw);
      setCurrentAdminPw('');
      setNextAdminPw('');
    },
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
        Manage user profiles - each one is a fully separate database, with its own (optional)
        Google Sheet.
      </p>

      <Card className="mb-6 max-w-xs p-4">
        <Label htmlFor="admin-authorize-pw" className="text-sm font-semibold">Authorize</Label>
        <p className="mb-3 mt-1 text-xs text-muted-foreground">
          Required below to create or delete a user, if a password is set (see "Admin password").
        </p>
        <Input
          id="admin-authorize-pw"
          type="password"
          placeholder="Admin password"
          value={adminPassword}
          onChange={(e) => setAdminPassword(e.target.value)}
        />
      </Card>

      {stats.data && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:max-w-2xl">
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Total users</div>
            <div className="mt-1 text-2xl font-bold">{stats.data.total_users}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Total disk usage</div>
            <div className="mt-1 text-2xl font-bold">{fmtBytes(stats.data.total_size_bytes)}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Total transactions</div>
            <div className="mt-1 text-2xl font-bold">{stats.data.total_transactions}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium uppercase text-muted-foreground">Password-protected</div>
            <div className="mt-1 text-2xl font-bold">{stats.data.users_with_password}/{stats.data.total_users}</div>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_320px]">
        <div>
          <Card className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Transactions</TableHead>
                  <TableHead>Disk usage</TableHead>
                  <TableHead>Password</TableHead>
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
                    <TableCell className="text-muted-foreground">{u.has_password ? 'Set' : '—'}</TableCell>
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
          {del.isError && <p className="mt-3 text-sm text-destructive">{(del.error as Error).message}</p>}
        </div>

        <div className="flex flex-col gap-5">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold">Create a new user</h2>
            <div className="flex flex-col gap-2.5">
              <Input placeholder="Username" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} />
              <Input
                type="password" placeholder="Password (min 4 characters)"
                value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
              />
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Checkbox checked={seedDemo} onCheckedChange={(c) => setSeedDemo(c === true)} />
                Fill with demo data
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

          <Card className="p-4">
            <h2 className="mb-1 text-sm font-semibold">Admin password</h2>
            <p className="mb-3 text-xs text-muted-foreground">
              {admin?.has_password
                ? 'Change the password that gates creating/deleting users.'
                : "Not set yet - anyone can create or delete users. Set one to lock this down."}
            </p>
            <div className="flex flex-col gap-2.5">
              {admin?.has_password && (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="admin-current-pw">Current password</Label>
                  <Input
                    id="admin-current-pw" type="password"
                    value={currentAdminPw} onChange={(e) => setCurrentAdminPw(e.target.value)}
                  />
                </div>
              )}
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="admin-next-pw">New password</Label>
                <Input
                  id="admin-next-pw" type="password"
                  value={nextAdminPw} onChange={(e) => setNextAdminPw(e.target.value)}
                />
              </div>
              <Button
                disabled={!admin || nextAdminPw.length < 4 || changeAdminPw.isPending}
                onClick={() => changeAdminPw.mutate()}
              >
                {admin?.has_password ? 'Change password' : 'Set password'}
              </Button>
              {changeAdminPw.isSuccess && <p className="text-xs text-green-600">Saved.</p>}
              {changeAdminPw.isError && <p className="text-xs text-destructive">{(changeAdminPw.error as Error).message}</p>}
            </div>
          </Card>
        </div>
      </div>

      {dialog}
    </>
  );
}
