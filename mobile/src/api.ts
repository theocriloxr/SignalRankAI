import * as SecureStore from 'expo-secure-store';

const API_URL = (process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8080').replace(/\/$/, '');
const ACCESS_KEY = 'signalrank.access_token';
const REFRESH_KEY = 'signalrank.refresh_token';

export type SessionPayload = {
  access_token?: string;
  refresh_token?: string;
  user?: Record<string, unknown>;
  authenticated?: boolean;
  mfa_required?: boolean;
  mfa_token?: string;
  expires_at?: string;
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
  if (!payload.mfa_required) await storeSession(payload);
  return payload;
}

export async function completeMfa(token: string, code: string): Promise<SessionPayload> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/mfa/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, code, client_type: 'mobile'}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'MFA verification failed');
  await storeSession(payload);
  return payload;
}

export async function requestMagicLink(email: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/magic-link/request`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email}),
  });
  if (!response.ok) throw new Error('Could not request sign-in link');
}

export async function requestPasswordReset(email: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/password-reset/request`, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({email}),
  });
  if (!response.ok) throw new Error('Could not request password reset');
}

export async function register(
  displayName: string,
  email: string,
  password: string,
  platformTermsAccepted: boolean,
  privacyAcknowledged: boolean,
  marketingConsent: boolean,
): Promise<SessionPayload> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/register`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      display_name: displayName,
      email,
      password,
      client_type: 'mobile',
      platform_terms_accepted: platformTermsAccepted,
      privacy_acknowledged: privacyAcknowledged,
      marketing_consent: marketingConsent,
    }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Registration failed');
  await storeSession(payload);
  return payload;
}

export function legalUrl(path: string): string {
  const root = API_URL.replace(/\/api(?:\/.*)?$/, '');
  return `${root}${path.startsWith('/') ? path : `/${path}`}`;
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
  const response = await fetch(`${API_URL}/api/v1/platform/auth/magic-link/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, client_type: 'mobile'}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || 'Sign-in link is invalid or expired');
  if (!payload.mfa_required) await storeSession(payload);
  return payload;
}

export async function completePasswordReset(token: string, newPassword: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/v1/platform/auth/password-reset/complete`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({token, new_password: newPassword}),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || 'Password reset failed');
}

export type BillingProduct = {
  product_id: string;
  tier: string;
  display_name: string;
  duration_days: number;
  currency: string;
  price_ngn: number;
  recurring?: boolean;
  renewal_disclosure?: string;
};

export async function getBillingProducts(): Promise<{products: BillingProduct[]}> {
  return api('/billing/products');
}

export async function createBillingCheckout(productId: string, recurringAcknowledged = false): Promise<{authorization_url: string; reference: string; recurring?: boolean}> {
  return api('/billing/checkout', {
    method: 'POST',
    body: JSON.stringify({product_id: productId, currency: 'NGN', recurring_acknowledged: recurringAcknowledged}),
  });
}

export async function getBilling(): Promise<{subscriptions: any[]; receipts: any[]; auto_renew?: boolean; provider_subscription_linked?: boolean}> {
  return api('/billing');
}

export async function cancelAutoRenew(): Promise<{success: boolean; policy?: string; support_ticket_id?: string | null}> {
  return api('/billing/cancel-auto-renew', {
    method: 'POST',
    body: JSON.stringify({confirm: true}),
  });
}

export async function requestRefundReview(paymentReference: string, reason: string): Promise<{ticket_id?: string; message?: string}> {
  return api('/billing/refund-request', {
    method: 'POST',
    body: JSON.stringify({payment_reference: paymentReference, reason}),
  });
}
