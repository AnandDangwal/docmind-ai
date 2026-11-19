import type { ChatUIMessage } from "@/lib/chatTypes"
import { api } from "@/lib/api"

const messageCache = new Map<string, ChatUIMessage[]>()
type InFlightRequest = {
  promise: Promise<ChatUIMessage[]>
  signal?: AbortSignal
}

const inFlightRequests = new Map<string, InFlightRequest>()

export function cachedThreadMessages(threadId: string): ChatUIMessage[] | undefined {
  return messageCache.get(threadId)
}

export function setCachedThreadMessages(
  threadId: string,
  messages: ChatUIMessage[],
): void {
  messageCache.set(threadId, messages)
}

export function loadThreadMessages(
  threadId: string,
  options: { force?: boolean; signal?: AbortSignal } = {},
): Promise<ChatUIMessage[]> {
  if (!options.force) {
    const cached = messageCache.get(threadId)
    if (cached) return Promise.resolve(cached)
  }

  const existing = inFlightRequests.get(threadId)
  if (existing && !existing.signal?.aborted) return existing.promise
  if (existing) inFlightRequests.delete(threadId)

  const request = api
    .getThreadMessages(threadId, { signal: options.signal })
    .then((messages) => {
      messageCache.set(threadId, messages)
      return messages
    })
    .finally(() => {
      if (inFlightRequests.get(threadId)?.promise === request) {
        inFlightRequests.delete(threadId)
      }
    })

  inFlightRequests.set(threadId, { promise: request, signal: options.signal })
  return request
}
