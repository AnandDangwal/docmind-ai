import type { Session } from "@supabase/supabase-js"
import { useEffect, useMemo, useState } from "react"

import { AuthContext, type AuthContextValue } from "@/auth/auth-store"
import { supabase } from "@/lib/supabase"

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true

    void supabase.auth.getSession().then(({ data, error }) => {
      if (!active) return
      if (error) console.error("Unable to restore Supabase session", error)
      setSession(data.session)
      setLoading(false)
    })

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })

    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      async signIn(email, password) {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      },
      async sendResetEmail(email) {
        const redirectTo = new URL("/reset-password", window.location.origin).toString()
        const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo })
        if (error) throw error
      },
      async updatePassword(password, currentPassword) {
        const { error } = await supabase.auth.updateUser({
          password,
          ...(currentPassword ? { current_password: currentPassword } : {}),
        })
        if (error) throw error
      },
      async signOut() {
        const { error } = await supabase.auth.signOut()
        if (error) throw error
      },
    }),
    [loading, session],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
