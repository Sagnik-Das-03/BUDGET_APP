import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { api } from '../lib/api';
import type { ViewFilters } from '../lib/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface SaveViewPopoverProps {
  filters: ViewFilters;
  onSave: (name: string) => void;
}

export function SaveViewPopover({ filters, onSave }: SaveViewPopoverProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [nameTouched, setNameTouched] = useState(false);

  const suggest = useMutation({
    mutationFn: () => api.suggestViewName(filters),
    onSuccess: (res) => {
      // Don't clobber a name the user already started typing while this was in flight.
      if (!nameTouched && res.name) setName(res.name);
    },
  });

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      setName('');
      setNameTouched(false);
      suggest.mutate();
    }
  }

  function confirm() {
    const trimmed = name.trim();
    if (!trimmed) return;
    onSave(trimmed);
    setName('');
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">Save View</Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64">
        <div className="flex flex-col gap-2.5">
          <Label htmlFor="save-view-name" className="text-xs text-muted-foreground">Name this view</Label>
          <Input
            id="save-view-name"
            autoFocus
            value={name}
            onChange={(e) => { setName(e.target.value); setNameTouched(true); }}
            onKeyDown={(e) => { if (e.key === 'Enter') confirm(); }}
            placeholder={suggest.isPending ? 'Suggesting…' : 'e.g. Zomato Spending'}
          />
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Sparkles className="size-3" /> {suggest.isPending ? 'Thinking…' : 'AI-suggested'}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
              <Button size="sm" disabled={!name.trim()} onClick={confirm}>Save</Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
