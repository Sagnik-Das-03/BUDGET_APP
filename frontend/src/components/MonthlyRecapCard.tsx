import { useMutation } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function MonthlyRecapCard() {
  const recap = useMutation({ mutationFn: () => api.monthlyRecap() });

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-primary" /> Monthly Recap
        </CardTitle>
        <Button size="sm" variant="outline" disabled={recap.isPending} onClick={() => recap.mutate()}>
          {recap.isPending ? 'Generating…' : recap.data ? 'Regenerate' : 'Generate'}
        </Button>
      </CardHeader>
      <CardContent>
        {recap.isPending && (
          <p className="text-sm text-muted-foreground">
            Thinking… the first recap can take up to a minute while the local model loads.
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
            Get a plain-English summary of this month's spending, written by a local AI model.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
