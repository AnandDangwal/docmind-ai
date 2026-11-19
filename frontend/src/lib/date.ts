import type { ThreadSummary } from "@/lib/types"

export type ThreadGroup = {
  label: string
  threads: ThreadSummary[]
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

export function groupThreads(threads: ThreadSummary[], now = new Date()): ThreadGroup[] {
  const today = startOfDay(now)
  const day = 86_400_000
  const buckets: Record<string, ThreadSummary[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    Older: [],
  }

  const sortedThreads = [...threads].sort(
    (a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt),
  )

  sortedThreads.forEach((thread) => {
      const age = Math.floor((today - startOfDay(new Date(thread.updatedAt))) / day)
      const label = age <= 0 ? "Today" : age === 1 ? "Yesterday" : age <= 7 ? "Previous 7 days" : "Older"
      buckets[label]?.push(thread)
  })

  return Object.entries(buckets)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, threads: items }))
}
