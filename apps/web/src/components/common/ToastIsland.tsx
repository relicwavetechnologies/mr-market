import { useEffect, useState } from 'react';
import { CheckCircle2, Info, Sparkles, TriangleAlert, X, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToastStore, type Toast, type ToastKind } from '@/stores/toastStore';
import { cn } from '@/lib/utils';

const KIND_META: Record<ToastKind, { icon: LucideIcon; iconClass: string; badgeClass: string }> = {
  info: {
    icon: Info,
    iconClass: 'text-foreground/70',
    badgeClass: 'bg-foreground/10 text-foreground',
  },
  success: {
    icon: CheckCircle2,
    iconClass: 'text-accent-green',
    badgeClass: 'bg-accent-green/15 text-accent-green',
  },
  warning: {
    icon: TriangleAlert,
    iconClass: 'text-amber-400',
    badgeClass: 'bg-amber-400/15 text-amber-400',
  },
  error: {
    icon: XCircle,
    iconClass: 'text-accent-red',
    badgeClass: 'bg-accent-red/15 text-accent-red',
  },
  pro: {
    icon: Sparkles,
    iconClass: 'text-teal',
    badgeClass: 'bg-teal/15 text-teal',
  },
};

/**
 * Renders the active toast stack. Designed to be placed *just above* the input
 * island in `ChatPage` / `HomePage`. Toasts fade-and-rise on mount, fall on
 * dismiss, and auto-dismiss based on `toast.duration`.
 */
export function ToastIsland() {
  const toasts = useToastStore((s) => s.toasts);

  if (toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Notifications"
      className="pointer-events-none mb-2 flex flex-col-reverse items-center gap-2"
    >
      {toasts.map((t) => (
        <ToastRow key={t.id} toast={t} />
      ))}
    </div>
  );
}

function ToastRow({ toast }: { toast: Toast }) {
  const dismiss = useToastStore((s) => s.dismiss);
  const meta = KIND_META[toast.kind];
  const Icon = meta.icon;
  const [closing, setClosing] = useState(false);

  // When the store removes this toast (auto-dismiss), the parent unmounts us
  // — so the exit animation only plays for manual dismiss. We orchestrate that
  // by delaying the actual `dismiss()` call until our exit anim finishes.
  useEffect(() => {
    if (!closing) return;
    const t = window.setTimeout(() => dismiss(toast.id), 160);
    return () => window.clearTimeout(t);
  }, [closing, dismiss, toast.id]);

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-auto flex max-w-[560px] items-center gap-3 rounded-full border border-border/70 bg-card/90 px-3 py-1.5 shadow-[0_8px_24px_-12px_rgb(0_0_0/0.5)] backdrop-blur-md',
        closing ? 'animate-toast-out' : 'animate-toast-in',
      )}
    >
      {toast.badge ? (
        <span
          className={cn(
            'flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider',
            meta.badgeClass,
          )}
        >
          <Icon className="size-3" />
          {toast.badge}
        </span>
      ) : (
        <Icon className={cn('size-4 shrink-0', meta.iconClass)} />
      )}

      <p className="truncate text-[12.5px] text-foreground">{toast.message}</p>

      {toast.action && (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => {
            toast.action?.onClick();
            setClosing(true);
          }}
          className="ml-auto h-6 shrink-0 rounded-full px-2.5 text-[11px] font-medium"
        >
          {toast.action.label}
        </Button>
      )}

      <button
        type="button"
        onClick={() => setClosing(true)}
        aria-label="Dismiss"
        className={cn(
          'flex size-5 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground',
          toast.action ? '' : 'ml-auto',
        )}
      >
        <X className="size-3" />
      </button>
    </div>
  );
}
