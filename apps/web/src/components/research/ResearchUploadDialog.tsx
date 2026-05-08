/**
 * Drag-drop / picker upload for research PDFs.
 *
 * UX: opens via the paperclip button in ChatInput. The user drops a PDF
 * (or clicks to pick), fills in the ticker + FY + title, and submits.
 * The dialog stays open during ingestion so the user can see live
 * progress (page count, chunks embedded). On success → toast + close.
 *
 * Re-uploading with the same (ticker, kind, fy) replaces the prior
 * chunks in the corpus — same idempotency `scripts.ingest_research`
 * provides on the CLI.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, FileText, Upload, XCircle } from 'lucide-react';
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
import { cn } from '@/lib/utils';
import {
  uploadResearchPdf,
  type ResearchUploadResult,
} from '@/services/researchApi';

interface Props {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

const KIND_OPTIONS = [
  { value: 'annual_report', label: 'Annual Report' },
  { value: 'concall_transcript', label: 'Earnings Call Transcript' },
  { value: 'research_note', label: 'Research Note' },
  { value: 'other', label: 'Other' },
] as const;

export function ResearchUploadDialog({ open, onOpenChange }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [ticker, setTicker] = useState('');
  const [title, setTitle] = useState('');
  const [fy, setFy] = useState('FY25');
  const [kind, setKind] = useState<(typeof KIND_OPTIONS)[number]['value']>('annual_report');
  const [sourceUrl, setSourceUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchUploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setFile(null);
    setTicker('');
    setTitle('');
    setFy('FY25');
    setKind('annual_report');
    setSourceUrl('');
    setBusy(false);
    setError(null);
    setResult(null);
  }, []);

  useEffect(() => {
    if (!open) {
      // Wait for the close animation before clearing state.
      const id = setTimeout(reset, 200);
      return () => clearTimeout(id);
    }
  }, [open, reset]);

  const handleFile = (next: File | null) => {
    if (!next) {
      setFile(null);
      return;
    }
    if (!next.name.toLowerCase().endsWith('.pdf')) {
      setError(`Only .pdf files are accepted (got "${next.name}")`);
      return;
    }
    if (next.size > 50 * 1024 * 1024) {
      setError(`File too large: ${(next.size / 1024 / 1024).toFixed(1)} MB > 50 MB cap`);
      return;
    }
    setError(null);
    setFile(next);
    if (!title) {
      // Try to derive a sensible default title from the filename.
      const stem = next.name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ').trim();
      setTitle(stem);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0] ?? null;
    handleFile(f);
  };

  const handleSubmit = async () => {
    if (!file || !ticker.trim() || !title.trim()) {
      setError('Need a PDF, a ticker, and a title.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await uploadResearchPdf({
        ticker,
        title,
        fy: fy || undefined,
        kind,
        sourceUrl: sourceUrl || undefined,
        file,
      });
      setResult(r);
      if (!r.ok && r.error) setError(r.error);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Upload research PDF</DialogTitle>
          <DialogDescription>
            Annual report, earnings-call transcript, or research note. Indexed
            into the RAG corpus so the chat can quote it directly.
          </DialogDescription>
        </DialogHeader>

        {/* Drop zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
            dragOver
              ? 'border-accent-blue bg-accent-blue/5'
              : 'border-border/70 hover:border-border bg-muted/20',
          )}
        >
          {file ? (
            <>
              <FileText className="size-6 text-foreground/80" />
              <p className="text-[13px] font-medium text-foreground">{file.name}</p>
              <p className="text-[11px] text-muted-foreground">
                {(file.size / 1024 / 1024).toFixed(2)} MB
              </p>
            </>
          ) : (
            <>
              <Upload className="size-6 text-muted-foreground" />
              <p className="text-[13px] font-medium text-foreground">
                Drop a PDF here, or click to pick
              </p>
              <p className="text-[11px] text-muted-foreground">Max 50 MB</p>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          />
        </div>

        {/* Metadata */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="upload-ticker" className="text-[11px]">
              Ticker
            </Label>
            <Input
              id="upload-ticker"
              placeholder="RELIANCE"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              disabled={busy}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="upload-fy" className="text-[11px]">
              Fiscal year
            </Label>
            <Input
              id="upload-fy"
              placeholder="FY25"
              value={fy}
              onChange={(e) => setFy(e.target.value.toUpperCase())}
              disabled={busy}
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="upload-title" className="text-[11px]">
              Title
            </Label>
            <Input
              id="upload-title"
              placeholder="Reliance Industries Annual Report 2024-25"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={busy}
            />
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="upload-kind" className="text-[11px]">
              Kind
            </Label>
            <select
              id="upload-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as typeof kind)}
              disabled={busy}
              className="flex h-9 w-full rounded-md border border-border bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
            >
              {KIND_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div className="col-span-2 space-y-1">
            <Label htmlFor="upload-source" className="text-[11px]">
              Source URL <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Input
              id="upload-source"
              placeholder="https://www.ril.com/.../annual-report-2024-25.pdf"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              disabled={busy}
            />
          </div>
        </div>

        {/* Status */}
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-accent-red/40 bg-accent-red/5 px-3 py-2 text-[12px] text-accent-red">
            <XCircle className="mt-0.5 size-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}
        {result?.ok && (
          <div className="flex items-start gap-2 rounded-md border border-teal/40 bg-teal/5 px-3 py-2 text-[12px] text-teal">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
            <span>
              Indexed <strong>{result.ticker}</strong> {result.fy && `(${result.fy})`}: {' '}
              {result.n_chunks} chunks across {result.n_pages} pages in{' '}
              {(result.duration_ms / 1000).toFixed(1)} s.
            </span>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            Close
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!file || !ticker || !title || busy}
          >
            {busy ? 'Indexing…' : 'Upload + Index'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
