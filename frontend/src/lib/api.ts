import type { UIMessage } from "ai"
import { env } from "@/lib/env"
import { createHttpClient } from "@/lib/http"
import { supabase } from "@/lib/supabase"

export { ApiError, isApiError } from "@/lib/http"

// getSession() refreshes an expired access token before returning it.
// Exported so lib/chatTransport.ts can attach the same bearer token to the
// AI SDK's own fetch calls, which bypass this http client entirely.
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession()
  return data.session?.access_token ?? null
}

export const api = createHttpClient({
  baseUrl: env.apiBaseUrl,
  getAccessToken,
})

export type Thread = {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export type ChatMessage = Pick<UIMessage, "id" | "role" | "parts"> & {
  created_at: string
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
