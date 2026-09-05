import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Send } from 'lucide-react';
import { api } from '../lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Exchange {
  question: string;
  answer: string;
}

const EXAMPLES = [
  'how much did I spend on food last month?',
  'how many transactions this year?',
  'what is my average shopping expense?',
];

export function Ask() {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<Exchange[]>([]);

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(q),
    onSuccess: (res, q) => setHistory((h) => [...h, { question: q, answer: res.answer }]),
    onError: (err: Error, q) => setHistory((h) => [...h, { question: q, answer: `Error: ${err.message}` }]),
  });

  function submit(q: string) {
    const trimmed = q.trim();
    if (!trimmed || ask.isPending) return;
    ask.mutate(trimmed);
    setQuestion('');
  }

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Ask Your Budget</h1>
      <p className="mb-5 mt-1 text-sm text-muted-foreground">
        Ask about your spending in plain English. A local AI model turns your question into a
        query over your own transactions — it doesn't do the arithmetic itself.
      </p>

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
            </div>
          </div>
        ))}
        {ask.isPending && (
          <div className="self-start rounded-lg bg-muted px-3.5 py-2 text-sm text-muted-foreground">
            Thinking… this can take up to a minute the first time, while the local model loads.
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
