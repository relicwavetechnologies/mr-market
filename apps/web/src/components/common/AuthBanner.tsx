import { useEffect, useState } from "react";
import { Check, KeyRound, RefreshCw, X } from "lucide-react";

type AuthStatus = {
  configured: boolean;
  source: "redis" | "env" | "codex_cli" | "none";
  model_work: string;
  model_router: string;
  codex_auth_path?: string | null;
  hint?: string | null;
};

const SOURCE_LABEL: Record<AuthStatus["source"], string> = {
  redis: "pasted key",
  env: ".env file",
  codex_cli: "codex login",
  none: "none",
};

export function AuthBanner() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteValue, setPasteValue] = useState("");
  const [pasteBusy, setPasteBusy] = useState(false);

  const refresh = async () => {
    try {
      const r = await fetch("/api/auth/openai/status");
      if (!r.ok) return;
      setStatus((await r.json()) as AuthStatus);
    } catch {
      /* offline */
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const submit = async () => {
    if (!pasteValue.trim()) return;
    setPasteBusy(true);
    try {
      await fetch("/api/auth/openai/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: pasteValue.trim() }),
      });
      setPasteValue("");
      setPasteOpen(false);
      await refresh();
    } finally {
      setPasteBusy(false);
    }
  };

  const clear = async () => {
    await fetch("/api/auth/openai/key", { method: "DELETE" });
    await refresh();
  };

  if (!status) return null;

  const okBg = "border-emerald-700/40 bg-emerald-900/20 text-emerald-200";
  const errBg = "border-amber-700/40 bg-amber-900/20 text-amber-200";

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${status.configured ? okBg : errBg}`}>
      <div className="flex items-center gap-3">
        {status.configured ? (
          <Check size={14} className="shrink-0 text-emerald-400" />
        ) : (
          <KeyRound size={14} className="shrink-0 text-amber-400" />
        )}
        <div className="flex-1">
          {status.configured ? (
            <>
              <span className="font-medium">OpenAI auth active</span>
              <span className="text-text-muted">
                {" · "}
                source: <code className="text-emerald-300">{SOURCE_LABEL[status.source]}</code>
                {status.codex_auth_path && (
                  <>
                    {" · "}
                    <code className="text-text-muted">{status.codex_auth_path}</code>
                  </>
                )}
                {" · "}
                model: <code className="text-emerald-300">{status.model_work}</code>
              </span>
            </>
          ) : (
            <>
              <span className="font-medium">No OpenAI credential.</span>
              <span className="text-text-muted">
                {" "}
                Run <code className="text-amber-300">codex login</code> in your terminal, or paste a key below.
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            className="rounded p-1 text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
            aria-label="Refresh auth status"
            title="Re-check (e.g., after codex login)"
          >
            <RefreshCw size={12} />
          </button>
          {status.source === "redis" ? (
            <button
              onClick={clear}
              className="rounded px-2 py-0.5 text-[11px] text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
            >
              <X size={11} className="-mt-0.5 mr-1 inline" />
              clear
            </button>
          ) : (
            <button
              onClick={() => setPasteOpen((o) => !o)}
              className="rounded px-2 py-0.5 text-[11px] text-text-muted transition-colors hover:bg-bg-hover hover:text-text-primary"
            >
              paste key
            </button>
          )}
        </div>
      </div>

      {pasteOpen && (
        <div className="mt-2 flex items-center gap-2">
          <input
            type="password"
            placeholder="sk-..."
            value={pasteValue}
            onChange={(e) => setPasteValue(e.target.value)}
            className="flex-1 rounded border border-border-subtle bg-bg-tertiary px-2 py-1 text-[12px] text-text-primary outline-none focus:border-accent"
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <button
            onClick={submit}
            disabled={pasteBusy || !pasteValue.trim()}
            className="rounded bg-accent px-3 py-1 text-[12px] font-medium text-white disabled:opacity-40"
          >
            {pasteBusy ? "saving…" : "save"}
          </button>
          <button
            onClick={() => {
              setPasteOpen(false);
              setPasteValue("");
            }}
            className="rounded px-2 py-1 text-[12px] text-text-muted hover:text-text-primary"
          >
            cancel
          </button>
        </div>
      )}
    </div>
  );
}
