import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Loader2, Plus, Send, ThumbsDown, ThumbsUp, X } from 'lucide-react';
import { api } from '../lib/api';
import type { AskRow, ChatMessage } from '../lib/types';
import { fmtMoney } from '../lib/format';
import { useElapsedSeconds } from '../lib/useElapsedSeconds';
import { useResizableWidth } from '../lib/useResizableWidth';
import { ModelBadge } from './ModelBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetTrigger } from '@/components/ui/sheet';
import { ResizeHandle } from '@/components/ui/resize-handle';

const ROW_PAGE_SIZE_OPTIONS = [10, 25, 50];

// The backend always sends every matching transaction, not a capped preview -
// this is the answer's actual evidence, so pagination here is purely a
// display convenience over the full set, never a truncation of it.
function AskRowsPanel({ rows }: { rows: AskRow[] }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paged = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <details className="mt-2" onToggle={() => setPage(1)}>
      <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
        {rows.length} matching transaction{rows.length !== 1 ? 's' : ''} found (evidence)
      </summary>
      <div className="mt-1.5 rounded-md border bg-background p-2">
        <div className="flex flex-col gap-1">
          {paged.map((r, ri) => (
            <div key={ri} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-muted-foreground">{r.date}</span>
              <span className="flex-1 truncate">{r.description}</span>
              <span className="text-muted-foreground">{r.category}</span>
              <span className="tabular-nums">{fmtMoney(r.amount)}</span>
            </div>
          ))}
        </div>
        {rows.length > ROW_PAGE_SIZE_OPTIONS[0] && (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t pt-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-1.5">
              <span>
                {(currentPage - 1) * pageSize + 1}–{Math.min(currentPage * pageSize, rows.length)} of {rows.length}
              </span>
              <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
                <SelectTrigger size="sm" className="h-6 w-[84px] text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROW_PAGE_SIZE_OPTIONS.map((n) => <SelectItem key={n} value={String(n)}>{n} / page</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-6 px-1.5" disabled={currentPage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <ChevronLeft className="size-3" />
              </Button>
              <span>Page {currentPage} of {totalPages}</span>
              <Button variant="outline" size="sm" className="h-6 px-1.5" disabled={currentPage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                <ChevronRight className="size-3" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </details>
  );
}

interface Exchange {
  id: number;
  question: string;
  answer: string;
  durationSec?: number;
  rows?: AskRow[];
  feedback?: 'up' | 'down' | null;
  confidence?: 'high' | 'medium' | 'low';
  confidenceReasons?: string[];
}

const EXAMPLES = [
  'how much did I spend on food last month?',
  'how many transactions this year?',
  'what is my average shopping expense?',
];

const CONFIDENCE_STYLE: Record<'high' | 'medium' | 'low', string> = {
  high: 'text-muted-foreground',
  medium: 'text-amber-600 dark:text-amber-500',
  low: 'text-destructive',
};

type StoredMessage = ChatMessage & { rows?: AskRow[]; confidence?: 'high' | 'medium' | 'low'; confidence_reasons?: string[] };

function toExchange(m: StoredMessage): Exchange {
  return {
    id: m.id, question: m.question, answer: m.answer,
    durationSec: m.duration_sec ?? undefined, rows: m.rows, feedback: m.feedback,
    confidence: m.confidence, confidenceReasons: m.confidence_reasons,
  };
}

// All of this component's state (mutations included) lives here, in the
// component that renders unconditionally from NavBar - not inside a child
// mounted only while the Sheet is open. Radix's Dialog.Content (which Sheet
// is built on) fully unmounts its children when closed, so any state that
// needs to survive closing/reopening the drawer, or navigating between the
// left-nav tabs while a question is in flight, has to live up here rather
// than in something that gets torn down with the drawer's visible content.
export function AskDrawer({ trigger }: { trigger: React.ReactNode }) {
  const queryClient = useQueryClient();
  const threads = useQuery({ queryKey: ['chatThreads'], queryFn: () => api.chatThreads() });

  // query_parse and summarize (the two tasks Ask uses) share the same
  // underlying model, so loading either one loads what Ask needs. Triggered
  // as soon as this app loads - rather than waiting for the first question -
  // so the "please wait" state is up front and explicit instead of the first
  // real answer silently taking up to a minute.
  const modelStatus = useQuery({ queryKey: ['llmModelStatus', 'query_parse'], queryFn: () => api.llmModelStatus('query_parse') });
  const warmup = useMutation({
    mutationFn: () => api.warmupModel('query_parse'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['llmModelStatus', 'query_parse'] }),
  });
  const warmupTriggered = useRef(false);
  useEffect(() => {
    if (modelStatus.data?.available && !modelStatus.data.loaded && !warmupTriggered.current) {
      warmupTriggered.current = true;
      warmup.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelStatus.data]);
  const modelLoading = warmup.isPending || (!!modelStatus.data?.available && !modelStatus.data.loaded && !warmup.isError);
  const modelLoadElapsed = useElapsedSeconds(warmup.isPending);

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
      const durationSec = res.duration_sec ?? (Date.now() - startRef.current) / 1000;
      const newMessage: StoredMessage = {
        id: res.message_id ?? Date.now(), question: q, answer: res.answer,
        duration_sec: durationSec, feedback: null, created_at: new Date().toISOString(),
        rows: res.rows, confidence: res.confidence, confidence_reasons: res.confidence_reasons,
      };
      if (activeId === null && res.thread_id) {
        queryClient.setQueryData(['chatMessages', res.thread_id], [newMessage]);
        setActiveId(res.thread_id);
        setDraftHistory([]);
      } else if (activeId !== null) {
        queryClient.setQueryData(['chatMessages', activeId], (old: ChatMessage[] | undefined) => [
          ...(old ?? []), newMessage,
        ]);
      }
      queryClient.invalidateQueries({ queryKey: ['chatThreads'] });
    },
    onError: (err: Error, q) => {
      const exchange: Exchange = { id: Date.now(), question: q, answer: `Error: ${err.message}` };
      if (activeId === null) setDraftHistory((h) => [...h, exchange]);
      else queryClient.setQueryData(['chatMessages', activeId], (old: ChatMessage[] | undefined) => [
        ...(old ?? []), { id: exchange.id, question: q, answer: exchange.answer, duration_sec: null, feedback: null, created_at: new Date().toISOString() },
      ]);
    },
  });

  const feedback = useMutation({
    mutationFn: ({ messageId, helpful, note }: { messageId: number; helpful: boolean; note?: string }) =>
      api.sendChatFeedback(messageId, helpful, note),
    onSuccess: (_res, { messageId, helpful }) => {
      const patch = (list: ChatMessage[] | undefined) =>
        (list ?? []).map((m) => (m.id === messageId ? { ...m, feedback: helpful ? 'up' as const : 'down' as const } : m));
      if (activeId === null) {
        setDraftHistory((h) => h.map((e) => (e.id === messageId ? { ...e, feedback: helpful ? 'up' : 'down' } : e)));
      } else {
        queryClient.setQueryData(['chatMessages', activeId], patch);
      }
    },
  });
  const [correctingId, setCorrectingId] = useState<number | null>(null);
  const [correctionNote, setCorrectionNote] = useState('');
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
    if (!trimmed || ask.isPending || modelLoading) return;
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

  const { width, onDragStart } = useResizableWidth('budget_tracker.askDrawerWidth', 576);

  return (
    <Sheet>
      <SheetTrigger asChild>{trigger}</SheetTrigger>
      <SheetContent side="right" className="flex flex-col" style={{ width, maxWidth: '95vw' }}>
        <ResizeHandle onMouseDown={onDragStart} />
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            Ask Your Budget
            <ModelBadge task="query_parse" />
          </SheetTitle>
          <SheetDescription>
            Ask about your spending in plain English - a local AI model turns your question into a
            query, then Python computes the exact answer from your data every time.
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-wrap items-center gap-1.5 border-b px-4 pb-2">
          {(threads.data ?? []).map((t) => (
            <div
              key={t.id}
              className={`group flex max-w-[160px] items-center gap-1.5 rounded-t-md border border-b-0 px-2.5 py-1 text-xs cursor-pointer ${
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
            className={`flex items-center gap-1 rounded-t-md border border-b-0 px-2 py-1 text-xs ${
              activeId === null ? 'bg-background font-medium' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
            }`}
            onClick={startNewChat}
          >
            <Plus className="size-3.5" /> New
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4">
          {modelLoading && (
            <div className="mb-4 flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2.5 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Please wait, loading the local AI model{modelLoadElapsed ? ` (${modelLoadElapsed}s)` : ''} — this only
              happens once per server restart, then answers come back fast.
            </div>
          )}
          {warmup.isError && (
            <div className="mb-4 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
              Couldn't load the AI model: {(warmup.error as Error).message}
            </div>
          )}

          {history.length === 0 && !ask.isPending && !modelLoading && (
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

          <div className="flex flex-col gap-3 pb-2">
            {history.map((h, i) => (
              <div key={i} className="flex flex-col gap-1.5">
                <div className="self-end max-w-[85%] rounded-lg bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                  {h.question}
                </div>
                <div className="self-start max-w-[90%] rounded-lg bg-muted px-3.5 py-2 text-sm">
                  {h.answer}
                  {(h.durationSec !== undefined || h.confidence) && (
                    <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      {h.durationSec !== undefined && <span>Answered in {h.durationSec.toFixed(1)}s</span>}
                      {h.durationSec !== undefined && h.confidence && <span>·</span>}
                      {h.confidence && (
                        <span
                          className={`capitalize ${CONFIDENCE_STYLE[h.confidence]}`}
                          title={h.confidenceReasons?.length ? h.confidenceReasons.join('; ') : 'No issues detected with this answer'}
                        >
                          {h.confidence} confidence
                        </span>
                      )}
                    </div>
                  )}

                  {!!h.rows?.length && <AskRowsPanel rows={h.rows} />}

                  <div className="mt-1.5 flex items-center gap-1">
                    <button
                      type="button"
                      aria-label="Helpful"
                      className={`rounded p-1 hover:bg-accent ${h.feedback === 'up' ? 'text-primary' : 'text-muted-foreground'}`}
                      disabled={feedback.isPending}
                      onClick={() => feedback.mutate({ messageId: h.id, helpful: true })}
                    >
                      <ThumbsUp className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label="Not helpful"
                      className={`rounded p-1 hover:bg-accent ${h.feedback === 'down' ? 'text-destructive' : 'text-muted-foreground'}`}
                      disabled={feedback.isPending}
                      onClick={() => { setCorrectingId(h.id); setCorrectionNote(''); }}
                    >
                      <ThumbsDown className="size-3.5" />
                    </button>
                  </div>

                  {correctingId === h.id && (
                    <div className="mt-1.5 flex gap-1.5">
                      <Input
                        className="h-7 text-xs"
                        placeholder="What was wrong? (optional, helps it not repeat the mistake)"
                        value={correctionNote}
                        onChange={(e) => setCorrectionNote(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            feedback.mutate({ messageId: h.id, helpful: false, note: correctionNote.trim() || undefined });
                            setCorrectingId(null);
                          }
                        }}
                      />
                      <Button
                        size="sm" variant="outline" className="h-7 px-2 text-xs"
                        onClick={() => {
                          feedback.mutate({ messageId: h.id, helpful: false, note: correctionNote.trim() || undefined });
                          setCorrectingId(null);
                        }}
                      >
                        Submit
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {ask.isPending && (
              <div className="flex flex-col gap-1.5">
                <div className="self-end max-w-[85%] rounded-lg bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                  {ask.variables}
                </div>
                <div className="self-start rounded-lg bg-muted px-3.5 py-2 text-sm text-muted-foreground">
                  Thinking… {elapsed}s elapsed.
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-2 border-t p-4 pt-3">
          <Input
            placeholder={modelLoading ? 'Waiting for the AI model to finish loading…' : 'e.g. how much did I spend on food last month?'}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(question); }}
            disabled={modelLoading}
          />
          <Button onClick={() => submit(question)} disabled={ask.isPending || modelLoading || !question.trim()}>
            <Send className="size-4" /> Ask
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
