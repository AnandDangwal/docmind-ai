import { FileText, SearchX, ShieldAlert } from "lucide-react"
import { isTextUIPart } from "ai"
import type { AnswerStatus, ChatUIMessage, CitationData } from "@/lib/chatTypes"

const filingDateFormatter = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "numeric",
  timeZone: "UTC",
})

function messageText(message: ChatUIMessage): string {
  return message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join("")
}

function answerStatus(message: ChatUIMessage): AnswerStatus {
  const part = message.parts.find((candidate) => candidate.type === "data-answer-status")
  return part?.data.status ?? "answered"
}

function citations(message: ChatUIMessage): CitationData[] {
  return message.parts
    .filter((part) => part.type === "data-citation")
    .map((part) => part.data)
}

function citationLabel(citation: CitationData): string {
  const location = [
    citation.page === null ? null : `p. ${citation.page}`,
    citation.section,
  ].filter(Boolean)

  return [
    citation.citationId,
    citation.ticker || citation.companyName,
    citation.filingType,
    filingDateFormatter.format(new Date(`${citation.filingDate}T00:00:00Z`)),
    ...location,
  ].join(" · ")
}

export function AssistantMessage({ message }: { message: ChatUIMessage }) {
  const status = answerStatus(message)
  const sourceCitations = citations(message)
  const isInsufficient = status === "insufficient_evidence"
  const isRefused = status === "refused"
  const NoticeIcon = isInsufficient ? SearchX : ShieldAlert

  return (
    <div className="max-w-[85%] space-y-2">
      <div
        className={`rounded-lg border px-3 py-2 text-sm whitespace-pre-wrap ${
          isInsufficient
            ? "border-amber-500/30 bg-amber-500/10"
            : isRefused
              ? "border-sky-500/30 bg-sky-500/10"
              : "border-transparent bg-muted text-foreground"
        }`}
      >
        {(isInsufficient || isRefused) && (
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium">
            <NoticeIcon className="size-3.5" aria-hidden="true" />
            {isInsufficient ? "Not enough filing evidence" : "Request outside supported scope"}
          </div>
        )}
        {messageText(message)}
      </div>

      {sourceCitations.length > 0 && (
        <div aria-label="Sources" className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <FileText className="size-3.5" aria-hidden="true" />
            Sources
          </div>
          <div className="flex flex-wrap gap-1.5">
            {sourceCitations.map((citation) => (
              <span
                key={citation.citationId}
                title={citation.companyName}
                className="rounded-full border border-border bg-background px-2.5 py-1 text-xs text-muted-foreground"
              >
                {citationLabel(citation)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
