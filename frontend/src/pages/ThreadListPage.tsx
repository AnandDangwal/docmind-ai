import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { supabase } from "@/lib/supabase"
import { useAuth } from "@/lib/auth"
import { createThread, isApiError, listThreads, type Thread } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export default function ThreadListPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [threads, setThreads] = useState<Thread[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    listThreads()
      .then((result) => {
        if (!cancelled) setThreads(result)
      })
      .catch((err) => {
        if (!cancelled) setError(isApiError(err) ? err.message : "Request failed")
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleNewChat() {
    setCreating(true)
    setError(null)
    try {
      const thread = await createThread()
      navigate(`/threads/${thread.id}`)
    } catch (err) {
      setError(isApiError(err) ? err.message : "Request failed")
      setCreating(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Document Copilot</h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{session?.user.email}</span>
          <Button variant="outline" size="sm" onClick={() => supabase.auth.signOut()}>
            Sign out
          </Button>
        </div>
      </header>
      <main className="flex flex-1 flex-col items-center px-6 pt-12 pb-24">
        <div className="flex w-full max-w-xl flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-2xl font-semibold text-foreground">Your chats</h2>
            <Button onClick={handleNewChat} disabled={creating}>
              New chat
            </Button>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          {!threads && !error && <p className="text-sm text-muted-foreground">Loading…</p>}

          {threads && threads.length === 0 && (
            <Card className="gap-3 py-5">
              <CardHeader className="gap-1">
                <CardTitle className="text-center">No chats yet</CardTitle>
              </CardHeader>
              <CardContent className="text-center text-sm text-muted-foreground">
                Start a new chat to ask a question about the filings corpus.
              </CardContent>
            </Card>
          )}

          {threads && threads.length > 0 && (
            <ul className="flex flex-col gap-2">
              {threads.map((thread) => (
                <li key={thread.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/threads/${thread.id}`)}
                    className="w-full rounded-lg border border-border bg-card px-4 py-3 text-left text-sm hover:bg-muted"
                  >
                    {thread.title ?? "Untitled chat"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </main>
    </div>
  )
}
