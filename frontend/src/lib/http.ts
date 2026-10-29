// Thin fetch wrapper: base URL, JSON in/out, bearer injection, timeouts and a
// single typed error. App code should use the `api` singleton in `@/lib/api`.

const DEFAULT_TIMEOUT_MS = 30_000

type ApiErrorInit = {
  status: number | null
  isNetworkError?: boolean
  isTimeout?: boolean
  body?: unknown
}

export class ApiError extends Error {
  /** HTTP status, or null when no response arrived (network/CORS/timeout). */
  readonly status: number | null
  /** True when the request never got an HTTP response (offline, DNS, CORS). */
  readonly isNetworkError: boolean
  readonly isTimeout: boolean
  /** Parsed response body, if any. */
  readonly body: unknown

  constructor(message: string, init: ApiErrorInit) {
    super(message)
    this.name = "ApiError"
    this.status = init.status
    this.isNetworkError = init.isNetworkError ?? false
    this.isTimeout = init.isTimeout ?? false
    this.body = init.body
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export type RequestOptions = {
  body?: unknown
  headers?: HeadersInit
  signal?: AbortSignal
  timeoutMs?: number
}

type HttpClientConfig = {
  baseUrl: string
  getAccessToken: () => Promise<string | null>
  onUnauthorized?: () => Promise<void> | void
  timeoutMs?: number
}

export function createHttpClient(config: HttpClientConfig) {
  const defaultTimeout = config.timeoutMs ?? DEFAULT_TIMEOUT_MS

  async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const headers = new Headers(options.headers)
    headers.set("Accept", "application/json")
    if (options.body !== undefined) headers.set("Content-Type", "application/json")
    const token = await config.getAccessToken()
    if (token) headers.set("Authorization", `Bearer ${token}`)

    const timeoutSignal = AbortSignal.timeout(options.timeoutMs ?? defaultTimeout)
    const signal = options.signal ? AbortSignal.any([options.signal, timeoutSignal]) : timeoutSignal

    let response: Response
    try {
      response = await fetch(`${config.baseUrl}${path}`, {
        method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal,
      })
    } catch (error) {
      // Caller-initiated aborts propagate unchanged so effects can ignore them.
      if (options.signal?.aborted) throw error
      if (timeoutSignal.aborted) {
        throw new ApiError(`Request timed out: ${method} ${path}`, { status: null, isTimeout: true })
      }
      // fetch rejects with TypeError for offline, DNS and CORS failures alike.
      throw new ApiError(`Network error: ${method} ${path}`, { status: null, isNetworkError: true })
    }

    if (response.status === 401) await config.onUnauthorized?.()
    const body = await readBody(response)
    if (!response.ok) {
      throw new ApiError(errorMessage(body, response), { status: response.status, body })
    }
    return body as T
  }

  return {
    request,
    get: <T>(path: string, options?: Omit<RequestOptions, "body">) => request<T>("GET", path, options),
    post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("POST", path, { ...options, body }),
    put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("PUT", path, { ...options, body }),
    patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
      request<T>("PATCH", path, { ...options, body }),
    delete: <T>(path: string, options?: RequestOptions) => request<T>("DELETE", path, options),
  }
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined
  const text = await response.text()
  if (!text) return undefined
  if (response.headers.get("Content-Type")?.includes("application/json")) {
    try {
      return JSON.parse(text)
    } catch {
      return text
    }
  }
  return text
}

// FastAPI errors are `{ detail: string }` or, for validation, `{ detail: [{ msg }] }`.
function errorMessage(body: unknown, response: Response): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const { detail } = body
    if (typeof detail === "string") return detail
    if (Array.isArray(detail) && typeof detail[0]?.msg === "string") return detail[0].msg
  }
  if (typeof body === "string" && body) return body
  return `HTTP ${response.status} ${response.statusText}`.trim()
}
