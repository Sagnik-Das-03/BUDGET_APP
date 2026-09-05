import { useMutation } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api, type DateBounds } from '../lib/api';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface RecapCardProps {
  range: string;
  dateBounds?: DateBounds;
  label: string;
}

// Mount with `key={label}` (or similar) from the parent so switching ranges
// remounts this component fresh instead of showing a stale recap for the
// period you just navigated away from.
export function RecapCard({ range, dateBounds, label }: RecapCardProps) {
  const recap = useMutation({ mutationFn: () => api.recap(range, dateBounds, label) });
  const elapsed = useElapsedSeconds(recap.isPending);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-primary" /> Recap — {label}
        </CardTitle>
        <Button size="sm" variant="outline" disabled={recap.isPending} onClick={() => recap.mutate()}>
          {recap.isPending ? `Generating… ${elapsed}s` : recap.data ? 'Regenerate' : 'Generate'}
        </Button>
      </CardHeader>
      <CardContent>
        {recap.isPending && (
          <p className="text-sm text-muted-foreground">
            Thinking… {elapsed}s elapsed — the first recap can take up to a minute while the local model loads.
          </p>
        )}
        {recap.isError && (
          <p className="text-sm text-destructive">{(recap.error as Error).message}</p>
        )}
        {!recap.isPending && !recap.isError && recap.data && (
          <p className="text-sm leading-relaxed">{recap.data.recap}</p>
        )}
        {!recap.isPending && !recap.isError && !recap.data && (
          <p className="text-sm text-muted-foreground">
            Get a plain-English summary of {label.toLowerCase()}'s spending, written by a local AI model.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
