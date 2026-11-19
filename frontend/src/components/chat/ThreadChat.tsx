import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useChat } from "@ai-sdk/react"
import { isTextUIPart } from "ai"
import { createChatTransport } from "@/lib/chatTransport"
import type { ChatUIMessage, CitationData } from "@/lib/chatTypes"
import { MessageList } from "@/components/chat/MessageList"
import { MessageInput } from "@/components/chat/MessageInput"

export function ThreadChat({
  threadId,
  initialMessages,
  pendingPrompt,
  onPromptConsumed,
  onCitationSelect,
  onConversationChanged,
}: {
  threadId: string
  initialMessages: ChatUIMessage[]
  pendingPrompt?: string
  onPromptConsumed?: () => void
  onCitationSelect?: (source: CitationData, allSources: CitationData[]) => void
  onConversationChanged?: (threadId: string) => void
}) {
  const transport = useMemo(() => createChatTransport(threadId), [threadId])
  const [draft, setDraft] = useState("")
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null)
  const sentPending = useRef(false)
  const consumedPending = useRef(false)
  const { messages, sendMessage, status, error, clearError, stop } = useChat<ChatUIMessage>({
    id: threadId,
    messages: initialMessages,
    transport,
    onFinish: () => {
      onConversationChanged?.(threadId)
    },
    onError: () => {
      onConversationChanged?.(threadId)
    },
  })

  const disabled = status === "submitted" || status === "streaming"

  const handleSend = useCallback(async (text: string, messageId?: string) => {
    clearError()
    await sendMessage({ text, ...(messageId ? { messageId } : {}) })
  }, [clearError, sendMessage])

  useEffect(() => {
    if (!pendingPrompt || sentPending.current) return
    const promptAlreadySent = messages.some(
      (message) =>
        message.role === "user" &&
        message.parts.filter(isTextUIPart).some((part) => part.text === pendingPrompt),
    )
    if (promptAlreadySent) return
    sentPending.current = true
    void Promise.resolve()
      .then(() => handleSend(pendingPrompt))
      .catch(() => {
        sentPending.current = false
      })
  }, [handleSend, messages, pendingPrompt])

  useEffect(() => {
    if (!pendingPrompt || consumedPending.current) return
    const promptAppeared = messages.some(
      (message) =>
        message.role === "user" &&
        message.parts.filter(isTextUIPart).some((part) => part.text === pendingPrompt),
    )
    if (!promptAppeared) return
    consumedPending.current = true
    onPromptConsumed?.()
  }, [messages, onPromptConsumed, pendingPrompt])

  async function submitDraft(text: string) {
    const messageId = editingMessageId ?? undefined
    setEditingMessageId(null)
    await handleSend(text, messageId)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <MessageList
        messages={messages}
        onCitationSelect={onCitationSelect}
        actionsDisabled={disabled}
        assistantActive={disabled}
        onEditPrompt={(messageId, text) => {
          clearError()
          setEditingMessageId(messageId)
          setDraft(text)
        }}
      />
      {error && (
        <div role="alert" className="mx-6 mb-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
          <p className="text-sm font-medium text-destructive">The assistant could not finish this turn</p>
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        </div>
      )}
      <MessageInput
        disabled={disabled}
        value={draft}
        onValueChange={setDraft}
        onSend={submitDraft}
        onStop={stop}
        editing={editingMessageId !== null}
        onCancelEdit={() => {
          setEditingMessageId(null)
          setDraft("")
        }}
      />
    </div>
  )
}
