import { useMemo, useRef, useState } from "react"
import { useChat } from "@ai-sdk/react"
import type { ChatMessage } from "@/lib/api"
import { createChatTransport } from "@/lib/chatTransport"
import { isPipelineStage, type ChatUIMessage, type PipelineStage } from "@/lib/chatTypes"
import { MessageList } from "@/components/chat/MessageList"
import { MessageInput } from "@/components/chat/MessageInput"
import { ProgressChecklist } from "@/components/chat/ProgressChecklist"

export function ThreadChat({
  threadId,
  initialMessages,
}: {
  threadId: string
  initialMessages: ChatMessage[]
}) {
  const transport = useMemo(() => createChatTransport(threadId), [threadId])
  const [progressStage, setProgressStage] = useState<PipelineStage | null>(null)
  const [progressFailed, setProgressFailed] = useState(false)
  const stageRef = useRef<PipelineStage | null>(null)
  const { messages, sendMessage, status, error, clearError } = useChat<ChatUIMessage>({
    id: threadId,
    messages: initialMessages,
    transport,
    onData: (part) => {
      if (part.type !== "data-status" || !isPipelineStage(part.data.stage)) return
      stageRef.current = part.data.stage
      setProgressStage(part.data.stage)
    },
    onFinish: () => {
      stageRef.current = null
      setProgressStage(null)
      setProgressFailed(false)
    },
    onError: () => {
      if (!stageRef.current) {
        stageRef.current = "searching"
        setProgressStage("searching")
      }
      setProgressFailed(true)
    },
  })

  const disabled = status === "submitted" || status === "streaming"

  function handleSend(text: string) {
    clearError()
    stageRef.current = "searching"
    setProgressStage("searching")
    setProgressFailed(false)
    void sendMessage({ text })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <MessageList messages={messages} />
      {progressStage && (disabled || progressFailed) && (
        <ProgressChecklist currentStage={progressStage} failed={progressFailed} />
      )}
      {error && (
        <div role="alert" className="mx-6 mb-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3">
          <p className="text-sm font-medium text-destructive">The assistant could not finish this turn</p>
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        </div>
      )}
      <MessageInput disabled={disabled} onSend={handleSend} />
    </div>
  )
}
