const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

if (typeof window !== "undefined" && !process.env.NEXT_PUBLIC_API_URL) {
  console.warn("[api] NEXT_PUBLIC_API_URL is not set — falling back to http://localhost:8000/api. Set this env var in production.");
}

// ─── Token helpers (access only — refresh lives in httpOnly cookie) ──────────
// Access token is stored in memory + localStorage for persistence across tabs.
// It is also set as httpOnly cookie by the backend, but we keep localStorage
// for the Authorization header so API calls work cross-origin.

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access");
}

export function getRefreshToken() {
  // Refresh token is now in httpOnly cookie — not accessible from JS.
  // This function exists for backwards compatibility but always returns null.
  return null;
}

export function setTokens(access: string, _refresh?: string) {
  localStorage.setItem("access", access);
  // refresh token is set by backend via httpOnly cookie, not stored in localStorage
}

export function clearTokens() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh"); // cleanup legacy
  localStorage.removeItem("is_superuser");
}

/** Decode JWT payload (no verification — for reading claims in frontend). */
export function decodeTokenPayload(token: string | null): Record<string, any> | null {
  if (!token) return null;
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/** Returns true if the current user is a superadmin. */
export function isSuperAdmin(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem("is_superuser") === "true";
}

/** Mark current session as superadmin (called after login verifies is_superuser). */
export function setSuperAdmin(value: boolean) {
  if (typeof window === "undefined") return;
  if (value) {
    localStorage.setItem("is_superuser", "true");
  } else {
    localStorage.removeItem("is_superuser");
  }
}

export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function safeParseJson(res: Response) {
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

// ─── Token Refresh Logic ──────────────────────────────────────────────────────
let refreshPromise: Promise<string | null> | null = null;

async function doRefresh(): Promise<string | null> {
  try {
    // Refresh token is sent automatically via httpOnly cookie
    const res = await fetch(`${API_URL}/auth/token/refresh/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({}),
    });

    if (!res.ok) return null;

    const data = await res.json();
    if (!data.access) return null;

    setTokens(data.access);
    return data.access;
  } catch {
    return null;
  }
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

/**
 * Detecta si el JWT está vencido localmente (sin pegar al server).
 *
 * Política CONSERVADORA: solo retorna `true` cuando tenemos CERTEZA de
 * que el token está vencido (tiene `exp` decodificable y está en el
 * pasado). Si no se puede decodificar o no tiene `exp`, retorna `false`
 * (asumimos válido y dejamos que el server decida).
 *
 * Esto evita falsos positivos con tokens dummy en tests, y preserva
 * el comportamiento original de "intentar la request" cuando el token
 * tiene forma rara.
 */
export function isTokenExpired(token: string | null = getAccessToken()): boolean {
  if (!token) return true;  // sin token = sin sesión = "vencido"
  const payload = decodeTokenPayload(token);
  if (!payload?.exp || typeof payload.exp !== "number") {
    // Token no decodificable o sin exp → no podemos decir nada con
    // certeza. Asumimos válido — el server lo va a validar.
    return false;
  }
  // exp está en segundos desde epoch; Date.now() en milisegundos.
  return payload.exp * 1000 < Date.now();
}

let isRedirecting = false;

function redirectToLogin(reason: "session_expired" | "no_session" = "session_expired") {
  // Idempotente: si ya estamos navegando al login, no disparar otra
  // redirección (ocurre cuando varias requests fallan en paralelo).
  if (isRedirecting) return;
  isRedirecting = true;

  // Si la sesión expiró estando en el panel superadmin, debemos volver al
  // login de superadmin, NO al login de tenants. clearTokens() borra la
  // marca is_superuser, así que la chequeamos ANTES de limpiar.
  const isSuper = typeof window !== "undefined"
    && localStorage.getItem("is_superuser") === "true";
  clearTokens();
  if (typeof window !== "undefined") {
    // window.location.replace() es atómico — interrumpe el JS actual y
    // navega. Usamos replace en vez de href para que el botón "atrás"
    // del navegador no devuelva al estado roto.
    const base = isSuper ? "/superadmin/login" : "/login";
    window.location.replace(`${base}?reason=${reason}`);
  }
}

function redirectToExpired() {
  if (typeof window !== "undefined" && !window.location.pathname.includes("/settings")) {
    window.location.href = "/dashboard/settings?tab=plan&expired=1";
  }
}

// ─── Main Fetch ───────────────────────────────────────────────────────────────

const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * Fetch con timeout configurable. Si la respuesta no llega en `timeoutMs`,
 * se aborta el request y throws AbortError.
 *
 * Usado por `apiFetch` internamente, y exportado para flujos públicos
 * (checkout, login, register) que NO usan apiFetch porque no requieren
 * el JWT — pero igual necesitan timeout para no colgar la UI si la API
 * se cuelga.
 */
export function fetchWithTimeout(url: string, init: RequestInit, timeoutMs: number = DEFAULT_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...init, signal: controller.signal }).finally(() => clearTimeout(timer));
}

export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const token = getAccessToken();

  // Pre-check: si el access token está vencido localmente, intentamos
  // refresh ANTES de pegar al server. Evita el caso "request muere por
  // timeout antes de descubrir que la sesión ya no existe".
  // Solo aplica si endpoint NO es de auth (sino loop).
  const skipExpiredCheck = endpoint.startsWith("/auth/");
  if (!skipExpiredCheck && token && isTokenExpired(token) && typeof window !== "undefined") {
    const refreshed = await refreshAccessToken();
    if (!refreshed) {
      // Refresh falló — sesión muerta. Redirect SILENCIOSO sin error visible.
      redirectToLogin("session_expired");
      throw new ApiError(401, "Sesión expirada", { silentRedirect: true });
    }
  }

  const finalToken = getAccessToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(finalToken ? { Authorization: `Bearer ${finalToken}` } : {}),
    ...(options.headers || {}),
  };

  let res: Response;
  try {
    res = await fetchWithTimeout(`${API_URL}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      // Timeout: si nuestra sesión está muerta, mejor redirect que mostrar
      // error genérico (era el caso de Mario el 14/05/26).
      if (typeof window !== "undefined" && isTokenExpired(getAccessToken())) {
        redirectToLogin("session_expired");
        throw new ApiError(401, "Sesión expirada", { silentRedirect: true });
      }
      throw new ApiError(0, "El servidor tardó demasiado en responder. Intenta de nuevo.");
    }
    throw new ApiError(0, "No se pudo conectar al servidor. Verifica tu conexión.");
  }

  // ── 401: try refresh before giving up ──────────────────────────────────
  if (res.status === 401 && typeof window !== "undefined") {
    const newToken = await refreshAccessToken();

    if (!newToken) {
      redirectToLogin("session_expired");
      throw new ApiError(401, "Sesión expirada", { silentRedirect: true });
    }

    const retryHeaders: HeadersInit = {
      ...headers,
      Authorization: `Bearer ${newToken}`,
    };

    let retryRes: Response;
    try {
      retryRes = await fetchWithTimeout(`${API_URL}${endpoint}`, {
        ...options,
        headers: retryHeaders,
        credentials: "include",
      });
    } catch (err: any) {
      if (err?.name === "AbortError") {
        throw new ApiError(0, "El servidor tardó demasiado en responder. Intenta de nuevo.");
      }
      throw new ApiError(0, "No se pudo conectar al servidor. Verifica tu conexión.");
    }

    if (retryRes.status === 401) {
      redirectToLogin("session_expired");
      throw new ApiError(401, "Sesión expirada", { silentRedirect: true });
    }

    const retryData = await safeParseJson(retryRes);

    if (!retryRes.ok) {
      const message =
        retryData && (retryData.detail || retryData.message)
          ? String(retryData.detail || retryData.message)
          : `API error ${retryRes.status}`;
      throw new ApiError(retryRes.status, message, retryData);
    }

    return retryData ?? null;
  }

  // ── 402: suscripción expirada → redirigir a settings ─────────────────
  if (res.status === 402 && typeof window !== "undefined") {
    redirectToExpired();
    throw new ApiError(402, "Tu suscripción ha expirado. Actualiza tu plan para continuar.");
  }

  // ── Normal flow ────────────────────────────────────────────────────────
  const data = await safeParseJson(res);

  if (!res.ok) {
    const message =
      data && (data.detail || data.message)
        ? String(data.detail || data.message)
        : `API error ${res.status}`;
    throw new ApiError(res.status, message, data);
  }

  return data ?? null;
}

export async function apiUpload(endpoint: string, formData: FormData) {
  const token = getAccessToken();
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

  let res: Response;
  try {
    res = await fetch(`${API_URL}${endpoint}`, {
      method: "POST",
      headers,
      body: formData,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "No se pudo conectar al servidor. Verifica tu conexión.");
  }

  if (res.status === 401 && typeof window !== "undefined") {
    const newToken = await refreshAccessToken();
    if (!newToken) { redirectToLogin(); throw new ApiError(401, "Sesión expirada"); }

    let retryRes: Response;
    try {
      retryRes = await fetch(`${API_URL}${endpoint}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${newToken}` },
        body: formData,
        credentials: "include",
      });
    } catch {
      throw new ApiError(0, "No se pudo conectar al servidor. Verifica tu conexión.");
    }

    if (retryRes.status === 401) { redirectToLogin(); throw new ApiError(401, "Sesión expirada"); }

    const ct = retryRes.headers.get("content-type") || "";
    const retryData = ct.includes("application/json") ? await retryRes.json() : await retryRes.text();
    if (!retryRes.ok) {
      const msg = typeof retryData === "object" && retryData && (retryData.detail || retryData.message)
        ? String(retryData.detail || retryData.message) : `API error ${retryRes.status}`;
      throw new ApiError(retryRes.status, msg, retryData);
    }
    return retryData;
  }

  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof data === "object" && data && (data.detail || data.message)
      ? String(data.detail || data.message) : `API error ${res.status}`;
    throw new ApiError(res.status, msg, data);
  }
  return data;
}
