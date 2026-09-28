import { useEffect, useState } from "react"
import { getThreadMessages, isApiError, type ChatMessage } from "@/lib/api"
import { ThreadChat } from "@/components/chat/ThreadChat"

// Keyed by threadId from the caller so switching threads remounts this
// component fresh, instead of resetting state synchronously inside an effect.
export function ThreadLoader({ threadId }: { threadId: string }) {
  const [initialMessages, setInitialMessages] = useState<ChatMessage[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getThreadMessages(threadId)
      .then((messages) => {
        if (!cancelled) setInitialMessages(messages)
      })
      .catch((err) => {
        if (!cancelled) setError(isApiError(err) ? err.message : "Request failed")
      })
    return () => {
      cancelled = true
    }
  }, [threadId])

  if (error) return <div className="p-6 text-sm text-destructive">{error}</div>
  if (!initialMessages) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>

  return <ThreadChat threadId={threadId} initialMessages={initialMessages} />
}
