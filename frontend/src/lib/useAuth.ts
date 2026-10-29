import { useContext } from "react"
import { AuthContext, type AuthState } from "@/lib/auth-context"

export function useAuth(): AuthState {
  const state = useContext(AuthContext)
  if (!state) throw new Error("useAuth must be used within an AuthProvider")
  return state
}
