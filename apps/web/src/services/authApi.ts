import type { AuthStatus } from '@/types';

const AUTH_BASE = '/api/auth/openai';

export async function getAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${AUTH_BASE}/status`);
  if (!res.ok) throw new Error(`Auth status failed (${res.status})`);
  return (await res.json()) as AuthStatus;
}

export async function setApiKey(apiKey: string, ttlSeconds = 86400): Promise<AuthStatus> {
  const res = await fetch(`${AUTH_BASE}/key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey, ttl_seconds: ttlSeconds }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Save key failed (${res.status}): ${text}`);
  }
  return (await res.json()) as AuthStatus;
}

export async function clearApiKey(): Promise<AuthStatus> {
  const res = await fetch(`${AUTH_BASE}/key`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Clear key failed (${res.status})`);
  return (await res.json()) as AuthStatus;
}
