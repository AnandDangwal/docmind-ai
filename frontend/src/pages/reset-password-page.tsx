import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { useAuth } from "@/auth/auth-store"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export function ResetPasswordPage() {
  const { updatePassword } = useAuth()
  const navigate = useNavigate()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const password = String(form.get("password"))
    const confirmation = String(form.get("confirmation"))

    if (password.length < 8) {
      setError("Use at least 8 characters.")
      return
    }

    if (password !== confirmation) {
      setError("The passwords do not match.")
      return
    }

    setPending(true)
    setError("")
    try {
      await updatePassword(password)
      navigate("/chat/new", { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update your password.")
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="reset-title">
      <div>
        <p className="mb-2 text-[11px] font-semibold tracking-[0.1em] text-muted-foreground uppercase">Almost there</p>
        <h1 id="reset-title" className="text-2xl font-semibold tracking-[-0.035em]">Choose a new password</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Use at least 8 characters and keep it unique to Document Copilot.</p>
      </div>
      <form className="mt-7 grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-2">
          <label className="text-xs font-medium" htmlFor="new-password">New password</label>
          <input className="h-10 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm outline-none transition focus:border-foreground/50 focus:ring-3 focus:ring-ring/20" id="new-password" name="password" type="password" autoComplete="new-password" minLength={8} required autoFocus />
        </div>
        <div className="grid gap-2">
          <label className="text-xs font-medium" htmlFor="confirm-password">Confirm new password</label>
          <input className="h-10 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm outline-none transition focus:border-foreground/50 focus:ring-3 focus:ring-ring/20" id="confirm-password" name="confirmation" type="password" autoComplete="new-password" minLength={8} required />
        </div>
        {error && <p className="text-xs leading-5 text-destructive" role="alert">{error}</p>}
        <Button type="submit" size="lg" disabled={pending}>
          {pending && <Spinner label="Updating password" />}
          Update password
        </Button>
      </form>
    </section>
  )
}
