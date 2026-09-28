import { DefaultChatTransport, type UIMessage } from "ai"
import { env } from "@/lib/env"
import { getAccessToken } from "@/lib/api"

// DefaultChatTransport does its own fetch, bypassing the `api` http client in
// @/lib/api — so the bearer token has to be attached here instead.
export function createChatTransport(threadId: string): DefaultChatTransport<UIMessage> {
  return new DefaultChatTransport({
    api: `${env.apiBaseUrl}/chat/stream`,
    fetch: async (input, init) => {
      const token = await getAccessToken()
      const headers = new Headers(init?.headers)
      if (token) headers.set("Authorization", `Bearer ${token}`)
      return fetch(input, { ...init, headers })
    },
    prepareSendMessagesRequest: ({ messages }) => ({
      body: { threadId, messages },
    }),
  })
}
