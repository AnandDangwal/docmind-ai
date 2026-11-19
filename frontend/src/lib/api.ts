import { ApiError, request } from "@/lib/http"
import { getAccessToken, supabase } from "@/lib/supabase"
import type { ChatUIMessage } from "@/lib/chatTypes"
import type { ThreadSummary } from "@/lib/types"

type ThreadWire = {
  id: string
  title?: string | null
  created_at?: string
  updated_at?: string
  createdAt?: string
  updatedAt?: string
}

export { getAccessToken }

export async function expireSession(): Promise<void> {
  await supabase.auth.signOut({ scope: "local" })
}

function mapThread(thread: ThreadWire): ThreadSummary {
  const now = new Date().toISOString()

  return {
    id: thread.id,
    title: thread.title?.trim() || "New research",
    createdAt: thread.createdAt ?? thread.created_at ?? now,
    updatedAt: thread.updatedAt ?? thread.updated_at ?? thread.createdAt ?? thread.created_at ?? now,
  }
}

function unwrapThreads(payload: ThreadWire[] | { threads: ThreadWire[] }): ThreadWire[] {
  return Array.isArray(payload) ? payload : payload.threads
}

export const api = {
  async listThreads(): Promise<ThreadSummary[]> {
    const payload = await request<ThreadWire[] | { threads: ThreadWire[] }>("/chat/threads")
    return unwrapThreads(payload).map(mapThread)
  },

  async createThread(firstPrompt: string): Promise<ThreadSummary> {
    const payload = await request<ThreadWire>("/chat/threads", {
      method: "POST",
      body: JSON.stringify({ title: firstPrompt.trim().slice(0, 80) }),
    })
    return mapThread(payload)
  },

  async getThreadMessages(
    threadId: string,
    options: { signal?: AbortSignal } = {},
  ): Promise<ChatUIMessage[]> {
    const path = `/chat/threads/${encodeURIComponent(threadId)}/messages`
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        return await request<ChatUIMessage[]>(path, {
          signal: options.signal,
          timeoutMs: 30_000,
        })
      } catch (error) {
        if (options.signal?.aborted) throw error
        const retryable =
          error instanceof ApiError && (error.isNetworkError || error.isTimeout)
        if (!retryable || attempt === 1) throw error
      }
    }
    throw new Error("Unable to load conversation messages.")
  },

  async renameThread(threadId: string, title: string): Promise<ThreadSummary> {
    const payload = await request<ThreadWire>(`/chat/threads/${threadId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: title.trim() }),
    })
    return mapThread(payload)
  },

  async deleteThread(threadId: string): Promise<void> {
    await request<void>(`/chat/threads/${threadId}`, { method: "DELETE" })
  },
}
