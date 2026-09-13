import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Lock } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import { getLanPassword, setLanPassword } from '@/lib/lanAuth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

// Gates the whole app behind the Android host's LAN password with a real
// shadcn form instead of the browser's native Basic Auth dialog.
// backend/app/auth.py's dynamic-password branch deliberately answers a bad/
// missing password with a WWW-Authenticate scheme other than "Basic" - a
// browser auto-prompts its OWN dialog for literally any 401 that says
// "Basic", including ones from fetch()/XHR, which would hijack this screen
// the instant the app made its first request otherwise.
//
// Uses the exact same ['syncConfig'] query useCapabilities() reads - one
// shared request, not a second probe - so on desktop this either resolves
// immediately (no LAN password concept there) or the browser's own
// separately-configured optional auth (still literally "Basic") already
// settled itself before this component ever sees a response. Either way,
// this UI is never reachable on desktop in practice.
export function LanPasswordGate({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const probe = useQuery({ queryKey: ['syncConfig'], queryFn: api.syncConfig, retry: false });
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (probe.isSuccess) return <>{children}</>;
  if (probe.isPending) return null;

  const status = probe.error instanceof ApiError ? probe.error.status : undefined;
  // Some other failure (network down, server not started yet) - not a login
  // problem, let the rest of the app's own loading/error states handle it.
  if (status !== 401 && status !== 503) return <>{children}</>;

  async function submit() {
    setSubmitting(true);
    setLanPassword(password);
    await queryClient.invalidateQueries({ queryKey: ['syncConfig'] });
    setSubmitting(false);
  }

  const wrongPassword = status === 401 && !!getLanPassword();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-1 flex items-center gap-2">
            <Lock className="size-5 text-primary" />
            <CardTitle>Budget Dashboard</CardTitle>
          </div>
          <CardDescription>
            {status === 503
              ? 'No LAN password has been set yet - set one from the Budget Dashboard app on the phone first.'
              : 'Enter the LAN password set on the phone to view this dashboard.'}
          </CardDescription>
        </CardHeader>
        {status === 401 && (
          <CardContent>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="lan-password">Password</Label>
                <Input
                  id="lan-password"
                  type="password"
                  autoFocus
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && password) submit(); }}
                />
              </div>
              <Button disabled={!password || submitting} onClick={submit}>
                {submitting ? 'Checking…' : 'Unlock'}
              </Button>
              {wrongPassword && <p className="text-sm text-destructive">Incorrect password - try again.</p>}
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
