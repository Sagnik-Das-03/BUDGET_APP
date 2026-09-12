import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Plus, User as UserIcon } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

// Switching users means switching to a completely different SQLite file on
// the backend - every piece of client state (React Query cache, and every
// component's own local state) is scoped to whichever user was active when
// it was created, so a full reload is the only way to guarantee none of the
// previous user's data lingers on screen after the switch.
export function UserSwitcher() {
  const queryClient = useQueryClient();
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.listUsers() });
  const [creating, setCreating] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [seedDemo, setSeedDemo] = useState(false);

  const activate = useMutation({
    mutationFn: (username: string) => api.activateUser(username),
    onSuccess: () => window.location.reload(),
  });

  const create = useMutation({
    mutationFn: () => api.createUser(newUsername.trim(), seedDemo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setCreating(false);
      setNewUsername('');
      setSeedDemo(false);
    },
  });

  const active = users.data?.find((u) => u.is_active)?.username ?? '';

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <UserIcon className="size-3.5 shrink-0 text-muted-foreground" />
        <Select
          value={active}
          onValueChange={(v) => { if (v !== active) activate.mutate(v); }}
          disabled={activate.isPending}
        >
          <SelectTrigger size="sm" className="h-7 flex-1 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {(users.data ?? []).map((u) => <SelectItem key={u.username} value={u.username}>{u.username}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="icon" className="size-7 shrink-0" aria-label="New user" onClick={() => setCreating((c) => !c)}>
          <Plus className="size-3.5" />
        </Button>
      </div>

      {creating && (
        <div className="flex flex-col gap-1.5 rounded-md border p-2">
          <Input
            className="h-7 text-xs"
            placeholder="Username"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && newUsername.trim()) create.mutate(); }}
          />
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Checkbox checked={seedDemo} onCheckedChange={(c) => setSeedDemo(c === true)} className="size-3.5" />
            Fill with demo data
          </label>
          <Button size="sm" className="h-7 text-xs" disabled={!newUsername.trim() || create.isPending} onClick={() => create.mutate()}>
            Create user
          </Button>
          {create.isError && <p className="text-xs text-destructive">{(create.error as Error).message}</p>}
        </div>
      )}
    </div>
  );
}
