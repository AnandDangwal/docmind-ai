import { Navigate, Route, Routes } from "react-router-dom"
import { lazy, Suspense } from "react"

import { ProtectedRoute } from "@/auth/protected-route"
import { AuthLayout } from "@/pages/auth-layout"

const ForgotPasswordPage = lazy(() => import("@/pages/forgot-password-page").then((module) => ({ default: module.ForgotPasswordPage })))
const LoginPage = lazy(() => import("@/pages/login-page").then((module) => ({ default: module.LoginPage })))
const ResetPasswordPage = lazy(() => import("@/pages/reset-password-page").then((module) => ({ default: module.ResetPasswordPage })))
const ResearchPage = lazy(() => import("@/pages/research-page").then((module) => ({ default: module.ResearchPage })))

export default function App() {
  return (
    <Suspense fallback={<main className="grid min-h-svh place-items-center text-xs text-muted-foreground">Loading Document Copilot…</main>}>
      <Routes>
        <Route element={<AuthLayout />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route path="/chat/new" element={<ResearchPage />} />
          <Route path="/chat/:threadId" element={<ResearchPage />} />
        </Route>

        <Route path="/" element={<Navigate to="/chat/new" replace />} />
        <Route path="*" element={<Navigate to="/chat/new" replace />} />
      </Routes>
    </Suspense>
  )
}
