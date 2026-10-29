import { isTextUIPart } from "ai"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { AssistantMessage } from "@/components/chat/AssistantMessage"
import type { ChatUIMessage } from "@/lib/chatTypes"

function messageText(message: ChatUIMessage): string {
  return message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join("")
}

export function MessageList({ messages }: { messages: ChatUIMessage[] }) {
  return (
    <ScrollArea className="flex-1 px-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4 py-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-md py-16 text-center">
            <h2 className="text-lg font-semibold text-foreground">Ask about the filings</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Compare company disclosures, trace a reported metric, or ask what the available
              filings say about a business topic.
            </p>
          </div>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex items-start gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
          >
            <Avatar size="sm">
              <AvatarFallback>{message.role === "user" ? "You" : "AI"}</AvatarFallback>
            </Avatar>
            {message.role === "assistant" ? (
              <AssistantMessage message={message} />
            ) : (
              <div className="max-w-[75%] rounded-lg bg-primary px-3 py-2 text-sm whitespace-pre-wrap text-primary-foreground">
                {messageText(message)}
              </div>
            )}
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
