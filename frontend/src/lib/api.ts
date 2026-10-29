import { env } from "@/lib/env"
import { createHttpClient, isApiError } from "@/lib/http"
import { supabase } from "@/lib/supabase"
import type { ChatUIMessage } from "@/lib/chatTypes"

export { ApiError, isApiError } from "@/lib/http"

// getSession() refreshes an expired access token before returning it.
// Exported so lib/chatTransport.ts can attach the same bearer token to the
// AI SDK's own fetch calls, which bypass this http client entirely.
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export async function expireSession(): Promise<void> {
  await supabase.auth.signOut({ scope: "local" })
}

export const api = createHttpClient({
  baseUrl: env.apiBaseUrl,
  getAccessToken,
  onUnauthorized: expireSession,
})

export type Thread = {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export type ChatMessage = Pick<ChatUIMessage, "id" | "role" | "parts"> & {
  created_at: string
}

export function requestErrorMessage(error: unknown): string {
  if (!isApiError(error)) return "The request failed. Please try again."
  if (error.status === 401) return "Your session expired. Sign in again to continue."
  if (error.isTimeout) return "The service took too long to respond. Please try again."
  if (error.isNetworkError) {
    return "The backend could not be reached. Check that it is running and that CORS is configured."
  }
  return error.message
}

export function createThread(title?: string): Promise<Thread> {
  return api.post<Thread>("/chat/threads", { title: title ?? null })
}

export function listThreads(): Promise<Thread[]> {
  return api.get<Thread[]>("/chat/threads")
}

export function getThreadMessages(threadId: string): Promise<ChatMessage[]> {
  return api.get<ChatMessage[]>(`/chat/threads/${threadId}/messages`)
}
