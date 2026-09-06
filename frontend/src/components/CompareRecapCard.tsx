import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { useLastDuration } from '../lib/useLastDuration';
import { ModelBadge } from './ModelBadge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface CompareRecapCardProps {
  labelA: string;
  labelB: string;
  dateFromA: string;
  dateToA: string;
  dateFromB: string;
  dateToB: string;
}

// See RecapCard.tsx for why this is a manually-triggered useQuery rather
// than useMutation - it keeps the generation alive in the shared QueryClient
// cache (keyed on the specific period pair) across navigating away and back,
// instead of losing it when this component unmounts.
export function CompareRecapCard({ labelA, labelB, dateFromA, dateToA, dateFromB, dateToB }: CompareRecapCardProps) {
  const recap = useQuery({
    queryKey: ['compareRecap', dateFromA, dateToA, dateFromB, dateToB],
    queryFn: () => api.compareRecap({
      label_a: labelA, label_b: labelB,
      date_from_a: dateFromA, date_to_a: dateToA,
      date_from_b: dateFromB, date_to_b: dateToB,
    }),
    enabled: false,
    retry: false,
    gcTime: 30 * 60 * 1000,
  });
  const elapsed = useElapsedSeconds(recap.isFetching);
  const duration = useLastDuration(recap.isFetching);

  return (
    <Card className="mt-6">
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div className="flex items-center gap-2.5">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" /> Compare Recap
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
            Thinking… {elapsed}s elapsed — this can take up to a minute while the local model loads.
          </p>
        )}
        {recap.isError && !recap.isFetching && <p className="text-sm text-destructive">{(recap.error as Error).message}</p>}
        {!recap.isFetching && !recap.isError && recap.data && (
          <>
            <p className="text-sm leading-relaxed">{recap.data.recap}</p>
            {duration !== null && (
              <p className="mt-2 text-xs text-muted-foreground">Generated in {duration.toFixed(1)}s</p>
            )}
          </>
        )}
        {!recap.isFetching && !recap.isError && !recap.data && (
          <p className="text-sm text-muted-foreground">
            Get a plain-English comparison of {labelA} vs {labelB}, written by a local AI model.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
