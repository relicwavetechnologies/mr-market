import { apiFetch, parseJsonOrThrow } from './apiClient';
import type { User } from '@/types';

interface ApiUser {
  id: string;
  email: string;
  display_name: string;
}

interface AuthResponse {
  user: ApiUser;
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface RefreshResponse {
  access_token: string;
  token_type: string;
}

export interface AuthSession {
  user: User;
  accessToken: string;
  refreshToken: string;
}

export async function signup(email: string, password: string, displayName: string): Promise<AuthSession> {
  const res = await fetch('/api/users/signup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  return normalizeAuth(await parseJsonOrThrow<AuthResponse>(res, 'Signup'));
}

export async function login(email: string, password: string): Promise<AuthSession> {
  const res = await fetch('/api/users/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  return normalizeAuth(await parseJsonOrThrow<AuthResponse>(res, 'Login'));
}

export async function refresh(refreshToken: string): Promise<string> {
  const res = await fetch('/api/users/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  const payload = await parseJsonOrThrow<RefreshResponse>(res, 'Refresh token');
  return payload.access_token;
}

export async function me(): Promise<User> {
  const res = await apiFetch('/api/users/me');
  const user = await parseJsonOrThrow<ApiUser>(res, 'Load current user');
  return normalizeUser(user);
}

export async function logout(): Promise<void> {
  const res = await apiFetch('/api/users/logout', { method: 'POST' });
  if (!res.ok && res.status !== 401) {
    const text = await res.text().catch(() => '');
    throw new Error(`Logout failed (${res.status}): ${text || res.statusText}`);
  }
}

function normalizeAuth(payload: AuthResponse): AuthSession {
  return {
    user: normalizeUser(payload.user),
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
  };
}

function normalizeUser(user: ApiUser): User {
  return {
    id: user.id,
    email: user.email,
    name: user.display_name,
    riskProfile: 'moderate',
  };
}
