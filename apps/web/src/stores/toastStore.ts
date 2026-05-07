import { create } from 'zustand';

export type ToastKind = 'info' | 'success' | 'warning' | 'error' | 'pro';

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface Toast {
  id: string;
  kind: ToastKind;
  message: string;
  /** Small left-side badge / label, e.g. "Pro", "Tip", "Saved". */
  badge?: string;
  /** Optional inline action button. */
  action?: ToastAction;
  /** ms before auto-dismiss. `null` keeps it until manually dismissed. */
  duration: number | null;
}

interface ToastState {
  toasts: Toast[];
  push: (input: Omit<Toast, 'id' | 'duration'> & { duration?: number | null }) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

const DEFAULT_DURATION = 5000;

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  push: (input) => {
    const id = crypto.randomUUID();
    const toast: Toast = {
      id,
      kind: input.kind,
      message: input.message,
      badge: input.badge,
      action: input.action,
      duration: input.duration === undefined ? DEFAULT_DURATION : input.duration,
    };
    set((s) => ({ toasts: [...s.toasts, toast] }));
    if (toast.duration !== null) {
      window.setTimeout(() => get().dismiss(id), toast.duration);
    }
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clear: () => set({ toasts: [] }),
}));

/** Sugar API. Usage: `toast.success({ message: 'Memory saved' })` */
export const toast = {
  info: (t: Omit<Toast, 'id' | 'kind' | 'duration'> & { duration?: number | null }) =>
    useToastStore.getState().push({ ...t, kind: 'info' }),
  success: (t: Omit<Toast, 'id' | 'kind' | 'duration'> & { duration?: number | null }) =>
    useToastStore.getState().push({ ...t, kind: 'success' }),
  warning: (t: Omit<Toast, 'id' | 'kind' | 'duration'> & { duration?: number | null }) =>
    useToastStore.getState().push({ ...t, kind: 'warning' }),
  error: (t: Omit<Toast, 'id' | 'kind' | 'duration'> & { duration?: number | null }) =>
    useToastStore.getState().push({ ...t, kind: 'error' }),
  pro: (t: Omit<Toast, 'id' | 'kind' | 'duration'> & { duration?: number | null }) =>
    useToastStore.getState().push({ ...t, kind: 'pro', badge: t.badge ?? 'Pro' }),
  dismiss: (id: string) => useToastStore.getState().dismiss(id),
};
