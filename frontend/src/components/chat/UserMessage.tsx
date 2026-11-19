import { Check, Copy, Pencil } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"

export function UserMessage({
  messageId,
  text,
  disabled,
  onEdit,
}: {
  messageId: string
  text: string
  disabled: boolean
  onEdit?: (messageId: string, text: string) => void
}) {
  const [copied, setCopied] = useState(false)

  async function copyPrompt() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1_200)
  }

  return (
    <div className="flex max-w-[78%] flex-col items-end gap-1.5">
      <div className="rounded-3xl bg-[#e5f2ff] px-4 py-3 text-sm leading-6 whitespace-pre-wrap text-[#183b5b]">
        {text}
      </div>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="xs"
          className="h-7 text-[10px] text-muted-foreground"
          onClick={() => void copyPrompt()}
          aria-label="Copy prompt"
        >
          {copied ? <Check /> : <Copy />}
          {copied ? "Copied" : "Copy"}
        </Button>
        {onEdit && (
          <Button
            variant="ghost"
            size="xs"
            className="h-7 text-[10px] text-muted-foreground"
            disabled={disabled}
            onClick={() => onEdit(messageId, text)}
            aria-label="Edit prompt"
          >
            <Pencil /> Edit
          </Button>
        )}
      </div>
    </div>
  )
}
