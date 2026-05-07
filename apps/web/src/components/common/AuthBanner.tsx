import { useEffect, useState } from 'react';
import { CheckCircle2, KeyRound, Loader2, RefreshCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { clearApiKey, getAuthStatus, setApiKey } from '@/services/authApi';
import type { AuthStatus } from '@/types';
import { cn } from '@/lib/utils';

const SOURCE_LABEL: Record<string, string> = {
  redis: 'Pasted key',
  env: '.env file',
  codex_cli: 'codex login',
  none: 'Not configured',
};

function sourceLabel(source: string) {
  return SOURCE_LABEL[source] ?? source;
}

export function AuthBanner() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await getAuthStatus());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const configured = status?.configured ?? false;

  return (
    <div className="flex items-center gap-2 text-[12px]">
      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium',
              configured
                ? 'text-foreground hover:bg-accent'
                : 'text-accent-red hover:bg-accent-red/10',
            )}
          >
            {loading ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : configured ? (
              <CheckCircle2 className="size-3.5 text-accent-green" />
            ) : (
              <KeyRound className="size-3.5" />
            )}
            <span>
              {configured ? sourceLabel(status!.source) : 'OpenAI key needed'}
            </span>
            {status && (
              <span className="text-muted-foreground">· {status.model_work}</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 p-0">
          <KeyManager status={status} onChanged={setStatus} onRefresh={refresh} />
        </PopoverContent>
      </Popover>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={refresh}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Refresh auth status"
          >
            <RefreshCw className={cn('size-3.5', loading && 'animate-spin')} />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Refresh status</TooltipContent>
      </Tooltip>

      {error && (
        <span className="text-[11px] text-accent-red">{error}</span>
      )}
    </div>
  );
}

interface KeyManagerProps {
  status: AuthStatus | null;
  onChanged: (s: AuthStatus) => void;
  onRefresh: () => void;
}

function KeyManager({ status, onChanged, onRefresh }: KeyManagerProps) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async () => {
    if (!key.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const next = await setApiKey(key.trim());
      onChanged(next);
      setKey('');
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setErr(null);
    try {
      const next = await clearApiKey();
      onChanged(next);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="flex flex-col gap-1">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          OpenAI credential
        </span>
        <div className="flex items-center gap-2 text-[13px] text-foreground">
          {status?.configured ? (
            <>
              <CheckCircle2 className="size-3.5 text-accent-green" />
              <span>{sourceLabel(status.source)}</span>
            </>
          ) : (
            <>
              <KeyRound className="size-3.5 text-accent-red" />
              <span>Not configured</span>
            </>
          )}
        </div>
        {status?.codex_auth_path && (
          <span className="truncate text-[11px] text-muted-foreground">
            {status.codex_auth_path}
          </span>
        )}
        {status?.hint && (
          <span className="text-[11px] text-muted-foreground">{status.hint}</span>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground" htmlFor="openai-key">
          Paste a key (24h Redis TTL)
        </label>
        <div className="flex gap-1.5">
          <Input
            id="openai-key"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-..."
            onKeyDown={(e) => e.key === 'Enter' && save()}
            className="h-8 text-[12px]"
          />
          <Button
            type="button"
            size="sm"
            onClick={save}
            disabled={busy || !key.trim()}
            className="h-8"
          >
            Save
          </Button>
        </div>
      </div>

      {status?.source === 'redis' && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={clear}
          disabled={busy}
          className="h-8 gap-1.5 text-xs"
        >
          <X className="size-3.5" />
          Clear pasted key
        </Button>
      )}

      <Button
        type="button"
        size="sm"
        variant="ghost"
        onClick={onRefresh}
        className="h-7 gap-1.5 self-start text-[11px] text-muted-foreground hover:text-foreground"
      >
        <RefreshCw className="size-3" />
        Re-check (after `codex login`)
      </Button>

      {err && <span className="text-[11px] text-accent-red">{err}</span>}
    </div>
  );
}
