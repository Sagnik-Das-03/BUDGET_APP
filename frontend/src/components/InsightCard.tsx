import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api, type DateBounds } from '../lib/api';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { useLastDuration } from '../lib/useLastDuration';
import { ModelBadge } from './ModelBadge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface InsightCardProps {
  range: string;
  dateBounds?: DateBounds;
  label: string;
}

// Replaces what used to be two separate features - a short Recap card and a
// one-line Anomaly summary banner - with a single longer, more detailed
// explanation that covers both the overall picture and any unusual
// transactions in one narrative. Kept as a manually-triggered useQuery (not
// useMutation): a useMutation's state lives on this component instance and
// is lost on navigating away, while keying a useQuery on the period stores
// it in the shared QueryClient cache so leaving this page and coming back
// picks the same generation back up instead of losing it.
export function InsightCard({ range, dateBounds, label }: InsightCardProps) {
  const insight = useQuery({
    queryKey: ['insight', range, dateBounds?.date_from, dateBounds?.date_to],
    queryFn: () => api.insight(range, dateBounds, label),
    enabled: false,
    retry: false,
    gcTime: 30 * 60 * 1000, // these are expensive to generate - keep them around a while
  });
  const elapsed = useElapsedSeconds(insight.isFetching);
  const duration = useLastDuration(insight.isFetching);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div className="flex items-center gap-2.5">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-primary" /> Explain — {label}
          </CardTitle>
          <ModelBadge task="summarize" />
        </div>
        <Button size="sm" variant="outline" disabled={insight.isFetching} onClick={() => insight.refetch()}>
          {insight.isFetching ? `Generating… ${elapsed}s` : insight.data ? 'Regenerate' : 'Generate'}
        </Button>
      </CardHeader>
      <CardContent>
        {insight.isFetching && (
          <p className="text-sm text-muted-foreground">
            Thinking… {elapsed}s elapsed — a detailed explanation can take up to a minute or more on the local model.
          </p>
        )}
        {insight.isError && !insight.isFetching && (
          <p className="text-sm text-destructive">{(insight.error as Error).message}</p>
        )}
        {!insight.isFetching && !insight.isError && insight.data && (
          <>
            <p className="whitespace-pre-line text-sm leading-relaxed">{insight.data.insight}</p>
            {duration !== null && (
              <p className="mt-2 text-xs text-muted-foreground">Generated in {duration.toFixed(1)}s</p>
            )}
          </>
        )}
        {!insight.isFetching && !insight.isError && !insight.data && (
          <p className="text-sm text-muted-foreground">
            Get a detailed, AI-written explanation of {label.toLowerCase()}'s finances — including a
            call-out of anything unusual, like a likely miscategorized transaction.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
