import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api, type DateBounds } from '../lib/api';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { ModelBadge } from './ModelBadge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface RecapCardProps {
  range: string;
  dateBounds?: DateBounds;
  label: string;
}

// A manually-triggered useQuery (not useMutation), keyed on the period.
// useMutation state lives on this component instance - navigating to another
// page unmounts it and the in-flight/completed generation is lost even
// though the request itself keeps running server-side. Keying a useQuery on
// the period instead stores it in the shared QueryClient cache, so leaving
// this page and coming back (or just switching range tabs and back) picks
// the same generation back up instead of losing it.
export function RecapCard({ range, dateBounds, label }: RecapCardProps) {
  const recap = useQuery({
    queryKey: ['recap', range, dateBounds?.date_from, dateBounds?.date_to],
    queryFn: () => api.recap(range, dateBounds, label),
    enabled: false,
    retry: false,
    gcTime: 30 * 60 * 1000, // these are expensive to generate - keep them around a while
  });
  const elapsed = useElapsedSeconds(recap.isFetching);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div className="flex items-center gap-2.5">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" /> Recap — {label}
          </CardTitle>
          <ModelBadge task="summarize" />
        </div>
        <Button size="sm" variant="outline" disabled={recap.isFetching} onClick={() => recap.refetch()}>
          {recap.isFetching ? `Generating… ${elapsed}s` : recap.data ? 'Regenerate' : 'Generate'}
        </Button>
      </CardHeader>
      <CardContent>
        {recap.isFetching && (
          <p className="text-sm text-muted-foreground">
            Thinking… {elapsed}s elapsed — the first recap can take up to a minute while the local model loads.
          </p>
        )}
        {recap.isError && !recap.isFetching && (
          <p className="text-sm text-destructive">{(recap.error as Error).message}</p>
        )}
        {!recap.isFetching && !recap.isError && recap.data && (
          <p className="text-sm leading-relaxed">{recap.data.recap}</p>
        )}
        {!recap.isFetching && !recap.isError && !recap.data && (
          <p className="text-sm text-muted-foreground">
            Get a plain-English summary of {label.toLowerCase()}'s spending, written by a local AI model.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
