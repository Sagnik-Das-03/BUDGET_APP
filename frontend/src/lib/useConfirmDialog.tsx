import { useCallback, useRef, useState } from 'react';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ConfirmOptions {
  title?: string;
  /** Styles the confirm button red - on by default, since this hook exists mainly for
   * "are you sure you want to delete/permanently remove this" prompts. */
  destructive?: boolean;
  confirmLabel?: string;
}

interface ConfirmState extends ConfirmOptions {
  message: string;
}

// Drop-in replacement for `if (confirm("...")) { ... }` that renders the app's own
// dialog instead of the browser's native one - use as `if (await confirm("...")) { ... }`
// inside an async handler, and render `{dialog}` once somewhere in the component's JSX.
export function useConfirmDialog() {
  const [state, setState] = useState<ConfirmState | null>(null);
  const resolverRef = useRef<((value: boolean) => void) | undefined>(undefined);

  const confirm = useCallback((message: string, options?: ConfirmOptions) => {
    setState({ message, destructive: true, ...options });
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  }, []);

  function settle(result: boolean) {
    setState(null);
    resolverRef.current?.(result);
  }

  const dialog = (
    <AlertDialog open={state !== null} onOpenChange={(open) => { if (!open) settle(false); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state?.title ?? 'Are you sure?'}</AlertDialogTitle>
          <AlertDialogDescription>{state?.message}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => settle(false)}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={cn(state?.destructive !== false && buttonVariants({ variant: 'destructive' }))}
            onClick={() => settle(true)}
          >
            {state?.confirmLabel ?? 'Confirm'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { confirm, dialog };
}
