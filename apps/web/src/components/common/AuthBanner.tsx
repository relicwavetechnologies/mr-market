import { useEffect, useState } from 'react';
import {
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Loader2,
  LogOut,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  clearApiKey,
  completeCodexLogin,
  disconnectCodexLogin,
  getAuthStatus,
  initiateCodexLogin,
  setApiKey,
} from '@/services/authApi';
import type { AuthStatus } from '@/types';
import { cn } from '@/lib/utils';

const SOURCE_LABEL: Record<string, string> = {
  codex_oauth: 'OpenAI connected',
  redis: 'Pasted key',
  env: '.env file',
  codex_cli: 'codex login',
  none: 'Not configured',
};

function sourceLabel(source: string) {
  return SOURCE_LABEL[source] ?? source;
}

function statusLabel(status: AuthStatus | null) {
  if (!status?.configured) return 'OpenAI key needed';
  return status.using_fallback ? 'Fallback mode' : sourceLabel(status.source);
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
            <span>{status?.source === 'none' ? 'No model key' : statusLabel(status)}</span>
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
  const [callbackUrl, setCallbackUrl] = useState('');
  const [fallbackKey, setFallbackKey] = useState('');
  const [redirectUri, setRedirectUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const connect = async () => {
    setBusy(true);
    setErr(null);
    try {
      const next = await initiateCodexLogin();
      setRedirectUri(next.redirect_uri);
      window.open(next.auth_url, '_blank', 'noopener,noreferrer');
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    if (!callbackUrl.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const next = await completeCodexLogin(callbackUrl.trim());
      onChanged(next);
      setCallbackUrl('');
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
      const next = await disconnectCodexLogin();
      onChanged(next);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saveFallbackKey = async () => {
    if (!fallbackKey.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const next = await setApiKey(fallbackKey.trim());
      onChanged(next);
      setFallbackKey('');
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const clearFallbackKey = async () => {
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
              <span>{statusLabel(status)}</span>
            </>
          ) : (
            <>
              <KeyRound className="size-3.5 text-accent-red" />
              <span>Neither Codex nor backend OPENAI_API_KEY is configured</span>
            </>
          )}
        </div>
        {status?.codex_auth_path && (
          <span className="truncate text-[11px] text-muted-foreground">
            {status.codex_auth_path}
          </span>
        )}
        {status?.expires_at && (
          <span className="text-[11px] text-muted-foreground">
            Token refreshes from Redis · {formatExpiry(status.expires_at)}
          </span>
        )}
        {status?.hint && (
          <span className="text-[11px] text-muted-foreground">{status.hint}</span>
        )}
        {status?.fallback_reason && !status?.hint && (
          <span className="text-[11px] text-muted-foreground">
            {status.fallback_reason}
          </span>
        )}
      </div>

      <Button
        type="button"
        size="sm"
        onClick={connect}
        disabled={busy}
        className="h-8 gap-1.5"
      >
        <ExternalLink className="size-3.5" />
        Open OpenAI login
      </Button>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground" htmlFor="openai-callback">
          Paste redirect URL
        </label>
        <Input
          id="openai-callback"
          value={callbackUrl}
          onChange={(e) => setCallbackUrl(e.target.value)}
          placeholder={redirectUri ?? 'http://localhost:1455/auth/callback?code=...'}
          onKeyDown={(e) => e.key === 'Enter' && complete()}
          className="h-8 text-[12px]"
        />
        <Button
          type="button"
          size="sm"
          onClick={complete}
          disabled={busy || !callbackUrl.trim()}
          className="h-8 self-start"
        >
          Use Codex token
        </Button>
      </div>

      {status?.source !== 'codex_oauth' && status?.source !== 'codex_cli' && (
        <div className="flex flex-col gap-1.5 border-t border-border/60 pt-3">
          <label className="text-[11px] text-muted-foreground" htmlFor="openai-fallback-key">
            Backend OPENAI_API_KEY fallback for GPT-4o mini
          </label>
          <div className="flex gap-1.5">
            <Input
              id="openai-fallback-key"
              type="password"
              value={fallbackKey}
              onChange={(e) => setFallbackKey(e.target.value)}
              placeholder="sk-..."
              onKeyDown={(e) => e.key === 'Enter' && saveFallbackKey()}
              className="h-8 text-[12px]"
            />
            <Button
              type="button"
              size="sm"
              onClick={saveFallbackKey}
              disabled={busy || !fallbackKey.trim()}
              className="h-8"
            >
              Save
            </Button>
          </div>
        </div>
      )}

      {status?.source === 'codex_oauth' && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={clear}
          disabled={busy}
          className="h-8 gap-1.5 text-xs"
        >
          <LogOut className="size-3.5" />
          Disconnect OpenAI
        </Button>
      )}

      {status?.source === 'redis' && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={clearFallbackKey}
          disabled={busy}
          className="h-8 gap-1.5 text-xs"
        >
          <LogOut className="size-3.5" />
          Clear fallback key
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
        Re-check
      </Button>

      {err && <span className="text-[11px] text-accent-red">{err}</span>}
    </div>
  );
}

function formatExpiry(epochSeconds: number) {
  const date = new Date(epochSeconds * 1000);
  if (Number.isNaN(date.getTime())) return 'expiry unknown';
  return `expires ${date.toLocaleString()}`;
}
