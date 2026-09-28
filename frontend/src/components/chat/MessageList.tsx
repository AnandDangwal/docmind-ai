import type { UIMessage } from "ai"
import { isTextUIPart } from "ai"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"

function messageText(message: UIMessage): string {
  return message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join("")
}

export function MessageList({ messages }: { messages: UIMessage[] }) {
  return (
    <ScrollArea className="flex-1 px-6">
      <div className="mx-auto flex max-w-2xl flex-col gap-4 py-6">
        {messages.length === 0 && (
          <p className="text-center text-sm text-muted-foreground">
            Ask a question to start the conversation.
          </p>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex items-start gap-3 ${message.role === "user" ? "flex-row-reverse" : ""}`}
          >
            <Avatar size="sm">
              <AvatarFallback>{message.role === "user" ? "You" : "AI"}</AvatarFallback>
            </Avatar>
            <div
              className={`max-w-[75%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              }`}
            >
              {messageText(message)}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  )
}
