interface ApiAuthConfig {
  getAccessToken: () => string | null;
  refreshAccessToken: () => Promise<string | null>;
  onUnauthorized: () => void;
}

let authConfig: ApiAuthConfig | null = null;

export function configureApiAuth(config: ApiAuthConfig) {
  authConfig = config;
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  return authedFetch(input, init, true);
}

async function authedFetch(
  input: RequestInfo | URL,
  init: RequestInit,
  retryOnUnauthorized: boolean,
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = authConfig?.getAccessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const res = await fetch(input, { ...init, headers });
  if (res.status !== 401 || !retryOnUnauthorized || !authConfig) return res;

  const refreshed = await authConfig.refreshAccessToken();
  if (!refreshed) {
    authConfig.onUnauthorized();
    return res;
  }

  const retryHeaders = new Headers(init.headers);
  retryHeaders.set('Authorization', `Bearer ${refreshed}`);
  const retry = await fetch(input, { ...init, headers: retryHeaders });
  if (retry.status === 401) authConfig.onUnauthorized();
  return retry;
}

export async function parseJsonOrThrow<T>(res: Response, label: string): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`${label} failed (${res.status}): ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}
