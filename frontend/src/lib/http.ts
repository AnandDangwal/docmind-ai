import { env } from "@/lib/env"
import { getAccessToken, supabase } from "@/lib/supabase"
import type { ApiErrorBody } from "@/lib/types"

const REQUEST_TIMEOUT_MS = 20_000

export type RequestOptions = RequestInit & {
  timeoutMs?: number
}

export class ApiError extends Error {
  readonly status: number | null
  readonly isNetworkError: boolean
  readonly isTimeout: boolean

  constructor(
    message: string,
    options: { status?: number; isNetworkError?: boolean; isTimeout?: boolean } = {},
  ) {
    super(message)
    this.name = "ApiError"
    this.status = options.status ?? null
    this.isNetworkError = options.isNetworkError ?? false
    this.isTimeout = options.isTimeout ?? false
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = {}

  try {
    body = (await response.json()) as ApiErrorBody
  } catch {
    // Non-JSON upstream failures still receive a useful HTTP-based message.
  }

  const message = body.detail ?? body.message ?? friendlyStatusMessage(response.status)
  return new ApiError(message, { status: response.status })
}

function friendlyStatusMessage(status: number): string {
  switch (status) {
    case 401:
      return "Your session has expired. Sign in again to continue."
    case 403:
      return "You do not have access to this conversation."
    case 404:
      return "The requested conversation could not be found."
    case 422:
      return "The request could not be processed. Review it and try again."
    case 502:
      return "The research service is temporarily unavailable. Try again shortly."
    default:
      return "Something went wrong while contacting Document Copilot."
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs = REQUEST_TIMEOUT_MS, signal: callerSignal, ...init } = options
  const timeoutSignal = AbortSignal.timeout(timeoutMs)
  const signal = callerSignal
    ? AbortSignal.any([callerSignal, timeoutSignal])
    : timeoutSignal

  try {
    const token = await getAccessToken()
    const headers = new Headers(init.headers)
    headers.set("Accept", "application/json")
    headers.set("Authorization", `Bearer ${token}`)
    if (init.body) headers.set("Content-Type", "application/json")
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      signal,
      headers,
    })

    if (!response.ok) {
      if (response.status === 401) {
        await supabase.auth.signOut({ scope: "local" })
      }
      throw await parseError(response)
    }

    if (response.status === 204) {
      return undefined as T
    }

    return (await response.json()) as T
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }

    if (callerSignal?.aborted) {
      throw error
    }

    if (timeoutSignal.aborted) {
      throw new ApiError("The request timed out. Check your connection and try again.", {
        isNetworkError: true,
        isTimeout: true,
      })
    }

    throw new ApiError("Unable to reach the API. Check the backend URL and CORS configuration.", {
      isNetworkError: true,
    })
  }
}
