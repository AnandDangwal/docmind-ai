import { useMemo } from "react"
import { useChat } from "@ai-sdk/react"
import type { ChatMessage } from "@/lib/api"
import { createChatTransport } from "@/lib/chatTransport"
import { MessageList } from "@/components/chat/MessageList"
import { MessageInput } from "@/components/chat/MessageInput"

export function ThreadChat({
  threadId,
  initialMessages,
}: {
  threadId: string
  initialMessages: ChatMessage[]
}) {
  const transport = useMemo(() => createChatTransport(threadId), [threadId])
  const { messages, sendMessage, status } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
  })

  const disabled = status === "submitted" || status === "streaming"

  return (
    <div className="flex h-svh flex-col">
      <MessageList messages={messages} />
      <MessageInput disabled={disabled} onSend={(text) => sendMessage({ text })} />
    </div>
  )
}
