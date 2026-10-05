import * as SecureStore from 'expo-secure-store';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8080').replace(/\/$/, '');
const ACCESS_KEY = 'signalrank.access_token';
const REFRESH_KEY = 'signalrank.refresh_token';

function mobileFetch(url: string, init: RequestInit = {}): Promise<Response> {
  // Native sessions use explicit bearer/refresh proof, never browser cookies.
  return fetch(url, {...init, credentials: 'omit'});
}

export class PlatformAPIError extends Error {
  constructor(message: string, public readonly status: number, public readonly code?: string, public readonly generation?: number) {
    super(message);
    this.name = 'PlatformAPIError';
  }
}

function responseError(payload: unknown, status: number): PlatformAPIError {
  const detail = payload && typeof payload === 'object' ? (payload as {detail?: unknown}).detail : undefined;
  if (typeof detail === 'string') return new PlatformAPIError(detail, status);
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const value = detail as {message?: unknown; code?: unknown};
    const code = typeof value.code === 'string' ? value.code : undefined;
    return new PlatformAPIError(typeof value.message === 'string' ? value.message : code || `Request failed (${status})`, status, code);
  }
  return new PlatformAPIError(`Request failed (${status})`, status);
}

export type SessionPayload = {
  access_token?: string;
  refresh_token?: string;
  user?: Record<string, unknown>;
  authenticated?: boolean;
  mfa_required?: boolean;
  mfa_token?: string;
  expires_at?: string;
};

let sessionGeneration = 0;
let sessionBlocked = false;
let sessionWrites: Promise<void> = Promise.resolve();
let refreshTask: {generation: number; promise: Promise<string | null>} | null = null;

export function getSessionGeneration(): number { return sessionGeneration; }

function assertGeneration(generation: number): void {
  if (generation !== sessionGeneration) throw new PlatformAPIError('Account session changed. Please retry.', 409, 'session_changed');
}

function queueSessionWrite(operation: () => Promise<void>): Promise<void> {
  const next = sessionWrites.catch(() => {}).then(operation);
  sessionWrites = next;
  return next;
}

async function persistSession(payload: SessionPayload, generation: number): Promise<void> {
  if (!payload.access_token || !payload.refresh_token) throw new PlatformAPIError('Could not establish a secure session. Please retry.', 503, 'invalid_session_response');
  await queueSessionWrite(async () => {
    try {
      assertGeneration(generation);
      await SecureStore.setItemAsync(ACCESS_KEY, payload.access_token!);
      assertGeneration(generation);
      await SecureStore.setItemAsync(REFRESH_KEY, payload.refresh_token!);
      assertGeneration(generation);
    } catch (error) {
      if (generation !== sessionGeneration) throw error;
      ++sessionGeneration;
      sessionBlocked = true;
      await Promise.allSettled([SecureStore.deleteItemAsync(ACCESS_KEY), SecureStore.deleteItemAsync(REFRESH_KEY)]);
      throw new PlatformAPIError('Secure session storage failed. Sign in again.', 503, 'session_storage_failed', sessionGeneration);
    }
  });
}

export async function storeSession(payload: SessionPayload, expectedGeneration = sessionGeneration): Promise<void> {
  assertGeneration(expectedGeneration);
  const generation = ++sessionGeneration;
  sessionBlocked = true;
  await persistSession(payload, generation);
  assertGeneration(generation);
  sessionBlocked = false;
}

export async function clearSession(): Promise<void> {
  ++sessionGeneration;
  sessionBlocked = true;
  await queueSessionWrite(async () => {
    await Promise.all([SecureStore.deleteItemAsync(ACCESS_KEY), SecureStore.deleteItemAsync(REFRESH_KEY)]);
  });
}

async function refresh(generation: number): Promise<string | null> {
  assertGeneration(generation);
  if (sessionBlocked) return null;
  if (refreshTask?.generation === generation) return refreshTask.promise;
  const promise = (async () => {
    const refreshToken = await SecureStore.getItemAsync(REFRESH_KEY);
    assertGeneration(generation);
    if (!refreshToken || sessionBlocked) return null;
    const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/refresh`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({refresh_token: refreshToken, client_type: 'mobile'}),
    });
    const payload = await response.json().catch(() => ({}));
    assertGeneration(generation);
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        const expiredGeneration = sessionGeneration + 1;
        await clearSession();
        assertGeneration(expiredGeneration);
        throw new PlatformAPIError('Session expired. Sign in again.', 401, 'session_expired', expiredGeneration);
      }
      throw responseError(payload, response.status);
    }
    await persistSession(payload as SessionPayload, generation);
    return (payload as SessionPayload).access_token || null;
  })();
  const task = {generation, promise};
  refreshTask = task;
  try { return await promise; }
  finally { if (refreshTask === task) refreshTask = null; }
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const generation = sessionGeneration;
  let accessToken = sessionBlocked ? null : await SecureStore.getItemAsync(ACCESS_KEY);
  const send = (token: string | null) => {
    assertGeneration(generation);
    return mobileFetch(`${API_URL}/api/v1/platform${path}`, {
      ...init,
      headers: {'Content-Type': 'application/json', ...(init.headers || {}), ...(token ? {Authorization: `Bearer ${token}`} : {})},
    });
  };
  let response = await send(accessToken);
  if (response.status === 401 && retry) {
    assertGeneration(generation);
    const currentToken = sessionBlocked ? null : await SecureStore.getItemAsync(ACCESS_KEY);
    accessToken = currentToken && currentToken !== accessToken ? currentToken : await refresh(generation);
    if (accessToken) response = await send(accessToken);
  }
  const payload = await response.json().catch(() => ({}));
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  return payload as T;
}

export async function login(email: string, password: string): Promise<SessionPayload> {
  const generation = sessionGeneration;
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/login`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  if (!payload.mfa_required) await storeSession(payload, generation);
  return payload;
}

export async function completeMfa(token: string, code: string): Promise<SessionPayload> {
  const generation = sessionGeneration;
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/mfa/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, code, client_type: 'mobile'}),
  });
  const payload = await response.json();
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  await storeSession(payload, generation);
  return payload;
}

export async function requestMagicLink(email: string): Promise<void> {
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/magic-link/request`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email}),
  });
  if (!response.ok) throw new Error('Could not request sign-in link');
}

export async function requestPasswordReset(email: string): Promise<void> {
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/password-reset/request`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email}),
  });
  if (!response.ok) throw new Error('Could not request password reset');
}

export async function register(displayName: string, email: string, password: string): Promise<SessionPayload> {
  const generation = sessionGeneration;
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/register`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({display_name: displayName, email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  await storeSession(payload, generation);
  return payload;
}

export async function activateTelegram(tokenOrCode: string, email: string, password: string): Promise<SessionPayload> {
  const generation = sessionGeneration;
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/telegram/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token_or_code: tokenOrCode, email, password, client_type: 'mobile'}),
  });
  const payload = await response.json();
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  await storeSession(payload, generation);
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


export type LogoutResult = {device_credentials_removed: boolean; server_session_revoked: boolean};

export async function logout(): Promise<LogoutResult> {
  // Invalidate in-flight login/refresh responses before waiting for storage or
  // the network. Capture and remove this actor's proof in the same write queue
  // so a later login is never deleted by this logout.
  ++sessionGeneration;
  sessionBlocked = true;
  let refreshToken: string | null = null;
  let deviceRemoved = false;
  await queueSessionWrite(async () => {
    try { refreshToken = await SecureStore.getItemAsync(REFRESH_KEY); } catch {}
    const removals = await Promise.allSettled([
      SecureStore.deleteItemAsync(ACCESS_KEY), SecureStore.deleteItemAsync(REFRESH_KEY),
    ]);
    deviceRemoved = removals.every(result => result.status === 'fulfilled');
  });
  let serverRevoked = false;
  if (refreshToken) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/logout-mobile`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, signal: controller.signal,
        body: JSON.stringify({refresh_token: refreshToken}),
      });
      const payload: unknown = await response.json().catch(() => null);
      serverRevoked = response.ok && !!payload && typeof payload === 'object'
        && (payload as {logged_out?: unknown}).logged_out === true;
    } catch {} finally { clearTimeout(timeout); }
  }
  return {device_credentials_removed: deviceRemoved, server_session_revoked: serverRevoked};
}


export async function updateProfile(input: Record<string, unknown>): Promise<{user: Record<string, unknown>}> {
  return api('/profile', {method: 'PATCH', body: JSON.stringify(input)});
}

export async function mfaStatus(): Promise<{enabled: boolean; unused_recovery_codes: number}> {
  return api('/security/mfa');
}

export async function beginMfaSetup(): Promise<{secret: string; provisioning_uri: string; expires_at: string}> {
  return api('/security/mfa/setup', {method: 'POST', body: '{}'});
}

export async function enableMfa(code: string): Promise<{enabled: boolean; recovery_codes: string[]}> {
  return api('/security/mfa/enable', {method: 'POST', body: JSON.stringify({code})});
}

export async function disableMfa(code: string): Promise<{enabled: boolean}> {
  return api('/security/mfa/disable', {method: 'POST', body: JSON.stringify({code})});
}

export async function completeMagicLogin(token: string): Promise<SessionPayload> {
  const generation = sessionGeneration;
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/magic-link/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, client_type: 'mobile'}),
  });
  const payload = await response.json();
  assertGeneration(generation);
  if (!response.ok) throw responseError(payload, response.status);
  if (!payload.mfa_required) await storeSession(payload, generation);
  return payload;
}

export async function completePasswordReset(token: string, newPassword: string): Promise<void> {
  const response = await mobileFetch(`${API_URL}/api/v1/platform/auth/password-reset/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, new_password: newPassword}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw responseError(payload, response.status);
}

export type BillingProduct = {
  product_id: string;
  tier: string;
  display_name: string;
  duration_days: number;
  currency: string;
  price_ngn: number;
};

export async function getBillingProducts(): Promise<{products: BillingProduct[]}> {
  return api('/billing/products');
}

export async function createBillingCheckout(productId: string): Promise<{authorization_url: string; reference: string}> {
  return api('/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({product_id: productId, currency: 'NGN'}),
  });
}

export async function getBilling(): Promise<{subscriptions: any[]; receipts: any[]}> {
  return api('/billing');
}
