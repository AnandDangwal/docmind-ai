import { useEffect, useState } from "react"
import { getThreadMessages, requestErrorMessage, type ChatMessage } from "@/lib/api"
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
        if (!cancelled) setError(requestErrorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [threadId])

  if (error) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-sm font-medium text-destructive">This conversation could not be loaded</p>
        <p className="max-w-md text-sm text-muted-foreground">{error}</p>
      </div>
    )
  }
  if (!initialMessages) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }

  return <ThreadChat threadId={threadId} initialMessages={initialMessages} />
}
