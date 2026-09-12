import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { Plus, Send, X } from 'lucide-react';
import { api } from '../lib/api';
import type { ChatMessage } from '../lib/types';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { ModelBadge } from '../components/ModelBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Exchange {
  question: string;
  answer: string;
  durationSec?: number;
}

const EXAMPLES = [
  'how much did I spend on food last month?',
  'how many transactions this year?',
  'what is my average shopping expense?',
];

function toExchange(m: ChatMessage): Exchange {
  return { question: m.question, answer: m.answer, durationSec: m.duration_sec ?? undefined };
}

export function Ask() {
  const queryClient = useQueryClient();
  const threads = useQuery({ queryKey: ['chatThreads'], queryFn: () => api.chatThreads() });

  // null = an unsaved "new chat" draft - no thread exists in the DB until the
  // first question is actually sent, so clicking "+" repeatedly doesn't litter
  // empty threads.
  const [activeId, setActiveId] = useState<number | null>(null);
  const [draftHistory, setDraftHistory] = useState<Exchange[]>([]);
  const [question, setQuestion] = useState('');

  const messages = useQuery({
    queryKey: ['chatMessages', activeId],
    queryFn: () => api.chatMessages(activeId as number),
    enabled: activeId !== null,
  });

  const history: Exchange[] = activeId === null ? draftHistory : (messages.data ?? []).map(toExchange);

  const startRef = useRef(0);
  const ask = useMutation({
    mutationFn: (q: string) => api.ask(q, activeId),
    onSuccess: (res, q) => {
      const exchange: Exchange = {
        question: q, answer: res.answer,
        durationSec: res.duration_sec ?? (Date.now() - startRef.current) / 1000,
      };
      if (activeId === null && res.thread_id) {
        queryClient.setQueryData(['chatMessages', res.thread_id], [
          { id: 0, question: q, answer: res.answer, duration_sec: exchange.durationSec ?? null, created_at: new Date().toISOString() },
        ]);
        setActiveId(res.thread_id);
        setDraftHistory([]);
      } else if (activeId !== null) {
        queryClient.setQueryData(['chatMessages', activeId], (old: ChatMessage[] | undefined) => [
          ...(old ?? []),
          { id: Date.now(), question: q, answer: res.answer, duration_sec: exchange.durationSec ?? null, created_at: new Date().toISOString() },
        ]);
      }
      queryClient.invalidateQueries({ queryKey: ['chatThreads'] });
    },
    onError: (err: Error, q) => {
      const exchange: Exchange = { question: q, answer: `Error: ${err.message}` };
      if (activeId === null) setDraftHistory((h) => [...h, exchange]);
      else queryClient.setQueryData(['chatMessages', activeId], (old: ChatMessage[] | undefined) => [
        ...(old ?? []), { id: Date.now(), question: q, answer: exchange.answer, duration_sec: null, created_at: new Date().toISOString() },
      ]);
    },
  });
  const elapsed = useElapsedSeconds(ask.isPending);

  const deleteThread = useMutation({
    mutationFn: (id: number) => api.deleteChatThread(id),
    onSuccess: (_res, id) => {
      queryClient.invalidateQueries({ queryKey: ['chatThreads'] });
      queryClient.removeQueries({ queryKey: ['chatMessages', id] });
      if (activeId === id) startNewChat();
    },
  });

  function startNewChat() {
    setActiveId(null);
    setDraftHistory([]);
    setQuestion('');
  }

  function submit(q: string) {
    const trimmed = q.trim();
    if (!trimmed || ask.isPending) return;
    startRef.current = Date.now();
    ask.mutate(trimmed);
    setQuestion('');
  }

  // If the active thread got deleted from another tab/session, fall back to a fresh draft.
  useEffect(() => {
    if (activeId !== null && threads.data && !threads.data.some((t) => t.id === activeId)) {
      startNewChat();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threads.data, activeId]);

  return (
    <>
      <div className="flex items-center gap-2.5">
        <h1 className="text-2xl font-bold tracking-tight">Ask Your Budget</h1>
        <ModelBadge task="query_parse" />
      </div>
      <p className="mb-4 mt-1 text-sm text-muted-foreground">
        Ask about your spending in plain English. A local AI model turns your question into a
        query over your own transactions, then another pass phrases the final answer — neither
        one does the arithmetic itself, that's computed straight from your data every time.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-1.5 border-b pb-2">
        {(threads.data ?? []).map((t) => (
          <div
            key={t.id}
            className={`group flex max-w-[220px] items-center gap-1.5 rounded-t-md border border-b-0 px-3 py-1.5 text-xs cursor-pointer ${
              t.id === activeId ? 'bg-background font-medium' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
            onClick={() => setActiveId(t.id)}
          >
            <span className="truncate">{t.title}</span>
            <button
              type="button"
              aria-label="Delete chat"
              className="rounded-sm opacity-0 group-hover:opacity-100 hover:bg-destructive/20"
              onClick={(e) => { e.stopPropagation(); deleteThread.mutate(t.id); }}
            >
              <X className="size-3" />
            </button>
          </div>
        ))}
        <button
          type="button"
          className={`flex items-center gap-1 rounded-t-md border border-b-0 px-2.5 py-1.5 text-xs ${
            activeId === null ? 'bg-background font-medium' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
          }`}
          onClick={startNewChat}
        >
          <Plus className="size-3.5" /> New
        </button>
      </div>

      {history.length === 0 && !ask.isPending && (
        <div className="mb-4 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
              onClick={() => submit(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3">
        {history.map((h, i) => (
          <div key={i} className="flex flex-col gap-1.5">
            <div className="self-end max-w-[80%] rounded-lg bg-primary px-3.5 py-2 text-sm text-primary-foreground">
              {h.question}
            </div>
            <div className="self-start max-w-[80%] rounded-lg bg-muted px-3.5 py-2 text-sm">
              {h.answer}
              {h.durationSec !== undefined && (
                <div className="mt-1 text-xs text-muted-foreground">Answered in {h.durationSec.toFixed(1)}s</div>
              )}
            </div>
          </div>
        ))}
        {ask.isPending && (
          <div className="self-start rounded-lg bg-muted px-3.5 py-2 text-sm text-muted-foreground">
            Thinking… {elapsed}s elapsed — this can take up to a minute the first time, while the local model loads.
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <Input
          placeholder="e.g. how much did I spend on food last month?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(question); }}
        />
        <Button onClick={() => submit(question)} disabled={ask.isPending || !question.trim()}>
          <Send className="size-4" /> Ask
        </Button>
      </div>
    </>
  );
}
