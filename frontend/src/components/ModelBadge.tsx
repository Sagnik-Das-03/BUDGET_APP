import { useQuery } from '@tanstack/react-query';
import { Cpu } from 'lucide-react';
import { api } from '../lib/api';

// Shows which local model actually answers a given AI task - e.g. "Qwen3 4B
// (int4)" next to the Recap button. Renders nothing until /api/llm/status
// resolves, and nothing at all for a task with no configured model.
export function ModelBadge({ task }: { task: string }) {
  const status = useQuery({ queryKey: ['llmStatus'], queryFn: api.llmStatus, staleTime: 5 * 60 * 1000 });
  const model = status.data?.models[task];
  if (!model) return null;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title={`Powered by ${model}, running locally`}>
      <Cpu className="size-3" /> {model}
    </span>
  );
}
