import { ArrowUpRight, BookOpen, FileText, PanelRightClose, PanelRightOpen, X } from "lucide-react"
import { Dialog } from "radix-ui"
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/ui/button"
import type { CitationData } from "@/lib/chatTypes"
import { useMediaQuery } from "@/lib/useMediaQuery"

const DEFAULT_SOURCE_WIDTH = 440
const MIN_SOURCE_WIDTH = 300
const MAX_SOURCE_WIDTH = 640
const MIN_CHAT_WIDTH = 480
const SOURCE_WIDTH_KEY = "document-copilot.source-width"
const SOURCE_COLLAPSED_KEY = "document-copilot:source-collapsed"
const COLLAPSED_SOURCE_WIDTH = 68

type SourceInspectorProps = {
  source: CitationData | null
  sources: CitationData[]
  onSelect: (source: CitationData) => void
  onClose: () => void
  leftSidebarWidth: number
}

function SourceExcerpt({ excerpt }: { excerpt: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = excerpt.length > 1_600

  return (
    <section className="mt-6 rounded-xl border border-border bg-background p-4" aria-label="Cited passage">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-foreground">
        <BookOpen className="size-4 text-muted-foreground" aria-hidden="true" />
        Cited passage
      </div>
      <div className="relative">
        <div
          className={`min-w-0 overflow-x-auto text-xs leading-6 text-muted-foreground [&_td:first-child]:sticky [&_td:first-child]:left-0 [&_td:first-child]:z-10 [&_td:first-child]:max-w-52 [&_td:first-child]:whitespace-normal [&_td:first-child]:bg-background [&_th:first-child]:sticky [&_th:first-child]:left-0 [&_th:first-child]:z-10 ${isLong && !expanded ? "max-h-[26rem] overflow-y-hidden" : ""}`}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-3 whitespace-pre-wrap last:mb-0">{children}</p>,
              h1: ({ children }) => <h4 className="mt-4 mb-2 text-sm font-semibold text-foreground first:mt-0">{children}</h4>,
              h2: ({ children }) => <h4 className="mt-4 mb-2 text-sm font-semibold text-foreground first:mt-0">{children}</h4>,
              h3: ({ children }) => <h4 className="mt-4 mb-2 text-xs font-semibold text-foreground first:mt-0">{children}</h4>,
              ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
              ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
              table: ({ children }) => <table className="mb-4 w-max min-w-full border-collapse text-[11px] last:mb-0">{children}</table>,
              th: ({ children }) => <th className="whitespace-nowrap border border-border bg-muted px-2 py-1.5 text-left font-semibold text-foreground">{children}</th>,
              td: ({ children }) => <td className="whitespace-nowrap border border-border px-2 py-1.5 align-top">{children}</td>,
              blockquote: ({ children }) => <blockquote className="border-l-2 border-foreground/20 pl-3">{children}</blockquote>,
              code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[11px] text-foreground">{children}</code>,
            }}
          >
            {excerpt.trim()}
          </ReactMarkdown>
        </div>
        {isLong && !expanded && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-background to-transparent" />
        )}
      </div>
      {isLong && (
        <button
          className="mt-3 text-xs font-medium text-foreground underline-offset-4 hover:underline"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? "Show less" : "Show full passage"}
        </button>
      )}
    </section>
  )
}

function SourceContent({
  source,
  sources,
  onSelect,
  onClose,
  onCollapse,
}: SourceInspectorProps & { onCollapse?: () => void }) {
  if (!source) return null
  const location = [source.filingType, source.filingDate, source.page === null ? null : `Page ${source.page}`, source.sectionPath || source.section].filter(Boolean)
  const filingUrl = source.sourceAnchor
    ? `${source.sourceUrl}#${encodeURIComponent(source.sourceAnchor)}`
    : source.sourceUrl

  return (
    <>
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-4">
        <div>
          <p className="text-[10px] font-semibold tracking-[0.1em] text-muted-foreground uppercase">{source.citationId}</p>
          <h2 className="text-sm font-semibold">Evidence</h2>
        </div>
        <div className="flex items-center gap-1">
          {onCollapse && (
            <Button variant="ghost" size="icon-sm" onClick={onCollapse} aria-label="Collapse source inspector" title="Collapse source inspector"><PanelRightClose /></Button>
          )}
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close source inspector" title="Close source inspector"><X /></Button>
        </div>
      </header>
      <div className="min-h-0 overflow-y-auto p-5">
        <span className="grid size-9 place-items-center rounded-lg border border-border bg-background"><FileText className="size-4" /></span>
        <h3 className="mt-3 text-sm font-semibold leading-5">{source.companyName || source.ticker}</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {location.map((item) => <span className="rounded-md bg-muted px-1.5 py-1 text-[10px] text-muted-foreground" key={item}>{item}</span>)}
        </div>
        <SourceExcerpt key={source.citationId} excerpt={source.excerpt} />
        {source.sourceUrl && (
          <Button asChild variant="outline" className="mt-5 w-full">
            <a href={filingUrl} target="_blank" rel="noreferrer">Open filing <ArrowUpRight /></a>
          </Button>
        )}
        {sources.length > 1 && (
          <section className="mt-7 border-t border-border pt-5">
            <h4 className="mb-2 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">Sources in this answer</h4>
            <div className="grid gap-1">
              {sources.map((item) => (
                <button
                  className={`grid min-h-10 grid-cols-[1.5rem_1fr] items-center gap-2 rounded-lg px-2 text-left text-xs hover:bg-muted ${item.citationId === source.citationId ? "bg-muted" : ""}`}
                  key={item.citationId}
                  onClick={() => onSelect(item)}
                >
                  <span className="grid size-5 place-items-center rounded border border-border bg-background text-[9px] font-semibold">{item.citationId.replace(/\D/g, "") || "•"}</span>
                  <span className="truncate">{item.companyName || item.ticker} · {item.filingType}</span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  )
}

function CollapsedSourceRail({
  source,
  onExpand,
  onClose,
}: {
  source: CitationData
  onExpand: () => void
  onClose: () => void
}) {
  return (
    <aside
      className="flex h-full shrink-0 flex-col items-center border-l border-border bg-muted/20 py-3"
      style={{ width: COLLAPSED_SOURCE_WIDTH }}
      aria-label="Collapsed source inspector"
    >
      <Button variant="ghost" size="icon-sm" onClick={onExpand} aria-label="Expand source inspector" title="Expand source inspector"><PanelRightOpen /></Button>
      <div className="mt-5 grid justify-items-center gap-2 text-center">
        <span className="grid size-9 place-items-center rounded-lg border border-border bg-background"><FileText className="size-4" /></span>
        <span className="text-[10px] font-semibold tracking-wide text-muted-foreground">{source.citationId}</span>
      </div>
      <Button className="mt-auto" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close source inspector" title="Close source inspector"><X /></Button>
    </aside>
  )
}

export function SourceInspector(props: SourceInspectorProps) {
  const { leftSidebarWidth, onClose, source } = props
  const isDesktopViewport = useMediaQuery("(min-width: 1024px)")
  const [viewportWidth, setViewportWidth] = useState(() => window.innerWidth)
  const [width, setWidth] = useState(() => {
    const stored = window.localStorage.getItem(SOURCE_WIDTH_KEY)
    if (stored === null) return DEFAULT_SOURCE_WIDTH
    const parsed = Number(stored)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SOURCE_WIDTH
  })
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem(SOURCE_COLLAPSED_KEY) === "true",
  )
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null)

  useEffect(() => {
    const update = () => setViewportWidth(window.innerWidth)
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [])

  const desktopInspector =
    isDesktopViewport &&
    viewportWidth - leftSidebarWidth >= MIN_CHAT_WIDTH + MIN_SOURCE_WIDTH

  useEffect(() => {
    if (!source || !desktopInspector) return
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", closeOnEscape)
    return () => window.removeEventListener("keydown", closeOnEscape)
  }, [desktopInspector, onClose, source])

  const maxWidth = Math.max(
    MIN_SOURCE_WIDTH,
    Math.min(
      MAX_SOURCE_WIDTH,
      viewportWidth * 0.45,
      viewportWidth - props.leftSidebarWidth - MIN_CHAT_WIDTH,
    ),
  )
  const panelWidth = Math.min(Math.max(width, MIN_SOURCE_WIDTH), maxWidth)

  function resize(nextWidth: number) {
    setWidth(Math.min(Math.max(nextWidth, MIN_SOURCE_WIDTH), maxWidth))
  }

  function changeCollapsed(nextCollapsed: boolean) {
    setCollapsed(nextCollapsed)
    window.localStorage.setItem(SOURCE_COLLAPSED_KEY, String(nextCollapsed))
  }

  function finishResize() {
    window.localStorage.setItem(SOURCE_WIDTH_KEY, String(panelWidth))
    drag.current = null
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: panelWidth,
    }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return
    resize(drag.current.startWidth + drag.current.startX - event.clientX)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next =
      event.key === "ArrowLeft"
        ? panelWidth + 24
        : event.key === "ArrowRight"
          ? panelWidth - 24
          : event.key === "Home"
            ? MIN_SOURCE_WIDTH
            : event.key === "End"
              ? maxWidth
              : null
    if (next === null) return
    event.preventDefault()
    const clamped = Math.min(Math.max(next, MIN_SOURCE_WIDTH), maxWidth)
    resize(clamped)
    window.localStorage.setItem(SOURCE_WIDTH_KEY, String(clamped))
  }

  if (!source) return null

  if (desktopInspector) {
    if (collapsed) {
      return (
        <CollapsedSourceRail
          source={source}
          onExpand={() => changeCollapsed(false)}
          onClose={onClose}
        />
      )
    }

    return (
      <aside
        className="relative flex h-full shrink-0 flex-col border-l border-border bg-muted/20"
        style={{ width: panelWidth }}
        aria-label="Source inspector"
      >
        <div
          className="group absolute inset-y-0 -left-1 z-20 w-2 cursor-col-resize touch-none outline-none"
          role="separator"
          aria-label="Resize source inspector"
          aria-orientation="vertical"
          aria-valuemin={MIN_SOURCE_WIDTH}
          aria-valuemax={Math.round(maxWidth)}
          aria-valuenow={Math.round(panelWidth)}
          tabIndex={0}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={(event) => {
            if (drag.current?.pointerId === event.pointerId) finishResize()
          }}
          onPointerCancel={finishResize}
          onKeyDown={handleKeyDown}
        >
          <span className="absolute inset-y-0 left-1/2 w-px bg-transparent transition-colors group-hover:bg-foreground/30 group-focus-visible:bg-foreground/50" />
        </div>
        <SourceContent {...props} onCollapse={() => changeCollapsed(true)} />
      </aside>
    )
  }

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) props.onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 flex max-h-[78svh] flex-col rounded-t-2xl bg-background pb-[env(safe-area-inset-bottom)] shadow-2xl outline-none">
          <Dialog.Title className="sr-only">Source evidence</Dialog.Title>
          <span className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-border" />
          <SourceContent {...props} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
