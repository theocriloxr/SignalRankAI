import * as SecureStore from 'expo-secure-store';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8080').replace(/\/$/, '');
const ACCESS_KEY = 'signalrank.access_token';
const REFRESH_KEY = 'signalrank.refresh_token';

export type SessionPayload = {
  access_token?: string;
  refresh_token?: string;
  user?: Record<string, unknown>;
};

export async function storeSession(payload: SessionPayload): Promise<void> {
  if (payload.access_token) await SecureStore.setItemAsync(ACCESS_KEY, payload.access_token);
  if (payload.refresh_token) await SecureStore.setItemAsync(REFRESH_KEY, payload.refresh_token);
}

export async function clearSession(): Promise<void> {
  await Promise.all([SecureStore.deleteItemAsync(ACCESS_KEY), SecureStore.deleteItemAsync(REFRESH_KEY)]);
}

async function refresh(): Promise<string | null> {
  const refreshToken = await SecureStore.getItemAsync(REFRESH_KEY);
  if (!refreshToken) return null;
  const response = await fetch(`${API_URL}/api/v1/platform/auth/refresh`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({refresh_token: refreshToken, client_type: 'mobile'}),
  });
  if (!response.ok) {
    await clearSession();
    return null;
  }
  const payload = await response.json() as SessionPayload;
  await storeSession(payload);
  return payload.access_token || null;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  let accessToken = await SecureStore.getItemAsync(ACCESS_KEY);
  const send = (token: string | null) => fetch(`${API_URL}/api/v1/platform${path}`, {
    ...init,
    headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {}), ...(init.headers || {})},
  });
  let response = await send(accessToken);
  if (response.status === 401 && retry) {
    accessToken = await refresh();
    if (accessToken) response = await send(accessToken);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload as T;
}

export async function login(email: string, password: string): Promise<SessionPayload> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/login`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Login failed');
  await storeSession(payload);
  return payload;
}

export async function register(displayName: string, email: string, password: string): Promise<SessionPayload> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/register`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({display_name: displayName, email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Registration failed');
  await storeSession(payload);
  return payload;
}

export async function activateTelegram(tokenOrCode: string, email: string, password: string): Promise<SessionPayload> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/telegram/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token_or_code: tokenOrCode, email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Activation failed');
  await storeSession(payload);
  return payload;
}

export async function registerPushDevice(input: {
  pushToken: string;
  platform: 'android' | 'ios';
  deviceId?: string;
  appVersion?: string;
}): Promise<{registered: boolean}> {
  return api('/push-devices', {
    method: 'POST',
    body: JSON.stringify({
      provider: 'expo',
      push_token: input.pushToken,
      platform: input.platform,
      device_id: input.deviceId,
      app_version: input.appVersion,
    }),
  });
}

export async function createTelegramLink(): Promise<{code: string; expires_at: string; telegram_deep_link?: string | null}> {
  return api('/account/telegram-link', {method: 'POST', body: JSON.stringify({})});
}

export async function createJournalEntry(input: {title?: string; notes: string; emotion?: string; tags?: string[]}): Promise<{journal_entry_id: string}> {
  return api('/journal', {method: 'POST', body: JSON.stringify(input)});
}
