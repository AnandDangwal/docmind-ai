export function AssistantThinking() {
  return (
    <div
      className="flex min-h-6 items-center gap-2 pt-0.5 text-xs font-medium text-muted-foreground"
      role="status"
      aria-live="polite"
      aria-label="Assistant is thinking"
    >
      <span>Thinking</span>
      <span className="flex items-center gap-1" aria-hidden="true">
        <span className="size-1.5 animate-bounce rounded-full bg-current motion-reduce:animate-none [animation-delay:-0.3s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-current motion-reduce:animate-none [animation-delay:-0.15s]" />
        <span className="size-1.5 animate-bounce rounded-full bg-current motion-reduce:animate-none" />
      </span>
    </div>
  )
}
