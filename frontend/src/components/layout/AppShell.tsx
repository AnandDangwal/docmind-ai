import { useCallback, useEffect, useState } from "react"
import { Outlet, useNavigate, useParams } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { useAuth } from "@/lib/auth"
import { createThread, isApiError, listThreads, type Thread } from "@/lib/api"
import { Button } from "@/components/ui/button"

export function AppShell() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const { id: activeThreadId } = useParams<{ id: string }>()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const refreshThreads = useCallback(() => {
    listThreads()
      .then(setThreads)
      .catch((err) => setError(isApiError(err) ? err.message : "Request failed"))
  }, [])

  useEffect(() => {
    refreshThreads()
  }, [refreshThreads])

  async function handleNewChat() {
    setCreating(true)
    setError(null)
    try {
      const thread = await createThread()
      setThreads((prev) => (prev ? [thread, ...prev] : [thread]))
      navigate(`/threads/${thread.id}`)
    } catch (err) {
      setError(isApiError(err) ? err.message : "Request failed")
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex h-svh">
      <aside className="flex w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="px-4 pt-5 pb-3">
          <h1 className="text-sm font-semibold text-sidebar-foreground">Document Copilot</h1>
          <p className="text-xs text-muted-foreground">SEC filing assistant</p>
        </div>

        <div className="px-4 pb-3">
          <Button size="sm" className="w-full" onClick={handleNewChat} disabled={creating}>
            New chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-4">
          <p className="pb-2 text-xs font-medium text-muted-foreground">Conversations</p>

          {error && <p className="text-xs text-destructive">{error}</p>}
          {!threads && !error && <p className="text-xs text-muted-foreground">Loading…</p>}
          {threads && threads.length === 0 && (
            <p className="text-xs text-muted-foreground">No conversations yet.</p>
          )}

          {threads && threads.length > 0 && (
            <ul className="flex flex-col gap-1">
              {threads.map((thread) => (
                <li key={thread.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/threads/${thread.id}`)}
                    className={`w-full truncate rounded-md px-2 py-1.5 text-left text-sm hover:bg-sidebar-accent ${
                      thread.id === activeThreadId
                        ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                        : "text-muted-foreground"
                    }`}
                  >
                    {thread.title ?? "Untitled chat"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex items-center justify-between gap-2 border-t border-sidebar-border px-4 py-3">
          <span className="truncate text-xs text-muted-foreground">{session?.user.email}</span>
          <Button variant="outline" size="sm" onClick={() => supabase.auth.signOut()}>
            Sign out
          </Button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
