import { Check, FileSearch, MessageSquareText, Scale } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { useLocation, useNavigate, useParams } from "react-router-dom"

import { MessageInput } from "@/components/chat/MessageInput"
import { SourceInspector } from "@/components/chat/SourceInspector"
import { ThreadChat } from "@/components/chat/ThreadChat"
import { AppIcon } from "@/components/brand"
import { ConversationSidebar } from "@/components/layout/ConversationSidebar"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import type { ChatUIMessage, CitationData } from "@/lib/chatTypes"
import { cachedThreadMessages, loadThreadMessages } from "@/lib/threadMessages"
import type { ThreadSummary } from "@/lib/types"

const SIDEBAR_COLLAPSED_KEY = "document-copilot:sidebar-collapsed"
const SIDEBAR_WIDTH_KEY = "document-copilot:sidebar-width"
const PENDING_PROMPT_PREFIX = "document-copilot:pending-prompt:"
const DEFAULT_SIDEBAR_WIDTH = 268
const MIN_SIDEBAR_WIDTH = 220
const MAX_SIDEBAR_WIDTH = 480
const MIN_MAIN_WIDTH = 420
const COLLAPSED_SIDEBAR_WIDTH = 68

const suggestions = [
  {
    icon: FileSearch,
    label: "Summarize a filing",
    prompt: "Summarize the most important disclosures in the latest filing, with citations.",
  },
  {
    icon: Scale,
    label: "Compare two periods",
    prompt: "Compare the latest reporting period with the prior period and cite the key changes.",
  },
  {
    icon: MessageSquareText,
    label: "Find risk factors",
    prompt: "What are the most material risk factors discussed in the filings? Cite each finding.",
  },
] as const

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

function initialSidebarCollapsed(): boolean {
  return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true"
}

function maximumSidebarWidth(): number {
  return Math.max(
    MIN_SIDEBAR_WIDTH,
    Math.min(MAX_SIDEBAR_WIDTH, window.innerWidth - MIN_MAIN_WIDTH),
  )
}

function clampSidebarWidth(width: number): number {
  return Math.min(Math.max(width, MIN_SIDEBAR_WIDTH), maximumSidebarWidth())
}

function initialSidebarWidth(): number {
  const stored = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY))
  return clampSidebarWidth(Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_SIDEBAR_WIDTH)
}

function pendingPromptKey(threadId: string): string {
  return `${PENDING_PROMPT_PREFIX}${threadId}`
}

function EmptyResearch({ onSubmit, pending }: { onSubmit: (text: string) => void; pending: boolean }) {
  const [draft, setDraft] = useState("")

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="m-auto w-[calc(100%-2rem)] max-w-2xl py-8 text-center">
        <AppIcon className="mx-auto mb-5 size-12 rounded-xl" />
        <h1 className="text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">What would you like to understand?</h1>
        <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-muted-foreground">Ask a question across your document library. Every answer links back to its evidence.</p>
        <div className="mx-auto mt-8 grid max-w-xl gap-2 sm:grid-cols-3">
          {suggestions.map(({ icon: Icon, label, prompt }) => (
            <button
              className="flex min-h-16 items-center gap-3 rounded-xl border border-border bg-background p-3 text-left text-xs font-medium transition hover:-translate-y-0.5 hover:bg-muted/50 sm:flex-col sm:items-start sm:justify-between"
              key={label}
              onClick={() => onSubmit(prompt)}
              disabled={pending}
            >
              <Icon className="size-4 text-muted-foreground" /> {label}
            </button>
          ))}
        </div>
      </div>
      <MessageInput disabled={pending} value={draft} onValueChange={setDraft} onSend={onSubmit} autoFocus />
    </div>
  )
}

function ConversationLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="grid min-h-0 flex-1 place-content-center px-6 text-center">
      <div className="max-w-sm rounded-xl border border-border bg-muted/20 p-5">
        <p className="text-sm font-medium">This conversation could not be opened</p>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">{message}</p>
        <Button className="mt-4" variant="outline" onClick={onRetry}>Try again</Button>
      </div>
    </div>
  )
}

function ConversationSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-8" aria-label="Opening conversation">
      <span className="ml-auto h-12 w-1/2 animate-pulse rounded-xl bg-muted" />
      <div className="grid max-w-2xl gap-3">
        <span className="h-3 w-full animate-pulse rounded bg-muted" />
        <span className="h-3 w-11/12 animate-pulse rounded bg-muted" />
        <span className="h-3 w-4/5 animate-pulse rounded bg-muted" />
      </div>
    </div>
  )
}

export function ResearchPage() {
  const { threadId } = useParams<{ threadId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [messages, setMessages] = useState<ChatUIMessage[] | null>(null)
  const [threadsLoading, setThreadsLoading] = useState(true)
  const [threadLoading, setThreadLoading] = useState(false)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [creating, setCreating] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(initialSidebarCollapsed)
  const [sidebarWidth, setSidebarWidth] = useState(initialSidebarWidth)
  const [source, setSource] = useState<CitationData | null>(null)
  const [sources, setSources] = useState<CitationData[]>([])
  const [threadListError, setThreadListError] = useState("")
  const [threadError, setThreadError] = useState("")
  const [createError, setCreateError] = useState("")
  const [deleteNotice, setDeleteNotice] = useState(0)

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await api.listThreads())
      setThreadListError("")
    } catch (caught) {
      setThreadListError(errorMessage(caught, "Unable to load conversations."))
    } finally {
      setThreadsLoading(false)
    }
  }, [])

  useEffect(() => {
    void Promise.resolve().then(refreshThreads)
  }, [refreshThreads])

  const openThread = useCallback(async (id: string, signal: AbortSignal) => {
    const cached = cachedThreadMessages(id)
    setMessages(cached ?? null)
    setThreadLoading(!cached)
    setThreadError("")
    setSource(null)
    setSources([])

    try {
      const loaded = await loadThreadMessages(id, { force: Boolean(cached), signal })
      if (!signal.aborted) setMessages(loaded)
    } catch (caught) {
      if (!signal.aborted) {
        setThreadError(errorMessage(caught, "Unable to open this conversation."))
      }
    } finally {
      if (!signal.aborted) setThreadLoading(false)
    }
  }, [])

  const openNewResearch = useCallback(() => {
    setMessages(null)
    setThreadLoading(false)
    setThreadError("")
    setSource(null)
    setSources([])
    setMobileOpen(false)
    navigate("/chat/new", { flushSync: true })
  }, [navigate])

  useEffect(() => {
    const controller = new AbortController()
    if (threadId) {
      void Promise.resolve().then(() => {
        if (!controller.signal.aborted) void openThread(threadId, controller.signal)
      })
    } else {
      void Promise.resolve().then(() => {
        if (controller.signal.aborted) return
        setMessages(null)
        setThreadLoading(false)
        setThreadError("")
        setSource(null)
        setSources([])
      })
    }
    return () => controller.abort()
  }, [loadAttempt, openThread, threadId])

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        openNewResearch()
      }
    }
    window.addEventListener("keydown", handleShortcut)
    return () => window.removeEventListener("keydown", handleShortcut)
  }, [openNewResearch])

  useEffect(() => {
    function fitSidebarToViewport() {
      setSidebarWidth((current) => clampSidebarWidth(current))
    }
    window.addEventListener("resize", fitSidebarToViewport)
    return () => window.removeEventListener("resize", fitSidebarToViewport)
  }, [])

  useEffect(() => {
    if (deleteNotice === 0) return
    const timeout = window.setTimeout(() => setDeleteNotice(0), 4_000)
    return () => window.clearTimeout(timeout)
  }, [deleteNotice])

  async function beginResearch(prompt: string) {
    setCreating(true)
    setCreateError("")
    try {
      const created = await api.createThread(prompt)
      setThreads((current) => [created, ...current])
      sessionStorage.setItem(pendingPromptKey(created.id), prompt)
      navigate(`/chat/${created.id}`)
    } catch (caught) {
      setCreateError(errorMessage(caught, "Unable to start a conversation."))
    } finally {
      setCreating(false)
    }
  }

  async function renameThread(id: string, title: string) {
    const updated = await api.renameThread(id, title)
    setThreads((current) => current.map((item) => item.id === id ? updated : item))
  }

  async function deleteThread(id: string) {
    await api.deleteThread(id)
    setThreads((current) => current.filter((item) => item.id !== id))
    if (id === threadId) navigate("/chat/new", { replace: true })
    setDeleteNotice((current) => current + 1)
  }

  function changeSidebarCollapsed(collapsed: boolean) {
    setSidebarCollapsed(collapsed)
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed))
  }

  function changeSidebarWidth(width: number) {
    const nextWidth = clampSidebarWidth(width)
    setSidebarWidth(nextWidth)
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(nextWidth))
  }

  function prefetchThread(id: string) {
    void loadThreadMessages(id).catch(() => undefined)
  }

  function conversationChanged(id: string) {
    void refreshThreads()
    void loadThreadMessages(id, { force: true }).catch(() => undefined)
  }

  function retryThread() {
    if (!threadId) return
    setLoadAttempt((current) => current + 1)
  }

  const routePrompt = (location.state as { pendingPrompt?: string } | null)?.pendingPrompt
  const pendingPrompt = threadId
    ? sessionStorage.getItem(pendingPromptKey(threadId)) ?? routePrompt
    : undefined

  return (
    <main className="flex h-svh min-w-0 overflow-hidden bg-background text-foreground">
      {deleteNotice > 0 && (
        <div
          className="fixed top-4 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-2 rounded-lg border border-emerald-600/20 bg-emerald-50 px-4 py-2.5 text-xs font-medium text-emerald-900 shadow-lg"
          role="status"
          aria-live="polite"
        >
          <span className="grid size-5 place-items-center rounded-full bg-emerald-600 text-white">
            <Check className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
          </span>
          Conversation deleted
        </div>
      )}
      <ConversationSidebar
        threads={threads}
        activeThreadId={threadId}
        loading={threadsLoading}
        error={threadListError}
        mobileOpen={mobileOpen}
        onMobileOpenChange={setMobileOpen}
        collapsed={sidebarCollapsed}
        onCollapsedChange={changeSidebarCollapsed}
        width={sidebarWidth}
        minWidth={MIN_SIDEBAR_WIDTH}
        maxWidth={maximumSidebarWidth()}
        onWidthChange={changeSidebarWidth}
        onNewResearch={openNewResearch}
        onPrefetch={prefetchThread}
        onRename={renameThread}
        onDelete={deleteThread}
      />
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {createError && !threadId && (
          <div className="mx-3 mt-3 flex min-h-10 items-center justify-between gap-3 rounded-lg border border-destructive/25 bg-destructive/5 px-3 text-xs text-destructive sm:mx-5" role="alert">
            <span>{createError}</span>
            <button className="shrink-0 font-semibold hover:underline" onClick={() => setCreateError("")}>Dismiss</button>
          </div>
        )}
        {threadError && messages && (
          <div className="mx-3 mt-3 flex min-h-10 items-center justify-between gap-3 rounded-lg border border-destructive/25 bg-destructive/5 px-3 text-xs text-destructive sm:mx-5" role="alert">
            <span>{threadError} Showing the last loaded messages.</span>
            <button className="shrink-0 font-semibold hover:underline" onClick={retryThread}>Try again</button>
          </div>
        )}
        {!threadId ? (
          <EmptyResearch onSubmit={(prompt) => void beginResearch(prompt)} pending={creating} />
        ) : messages ? (
          <ThreadChat
            key={threadId}
            threadId={threadId}
            initialMessages={messages}
            pendingPrompt={pendingPrompt}
            onPromptConsumed={() => {
              sessionStorage.removeItem(pendingPromptKey(threadId))
              if (routePrompt) navigate(location.pathname, { replace: true, state: null })
            }}
            onCitationSelect={(selected, all) => { setSource(selected); setSources(all) }}
            onConversationChanged={conversationChanged}
          />
        ) : threadLoading ? (
          <ConversationSkeleton />
        ) : threadError ? (
          <ConversationLoadError message={threadError} onRetry={retryThread} />
        ) : (
          <div className="grid min-h-0 flex-1 place-content-center text-sm text-muted-foreground">Conversation not found.</div>
        )}
      </section>
      <SourceInspector
        source={source}
        sources={sources}
        leftSidebarWidth={sidebarCollapsed ? COLLAPSED_SIDEBAR_WIDTH : sidebarWidth}
        onSelect={setSource}
        onClose={() => setSource(null)}
      />
    </main>
  )
}
