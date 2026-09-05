import { useMutation } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
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

// Mount with a key derived from the four dates so switching either period
// remounts this fresh instead of showing a stale comparison.
export function CompareRecapCard({ labelA, labelB, dateFromA, dateToA, dateFromB, dateToB }: CompareRecapCardProps) {
  const recap = useMutation({
    mutationFn: () => api.compareRecap({
      label_a: labelA, label_b: labelB,
      date_from_a: dateFromA, date_to_a: dateToA,
      date_from_b: dateFromB, date_to_b: dateToB,
    }),
  });
  const elapsed = useElapsedSeconds(recap.isPending);

  return (
    <Card className="mt-6">
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-primary" /> Compare Recap
        </CardTitle>
        <Button size="sm" variant="outline" disabled={recap.isPending} onClick={() => recap.mutate()}>
          {recap.isPending ? `Generating… ${elapsed}s` : recap.data ? 'Regenerate' : 'Generate'}
        </Button>
      </CardHeader>
      <CardContent>
        {recap.isPending && (
          <p className="text-sm text-muted-foreground">
            Thinking… {elapsed}s elapsed — this can take up to a minute while the local model loads.
          </p>
        )}
        {recap.isError && <p className="text-sm text-destructive">{(recap.error as Error).message}</p>}
        {!recap.isPending && !recap.isError && recap.data && (
          <p className="text-sm leading-relaxed">{recap.data.recap}</p>
        )}
        {!recap.isPending && !recap.isError && !recap.data && (
          <p className="text-sm text-muted-foreground">
            Get a plain-English comparison of {labelA} vs {labelB}, written by a local AI model.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
