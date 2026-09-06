/** The ONLY module that knows about transport: base URL, auth header, error envelope. */

import type { ApiErrorBody } from "@/types/api";

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const apiKey = import.meta.env.VITE_API_KEY ?? "";

export function eventsUrl(path: string): string {
  const base = `${apiBaseUrl}${path}`;
  if (!apiKey) return base;
  const join = base.includes("?") ? "&" : "?";
  return `${base}${join}api_key=${encodeURIComponent(apiKey)}`;
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// Owner sign-in credential (Google ID token). The API key identifies the
// machine; this header identifies the OWNER for owner-class writes
// (settings). Held in memory only — never persisted to storage.
let googleIdToken = "";
export function setGoogleIdToken(token: string): void {
  googleIdToken = token;
}
export function hasGoogleCredential(): boolean {
  return googleIdToken.length > 0;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (apiKey) headers.set("X-API-Key", apiKey);
  if (googleIdToken) headers.set("X-Google-ID-Token", googleIdToken);
  if (init?.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let code = "unknown";
    let message = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as Partial<ApiErrorBody>;
      if (body.error) {
        code = body.error.code;
        message = body.error.message;
      }
    } catch {
      // non-JSON error body — keep statusText defaults
    }
    throw new ApiError(code, message, response.status);
  }
  return (await response.json()) as T;
}
