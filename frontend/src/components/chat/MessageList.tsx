import { isTextUIPart } from "ai"
import { useEffect, useRef, type UIEvent } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AssistantMessage } from "@/components/chat/AssistantMessage"
import { AssistantThinking } from "@/components/chat/AssistantThinking"
import { UserMessage } from "@/components/chat/UserMessage"
import type { ChatUIMessage, CitationData } from "@/lib/chatTypes"

function messageText(message: ChatUIMessage): string {
  return message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join("")
}

export function MessageList({
  messages,
  onCitationSelect,
  onEditPrompt,
  actionsDisabled = false,
  assistantActive = false,
}: {
  messages: ChatUIMessage[]
  onCitationSelect?: (source: CitationData, allSources: CitationData[]) => void
  onEditPrompt?: (messageId: string, text: string) => void
  actionsDisabled?: boolean
  assistantActive?: boolean
}) {
  const lastMessage = messages.at(-1)
  const needsThinkingRow = assistantActive && lastMessage?.role !== "assistant"
  const viewportRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const followingRef = useRef(true)
  const wasAssistantActiveRef = useRef(false)

  useEffect(() => {
    const assistantStarted = assistantActive && !wasAssistantActiveRef.current
    wasAssistantActiveRef.current = assistantActive
    if (!assistantStarted && !followingRef.current) return

    bottomRef.current?.scrollIntoView({ block: "end" })
    followingRef.current = true
  }, [assistantActive, messages])

  function handleScroll(event: UIEvent<HTMLDivElement>) {
    const viewport = event.currentTarget
    const distanceFromBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight
    followingRef.current = distanceFromBottom < 80
  }

  return (
    <ScrollArea
      className="min-h-0 flex-1 px-3 sm:px-6"
      viewportRef={viewportRef}
      onViewportScroll={handleScroll}
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-8 py-8">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md py-16 text-center">
            <h2 className="text-lg font-semibold text-foreground">Ask about the filings</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Compare company disclosures, trace a reported metric, or ask what the available
              filings say about a business topic.
            </p>
          </div>
        )}
        {messages.map((message, index) => (
          <div
            key={message.id}
            className={`flex items-start ${message.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {message.role === "assistant" ? (
              assistantActive && index === messages.length - 1 && !messageText(message).trim() ? (
                <AssistantThinking />
              ) : (
                <AssistantMessage message={message} onCitationSelect={onCitationSelect} />
              )
            ) : (
              <UserMessage
                messageId={message.id}
                text={messageText(message)}
                disabled={actionsDisabled}
                onEdit={onEditPrompt}
              />
            )}
          </div>
        ))}
        {needsThinkingRow && (
          <div className="flex items-start">
            <AssistantThinking />
          </div>
        )}
        <div ref={bottomRef} aria-hidden="true" />
      </div>
    </ScrollArea>
  )
}
