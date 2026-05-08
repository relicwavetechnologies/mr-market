/**
 * Drag-drop / paste import for a portfolio.
 *
 * UX: opens via the briefcase button in `SearchInput`. Two paths:
 *  1. **Paste** Zerodha holdings (or any CSV with ticker / qty / avg-price
 *     columns) into the textarea. The server auto-detects the format.
 *  2. **Drop a CSV file** onto the dropzone — same parser, just delivered
 *     as raw text instead of typed.
 *
 * After a successful import, the dialog shows a green summary plus an
 * "Analyze this portfolio" button that closes the dialog and pre-fills
 * the chat with `analyse my portfolio (id=N)`. The user just hits Enter
 * to fire `analyse_portfolio` against their freshly-imported portfolio.
 *
 * Out-of-NIFTY-100 tickers are dropped server-side and surfaced in
 * `unknown_tickers`; repeated rows for the same ticker are collapsed
 * with a weighted-average cost.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  Briefcase,
  CheckCircle2,
  FileText,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import {
  importPortfolio,
  type PortfolioImportResult,
} from '@/services/portfolioApi';

interface Props {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  /** Pre-fill chat input when the user clicks "Analyze". */
  onAnalyze?: (prompt: string) => void;
}

const PASTE_PLACEHOLDER = `Examples:

ticker,quantity,avg_price
RELIANCE,50,1380.50
TCS,10,2150.00
INFY,20,1450.00

— or paste straight from Zerodha holdings (tab-separated):

Instrument   Qty   Avg cost   LTP   Cur val   P&L   Net chg
RELIANCE     50    1380.50    1436  71800     2825  3.94%
TCS          10    2150.00    2401  24010     2510  11.68%`;

export function PortfolioImportDialog({ open, onOpenChange, onAnalyze }: Props) {
  const [rawText, setRawText] = useState('');
  const [name, setName] = useState('My Portfolio');
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PortfolioImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const reset = useCallback(() => {
    setRawText('');
    setName('My Portfolio');
    setBusy(false);
    setError(null);
    setResult(null);
  }, []);

  useEffect(() => {
    if (!open) {
      const id = setTimeout(reset, 200);
      return () => clearTimeout(id);
    }
  }, [open, reset]);

  const handleFile = (file: File | null) => {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError(`File too large: ${(file.size / 1024 / 1024).toFixed(1)} MB > 5 MB cap`);
      return;
    }
    setError(null);
    file.text().then((txt) => {
      setRawText(txt);
      // Bring focus to textarea so the user can review before import.
      textareaRef.current?.focus();
    });
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0] ?? null;
    handleFile(f);
  };

  const handleSubmit = async () => {
    if (!rawText.trim()) {
      setError('Paste a CSV / holdings block first.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await importPortfolio({
        rawText,
        name: name.trim() || 'My Portfolio',
      });
      setResult(r);
      if (r.error) setError(r.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleAnalyze = () => {
    if (!result?.portfolio_id) return;
    // No id in the prompt — the server defaults to the user's most
    // recently imported portfolio (which is the one we just imported).
    // If the user has multiple portfolios, the analyse_portfolio tool
    // returns a picker payload and the model asks them which one.
    const prompt = `Diagnose my portfolio — concentration, sector mix, beta, drawdown.`;
    onOpenChange(false);
    setTimeout(() => onAnalyze?.(prompt), 200);
  };

  const successWarn =
    result?.unknown_tickers && result.unknown_tickers.length > 0
      ? `Dropped (out of NIFTY-100): ${result.unknown_tickers.join(', ')}`
      : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Briefcase className="size-4" />
            Import portfolio
          </DialogTitle>
          <DialogDescription>
            Paste a CSV or your Zerodha holdings, or drop a CSV file. Tickers
            outside the NIFTY-100 universe are dropped automatically.
          </DialogDescription>
        </DialogHeader>

        {/* Drop zone for CSV files (compact). */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'flex cursor-pointer items-center justify-center gap-2 rounded-lg border-2 border-dashed px-3 py-3 text-center text-[12px] transition-colors',
            dragOver
              ? 'border-accent-blue bg-accent-blue/5'
              : 'border-border/70 bg-muted/20 hover:border-border',
          )}
        >
          {rawText && rawText.length > 0 ? (
            <>
              <FileText className="size-4 text-foreground/80" />
              <span className="font-medium text-foreground">
                {rawText.split('\n').filter((l) => l.trim()).length} lines pasted
              </span>
              <span className="text-muted-foreground">— edit below</span>
            </>
          ) : (
            <>
              <Upload className="size-4 text-muted-foreground" />
              <span className="text-foreground">Drop a CSV file</span>
              <span className="text-muted-foreground">or paste below</span>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv,text/plain"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {/* Paste textarea */}
        <div className="space-y-1">
          <Label htmlFor="portfolio-paste" className="text-[11px]">
            Holdings (CSV or Zerodha paste)
          </Label>
          <Textarea
            id="portfolio-paste"
            ref={textareaRef}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            placeholder={PASTE_PLACEHOLDER}
            disabled={busy}
            rows={10}
            className="font-mono text-[12px]"
          />
        </div>

        {/* Optional portfolio name */}
        <div className="space-y-1">
          <Label htmlFor="portfolio-name" className="text-[11px]">
            Portfolio name <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Input
            id="portfolio-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
            maxLength={64}
            placeholder="My Portfolio"
          />
        </div>

        {/* Status */}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-accent-red/40 bg-accent-red/5 px-3 py-2 text-[12px] text-accent-red">
            <XCircle className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {result?.portfolio_id && !error && (
          <div className="space-y-2">
            <div className="flex items-start gap-2 rounded-md border border-teal/40 bg-teal/5 px-3 py-2 text-[12px] text-teal">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
              <span>
                Imported <strong>{result.n_positions} position{result.n_positions === 1 ? '' : 's'}</strong>
                {' '}(portfolio_id <strong>{result.portfolio_id}</strong>) — total cost ₹
                {Number(result.total_cost_inr).toLocaleString('en-IN')}.
              </span>
            </div>
            {successWarn && (
              <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-500">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                <span>{successWarn}</span>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Close
          </Button>
          {result?.portfolio_id ? (
            <Button onClick={handleAnalyze}>
              Analyze this portfolio →
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={!rawText.trim() || busy}>
              {busy ? 'Importing…' : 'Import'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
