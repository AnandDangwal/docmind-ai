import {
  ChevronDown,
  KeyRound,
  LogOut,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react"
import { AlertDialog, Dialog, DropdownMenu } from "radix-ui"
import {
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
} from "react"
import { useNavigate } from "react-router-dom"

import { useAuth } from "@/auth/auth-store"
import { Brand } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { groupThreads } from "@/lib/date"
import type { ThreadSummary } from "@/lib/types"
import { summarizeUser } from "@/lib/user"

type ConversationSidebarProps = {
  threads: ThreadSummary[]
  activeThreadId?: string
  loading: boolean
  error?: string
  mobileOpen: boolean
  onMobileOpenChange: (open: boolean) => void
  collapsed: boolean
  onCollapsedChange: (collapsed: boolean) => void
  width: number
  minWidth: number
  maxWidth: number
  onWidthChange: (width: number) => void
  onNewResearch: () => void
  onPrefetch: (threadId: string) => void
  onRename: (threadId: string, title: string) => Promise<void>
  onDelete: (threadId: string) => Promise<void>
}

function SidebarFrame({
  children,
  mobile,
  onClose,
  collapsed = false,
  onCollapsedChange,
  width = 268,
  minWidth = 220,
  maxWidth = 480,
  onWidthChange,
}: {
  children: ReactNode
  mobile?: boolean
  onClose?: () => void
  collapsed?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  width?: number
  minWidth?: number
  maxWidth?: number
  onWidthChange?: (width: number) => void
}) {
  const drag = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null)
  const [resizing, setResizing] = useState(false)

  function resize(nextWidth: number) {
    onWidthChange?.(Math.min(Math.max(nextWidth, minWidth), maxWidth))
  }

  function handlePointerDown(event: PointerEvent<HTMLDivElement>) {
    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
    }
    setResizing(true)
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: PointerEvent<HTMLDivElement>) {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return
    resize(drag.current.startWidth + event.clientX - drag.current.startX)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next =
      event.key === "ArrowLeft"
        ? width - 24
        : event.key === "ArrowRight"
          ? width + 24
          : event.key === "Home"
            ? minWidth
            : event.key === "End"
              ? maxWidth
              : null
    if (next === null) return
    event.preventDefault()
    resize(next)
  }

  const toggleCollapsed = onCollapsedChange
  ? () => onCollapsedChange(!collapsed)
  : undefined
  
  return (
    <aside
      className={`relative flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar pt-4 pb-3 ${
        resizing ? "" : "transition-[width,padding] duration-200"
      } ${
        collapsed ? "px-2" : "px-3"
      }`}
      style={{ width: collapsed ? 68 : width }}
    >
      <div className={`flex items-center px-2 ${collapsed ? "flex-col gap-2" : "h-9 justify-between"}`}>
        <Brand
          compact={collapsed}
          onIconClick={mobile ? undefined : toggleCollapsed}
          iconLabel={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        />
        {mobile && (
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close navigation">
            <X />
          </Button>
        )}
      </div>
      {children}
      {!mobile && !collapsed && onWidthChange && (
        <div
          className="group absolute inset-y-0 -right-1 z-20 w-2 cursor-col-resize touch-none outline-none"
          role="separator"
          aria-label="Resize conversation sidebar"
          aria-orientation="vertical"
          aria-valuemin={Math.round(minWidth)}
          aria-valuemax={Math.round(maxWidth)}
          aria-valuenow={Math.round(width)}
          tabIndex={0}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={(event) => {
            if (drag.current?.pointerId !== event.pointerId) return
            drag.current = null
            setResizing(false)
          }}
          onPointerCancel={() => {
            drag.current = null
            setResizing(false)
          }}
          onKeyDown={handleKeyDown}
        >
          <span className="absolute inset-y-0 left-1/2 w-px bg-transparent transition-colors group-hover:bg-foreground/30 group-focus-visible:bg-foreground/50 group-active:bg-foreground/50" />
        </div>
      )}
    </aside>
  )
}

function EditThreadDialog({
  thread,
  onOpenChange,
  onRename,
}: {
  thread: ThreadSummary | null
  onOpenChange: (open: boolean) => void
  onRename: (threadId: string, title: string) => Promise<void>
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!thread) return
    const title = String(new FormData(event.currentTarget).get("title")).trim()
    if (!title) return
    setPending(true)
    setError("")
    try {
      await onRename(thread.id, title)
      onOpenChange(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to rename this conversation.")
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog.Root open={Boolean(thread)} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35 data-[state=closed]:opacity-0" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-5 shadow-xl">
          <Dialog.Title className="text-base font-semibold">Rename conversation</Dialog.Title>
          <Dialog.Description className="mt-1 text-xs leading-5 text-muted-foreground">Choose a short title that will be easy to find later.</Dialog.Description>
          <form className="mt-5 grid gap-4" onSubmit={submit}>
            <input
              className="h-10 rounded-lg border border-input bg-background px-3 text-sm outline-none focus:border-foreground/50 focus:ring-3 focus:ring-ring/20"
              name="title"
              defaultValue={thread?.title}
              maxLength={100}
              autoFocus
              required
            />
            {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild><Button variant="outline">Cancel</Button></Dialog.Close>
              <Button type="submit" disabled={pending}>{pending ? "Saving…" : "Save"}</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function PasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { updatePassword } = useAuth()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const currentPassword = String(form.get("currentPassword"))
    const password = String(form.get("password"))
    const confirmation = String(form.get("confirmation"))
    if (password !== confirmation) {
      setError("The new passwords do not match.")
      return
    }
    setPending(true)
    setError("")
    try {
      await updatePassword(password, currentPassword)
      onOpenChange(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update your password.")
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35 data-[state=closed]:opacity-0" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-5 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-base font-semibold">Change password</Dialog.Title>
              <Dialog.Description className="mt-1 text-xs leading-5 text-muted-foreground">Use at least eight characters.</Dialog.Description>
            </div>
            <Dialog.Close asChild><Button variant="ghost" size="icon-sm" aria-label="Close"><X /></Button></Dialog.Close>
          </div>
          <form className="mt-5 grid gap-4" onSubmit={submit}>
            {[
              ["currentPassword", "Current password"],
              ["password", "New password"],
              ["confirmation", "Confirm new password"],
            ].map(([name, label]) => (
              <label className="grid gap-2 text-xs font-medium" key={name}>
                {label}
                <input className="h-10 rounded-lg border border-input bg-background px-3 text-sm font-normal outline-none focus:border-foreground/50 focus:ring-3 focus:ring-ring/20" name={name} type="password" minLength={8} autoComplete={name === "currentPassword" ? "current-password" : "new-password"} required />
              </label>
            ))}
            {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
            <Button type="submit" className="justify-self-end" disabled={pending}>{pending ? "Updating…" : "Update password"}</Button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function SidebarContent(
  props: ConversationSidebarProps & { compact?: boolean },
) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [editing, setEditing] = useState<ThreadSummary | null>(null)
  const [deleting, setDeleting] = useState<ThreadSummary | null>(null)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [deletePending, setDeletePending] = useState(false)
  const [deleteError, setDeleteError] = useState("")
  const summary = user ? summarizeUser(user) : null
  const compact = props.compact ?? false
  const filtered = useMemo(
    () => props.threads.filter((thread) => thread.title.toLowerCase().includes(query.trim().toLowerCase())),
    [props.threads, query],
  )

  function go(path: string) {
    props.onMobileOpenChange(false)
    navigate(path)
  }

  async function confirmDelete() {
    if (!deleting) return
    setDeletePending(true)
    setDeleteError("")
    try {
      await props.onDelete(deleting.id)
      setDeleting(null)
    } catch (caught) {
      setDeleteError(
        caught instanceof Error
          ? caught.message
          : "Unable to delete this conversation.",
      )
    } finally {
      setDeletePending(false)
    }
  }

  return (
    <>
      <Button
        variant="outline"
        className={`mt-4 h-10 bg-background ${compact ? "w-full px-0" : "w-full justify-start px-3"}`}
        onClick={() => {
          props.onMobileOpenChange(false)
          props.onNewResearch()
        }}
        aria-label="New research"
        title={compact ? "New research" : undefined}
      >
        <Plus />
        {!compact && (
          <>
            New research
            <kbd className="ml-auto text-[10px] font-normal text-muted-foreground">⌘ K</kbd>
          </>
        )}
      </Button>
      {!compact && (
        <label className="mt-2 flex h-9 items-center gap-2 rounded-lg px-2 text-muted-foreground focus-within:bg-muted">
          <Search className="size-4" />
          <input id="conversation-search" name="conversation-search" className="min-w-0 flex-1 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" />
        </label>
      )}

      <div className={`min-h-0 flex-1 overflow-y-auto pb-4 ${compact ? "mt-4" : "mt-2"}`}>
        {!compact && props.error && props.threads.length > 0 && (
          <p className="mx-2 mb-2 rounded-md bg-destructive/5 px-2 py-2 text-[10px] leading-4 text-destructive" role="status">Unable to refresh conversations.</p>
        )}
        {compact ? null : props.loading ? (
          <div className="grid gap-2 px-2 py-3" aria-label="Loading conversations">
            <span className="h-3 animate-pulse rounded bg-muted" />
            <span className="h-3 w-4/5 animate-pulse rounded bg-muted" />
            <span className="h-3 w-11/12 animate-pulse rounded bg-muted" />
          </div>
        ) : props.error && props.threads.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-5 text-destructive" role="status">{props.error}</p>
        ) : props.threads.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-5 text-muted-foreground">Your conversations will appear here.</p>
        ) : filtered.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-5 text-muted-foreground">No conversations match “{query}”.</p>
        ) : (
          groupThreads(filtered).map((group) => (
            <section className="mb-5" key={group.label}>
              <h2 className="mb-1 px-2 text-[10px] font-semibold tracking-wide text-muted-foreground">{group.label}</h2>
              {group.threads.map((thread) => (
                <div className={`group relative flex h-9 items-center rounded-lg ${thread.id === props.activeThreadId ? "bg-sidebar-accent" : "hover:bg-sidebar-accent/70"}`} key={thread.id}>
                  <button
                    className="min-w-0 flex-1 truncate px-2 pr-9 text-left text-xs"
                    onClick={() => go(`/chat/${thread.id}`)}
                    onPointerEnter={() => props.onPrefetch(thread.id)}
                    onFocus={() => props.onPrefetch(thread.id)}
                  >
                    {thread.title}
                  </button>
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger asChild>
                      <Button variant="ghost" size="icon-xs" className="absolute right-1 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100" aria-label={`Actions for ${thread.title}`}><MoreHorizontal /></Button>
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Portal>
                        <DropdownMenu.Content sideOffset={4} align="end" className="z-40 w-40 rounded-lg border border-border bg-popover p-1 text-xs shadow-lg">
                          <DropdownMenu.Item className="flex cursor-default items-center gap-2 rounded-md px-2 py-2 outline-none data-[highlighted]:bg-muted" onClick={() => setEditing(thread)}><Pencil className="size-3.5" /> Rename</DropdownMenu.Item>
                          <DropdownMenu.Item className="flex cursor-default items-center gap-2 rounded-md px-2 py-2 text-destructive outline-none data-[highlighted]:bg-destructive/10" onClick={() => { setDeleteError(""); setDeleting(thread) }}><Trash2 className="size-3.5" /> Delete</DropdownMenu.Item>
                        </DropdownMenu.Content>
                    </DropdownMenu.Portal>
                  </DropdownMenu.Root>
                </div>
              ))}
            </section>
          ))
        )}
      </div>

      {summary && (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              className={`flex w-full items-center rounded-lg border-t border-sidebar-border pt-3 text-left hover:bg-sidebar-accent ${compact ? "justify-center" : "gap-2 px-2"}`}
              aria-label="Open account menu"
              title={compact ? summary.displayName : undefined}
            >
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-foreground text-[10px] font-semibold text-background">{summary.initials}</span>
            {!compact && (
              <>
                <span className="min-w-0 flex-1">
                  <strong className="block truncate text-xs font-medium">{summary.displayName}</strong>
                  <small className="block truncate text-[10px] text-muted-foreground">{summary.email}</small>
                </span>
                <ChevronDown className="size-4 text-muted-foreground" />
              </>
            )}
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
              <DropdownMenu.Content side={compact ? "right" : "top"} sideOffset={6} align="start" className="z-40 w-56 rounded-lg border border-border bg-popover p-1 text-xs shadow-lg">
                <DropdownMenu.Item className="flex cursor-default items-center gap-2 rounded-md px-2 py-2 outline-none data-[highlighted]:bg-muted" onClick={() => setPasswordOpen(true)}><KeyRound className="size-3.5" /> Change password</DropdownMenu.Item>
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
                <DropdownMenu.Item className="flex cursor-default items-center gap-2 rounded-md px-2 py-2 text-destructive outline-none data-[highlighted]:bg-destructive/10" onClick={() => void signOut()}><LogOut className="size-3.5" /> Sign out</DropdownMenu.Item>
              </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      )}

      <EditThreadDialog thread={editing} onOpenChange={(open) => { if (!open) setEditing(null) }} onRename={props.onRename} />
      <PasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
      <AlertDialog.Root open={Boolean(deleting)} onOpenChange={(open) => { if (!open && !deletePending) { setDeleting(null); setDeleteError("") } }}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/35" />
          <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-5 shadow-xl">
            <span className="mb-4 grid size-9 place-items-center rounded-lg bg-destructive/10 text-destructive"><Trash2 className="size-4" /></span>
            <AlertDialog.Title className="text-base font-semibold">Delete this conversation?</AlertDialog.Title>
            <AlertDialog.Description className="mt-2 text-xs leading-5 text-muted-foreground">“{deleting?.title}” and its messages will be permanently removed.</AlertDialog.Description>
            {deleteError && <p className="mt-3 text-xs leading-5 text-destructive" role="alert">{deleteError}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <AlertDialog.Cancel asChild><Button variant="outline" disabled={deletePending}>Cancel</Button></AlertDialog.Cancel>
              <Button variant="destructive" disabled={deletePending} onClick={() => void confirmDelete()}>{deletePending ? "Deleting…" : "Delete"}</Button>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </>
  )
}

export function ConversationSidebar(props: ConversationSidebarProps) {
  return (
    <>
      <div className="hidden h-full md:block">
        <SidebarFrame
          collapsed={props.collapsed}
          onCollapsedChange={props.onCollapsedChange}
          width={props.width}
          minWidth={props.minWidth}
          maxWidth={props.maxWidth}
          onWidthChange={props.onWidthChange}
        >
          <SidebarContent {...props} compact={props.collapsed} />
        </SidebarFrame>
      </div>
      <Dialog.Root open={props.mobileOpen} onOpenChange={props.onMobileOpenChange}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/35 md:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 outline-none md:hidden">
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <SidebarFrame mobile onClose={() => props.onMobileOpenChange(false)}>
              <SidebarContent {...props} compact={false} />
            </SidebarFrame>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  )
}
