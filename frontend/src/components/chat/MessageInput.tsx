import { ArrowUp, Square } from "lucide-react"
import { type FormEvent, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

export function MessageInput({
  disabled,
  onSend,
  onStop,
  autoFocus = false,
  value,
  onValueChange,
  editing = false,
  onCancelEdit,
}: {
  disabled: boolean
  onSend: (text: string) => void | Promise<void>
  onStop?: () => void
  autoFocus?: boolean
  value: string
  onValueChange: (value: string) => void
  editing?: boolean
  onCancelEdit?: () => void
}) {
  function submit() {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    void onSend(trimmed)
    onValueChange("")
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    submit()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-3xl px-3 pb-3 sm:px-6">
      {editing && (
        <div className="mb-2 flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs">
          <span>
            <strong className="font-semibold">Editing prompt.</strong>{" "}
            Saving replaces this turn and removes all later replies.
          </span>
          <Button type="button" variant="ghost" size="xs" onClick={onCancelEdit}>
            Cancel
          </Button>
        </div>
      )}
      <div className="flex items-end gap-2 rounded-xl border border-border bg-background p-2.5 pl-3.5 shadow-[0_7px_25px_rgba(0,0,0,0.06)] focus-within:border-foreground/30 focus-within:ring-3 focus-within:ring-ring/15">
        <Textarea
        id="research-prompt"
        name="research-prompt"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about a filing, policy, or disclosure…"
        className="max-h-40 min-h-8 flex-1 resize-none border-0 bg-transparent p-1 shadow-none focus-visible:ring-0"
        disabled={disabled}
        autoFocus={autoFocus}
      />
        {disabled && onStop ? (
          <Button
            type="button"
            size="icon"
            className="size-10 rounded-full bg-[#3b82f6] text-white shadow-sm hover:bg-[#2f72e5] focus-visible:border-[#3b82f6] focus-visible:ring-[#3b82f6]/30"
            onClick={onStop}
            aria-label="Stop generating"
          >
            <Square className="size-3 fill-white text-white" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            className="size-10 rounded-full bg-[#3b82f6] text-white shadow-sm hover:bg-[#2f72e5] focus-visible:border-[#3b82f6] focus-visible:ring-[#3b82f6]/30 disabled:bg-[#3b82f6] disabled:text-white"
            disabled={disabled || !value.trim()}
            aria-label={editing ? "Save and regenerate" : "Send message"}
            title={editing ? "Save and regenerate" : "Send message"}
          >
            <ArrowUp className="size-5" strokeWidth={2} />
          </Button>
        )}
      </div>
      <p className="mt-1.5 text-center text-[9px] text-muted-foreground">Document Copilot can make mistakes. Verify important details in the cited filing.</p>
    </form>
  )
}
