import { Check, Copy, FileText, SearchX, ShieldAlert } from "lucide-react"
import { isTextUIPart } from "ai"
import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

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
  return [
    citation.citationId,
    citation.ticker || citation.companyName,
    citation.filingType,
    `FY${citation.fiscalYear}`,
  ].join(" · ")
}

function citationTitle(citation: CitationData): string {
  const location = [
    citation.page === null ? null : `p. ${citation.page}`,
    citation.sectionPath || citation.section,
  ].filter(Boolean)

  return [
    citation.ticker || citation.companyName,
    citation.filingType,
    filingDateFormatter.format(new Date(`${citation.filingDate}T00:00:00Z`)),
    ...location,
  ].join(" · ")
}

function linkedCitations(markdown: string, sourceCitations: CitationData[]) {
  return markdown.replace(/\[(C[1-9]\d*)]/g, (marker, citationId: string) =>
    sourceCitations.some((citation) => citation.citationId === citationId)
      ? `[${citationId}](#citation-${citationId})`
      : marker,
  )
}

function normalizeMarkdownLineBreaks(markdown: string): string {
  return markdown.replace(/<br\s*\/?>/gi, "\n")
}

export function AssistantMessage({
  message,
  onCitationSelect,
}: {
  message: ChatUIMessage
  onCitationSelect?: (source: CitationData, allSources: CitationData[]) => void
}) {
  const [copied, setCopied] = useState(false)
  const status = answerStatus(message)
  const sourceCitations = citations(message)
  const text = normalizeMarkdownLineBreaks(messageText(message))
  const isInsufficient = status === "insufficient_evidence"
  const isRefused = status === "refused"
  const NoticeIcon = isInsufficient ? SearchX : ShieldAlert

  return (
    <div className="min-w-0 max-w-[90%] space-y-3">
      <div
        className={`text-[15px] leading-6 sm:text-base sm:leading-6 ${
          isInsufficient
            ? "rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2"
            : isRefused
              ? "rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2"
              : "text-foreground"
        }`}
      >
        {(isInsufficient || isRefused) && (
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium">
            <NoticeIcon className="size-3.5" aria-hidden="true" />
            {isInsufficient ? "Not enough filing evidence" : "Request outside supported scope"}
          </div>
        )}
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            p: ({ children }) => <p className="my-4 first:mt-0 last:mb-0">{children}</p>,
            h1: ({ children }) => <h1 className="mt-2 mb-5 text-xl font-semibold tracking-[-0.03em] text-foreground first:mt-0 sm:text-2xl">{children}</h1>,
            h2: ({ children }) => <h2 className="mt-9 mb-3 text-xl font-semibold tracking-[-0.02em] text-foreground first:mt-0 sm:text-2xl">{children}</h2>,
            h3: ({ children }) => <h3 className="mt-7 mb-2 text-lg font-semibold tracking-tight text-foreground first:mt-0 sm:text-xl">{children}</h3>,
            h4: ({ children }) => <h4 className="mt-6 mb-2 font-semibold text-foreground first:mt-0">{children}</h4>,
            ul: ({ children }) => <ul className="my-4 list-disc space-y-2 pl-6 marker:font-bold marker:text-foreground">{children}</ul>,
            ol: ({ children }) => <ol className="my-4 list-decimal space-y-2 pl-6 marker:font-medium marker:text-muted-foreground">{children}</ol>,
            li: ({ children }) => <li className="pl-1">{children}</li>,
            strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
            blockquote: ({ children }) => <blockquote className="my-5 border-l-3 border-foreground/20 bg-muted/35 py-1 pr-4 pl-4 text-muted-foreground">{children}</blockquote>,
            hr: () => <hr className="my-8 border-border" />,
            pre: ({ children }) => <pre className="my-5 overflow-x-auto rounded-xl border border-border bg-muted/50 p-4 text-sm leading-6">{children}</pre>,
            code: ({ className, children }) => className
              ? <code className={`${className} font-mono text-sm`}>{children}</code>
              : <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.875em]">{children}</code>,
            table: ({ children }) => <div className="my-6 overflow-x-auto rounded-xl border border-border"><table className="w-full border-collapse text-sm">{children}</table></div>,
            th: ({ children }) => <th className="border-b border-border bg-muted/70 px-3 py-2 text-left text-xs font-semibold tracking-wide text-foreground">{children}</th>,
            td: ({ children }) => <td className="border-b border-border px-3 py-2 align-top last:border-b-0">{children}</td>,
            a: ({ href, children }) => {
              if (href?.startsWith("#citation-")) {
                const citationId = href.slice("#citation-".length)
                const source = sourceCitations.find((citation) => citation.citationId === citationId)
                return source ? (
                  <button
                    className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded border border-border bg-muted px-1 text-[10px] font-semibold leading-none hover:border-foreground/30 hover:bg-muted/70"
                    onClick={() => onCitationSelect?.(source, sourceCitations)}
                    aria-label={`Open source ${children?.toString() ?? ""}`}
                  >
                    {children}
                  </button>
                ) : <>{children}</>
              }
              return <a className="underline underline-offset-2" href={href} target="_blank" rel="noreferrer">{children}</a>
            },
          }}
        >
          {linkedCitations(text, sourceCitations)}
        </ReactMarkdown>
      </div>

      {sourceCitations.length > 0 && (
        <div aria-label="Sources" className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="mr-0.5 inline-flex items-center gap-1 text-[10px] font-semibold tracking-wide text-muted-foreground uppercase">
            <FileText className="size-3" aria-hidden="true" />
            Sources
          </span>
          {sourceCitations.map((citation) => (
            <button
              key={citation.citationId}
              title={citationTitle(citation)}
              className="max-w-full truncate rounded-full border border-border bg-muted/30 px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-foreground/20 hover:bg-muted hover:text-foreground"
              onClick={() => onCitationSelect?.(citation, sourceCitations)}
            >
              {citationLabel(citation)}
            </button>
          ))}
        </div>
      )}
      {text && (
        <button
          className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={async () => {
            await navigator.clipboard.writeText(text)
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1_200)
          }}
        >
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  )
}
