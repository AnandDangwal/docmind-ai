import { DefaultChatTransport } from "ai"
import { env } from "@/lib/env"
import { expireSession, getAccessToken } from "@/lib/api"
import type { ChatUIMessage } from "@/lib/chatTypes"

// DefaultChatTransport does its own fetch, bypassing the `api` http client in
// @/lib/api — so the bearer token has to be attached here instead.
export function createChatTransport(threadId: string): DefaultChatTransport<ChatUIMessage> {
  return new DefaultChatTransport({
    api: `${env.apiBaseUrl}/chat/stream`,
    fetch: async (input, init) => {
      const token = await getAccessToken()
      const headers = new Headers(init?.headers)
      if (token) headers.set("Authorization", `Bearer ${token}`)
      try {
        const response = await fetch(input, { ...init, headers })
        if (response.status === 401) await expireSession()
        return response
      } catch (error) {
        if (init?.signal?.aborted) throw error
        if (error instanceof TypeError) {
          throw new Error(
            "The backend could not be reached. Check that it is running and that CORS is configured.",
            { cause: error },
          )
        }
        throw error
      }
    },
    prepareSendMessagesRequest: ({ messages }) => ({
      body: { threadId, messages },
    }),
  })
}
