import { useState } from "react"
import { Link } from "react-router-dom"

import { useAuth } from "@/auth/auth-store"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export function ForgotPasswordPage() {
  const { sendResetEmail } = useAuth()
  const [pending, setPending] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState("")

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError("")
    const email = String(new FormData(event.currentTarget).get("email"))

    try {
      await sendResetEmail(email)
      setSent(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to request a reset email.")
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="forgot-title">
      <div>
        <p className="mb-2 text-[11px] font-semibold tracking-[0.1em] text-muted-foreground uppercase">Account recovery</p>
        <h1 id="forgot-title" className="text-2xl font-semibold tracking-[-0.035em]">Reset your password</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Enter your work email and we&apos;ll send password reset instructions.</p>
      </div>

      {sent ? (
        <div className="mt-7 grid gap-4" role="status">
          <h2 className="text-lg font-semibold">Check your email</h2>
          <p className="text-sm leading-6 text-muted-foreground">If an authorized account exists for that address, a reset link is on its way.</p>
          <Button asChild size="lg"><Link to="/login">Back to sign in</Link></Button>
        </div>
      ) : (
        <form className="mt-7 grid gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-2">
            <label className="text-xs font-medium" htmlFor="reset-email">Work email</label>
            <input className="h-10 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm outline-none transition focus:border-foreground/50 focus:ring-3 focus:ring-ring/20" id="reset-email" name="email" type="email" autoComplete="email" placeholder="you@driftwoodcapital.com" required autoFocus />
          </div>
          {error && <p className="text-xs leading-5 text-destructive" role="alert">{error}</p>}
          <Button type="submit" size="lg" disabled={pending}>
            {pending && <Spinner label="Sending reset email" />}
            Send reset link
          </Button>
          <Link className="text-center text-xs font-medium text-muted-foreground hover:text-foreground hover:underline" to="/login">Back to sign in</Link>
        </form>
      )}
    </section>
  )
}
