import { Navigate, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/auth/auth-store"
import { Brand } from "@/components/brand"
import { Spinner } from "@/components/ui/spinner"

export function ProtectedRoute() {
  const { loading, session } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <main className="grid min-h-svh place-content-center justify-items-center gap-4 bg-background">
        <Brand />
        <Spinner label="Restoring your session" />
      </main>
    )
  }

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}
