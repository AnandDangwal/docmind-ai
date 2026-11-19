import { Eye, EyeOff } from "lucide-react"
import { useState } from "react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/auth/auth-store"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export function LoginPage() {
  const { session, signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  if (session) return <Navigate to="/chat/new" replace />

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPending(true)
    setError("")
    const form = new FormData(event.currentTarget)

    try {
      await signIn(String(form.get("email")), String(form.get("password")))
      const destination = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/chat/new"
      navigate(destination, { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign in. Check your details and try again.")
    } finally {
      setPending(false)
    }
  }

  return (
    <section aria-labelledby="login-title">
      <div>
        <p className="mb-2 text-[11px] font-semibold tracking-[0.1em] text-muted-foreground uppercase">Welcome back</p>
        <h1 id="login-title" className="text-2xl font-semibold tracking-[-0.035em] text-foreground">Sign in to Document Copilot</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">Use your Driftwood Capital email to continue.</p>
      </div>

      <form className="mt-7 grid gap-4" onSubmit={handleSubmit}>
        <div className="grid gap-2">
          <label className="text-xs font-medium" htmlFor="email">Work email</label>
          <input className="h-10 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm outline-none transition focus:border-foreground/50 focus:ring-3 focus:ring-ring/20" id="email" name="email" type="email" autoComplete="email" placeholder="you@driftwoodcapital.com" required autoFocus />
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium" htmlFor="password">Password</label>
            <button className="text-xs font-medium text-muted-foreground hover:text-foreground hover:underline" type="button" onClick={() => navigate("/forgot-password")}>Forgot password?</button>
          </div>
          <div className="relative">
            <input
              className="h-10 w-full rounded-lg border border-input bg-background px-3 pr-10 text-sm outline-none transition focus:border-foreground/50 focus:ring-3 focus:ring-ring/20"
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="Enter your password"
              required
            />
            <button
              type="button"
              className="absolute top-1 right-1 grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((value) => !value)}
            >
              {showPassword ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
            </button>
          </div>
        </div>

        {error && <p className="text-xs leading-5 text-destructive" role="alert">{error}</p>}

        <Button type="submit" size="lg" className="w-full" disabled={pending}>
          {pending && <Spinner label="Signing in" />}
          Sign in
        </Button>
      </form>

      <p className="mt-6 text-center text-[11px] text-muted-foreground">Access is limited to authorized Driftwood Capital users.</p>
    </section>
  )
}
