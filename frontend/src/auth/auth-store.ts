import type { Session, User } from "@supabase/supabase-js"
import { createContext, useContext } from "react"

export type AuthContextValue = {
  session: Session | null
  user: User | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  sendResetEmail: (email: string) => Promise<void>
  updatePassword: (password: string, currentPassword?: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error("useAuth must be used within AuthProvider")
  return value
}
