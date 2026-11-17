import type { ApiErrorBody } from './types';

export class ApiError extends Error {
  readonly code: string;
  readonly detail: unknown;

  constructor(code: string, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.detail = detail;
  }
}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? '/api';

type FetchParams = Record<string, string | number | boolean | undefined | null>;

interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  params?: FetchParams;
  body?: BodyInit | object | null;
}

export async function apiFetch<T>(path: string, opts: ApiFetchOptions = {}): Promise<T> {
  const { params, body, headers: extraHeaders, ...rest } = opts;

  let url = `${BASE}${path}`;

  if (params) {
    const search = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null) search.set(k, String(v));
    }
    const qs = search.toString();
    if (qs) url += `?${qs}`;
  }

  const isFormData = body instanceof FormData;
  const resolvedBody: BodyInit | null | undefined = isFormData
    ? body
    : body !== undefined && body !== null
    ? JSON.stringify(body)
    : undefined;

  const headers: HeadersInit = isFormData
    ? { ...(extraHeaders as Record<string, string>) }
    : { 'Content-Type': 'application/json', ...(extraHeaders as Record<string, string>) };

  const res = await fetch(url, { headers, body: resolvedBody, ...rest });

  if (!res.ok) {
    let errBody: { error: ApiErrorBody };
    try {
      errBody = await res.json();
      throw new ApiError(
        errBody.error.code,
        errBody.error.message,
        errBody.error.detail,
      );
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError('network_error', `HTTP ${res.status}`);
    }
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
