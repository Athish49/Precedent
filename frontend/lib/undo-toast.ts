import { toast } from 'sonner';

interface UndoToastOptions {
  message: string;
  onUndo: () => void;
  duration?: number;
}

export function undoToast({ message, onUndo, duration = 5000 }: UndoToastOptions): string | number {
  return toast.success(message, {
    duration,
    action: {
      label: 'Undo',
      onClick: onUndo,
    },
  });
}
