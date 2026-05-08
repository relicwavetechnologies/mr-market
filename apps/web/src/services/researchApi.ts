import { apiFetch, parseJsonOrThrow } from './apiClient';

export interface ResearchUploadResult {
  ok: boolean;
  ticker: string;
  title: string;
  fy: string | null;
  kind: string;
  n_pages: number;
  n_chunks: number;
  n_embedded: number;
  duration_ms: number;
  size_bytes: number;
  uploaded_by: string;
  error?: string;
}

export interface UploadOptions {
  ticker: string;
  title: string;
  fy?: string;
  kind?: 'annual_report' | 'concall_transcript' | 'research_note' | 'other';
  sourceUrl?: string;
  file: File;
  onProgress?: (loaded: number, total: number) => void;
}

/**
 * POST /research/upload — multipart PDF ingestion.
 *
 * Streams the PDF to the backend, which parses → chunks → embeds →
 * upserts to Pinecone (or JSONB fallback). Returns ingest stats:
 * pages, chunks, embedded count, duration. Re-uploading with the
 * same (ticker, kind, fy) cleanly replaces the previous chunks.
 *
 * Auth required (PM-1 JWT). The backend universe-gates the ticker
 * (only NIFTY-100 names are accepted today) and caps file size at
 * 50 MB.
 */
export async function uploadResearchPdf(opts: UploadOptions): Promise<ResearchUploadResult> {
  const form = new FormData();
  form.append('ticker', opts.ticker.trim().toUpperCase());
  form.append('title', opts.title.trim());
  if (opts.fy) form.append('fy', opts.fy.trim());
  if (opts.kind) form.append('kind', opts.kind);
  if (opts.sourceUrl) form.append('source_url', opts.sourceUrl.trim());
  form.append('file', opts.file);

  const res = await apiFetch('/research/upload', {
    method: 'POST',
    body: form,
  });
  return parseJsonOrThrow<ResearchUploadResult>(res, 'upload research');
}
